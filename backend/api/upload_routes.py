"""
Upload routes for genetic data files with optimized variant storage.
"""
import asyncio
import logging
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func, delete, update

from .auth_routes import get_current_user
from ..db.database import get_session, async_session_factory
from ..db.models import GeneticAnalysis, AnalysisVariant, DashboardCache
from ..utils.vcf_parser import VCFParser
from ..services.variant_uploader import VariantUploader
from ..services.analysis_service import ComprehensiveAnalysisService
from ..services.analysis_queue import queue_analysis
from ..core.container import ServiceManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])


async def _process_upload_background(
    analysis_id: int,
    variants_data: list,
    user_id: int,
):
    """Background task: upload variants in batches, then auto-start analysis."""
    try:
        async with async_session_factory() as session:
            uploader = VariantUploader(session)

            async def report_progress(processed: int, total: int):
                pct = min(95, int(processed / total * 100)) if total else 0
                await session.execute(
                    update(GeneticAnalysis)
                    .where(GeneticAnalysis.id == analysis_id)
                    .values(
                        progress_percentage=pct,
                        processed_variants=processed,
                    )
                )
                await session.commit()

            processed_count, new_count = await uploader.upload_variants(
                analysis_id, variants_data, on_progress=report_progress,
            )

            # Mark variant upload complete
            await session.execute(
                update(GeneticAnalysis)
                .where(GeneticAnalysis.id == analysis_id)
                .values(
                    total_variants=processed_count,
                    processed_variants=0,
                    progress_percentage=0,
                    current_step='starting_analysis',
                )
            )
            await session.commit()

        # Auto-start the comprehensive analysis
        try:
            async with ServiceManager() as service_manager:
                analysis_service = service_manager.get_analysis_service(user_id)
                await analysis_service.process_analysis(analysis_id)
        except Exception as e:
            logger.error(f"Background analysis failed for {analysis_id}: {e}")
            async with async_session_factory() as session:
                await session.execute(
                    update(GeneticAnalysis)
                    .where(GeneticAnalysis.id == analysis_id)
                    .values(
                        analysis_status='failed',
                        current_step=f'Analysis error: {str(e)[:200]}',
                    )
                )
                await session.commit()

    except Exception as e:
        logger.error(f"Background upload failed for analysis {analysis_id}: {e}")
        try:
            async with async_session_factory() as session:
                await session.execute(
                    update(GeneticAnalysis)
                    .where(GeneticAnalysis.id == analysis_id)
                    .values(
                        analysis_status='failed',
                        current_step=f'Upload error: {str(e)[:200]}',
                    )
                )
                await session.commit()
        except Exception:
            logger.exception(f"Failed to mark analysis {analysis_id} as failed")


