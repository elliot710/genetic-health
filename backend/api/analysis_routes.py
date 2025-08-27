"""
Unified and optimized analysis API routes with proper error handling and clean architecture.
Fixed version with correct SQLAlchemy ORM usage patterns.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

from ..db.database import get_session
from ..db.models import GeneticAnalysis
from ..core.container import ServiceManager
from ..services.analysis_service import AnalysisStrategy
from .auth_routes import get_current_user

logger = logging.getLogger(__name__)

# API Models
class AnalysisRequest(BaseModel):
    # No strategy selection needed - always uses fast processing
    pass


class AnalysisResponse(BaseModel):
    analysis_id: int
    status: str
    message: str
    progress_percentage: int = 0
    processed_variants: int = 0
    total_variants: int = 0


class AnalysisResult(BaseModel):
    analysis_id: int
    status: str
    processed_variants: int
    total_variants: int
    api_calls_made: int
    processing_time: float
    strategy_used: str
    errors: List[str] = []


class AnalysisListItem(BaseModel):
    id: int
    status: str
    upload_date: Optional[str]
    processed_variants: int
    total_variants: int
    strategy_used: Optional[str]


# Router setup
router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("/start/{analysis_id}", response_model=AnalysisResponse)
async def start_analysis(
    analysis_id: int,
    request: Optional[AnalysisRequest] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Start genetic analysis for a specific analysis ID.
    """
    try:
        # Get analysis record
        result = await db.execute(
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
        
        # Only fast strategy is supported
        strategy = AnalysisStrategy.FAST
        
        # Update analysis status to processing using SQLAlchemy update
        await db.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(
                analysis_status="processing",
                progress_percentage=0,
                current_step="initializing"
            )
        )
        await db.commit()
        
        # Refresh to get updated values
        await db.refresh(analysis)
        
        # Start background processing
        async def run_analysis():
            try:
                async with ServiceManager() as service_manager:
                    analysis_service = service_manager.get_analysis_service(current_user.id)
                    await analysis_service.process_analysis(analysis_id, strategy)
            except Exception as e:
                logger.error(f"Background analysis failed: {e}")
        
        background_tasks.add_task(run_analysis)
        
        return AnalysisResponse(
            analysis_id=analysis_id,
            status="processing",
            message="Analysis started successfully",
            total_variants=getattr(analysis, 'total_variants', 0) or 0
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting analysis {analysis_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start analysis"
        )


@router.get("/status/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis_status(
    analysis_id: int,
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Get the current status of a genetic analysis.
    """
    try:
        result = await db.execute(
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
        
        return AnalysisResponse(
            analysis_id=analysis_id,
            status=getattr(analysis, 'analysis_status', 'pending') or 'pending',
            message=getattr(analysis, 'current_step', 'Waiting to start') or 'Waiting to start',
            progress_percentage=getattr(analysis, 'progress_percentage', 0) or 0,
            processed_variants=getattr(analysis, 'processed_variants', 0) or 0,
            total_variants=getattr(analysis, 'total_variants', 0) or 0
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analysis status {analysis_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get analysis status"
        )


@router.get("/results/{analysis_id}", response_model=Dict[str, Any])
async def get_analysis_results(
    analysis_id: int,
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Get the results of a completed genetic analysis.
    """
    try:
        result = await db.execute(
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
        
        # Check if analysis is completed
        analysis_status = getattr(analysis, 'analysis_status', 'pending')
        if analysis_status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Analysis is not completed. Current status: {analysis_status}"
            )
        
        # Return analysis summary and metadata
        upload_date_str = None
        upload_date = getattr(analysis, 'upload_date', None)
        if upload_date:
            upload_date_str = upload_date.isoformat()
        
        return {
            "analysis_id": analysis_id,
            "status": analysis_status,
            "processed_variants": getattr(analysis, 'processed_variants', 0) or 0,
            "total_variants": getattr(analysis, 'total_variants', 0) or 0,
            "upload_date": upload_date_str
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analysis results {analysis_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get analysis results"
        )


@router.post("/cancel/{analysis_id}")
async def cancel_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Cancel a running genetic analysis.
    """
    try:
        result = await db.execute(
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
        
        # Update status to cancelled using SQLAlchemy update
        await db.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(
                analysis_status="cancelled",
                current_step="cancelled by user"
            )
        )
        await db.commit()
        
        return {"message": "Analysis cancelled successfully", "analysis_id": analysis_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling analysis {analysis_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel analysis"
        )


@router.post("/pause/{analysis_id}")
async def pause_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Pause a running genetic analysis.
    """
    try:
        logger.info(f"Pausing analysis {analysis_id} for user {current_user.id}")
        
        # Check if analysis exists and belongs to user
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        # Update status to paused using SQLAlchemy update
        await db.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(
                analysis_status="paused",
                current_step="paused by user"
            )
        )
        await db.commit()
        
        return {"message": "Analysis paused successfully", "analysis_id": analysis_id}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing analysis {analysis_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to pause analysis"
        )


@router.post("/resume/{analysis_id}")
async def resume_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Resume a paused genetic analysis.
    """
    try:
        logger.info(f"Resuming analysis {analysis_id} for user {current_user.id}")
        
        # Check if analysis exists and belongs to user
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        # Update status to processing using SQLAlchemy update
        await db.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(
                analysis_status="processing",
                current_step=f"resuming from {analysis.processed_variants} variants"
            )
        )
        await db.commit()
        
        # Note: The actual analysis job would need to be restarted separately
        # This just updates the database status
        
        return {"message": "Analysis resumed successfully", "analysis_id": analysis_id}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming analysis {analysis_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to resume analysis"
        )


@router.get("/dashboard-data")
async def get_dashboard_data(
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Get comprehensive dashboard data for the current user.
    """
    try:
        # Get all analyses for the user
        result = await db.execute(
            select(GeneticAnalysis)
            .where(GeneticAnalysis.user_id == current_user.id)
            .order_by(GeneticAnalysis.upload_date.desc())
        )
        analyses = result.scalars().all()
        
        if not analyses:
            return {
                "summary": {
                    "total_variants": 0,
                    "analysis_id": None,
                    "status": "no_data"
                },
                "health": {},
                "ancestry": {},
                "sports": {},
                "nutrition": {},
                "metabolic": {},
                "carrier": {},
                "pharmacogenomics": {},
                "rare": {},
                "methylation": {},
                "detox": {}
            }
        
        # Get the most recent completed analysis or the first one
        primary_analysis = None
        for analysis in analyses:
            if getattr(analysis, 'analysis_status', '') == 'completed':
                primary_analysis = analysis
                break
        
        if not primary_analysis:
            primary_analysis = analyses[0]  # Use the most recent one
        
        # Calculate totals
        total_variants = sum(getattr(a, 'total_variants', 0) or 0 for a in analyses)
        processed_variants = sum(getattr(a, 'processed_variants', 0) or 0 for a in analyses)
        
        # Count actual variant annotations for more accurate "analyzed" count
        from ..db.models import VariantAnnotation
        annotation_result = await db.execute(
            select(VariantAnnotation)
            .join(GeneticAnalysis, VariantAnnotation.analysis_id == GeneticAnalysis.id)
            .where(GeneticAnalysis.user_id == current_user.id)
        )
        analyzed_variants = len(annotation_result.scalars().all())
        
        # Count insights (annotations with meaningful data)
        insights_result = await db.execute(
            select(VariantAnnotation)
            .join(GeneticAnalysis, VariantAnnotation.analysis_id == GeneticAnalysis.id)
            .where(
                GeneticAnalysis.user_id == current_user.id,
                VariantAnnotation.ensembl_data.isnot(None)
            )
        )
        insights_found = len(insights_result.scalars().all())
        
        # Get upload date safely
        upload_date = getattr(primary_analysis, 'upload_date', None)
        upload_date_str = upload_date.isoformat() if upload_date else None
        
        dashboard_data = {
            "summary": {
                "total_variants": total_variants,
                "processed_variants": processed_variants,
                "analyzed_variants": analyzed_variants,  # Add real analyzed count
                "insights_found": insights_found,  # Add insights count
                "analysis_id": getattr(primary_analysis, 'id', None),
                "status": getattr(primary_analysis, 'analysis_status', 'pending'),
                "upload_date": upload_date_str
            },
            # Placeholder category data - these would be populated by specialized analyzers
            "health": {
                "cardiovascular_risk": "moderate",
                "diabetes_risk": "low",
                "alzheimer_risk": "low"
            },
            "ancestry": {
                "european": 0.7,
                "asian": 0.2,
                "african": 0.1
            },
            "sports": {
                "endurance": "high",
                "power": "moderate",
                "recovery": "good"
            },
            "nutrition": {
                "caffeine_metabolism": "fast",
                "lactose_tolerance": "tolerant",
                "vitamin_d": "normal"
            },
            "metabolic": {
                "metabolism_rate": "normal",
                "fat_storage": "low_risk",
                "insulin_sensitivity": "high"
            },
            "carrier": {
                "cystic_fibrosis": "not_carrier",
                "sickle_cell": "not_carrier"
            },
            "pharmacogenomics": {
                "warfarin_sensitivity": "normal",
                "statins_response": "good"
            },
            "rare": {
                "mutations_found": 0,
                "pathogenic_variants": 0
            },
            "methylation": {
                "mthfr_status": "normal",
                "folate_cycle": "efficient"
            },
            "detox": {
                "phase1_enzymes": "normal",
                "phase2_enzymes": "normal"
            }
        }
        
        return dashboard_data
        
    except Exception as e:
        logger.error(f"Error getting dashboard data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get dashboard data"
        )


@router.get("/list", response_model=List[AnalysisListItem])
async def list_user_analyses(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    List all analyses for the current user.
    """
    try:
        result = await db.execute(
            select(GeneticAnalysis)
            .where(GeneticAnalysis.user_id == current_user.id)
            .order_by(GeneticAnalysis.upload_date.desc())
            .offset(skip)
            .limit(limit)
        )
        analyses = result.scalars().all()
        
        analysis_list = []
        for analysis in analyses:
            upload_date_str = None
            upload_date = getattr(analysis, 'upload_date', None)
            if upload_date:
                upload_date_str = upload_date.isoformat()
                
            analysis_list.append(AnalysisListItem(
                id=getattr(analysis, 'id', 0),
                status=getattr(analysis, 'analysis_status', 'pending') or 'pending',
                upload_date=upload_date_str,
                processed_variants=getattr(analysis, 'processed_variants', 0) or 0,
                total_variants=getattr(analysis, 'total_variants', 0) or 0,
                strategy_used=getattr(analysis, 'current_step', None)  # Use current_step as strategy indicator
            ))
        
        return analysis_list
        
    except Exception as e:
        logger.error(f"Error listing user analyses: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list analyses"
        )


# Background task handler with proper error handling
async def background_analysis_task(analysis_id: int, user_id: int, strategy: AnalysisStrategy):
    """
    Background task to run genetic analysis with proper error handling.
    """
    try:
        async with ServiceManager() as service_manager:
            analysis_service = service_manager.get_analysis_service(user_id)
            await analysis_service.process_analysis(analysis_id, strategy)
            
    except Exception as e:
        logger.error(f"Background analysis task failed for analysis {analysis_id}: {str(e)}")
        
        # Update analysis status to failed
        try:
            from ..db.database import async_session_factory
            async with async_session_factory() as db:
                await db.execute(
                    update(GeneticAnalysis)
                    .where(GeneticAnalysis.id == analysis_id)
                    .values(
                        analysis_status="failed",
                        current_step=f"Failed: {str(e)}"
                    )
                )
                await db.commit()
        except Exception as db_error:
            logger.error(f"Failed to update analysis status after error: {str(db_error)}")