"""
Upload routes for genetic data files with optimized variant storage.
"""
import logging
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func, delete, update

from .auth_routes import get_current_user
from ..db.database import get_session
from ..db.models import GeneticAnalysis, AnalysisVariant
from ..utils.vcf_parser import VCFParser
from ..services.variant_uploader import VariantUploader
from ..services.analysis_service import ComprehensiveAnalysisService
from ..services.analysis_queue import queue_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/vcf")
async def upload_vcf(
    file: UploadFile = File(...),
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
            current_step='uploading_variants'
        )
        session.add(analysis)
        await session.commit()
        await session.refresh(analysis)

        # Parse VCF and upload variants
        parser = VCFParser()
        variants_data = await parser.parse_vcf_content(content)
        
        # Get the analysis ID value after refresh
        analysis_id = getattr(analysis, 'id')
        
        uploader = VariantUploader(session)
        processed_count, new_count = await uploader.upload_variants(analysis_id, variants_data)
        
        # Update total_variants in the analysis record
        await session.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(total_variants=processed_count)
        )
        await session.commit()

        # Return immediately - frontend will trigger background analysis via /api/analysis/start/{id}
        return JSONResponse({
            "status": "uploaded",
            "analysis_id": analysis_id,
            "message": "VCF file uploaded successfully",
            "processed_variants": processed_count,
            "stats": {
                "total_variants": processed_count,
                "new_variants": new_count,
                "reused_variants": processed_count - new_count
            }
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
            current_step='uploading_variants'
        )
        session.add(analysis)
        await session.commit()
        await session.refresh(analysis)

        # Parse CSV and upload variants
        parser = VCFParser()
        variants_data = await parser.parse_vcf_content(content)
        
        # Get the analysis ID value after refresh
        analysis_id = getattr(analysis, 'id')
        
        uploader = VariantUploader(session)
        processed_count, new_count = await uploader.upload_variants(analysis_id, variants_data)
        
        # Update total_variants in the analysis record
        await session.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(total_variants=processed_count)
        )
        await session.commit()

        # Return immediately - frontend will trigger background analysis via /api/analysis/start/{id}
        return JSONResponse({
            "status": "uploaded",
            "analysis_id": analysis_id,
            "message": "CSV file uploaded successfully",
            "processed_variants": processed_count,
            "stats": {
                "total_variants": processed_count,
                "new_variants": new_count,
                "reused_variants": processed_count - new_count
            },
            "redirect_to_dashboard": True
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
    This only deletes user-specific data (analyses and their insights),
    but preserves shared variant annotations for efficiency.
    """
    try:
        # Get all user's analyses with their related data
        from sqlalchemy import delete
        from ..db.models import (
            VariantAnnotation, AnalysisVariant, HealthRisk, DrugResponse,
            PhysicalTrait, NutritionTrait, SportsPerformance, CognitiveProfile,
            PersonalityTrait, AncestryResult, CarrierStatus, WellnessMetric,
            MethylationProfile, DetoxificationProfile, RareMutation, UncommonMutation
        )
        
        result = await session.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analyses = result.scalars().all()
        
        if not analyses:
            return JSONResponse({
                "status": "success",
                "message": "No data found to delete"
            })

        analysis_ids = [analysis.id for analysis in analyses]
        deleted_count = len(analysis_ids)
        
        # Delete in correct order to respect foreign key constraints
        # All insight tables have CASCADE delete on analysis_id, so we just need to delete analyses
        # and the system will automatically clean up user-specific data while preserving shared annotations
        
        # Delete analyses (this will cascade to all user-specific data)
        await session.execute(
            delete(GeneticAnalysis).where(GeneticAnalysis.id.in_(analysis_ids))
        )
        
        await session.commit()

        return JSONResponse({
            "status": "success",
            "message": f"Successfully deleted {deleted_count} analyses and user-specific data",
            "deleted_analyses": analysis_ids,
            "note": "User-specific data deleted, shared annotations automatically preserved"
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

        # Import necessary models for explicit deletion
        from sqlalchemy import delete

        # Delete analysis (this will cascade to all user-specific data while preserving shared annotations)
        await session.execute(
            delete(GeneticAnalysis).where(GeneticAnalysis.id == analysis_id)
        )
        
        await session.commit()

        return JSONResponse({
            "status": "success",
            "message": f"Analysis {analysis_id} deleted successfully",
            "note": "User-specific data deleted, shared annotations automatically preserved"
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
                GeneticAnalysis.user_id == current_user.id
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
                GeneticAnalysis.user_id == current_user.id
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
                GeneticAnalysis.user_id == current_user.id
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