@router.post("/vcf")
async def upload_vcf(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """Upload VCF file and process genetic variants with comprehensive analysis."""
    try:
        if not file.filename or not file.filename.endswith('.vcf'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only VCF files are supported"
            )

        # Read file content
        content = await file.read()
        
        # Create analysis record
        analysis = GeneticAnalysis(
            user_id=current_user.id,
            filename=file.filename,
            file_type='vcf',
            analysis_status='processing',
            current_step='uploading_variants',
            progress_percentage=0,
        )
        session.add(analysis)
        await session.commit()
        await session.refresh(analysis)

        # Parse VCF into memory (fast)
        parser = VCFParser()
        variants_data = await parser.parse_vcf_content(content)
        
        analysis_id = getattr(analysis, 'id')

        # Process variants + run analysis in background
        background_tasks.add_task(
            _process_upload_background,
            analysis_id=analysis_id,
            variants_data=variants_data,
            user_id=current_user.id,
        )

        # Return immediately — SSE stream will provide real-time progress
        return JSONResponse({
            "status": "uploading_variants",
            "analysis_id": analysis_id,
            "message": "VCF file parsed, processing variants...",
            "total_variants": len(variants_data),
        })

    except Exception as e:
        logger.error(f"VCF upload error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process VCF file: {str(e)}"
        )


@router.post("/csv")
async def upload_csv(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """Upload CSV file and process genetic variants with comprehensive analysis."""
    try:
        if not file.filename or not (file.filename.endswith('.csv') or file.filename.endswith('.txt')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only CSV and TXT files are supported"
            )

        # Read file content
        content = await file.read()
        
        # Create analysis record
        analysis = GeneticAnalysis(
            user_id=current_user.id,
            filename=file.filename,
            file_type='csv',
            analysis_status='processing',
            current_step='uploading_variants',
            progress_percentage=0,
        )
        session.add(analysis)
        await session.commit()
        await session.refresh(analysis)

        # Parse CSV into memory (fast)
        parser = VCFParser()
        variants_data = await parser.parse_vcf_content(content)
        
        analysis_id = getattr(analysis, 'id')

        # Process variants + run analysis in background
        background_tasks.add_task(
            _process_upload_background,
            analysis_id=analysis_id,
            variants_data=variants_data,
            user_id=current_user.id,
        )

        # Return immediately — SSE stream will provide real-time progress
        return JSONResponse({
            "status": "uploading_variants",
            "analysis_id": analysis_id,
            "message": "CSV file parsed, processing variants...",
            "total_variants": len(variants_data),
        })

    except Exception as e:
        logger.error(f"CSV upload error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process CSV file: {str(e)}"
        )


@router.delete("/data")
async def delete_all_user_data(
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Delete all genetic data for the current user.
    Instantly marks analyses as deleted (so UI updates immediately),
    then cleans up the big child tables in the background.
    Preserves shared variant annotations by design.
    """
    try:
        # Count analyses first for the response message
        # Exclude processing/pending analyses — they must finish or be cancelled first
        result = await session.execute(
            select(GeneticAnalysis.id).where(
                GeneticAnalysis.user_id == current_user.id,
                GeneticAnalysis.deleted_at.is_(None),
                GeneticAnalysis.analysis_status.notin_(['processing', 'pending']),
            )
        )
        analysis_ids = [row[0] for row in result.all()]
        
        if not analysis_ids:
            # Check if there are processing analyses that weren't deleted
            processing_result = await session.execute(
                select(func.count()).where(
                    GeneticAnalysis.user_id == current_user.id,
                    GeneticAnalysis.deleted_at.is_(None),
                    GeneticAnalysis.analysis_status.in_(['processing', 'pending']),
                )
            )
            processing_count = processing_result.scalar() or 0
            if processing_count > 0:
                return JSONResponse({
                    "status": "success",
                    "message": f"No completed data to delete. {processing_count} analysis job(s) still running."
                })
            return JSONResponse({
                "status": "success",
                "message": "No data found to delete"
            })

        deleted_count = len(analysis_ids)

        # Soft delete: mark as deleted with timestamp (skip processing/pending)
        await session.execute(
            update(GeneticAnalysis)
            .where(
                GeneticAnalysis.user_id == current_user.id,
                GeneticAnalysis.deleted_at.is_(None),
                GeneticAnalysis.analysis_status.notin_(['processing', 'pending']),
            )
            .values(analysis_status='deleted', deleted_at=func.now())
        )

        # Invalidate dashboard cache so stale data isn't served after re-upload
        await session.execute(
            delete(DashboardCache).where(DashboardCache.user_id == current_user.id)
        )

        await session.commit()

        return JSONResponse({
            "status": "success",
            "message": f"Successfully deleted {deleted_count} analyses",
            "deleted_analyses": analysis_ids,
        })

    except Exception as e:
        logger.error(f"Delete all data error: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete data: {str(e)}"
        )


@router.delete("/analysis/{analysis_id}")
async def delete_analysis(
    analysis_id: int,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Delete an analysis and all associated user data.
    Preserves shared variant annotations for system efficiency.
    """
    try:
        # Get analysis
        result = await session.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )

        if analysis.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )

        # Soft delete: mark as deleted with timestamp
        await session.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(analysis_status='deleted', deleted_at=func.now())
        )
        await session.commit()

        return JSONResponse({
            "status": "success",
            "message": f"Analysis {analysis_id} deleted successfully"
        })

    except Exception as e:
        logger.error(f"Delete analysis error: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete analysis: {str(e)}"
        )


