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
from ..db.models import GeneticAnalysis, HealthRisk, DrugResponse, PhysicalTrait, NutritionTrait, SportsPerformance, CognitiveProfile, PersonalityTrait, AncestryResult, CarrierStatus, WellnessMetric, MethylationProfile, DetoxificationProfile, RareMutation, UncommonMutation
from ..core.container import ServiceManager
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
                    await analysis_service.process_analysis(analysis_id)
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
        
        # Update status to stopped using SQLAlchemy update
        await db.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(
                analysis_status="stopped",
                current_step="stopped by user"
            )
        )
        await db.commit()
        
        return {"message": "Analysis stopped successfully", "analysis_id": analysis_id}
        
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
        
        current_status = getattr(analysis, 'analysis_status', 'pending')
        
        # Check if analysis can be paused
        if current_status not in ['processing', 'running']:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot pause analysis with status '{current_status}'. Only running/processing analysis can be paused."
            )
        
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
        
        logger.info(f"Analysis {analysis_id} paused successfully")
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
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Resume a paused or stopped genetic analysis.
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
        
        current_status = getattr(analysis, 'analysis_status', 'pending')
        if current_status not in ['paused', 'stopped']:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot resume analysis with status '{current_status}'. Only paused/stopped analysis can be resumed."
            )
        
        # Update status to processing
        await db.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(
                analysis_status="processing",
                current_step=f"resuming from {analysis.processed_variants or 0} variants"
            )
        )
        await db.commit()
        
        # Restart the background processing job
        async def run_analysis():
            try:
                async with ServiceManager() as service_manager:
                    analysis_service = service_manager.get_analysis_service(current_user.id)
                    await analysis_service.process_analysis(analysis_id)
            except Exception as e:
                logger.error(f"Resumed analysis failed: {e}")
        
        background_tasks.add_task(run_analysis)
        
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
                "health_risks": [],
                "ancestry_results": [],
                "sports_performance": [],
                "nutrition_traits": [],
                "metabolic": {},
                "carrier_status": [],
                "drug_responses": [],
                "rare_mutations": [],
                "methylation_profiles": [],
                "detoxification_profiles": [],
                "physical_traits": [],
                "intelligence": [],
                "personality_traits": [],
                "wellness_traits": [],
                "uncommon_mutations": []
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
        from ..db.models import VariantAnnotation, SharedVariantAnnotation
        annotation_result = await db.execute(
            select(VariantAnnotation)
            .join(GeneticAnalysis, VariantAnnotation.analysis_id == GeneticAnalysis.id)
            .where(GeneticAnalysis.user_id == current_user.id)
        )
        analyzed_variants = len(annotation_result.scalars().all())
        
        # Count insights (annotations with meaningful data) using shared annotations
        insights_result = await db.execute(
            select(VariantAnnotation)
            .join(GeneticAnalysis, VariantAnnotation.analysis_id == GeneticAnalysis.id)
            .join(SharedVariantAnnotation, VariantAnnotation.shared_annotation_id == SharedVariantAnnotation.id)
            .where(
                GeneticAnalysis.user_id == current_user.id,
                SharedVariantAnnotation.ensembl_data.isnot(None)
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
                "analyzed_variants": analyzed_variants,
                "insights_found": insights_found,
                "analysis_id": getattr(primary_analysis, 'id', None),
                "status": getattr(primary_analysis, 'analysis_status', 'pending'),
                "upload_date": upload_date_str,
                "filename": getattr(primary_analysis, 'filename', None)
            },
        }

        analysis_ids = [a.id for a in analyses]

        # Health risks
        hr = await db.execute(
            select(HealthRisk).where(HealthRisk.analysis_id.in_(analysis_ids))
        )
        health_rows = hr.scalars().all()
        dashboard_data["health_risks"] = [
            {"condition": r.condition, "risk_level": r.risk_level, "risk_score": r.risk_score,
             "associated_variants": r.associated_variants, "recommendations": r.recommendations}
            for r in health_rows
        ]

        # Drug responses
        dr = await db.execute(
            select(DrugResponse).where(DrugResponse.analysis_id.in_(analysis_ids))
        )
        drug_rows = dr.scalars().all()
        dashboard_data["drug_responses"] = [
            {"gene": r.gene, "drug": r.drug, "response_type": r.response_type,
             "recommendations": r.recommendations, "variants_involved": r.variants_involved}
            for r in drug_rows
        ]

        # Ancestry
        ar = await db.execute(
            select(AncestryResult).where(AncestryResult.analysis_id.in_(analysis_ids))
        )
        ancestry_rows = ar.scalars().all()
        dashboard_data["ancestry_results"] = [
            {"population": r.population, "percentage": r.percentage,
             "confidence": r.confidence, "geographic_origin": r.geographic_origin}
            for r in ancestry_rows
        ]

        # Sports
        sp = await db.execute(
            select(SportsPerformance).where(SportsPerformance.analysis_id.in_(analysis_ids))
        )
        sports_rows = sp.scalars().all()
        dashboard_data["sports_performance"] = [
            {"category": r.performance_category, "genetic_advantage": r.genetic_advantage,
             "sport_recommendations": r.sport_recommendations, "training_advice": r.training_advice}
            for r in sports_rows
        ]

        # Nutrition
        nt = await db.execute(
            select(NutritionTrait).where(NutritionTrait.analysis_id.in_(analysis_ids))
        )
        nutrition_rows = nt.scalars().all()
        dashboard_data["nutrition_traits"] = [
            {"nutrient": r.nutrient, "metabolism_type": r.metabolism_type,
             "dietary_recommendations": r.dietary_recommendations, "sensitivity_level": r.sensitivity_level}
            for r in nutrition_rows
        ]

        # Carrier status
        cs = await db.execute(
            select(CarrierStatus).where(CarrierStatus.analysis_id.in_(analysis_ids))
        )
        carrier_rows = cs.scalars().all()
        dashboard_data["carrier_status"] = [
            {"condition": r.condition, "carrier_status": r.carrier_status,
             "inheritance_pattern": r.inheritance_pattern,
             "genetic_counseling_recommended": r.genetic_counseling_recommended}
            for r in carrier_rows
        ]

        # Methylation profiles
        mp = await db.execute(
            select(MethylationProfile).where(MethylationProfile.analysis_id.in_(analysis_ids))
        )
        methylation_rows = mp.scalars().all()
        dashboard_data["methylation_profiles"] = [
            {"gene": r.gene, "variant": r.variant,
             "methylation_capacity": r.methylation_capacity,
             "supplement_recommendations": r.supplement_recommendations,
             "associated_variants": r.associated_variants}
            for r in methylation_rows
        ]

        # Detoxification profiles
        dp = await db.execute(
            select(DetoxificationProfile).where(DetoxificationProfile.analysis_id.in_(analysis_ids))
        )
        detox_rows = dp.scalars().all()
        dashboard_data["detoxification_profiles"] = [
            {"detox_phase": r.detox_phase, "gene": r.gene,
             "detox_capacity": r.detox_capacity, "toxin_sensitivity": r.toxin_sensitivity,
             "support_recommendations": r.support_recommendations,
             "associated_variants": r.associated_variants}
            for r in detox_rows
        ]

        # Rare mutations
        rm = await db.execute(
            select(RareMutation).where(RareMutation.analysis_id.in_(analysis_ids))
        )
        rare_rows = rm.scalars().all()
        dashboard_data["rare_mutations"] = [
            {"gene": r.gene, "mutation_type": r.mutation_type,
             "mutation_name": r.mutation_name,
             "clinical_significance": r.clinical_significance,
             "disease_association": r.disease_association,
             "penetrance": r.penetrance,
             "population_frequency": r.population_frequency,
             "associated_variants": r.associated_variants}
            for r in rare_rows
        ]

        # Cognitive, Personality, Wellness, Physical Traits - metabolic/wellness
        wm = await db.execute(
            select(WellnessMetric).where(WellnessMetric.analysis_id.in_(analysis_ids))
        )
        wellness_rows = wm.scalars().all()
        dashboard_data["metabolic"] = {
            "metrics": [
                {"metric_name": r.metric_name, "genetic_predisposition": r.genetic_predisposition,
                 "optimization_score": r.optimization_score,
                 "lifestyle_recommendations": r.lifestyle_recommendations}
                for r in wellness_rows
            ]
        } if wellness_rows else {}

        # Also provide wellness data under wellness_traits key for frontend compatibility
        dashboard_data["wellness_traits"] = [
            {"trait": r.metric_name, "category": "Wellness", "value": r.genetic_predisposition,
             "gene": (r.associated_variants[0] if r.associated_variants and len(r.associated_variants) == 1 else "Multiple"),
             "confidence": r.optimization_score or "Medium",
             "associated_variants": r.associated_variants or [],
             "recommendations": r.lifestyle_recommendations}
            for r in wellness_rows
        ] if wellness_rows else []

        # Physical traits
        pt = await db.execute(
            select(PhysicalTrait).where(PhysicalTrait.analysis_id.in_(analysis_ids))
        )
        physical_rows = pt.scalars().all()
        dashboard_data["physical_traits"] = [
            {"trait_name": r.trait_name, "trait_category": r.trait_category,
             "genetic_result": r.genetic_result, "confidence": r.confidence,
             "associated_variants": r.associated_variants, "description": r.description,
             "category": r.trait_category}
            for r in physical_rows
        ] if physical_rows else []

        # Cognitive profiles (intelligence)
        cp = await db.execute(
            select(CognitiveProfile).where(CognitiveProfile.analysis_id.in_(analysis_ids))
        )
        cognitive_rows = cp.scalars().all()
        dashboard_data["intelligence"] = [
            {"cognitive_ability": r.cognitive_domain, "trait_name": r.cognitive_domain,
             "genetic_advantage": r.genetic_score, "genetic_result": r.genetic_score,
             "percentile": r.percentile,
             "associated_variants": r.associated_variants,
             "description": '; '.join(r.enhancement_suggestions) if r.enhancement_suggestions else '',
             "enhancement_suggestions": r.enhancement_suggestions}
            for r in cognitive_rows
        ] if cognitive_rows else []

        # Personality traits
        pp = await db.execute(
            select(PersonalityTrait).where(PersonalityTrait.analysis_id.in_(analysis_ids))
        )
        personality_rows = pp.scalars().all()
        dashboard_data["personality_traits"] = [
            {"trait": r.trait_name,
             "score": 70 if r.genetic_tendency == 'moderate' else (85 if r.genetic_tendency == 'high' else 55),
             "confidence": r.confidence_level,
             "gene": r.associated_variants[0] if r.associated_variants else "Multiple markers",
             "description": r.behavioral_insights[0] if r.behavioral_insights else "Genetic analysis based",
             "characteristics": (r.behavioral_insights[1:] if r.behavioral_insights and len(r.behavioral_insights) > 1 else [])}
            for r in personality_rows
        ] if personality_rows else []

        # Uncommon mutations
        um = await db.execute(
            select(UncommonMutation).where(UncommonMutation.analysis_id.in_(analysis_ids))
        )
        uncommon_rows = um.scalars().all()
        dashboard_data["uncommon_mutations"] = [
            {"rsid": r.associated_variants[0] if r.associated_variants else r.mutation_name,
             "gene": r.gene, "effect": r.trait_association or r.mutation_name,
             "population_frequency": r.population_frequency or 0,
             "effect_size": r.effect_size or "small",
             "research_status": r.research_status or "emerging",
             "clinical_relevance": r.clinical_significance or "low",
             "literature_count": 0,
             "mutation_name": r.mutation_name,
             "mutation_type": r.mutation_type}
            for r in uncommon_rows
        ] if uncommon_rows else []
        
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
async def background_analysis_task(analysis_id: int, user_id: int, strategy: str):
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