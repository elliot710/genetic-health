"""
Upload routes for genetic data files with optimized variant storage.
"""
import logging
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, delete, func

from .auth_routes import get_current_user
from ..db.database import get_session
from ..db.models import GeneticAnalysis, AnalysisVariant
from ..utils.vcf_parser import VCFParser
from ..services.optimized_variant_uploader import OptimizedVariantUploader
from ..services.analysis_queue import queue_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/vcf")
async def upload_vcf(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """Upload VCF file and process genetic variants."""
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
            file_type='vcf'
        )
        session.add(analysis)
        await session.commit()
        await session.refresh(analysis)

        # Parse VCF and upload variants
        parser = VCFParser()
        variants_data = await parser.parse_vcf_content(content)
        
        uploader = OptimizedVariantUploader(session)
        processed_count, _ = await uploader.upload_variants(analysis.id, variants_data)
        
        await session.commit()

        # Queue background analysis
        success = await queue_analysis(analysis.id, current_user.id, priority=1)
        if not success:
            logger.warning(f"Failed to queue analysis {analysis.id} for user {current_user.id}")

        return JSONResponse({
            "status": "success",
            "analysis_id": analysis.id,
            "message": "VCF file processed successfully",
            "processed_variants": processed_count
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
    """Upload CSV file and process genetic variants."""
    try:
        if not file.filename or not file.filename.endswith('.csv'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only CSV files are supported"
            )

        # Read file content
        content = await file.read()
        
        # Create analysis record
        analysis = GeneticAnalysis(
            user_id=current_user.id,
            filename=file.filename,
            file_type='csv'
        )
        session.add(analysis)
        await session.commit()
        await session.refresh(analysis)

        # Parse CSV and upload variants
        parser = VCFParser()
        variants_data = await parser.parse_vcf_content(content)  # VCFParser can handle CSV too
        
        uploader = OptimizedVariantUploader(session)
        analysis_id = getattr(analysis, 'id')  # Get the actual ID value
        stats = await uploader.upload_variants(analysis_id, variants_data)
        
        await session.commit()

        # Queue background analysis
        success = await queue_analysis(analysis_id, current_user.id, priority=1)
        if not success:
            logger.warning(f"Failed to queue analysis {analysis_id} for user {current_user.id}")

        return JSONResponse({
            "status": "success",
            "analysis_id": analysis_id,
            "message": "CSV file processed successfully",
            "stats": stats
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
    """Delete all genetic data for the current user."""
    try:
        # Get all user's analyses
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

        deleted_count = 0
        # Delete each analysis and its associated data
        for analysis in analyses:
            # Delete associated AnalysisVariant records (cascades will handle the rest)
            await session.execute(
                delete(AnalysisVariant).where(AnalysisVariant.analysis_id == analysis.id)
            )
            
            # Delete the analysis
            await session.delete(analysis)
            deleted_count += 1
        
        await session.commit()

        return JSONResponse({
            "status": "success",
            "message": f"Successfully deleted {deleted_count} analyses and all associated data"
        })

    except Exception as e:
        logger.error(f"Delete all data error: {e}")
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
    """Delete an analysis and all associated data."""
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

        # Delete associated AnalysisVariant records (cascades will handle the rest)
        await session.execute(
            delete(AnalysisVariant).where(AnalysisVariant.analysis_id == analysis.id)
        )
        
        # Delete the analysis
        await session.delete(analysis)
        await session.commit()

        return JSONResponse({
            "status": "success",
            "message": f"Analysis {analysis_id} deleted successfully"
        })

    except Exception as e:
        logger.error(f"Delete analysis error: {e}")
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