@router.get("/data-summary")
async def get_data_summary(
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """Get summary of user's uploaded data."""
    try:
        # Get user's analyses
        result = await session.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.user_id == current_user.id,
                GeneticAnalysis.deleted_at.is_(None),
            ).options(selectinload(GeneticAnalysis.analysis_variants))
        )
        analyses = result.scalars().all()

        summary = {
            "total_analyses": len(analyses),
            "total_variants": sum(len(a.analysis_variants) for a in analyses),
            "analyses": []
        }

        for a in analyses:
            summary["analyses"].append({
                "id": a.id,
                "file_name": a.filename,  # Correct field name
                "file_type": a.file_type,
                "variant_count": len(a.analysis_variants),
                "upload_date": a.upload_date.isoformat() if a.upload_date is not None else None
            })

        return JSONResponse(summary)

    except Exception as e:
        logger.error(f"Data summary error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get data summary: {str(e)}"
        )


@router.get("/analysis/{analysis_id}/variants")
async def get_analysis_variants(
    analysis_id: int,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """Get variants for a specific analysis."""
    try:
        # Verify user owns the analysis
        result = await session.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id,
                GeneticAnalysis.deleted_at.is_(None),
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )

        # Get variants with pagination
        result = await session.execute(
            select(AnalysisVariant).where(
                AnalysisVariant.analysis_id == analysis_id
            ).limit(limit).offset(offset)
        )
        analysis_variants = result.scalars().all()

        # Get total count
        total_result = await session.execute(
            select(func.count(AnalysisVariant.id)).where(
                AnalysisVariant.analysis_id == analysis_id
            )
        )
        total_count = total_result.scalar()

        variants_data = []
        for av in analysis_variants:
            variants_data.append({
                "analysis_variant_id": av.id,
                "chromosome": av.chromosome,
                "position": av.position,
                "rsid": av.rsid,
                "ref_allele": av.ref_allele,
                "alt_allele": av.alt_allele,
                "genotype": av.genotype,
                "quality": av.quality
            })

        return JSONResponse({
            "analysis_id": analysis_id,
            "variants": variants_data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset
        })

    except Exception as e:
        logger.error(f"Get variants error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get variants: {str(e)}"
        )


@router.post("/analysis/{analysis_id}/reanalyze")
async def reanalyze_data(
    analysis_id: int,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Re-run comprehensive analysis on existing uploaded data.
    Useful for getting updated insights or after system improvements.
    """
    try:
        # Verify user owns the analysis
        result = await session.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id,
                GeneticAnalysis.deleted_at.is_(None),
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )

        # Run comprehensive analysis
        try:
            analysis_service = ComprehensiveAnalysisService(user_id=current_user.id)
            analysis_result = await analysis_service.process_analysis(analysis_id)
            
            if analysis_result.get('success'):
                return JSONResponse({
                    "status": "success",
                    "analysis_id": analysis_id,
                    "message": "Analysis completed successfully",
                    "processed_variants": analysis_result.get('processed_variants', 0),
                    "reused_annotations": analysis_result.get('reused_annotations', 0),
                    "new_annotations": analysis_result.get('new_annotations', 0),
                    "insights_generated": analysis_result.get('insights_generated', 0),
                    "processing_time": analysis_result.get('processing_time', 0)
                })
            else:
                return JSONResponse({
                    "status": "completed_with_errors",
                    "analysis_id": analysis_id,
                    "message": "Analysis completed with errors",
                    "error": analysis_result.get('error', 'Unknown analysis error')
                })
                
        except Exception as analysis_error:
            logger.error(f"Re-analysis failed: {analysis_error}")
            
            # Fall back to background queue
            success = await queue_analysis(analysis_id, current_user.id, priority=1)
            if not success:
                logger.warning(f"Failed to queue analysis {analysis_id} for user {current_user.id}")

            return JSONResponse({
                "status": "queued",
                "analysis_id": analysis_id,
                "message": "Analysis queued in background due to error in immediate processing",
                "analysis_error": str(analysis_error)
            })

    except Exception as e:
        logger.error(f"Reanalyze error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reanalyze: {str(e)}"
        )