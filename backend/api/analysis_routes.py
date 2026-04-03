"""
Unified and optimized analysis API routes with proper error handling and clean architecture.
Fixed version with correct SQLAlchemy ORM usage patterns.
"""
import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from starlette.responses import StreamingResponse
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

from ..db.database import get_session, async_session_factory
from ..db.models import GeneticAnalysis, HealthRisk, DrugResponse, PhysicalTrait, NutritionTrait, SportsPerformance, CognitiveProfile, PersonalityTrait, AncestryResult, CarrierStatus, WellnessMetric, MethylationProfile, DetoxificationProfile, RareMutation, UncommonMutation, DashboardCache, ClinVarGeneStats, ClinVarGeneCondition
from .auth_routes import get_current_user
from ..services.notification_service import get_notification_service

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
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Queue a genetic analysis.  The worker process picks it up within ~2 s.
    """
    try:
        result = await db.execute(
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

        current_status = getattr(analysis, 'analysis_status', None)
        if current_status in ('processing', 'queued', 'pending'):
            return AnalysisResponse(
                analysis_id=analysis_id,
                status=current_status,
                message="Analysis is already queued or in progress",
                total_variants=getattr(analysis, 'total_variants', 0) or 0
            )

        # Write 'pending' — the worker detects this and starts working
        await db.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(
                analysis_status="pending",
                progress_percentage=0,
                current_step="queued",
                job_logs=None,
            )
        )
        await db.commit()

        # Notify user that analysis has been queued
        try:
            fname = getattr(analysis, 'filename', 'your file')
            svc = get_notification_service()
            await svc.create(
                user_id=current_user.id,
                type="analysis_queued",
                title="Analysis Queued",
                message=f"Analysis of {fname!r} queued — the worker will start shortly.",
                data={"analysis_id": analysis_id, "filename": fname},
            )
        except Exception as ne:
            logger.warning(f"Could not send analysis-queued notification: {ne}")

        return AnalysisResponse(
            analysis_id=analysis_id,
            status="pending",
            message="Analysis queued — worker will start shortly",
            total_variants=getattr(analysis, 'total_variants', 0) or 0
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting analysis {analysis_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue analysis"
        )


@router.post("/regenerate-insights/{analysis_id}")
async def regenerate_insights(
    analysis_id: int,
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    """Queue insight regeneration.  Worker picks it up within ~2 s."""
    try:
        result = await db.execute(
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
                detail="Analysis not found",
            )

        current_status = getattr(analysis, 'analysis_status', None)
        if current_status in ('processing', 'queued', 'pending'):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Analysis is currently processing",
            )

        await db.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(
                analysis_status="pending",
                progress_percentage=90,
                current_step="regenerating_insights",
                job_logs=None,
            )
        )
        await db.commit()

        return {
            "analysis_id": analysis_id,
            "status": "pending",
            "message": "Insight regeneration queued",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting insight regeneration for {analysis_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start insight regeneration",
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


@router.get("/stream/{analysis_id}")
async def stream_analysis_progress(
    analysis_id: int,
    request: Request,
    current_user = Depends(get_current_user)
):
    """
    Stream analysis progress via Server-Sent Events (SSE).
    Replaces polling — client connects once and receives updates until completion.
    """
    async def event_generator():
        terminal_statuses = {'completed', 'failed', 'stopped', 'cancelled'}
        while True:
            if await request.is_disconnected():
                break

            try:
                async with async_session_factory() as session:
                    result = await session.execute(
                        select(GeneticAnalysis).where(
                            GeneticAnalysis.id == analysis_id,
                            GeneticAnalysis.user_id == current_user.id,
                            GeneticAnalysis.deleted_at.is_(None),
                        )
                    )
                    analysis = result.scalar_one_or_none()

                if not analysis:
                    yield f"event: error\ndata: {json.dumps({'error': 'Analysis not found'})}\n\n"
                    break

                estimated_completion = None
                ec = getattr(analysis, 'estimated_completion', None)
                if ec:
                    estimated_completion = ec.isoformat()

                status_data = {
                    "analysis_id": analysis_id,
                    "status": getattr(analysis, 'analysis_status', 'pending') or 'pending',
                    "message": getattr(analysis, 'current_step', 'Waiting to start') or 'Waiting to start',
                    "current_step": getattr(analysis, 'current_step', 'Waiting to start') or 'Waiting to start',
                    "progress_percentage": getattr(analysis, 'progress_percentage', 0) or 0,
                    "processed_variants": getattr(analysis, 'processed_variants', 0) or 0,
                    "total_variants": getattr(analysis, 'total_variants', 0) or 0,
                    "filename": getattr(analysis, 'filename', '') or '',
                    "estimated_completion": estimated_completion,
                }

                yield f"data: {json.dumps(status_data)}\n\n"

                if status_data['status'] in terminal_statuses:
                    break

            except Exception as e:
                logger.error(f"SSE stream error for analysis {analysis_id}: {e}")
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
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
                GeneticAnalysis.user_id == current_user.id,
                GeneticAnalysis.deleted_at.is_(None),
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
                GeneticAnalysis.user_id == current_user.id,
                GeneticAnalysis.deleted_at.is_(None),
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        current_status = getattr(analysis, 'analysis_status', 'pending')
        if current_status not in ['paused', 'stopped', 'failed', 'processing']:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot resume analysis with status '{current_status}'. Only paused/stopped/failed/processing analyses can be resumed."
            )
        
        # Queue the analysis — the worker picks it up within ~2 s
        await db.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(
                analysis_status="pending",
                current_step=f"queued (resume from {analysis.processed_variants or 0} variants)",
                job_logs=None,
            )
        )
        await db.commit()

        return {"message": "Analysis queued for resume", "analysis_id": analysis_id}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming analysis {analysis_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to resume analysis"
        )


def _dedup_by(items: list, key: str) -> list:
    """Deduplicate a list of dicts by a given key, keeping the first occurrence."""
    seen: set = set()
    result = []
    for item in items:
        val = item.get(key)
        if val not in seen:
            seen.add(val)
            result.append(item)
    return result


def _clean_trait_name(raw: str) -> str:
    """Clean up raw ClinVar condition strings used as trait names.
    
    If the name contains pipe delimiters or semicolons (raw ClinVar data),
    extract the first meaningful condition name and capitalize it.
    """
    if not raw:
        return "Unknown"
    # If it doesn't look like raw ClinVar data, return as-is
    if '|' not in raw and ';' not in raw:
        return raw
    # Split on pipe first, then semicolons
    parts = raw.replace(';', '|').split('|')
    # Filter out generic/useless entries
    skip = {'not provided', 'not specified', 'see cases', 'not applicable'}
    for part in parts:
        cleaned = part.strip()
        if cleaned and cleaned.lower() not in skip:
            # Capitalize if all-uppercase (e.g., "MTHFR THERMOLABILE POLYMORPHISM")
            if cleaned.isupper():
                cleaned = cleaned.title()
            return cleaned
    return parts[0].strip().title() if parts else raw


def _to_list(val) -> list:
    """Normalize a JSON column value (list, string, or None) to always return a list."""
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val:
        return [val]
    return []


def _analysis_fingerprint(analyses) -> str:
    """Hash of analysis IDs + statuses to detect any changes."""
    parts = sorted(f"{a.id}:{a.analysis_status}:{a.processed_variants or 0}" for a in analyses)
    return "|".join(parts)


@router.get("/dashboard-data")
async def get_dashboard_data(
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Get comprehensive dashboard data for the current user.
    Serves from a per-user cache when available; rebuilds on cache miss.
    """
    try:
        # Get all analyses for the user (exclude soft-deleted)
        result = await db.execute(
            select(GeneticAnalysis)
            .where(
                GeneticAnalysis.user_id == current_user.id,
                GeneticAnalysis.deleted_at.is_(None),
            )
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

        # Check dashboard cache — single row read instead of 18+ queries
        fingerprint = _analysis_fingerprint(analyses)
        cache_row = await db.execute(
            select(DashboardCache).where(DashboardCache.user_id == current_user.id)
        )
        cached = cache_row.scalar_one_or_none()
        if cached and cached.analysis_fingerprint == fingerprint:
            return cached.dashboard_json

        # If a job is currently running and we have stale cache, return it —
        # the new insights aren't ready yet and the heavy queries would compete
        # with the analysis for DB resources.
        # BUT only if the cache belongs to the same set of analyses (not stale
        # from a prior upload that was since deleted).
        any_running = any(
            getattr(a, 'analysis_status', '') in ('processing', 'pending')
            for a in analyses
        )
        if any_running:
            current_ids = {str(a.id) for a in analyses}
            cache_ids = set()
            if cached and cached.analysis_fingerprint:
                for part in cached.analysis_fingerprint.split("|"):
                    aid = part.split(":")[0]
                    cache_ids.add(aid)
            # Only return stale cache if it overlaps with the current analyses
            if cached and cached.dashboard_json and current_ids & cache_ids:
                stale = cached.dashboard_json
                if isinstance(stale.get("summary"), dict):
                    stale["summary"]["status"] = "processing"
                return stale
            # No relevant cache — return a processing placeholder
            primary = analyses[0]
            return {
                "summary": {
                    "total_variants": sum(getattr(a, 'total_variants', 0) or 0 for a in analyses),
                    "processed_variants": sum(getattr(a, 'processed_variants', 0) or 0 for a in analyses),
                    "analyzed_variants": 0,
                    "insights_found": 0,
                    "analysis_id": getattr(primary, 'id', None),
                    "status": "processing",
                    "filename": getattr(primary, 'filename', None),
                },
                "health_risks": [], "ancestry_results": [], "sports_performance": [],
                "nutrition_traits": [], "metabolic": {}, "carrier_status": [],
                "drug_responses": [], "rare_mutations": [], "methylation_profiles": [],
                "detoxification_profiles": [], "physical_traits": [], "intelligence": [],
                "personality_traits": [], "wellness_traits": [], "uncommon_mutations": [],
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
        
        # "Analyzed" = processed variants (includes both new and reused annotations)
        analyzed_variants = processed_variants

        # Count insights generated across all insight tables for this user
        from ..db.models import (
            HealthRisk, DrugResponse, PhysicalTrait, NutritionTrait,
            SportsPerformance, CognitiveProfile, PersonalityTrait,
            AncestryResult, CarrierStatus, WellnessMetric,
            MethylationProfile, DetoxificationProfile, RareMutation,
            UncommonMutation,
        )
        analysis_ids_for_insights = [a.id for a in analyses]
        insights_found = 0
        for insight_tbl in (
            HealthRisk, DrugResponse, PhysicalTrait, NutritionTrait,
            SportsPerformance, CognitiveProfile, PersonalityTrait,
            AncestryResult, CarrierStatus, WellnessMetric,
            MethylationProfile, DetoxificationProfile, RareMutation,
            UncommonMutation,
        ):
            cnt_result = await db.execute(
                select(func.count()).where(
                    insight_tbl.analysis_id.in_(analysis_ids_for_insights)
                )
            )
            insights_found += (cnt_result.scalar() or 0)
        
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
        dashboard_data["health_risks"] = _dedup_by([
            {"condition": _clean_trait_name(r.condition), "risk_level": r.risk_level, "risk_score": r.risk_score,
             "associated_variants": r.associated_variants, "recommendations": _to_list(r.recommendations),
             "gene": r.gene, "review_status": r.review_status,
             "pathogenicity_classification": r.pathogenicity_classification}
            for r in health_rows
        ], "condition")

        # Drug responses
        dr = await db.execute(
            select(DrugResponse).where(DrugResponse.analysis_id.in_(analysis_ids))
        )
        drug_rows = dr.scalars().all()
        dashboard_data["drug_responses"] = _dedup_by([
            {"gene": r.gene, "drug": r.drug, "response_type": r.response_type,
             "recommendations": _to_list(r.recommendations), "variants_involved": r.variants_involved}
            for r in drug_rows
        ], "drug")

        # Ancestry
        ar = await db.execute(
            select(AncestryResult).where(AncestryResult.analysis_id.in_(analysis_ids))
        )
        ancestry_rows = ar.scalars().all()
        dashboard_data["ancestry_results"] = _dedup_by([
            {"population": r.population, "percentage": r.percentage,
             "confidence": r.confidence, "geographic_origin": r.geographic_origin,
             "composition": r.composition,
             "maternal_haplogroup": r.maternal_haplogroup,
             "paternal_haplogroup": r.paternal_haplogroup,
             "neanderthal_variants": r.neanderthal_variants}
            for r in ancestry_rows
        ], "population")

        # Sports
        sp = await db.execute(
            select(SportsPerformance).where(SportsPerformance.analysis_id.in_(analysis_ids))
        )
        sports_rows = sp.scalars().all()
        dashboard_data["sports_performance"] = _dedup_by([
            {"category": r.performance_category, "genetic_advantage": r.genetic_advantage,
             "sport_recommendations": _to_list(r.sport_recommendations), "training_advice": r.training_advice,
             "associated_variants": r.associated_variants or []}
            for r in sports_rows
        ], "category")

        # Nutrition
        nt = await db.execute(
            select(NutritionTrait).where(NutritionTrait.analysis_id.in_(analysis_ids))
        )
        nutrition_rows = nt.scalars().all()
        dashboard_data["nutrition_traits"] = _dedup_by([
            {"nutrient": r.nutrient, "metabolism_type": r.metabolism_type,
             "dietary_recommendations": _to_list(r.dietary_recommendations), "sensitivity_level": r.sensitivity_level,
             "associated_variants": r.associated_variants or []}
            for r in nutrition_rows
        ], "nutrient")

        # Carrier status
        cs = await db.execute(
            select(CarrierStatus).where(CarrierStatus.analysis_id.in_(analysis_ids))
        )
        carrier_rows = cs.scalars().all()
        dashboard_data["carrier_status"] = _dedup_by([
            {"condition": _clean_trait_name(r.condition), "carrier_status": r.carrier_status,
             "inheritance_pattern": r.inheritance_pattern,
             "associated_variants": r.associated_variants or [],
             "genetic_counseling_recommended": r.genetic_counseling_recommended,
             "gene": r.gene or ""}
            for r in carrier_rows
        ], "condition")

        # Methylation profiles
        mp = await db.execute(
            select(MethylationProfile).where(MethylationProfile.analysis_id.in_(analysis_ids))
        )
        methylation_rows = mp.scalars().all()
        dashboard_data["methylation_profiles"] = _dedup_by([
            {"gene": r.gene, "variant": r.variant,
             "methylation_capacity": r.methylation_capacity,
             "supplement_recommendations": _to_list(r.supplement_recommendations),
             "associated_variants": r.associated_variants}
            for r in methylation_rows
        ], "gene")

        # Detoxification profiles
        dp = await db.execute(
            select(DetoxificationProfile).where(DetoxificationProfile.analysis_id.in_(analysis_ids))
        )
        detox_rows = dp.scalars().all()
        dashboard_data["detoxification_profiles"] = _dedup_by([
            {"detox_phase": r.detox_phase, "gene": r.gene,
             "detox_capacity": r.detox_capacity, "toxin_sensitivity": r.toxin_sensitivity,
             "support_recommendations": _to_list(r.support_recommendations),
             "associated_variants": r.associated_variants}
            for r in detox_rows
        ], "gene")

        # Rare mutations
        rm = await db.execute(
            select(RareMutation).where(RareMutation.analysis_id.in_(analysis_ids))
        )
        rare_rows = rm.scalars().all()
        dashboard_data["rare_mutations"] = _dedup_by([
            {"gene": r.gene, "mutation_type": r.mutation_type,
             "mutation_name": _clean_trait_name(r.mutation_name),
             "clinical_significance": r.clinical_significance,
             "disease_association": _clean_trait_name(r.disease_association) if r.disease_association else r.disease_association,
             "penetrance": r.penetrance,
             "population_frequency": r.population_frequency,
             "associated_variants": r.associated_variants,
             "clinical_actions": _to_list(r.clinical_actions),
             "monitoring_recommendations": _to_list(r.monitoring_recommendations)}
            for r in rare_rows
        ], "mutation_name")

        # Cognitive, Personality, Wellness, Physical Traits - metabolic/wellness
        wm = await db.execute(
            select(WellnessMetric).where(WellnessMetric.analysis_id.in_(analysis_ids))
        )
        wellness_rows = wm.scalars().all()
        dashboard_data["metabolic"] = {
            "metrics": _dedup_by([
                {"metric_name": r.metric_name, "genetic_predisposition": r.genetic_predisposition,
                 "optimization_score": r.optimization_score,
                 "lifestyle_recommendations": r.lifestyle_recommendations}
                for r in wellness_rows
            ], "metric_name")
        } if wellness_rows else {}

        # Also provide wellness data under wellness_traits key for frontend compatibility
        dashboard_data["wellness_traits"] = _dedup_by([
            {"trait": _clean_trait_name(r.metric_name), "category": "Wellness", "value": r.genetic_predisposition,
             "gene": "Multiple", "confidence": r.optimization_score or "Medium",
             "name": _clean_trait_name(r.metric_name), "result": r.genetic_predisposition,
             "marker": "Multiple genes",
             "associated_variants": r.associated_variants or [],
             "recommendations": _to_list(r.lifestyle_recommendations)}
            for r in wellness_rows
        ], "trait") if wellness_rows else []

        # Physical traits
        pt = await db.execute(
            select(PhysicalTrait).where(PhysicalTrait.analysis_id.in_(analysis_ids))
        )
        physical_rows = pt.scalars().all()
        dashboard_data["physical_traits"] = _dedup_by([
            {"trait_name": _clean_trait_name(r.trait_name), "trait_category": _clean_trait_name(r.trait_category),
             "genetic_result": r.genetic_result, "confidence": r.confidence,
             "associated_variants": r.associated_variants, "description": r.description,
             "category": _clean_trait_name(r.trait_category)}
            for r in physical_rows
        ], "trait_name") if physical_rows else []

        # Cognitive profiles (intelligence)
        cp = await db.execute(
            select(CognitiveProfile).where(CognitiveProfile.analysis_id.in_(analysis_ids))
        )
        cognitive_rows = cp.scalars().all()
        dashboard_data["intelligence"] = _dedup_by([
            {"cognitive_ability": _clean_trait_name(r.cognitive_domain), "trait_name": _clean_trait_name(r.cognitive_domain),
             "genetic_advantage": r.genetic_score, "genetic_result": r.genetic_score,
             "percentile": r.percentile,
             "associated_variants": r.associated_variants,
             "description": '; '.join(r.enhancement_suggestions) if isinstance(r.enhancement_suggestions, list) else (r.enhancement_suggestions or ''),
             "enhancement_suggestions": r.enhancement_suggestions if isinstance(r.enhancement_suggestions, list) else ([r.enhancement_suggestions] if r.enhancement_suggestions else [])}
            for r in cognitive_rows
        ], "trait_name") if cognitive_rows else []

        # Personality traits
        pp = await db.execute(
            select(PersonalityTrait).where(PersonalityTrait.analysis_id.in_(analysis_ids))
        )
        personality_rows = pp.scalars().all()
        dashboard_data["personality_traits"] = _dedup_by([
            {"trait": _clean_trait_name(r.trait_name), "name": _clean_trait_name(r.trait_name),
             "score": 70 if r.genetic_tendency == 'moderate' else (85 if r.genetic_tendency == 'high' else 55),
             "confidence": r.confidence_level,
             "gene": r.associated_variants[0] if r.associated_variants else "Multiple markers",
             "marker": r.associated_variants[0] if r.associated_variants else "Multiple markers",
             "associated_variants": r.associated_variants or [],
             "description": (_to_list(r.behavioral_insights) or ["Genetic analysis based"])[0],
             "summary": (_to_list(r.behavioral_insights) or ["Genetic analysis based"])[0],
             "characteristics": _to_list(r.behavioral_insights) or ["Trait-based behavior"]}
            for r in personality_rows
        ], "trait") if personality_rows else []

        # Uncommon mutations
        um = await db.execute(
            select(UncommonMutation).where(UncommonMutation.analysis_id.in_(analysis_ids))
        )
        uncommon_rows = um.scalars().all()
        dashboard_data["uncommon_mutations"] = _dedup_by([
            {"rsid": r.associated_variants[0] if r.associated_variants else r.mutation_name,
             "gene": r.gene, "effect": _clean_trait_name(r.trait_association or r.mutation_name),
             "population_frequency": r.population_frequency or 0,
             "effect_size": r.effect_size or "small",
             "research_status": r.research_status or "emerging",
             "clinical_relevance": r.clinical_significance or "low",
             "literature_count": 0,
             "mutation_name": r.mutation_name,
             "mutation_type": r.mutation_type}
            for r in uncommon_rows
        ], "mutation_name") if uncommon_rows else []

        # AlphaMissense + ClinVar + AlphaFold + PharmGKB maps: rsid → data for all annotated variants
        from ..db.models import AnalysisVariant, GeneticMarker, SharedVariantAnnotation
        annotation_rows = (await db.execute(
            select(
                GeneticMarker.rsid,
                SharedVariantAnnotation.alpha_missense_data,
                SharedVariantAnnotation.clinvar_data,
                SharedVariantAnnotation.clinvar_local_data,
                SharedVariantAnnotation.alphafold_data,
                SharedVariantAnnotation.pharmgkb_data,
                SharedVariantAnnotation.ensembl_data,
            )
            .select_from(AnalysisVariant)
            .join(GeneticMarker, AnalysisVariant.marker_id == GeneticMarker.id)
            .join(SharedVariantAnnotation, SharedVariantAnnotation.marker_id == GeneticMarker.id)
            .where(AnalysisVariant.analysis_id == primary_analysis.id)
        )).all()
        am_map: Dict[str, Any] = {}
        cv_count_map: Dict[str, int] = {}
        allele_string_map: Dict[str, str] = {}
        for row in annotation_rows:
            am = row.alpha_missense_data
            if isinstance(am, dict) and am.get('found'):
                am_map[row.rsid] = {
                    "score": am.get('am_pathogenicity'),
                    "classification": am.get('am_class'),
                }
            cv = row.clinvar_data
            if isinstance(cv, dict) and cv.get('found'):
                count = cv.get('count', 0)
                if count > 0:
                    cv_count_map[row.rsid] = count
            # Extract allele_string from Ensembl VEP data for panel allele coloring
            ensembl = row.ensembl_data
            if isinstance(ensembl, dict):
                data_list = ensembl.get('data', [])
                if data_list and isinstance(data_list, list):
                    allele_str = data_list[0].get('allele_string', '')
                    if allele_str and '/' in allele_str:
                        allele_string_map[row.rsid] = allele_str
        dashboard_data["alpha_missense_map"] = am_map
        dashboard_data["clinvar_count_map"] = cv_count_map
        dashboard_data["allele_string_map"] = allele_string_map

        # Build alphafold_map: rsid → {confidence, high_confidence_pct, low_confidence_pct, protein_name}
        # Built at dashboard time from gene_symbol_map + AlphaFold local DB (20k proteins),
        # not from pre-stored annotation data (which requires re-analysis to populate).
        alphafold_map: Dict[str, Any] = {}
        pharmgkb_map: Dict[str, Any] = {}
        for row in annotation_rows:
            pgkb = row.pharmgkb_data
            if isinstance(pgkb, dict) and pgkb.get('found'):
                # Extract most clinically relevant PharmGKB fields for panel display
                pgkb_entry: Dict[str, Any] = {"gene": pgkb.get('gene', '')}
                # Haplotypes / star alleles
                variants_data = pgkb.get('variants', [])
                if isinstance(variants_data, list):
                    haplotypes = [v.get('haplotype') or v.get('star_allele') for v in variants_data if v.get('haplotype') or v.get('star_allele')]
                    if haplotypes:
                        pgkb_entry['haplotypes'] = haplotypes[:4]
                # CPIC guideline URL / name
                guidelines = pgkb.get('guidelines', [])
                if isinstance(guidelines, list) and guidelines:
                    g = guidelines[0]
                    pgkb_entry['cpic_guideline'] = g.get('name') or g.get('url') or ''
                # Phenotype from top variant
                if isinstance(variants_data, list) and variants_data:
                    top = variants_data[0]
                    pgkb_entry['phenotype'] = top.get('phenotype') or top.get('function') or ''
                    pgkb_entry['star_allele'] = top.get('star_allele') or top.get('haplotype') or ''
                pharmgkb_map[row.rsid] = pgkb_entry
        dashboard_data["pharmgkb_map"] = pharmgkb_map

        # Build rsid → genotype map only for variants referenced in panel data
        panel_rsids: set = set()
        for key in ("health_risks", "sports_performance", "nutrition_traits",
                     "carrier_status", "methylation_profiles", "detoxification_profiles",
                     "rare_mutations", "physical_traits", "intelligence",
                     "personality_traits", "wellness_traits", "uncommon_mutations"):
            items = dashboard_data.get(key, [])
            if isinstance(items, dict):
                items = items.get("metrics", [])
            for item in items:
                for v in (item.get("associated_variants") or []):
                    if isinstance(v, str) and v.startswith("rs"):
                        panel_rsids.add(v)
                for field in ("rsid", "variant", "gene", "marker"):
                    val = item.get(field)
                    if isinstance(val, str) and val.startswith("rs"):
                        panel_rsids.add(val)
        # Drug responses use variants_involved
        for dr_item in dashboard_data.get("drug_responses", []):
            for v in (dr_item.get("variants_involved") or []):
                if isinstance(v, str) and v.startswith("rs"):
                    panel_rsids.add(v)

        genotype_map: Dict[str, str] = {}
        if panel_rsids:
            genotype_query = await db.execute(
                select(GeneticMarker.rsid, AnalysisVariant.genotype)
                .select_from(AnalysisVariant)
                .join(GeneticMarker, AnalysisVariant.marker_id == GeneticMarker.id)
                .where(AnalysisVariant.analysis_id.in_(analysis_ids))
                .where(GeneticMarker.rsid.in_(panel_rsids))
                .where(AnalysisVariant.genotype.isnot(None))
                .where(AnalysisVariant.genotype != '')
            )
            for row in genotype_query.all():
                genotype_map[row.rsid] = row.genotype
        dashboard_data["genotype_map"] = genotype_map

        # Build rsid → gene symbol map from genetic_markers table
        gene_symbol_map: Dict[str, str] = {}
        if panel_rsids:
            gs_query = await db.execute(
                select(GeneticMarker.rsid, GeneticMarker.gene_symbol)
                .where(GeneticMarker.rsid.in_(panel_rsids))
                .where(GeneticMarker.gene_symbol.isnot(None))
                .where(GeneticMarker.gene_symbol != '')
            )
            for row in gs_query.all():
                gene_symbol_map[row.rsid] = row.gene_symbol
        dashboard_data["gene_symbol_map"] = gene_symbol_map

        # Build alphafold_map live from gene_symbol_map + AlphaFold local DB.
        # This avoids requiring re-analysis — AlphaFold data is gene-based and
        # the local DB has 20k proteins that can be looked up instantly.
        try:
            from ..services.alphafold_local import get_alphafold_local_service
            af_svc = get_alphafold_local_service()
            if af_svc.available and gene_symbol_map:
                # Only look up genes for rsids that are actually used in panels
                panel_gene_rsids = {r: g for r, g in gene_symbol_map.items() if r in panel_rsids}
                unique_genes = list(set(panel_gene_rsids.values()))
                if unique_genes:
                    gene_results = af_svc.bulk_lookup_genes(unique_genes)
                    for rsid, gene in panel_gene_rsids.items():
                        af_data = gene_results.get(gene)
                        if af_data and af_data.get('found'):
                            alphafold_map[rsid] = {
                                "confidence": af_data.get('global_confidence'),
                                "high_confidence_pct": af_data.get('plddt_very_high', 0) or 0,
                                "low_confidence_pct": af_data.get('plddt_very_low', 0) or 0,
                                "protein_name": af_data.get('protein_name'),
                            }
        except Exception:
            logger.warning("Failed to build alphafold_map from local DB")
        dashboard_data["alphafold_map"] = alphafold_map

        # Build pathogenicity_map: rsid → {score, classification, confidence, evidence_count}
        # Uses the same ScoringEngine as VariantDetailDialog for consistency
        pathogenicity_map: Dict[str, Any] = {}
        if panel_rsids:
            try:
                from ..services.scoring_engine import get_scoring_engine
                scoring_engine = get_scoring_engine()
                scoring_rows = (await db.execute(
                    select(
                        GeneticMarker.rsid,
                        SharedVariantAnnotation.ensembl_data,
                        SharedVariantAnnotation.clinvar_data,
                        SharedVariantAnnotation.clinvar_local_data,
                        SharedVariantAnnotation.alpha_missense_data,
                        SharedVariantAnnotation.gnomad_data,
                    )
                    .select_from(AnalysisVariant)
                    .join(GeneticMarker, AnalysisVariant.marker_id == GeneticMarker.id)
                    .join(SharedVariantAnnotation, SharedVariantAnnotation.marker_id == GeneticMarker.id)
                    .where(AnalysisVariant.analysis_id == primary_analysis.id)
                    .where(GeneticMarker.rsid.in_(panel_rsids))
                )).all()
                for row in scoring_rows:
                    annotations = {}
                    if row.ensembl_data:
                        annotations["ensembl"] = row.ensembl_data
                    if row.clinvar_data:
                        annotations["clinvar"] = row.clinvar_data
                    if row.clinvar_local_data:
                        annotations["clinvar_local"] = row.clinvar_local_data
                    if row.alpha_missense_data:
                        annotations["alpha_missense"] = row.alpha_missense_data
                    if row.gnomad_data:
                        annotations["gnomad"] = row.gnomad_data
                    if annotations:
                        result = scoring_engine.score_variant(annotations)
                        if result.get("evidence_count", 0) > 0:
                            pathogenicity_map[row.rsid] = {
                                "score": round(result["composite_score"] * 100),
                                "classification": result.get("classification", "unknown"),
                                "confidence": result.get("confidence", "none"),
                                "evidence_count": result.get("evidence_count", 0),
                            }
            except Exception:
                logger.warning("Failed to compute pathogenicity_map – skipping")
        dashboard_data["pathogenicity_map"] = pathogenicity_map

        # ── Clinical significance backfill ───────────────────────────────────
        # Populate clinical_significance on health_risks from clinvar_local_data
        # (the HealthRisk DB row has no such column, so we derive it from annotations)
        try:
            clinvar_sig_map: Dict[str, str] = {}
            for row in annotation_rows:
                cv_local = row.clinvar_local_data
                if isinstance(cv_local, dict):
                    sigs: list = []
                    for entry in cv_local.get("entries", []):
                        for sig in entry.get("clinical_significance", []):
                            if sig and sig not in sigs:
                                sigs.append(sig)
                    if sigs:
                        clinvar_sig_map[row.rsid] = "; ".join(sigs)
                    elif cv_local.get("clinical_significance"):
                        raw = cv_local["clinical_significance"]
                        clinvar_sig_map[row.rsid] = raw if isinstance(raw, str) else "; ".join(raw)
            # Patch health_risks in-place
            for hr_item in dashboard_data.get("health_risks", []):
                variants = hr_item.get("associated_variants") or []
                for v in variants:
                    sig = clinvar_sig_map.get(v)
                    if sig:
                        hr_item["clinical_significance"] = sig
                        break
        except Exception:
            logger.warning("Failed to backfill clinical_significance – skipping")

        # ── Gene stats enrichment ────────────────────────────────────────────
        # Collect all gene symbols from clinical panels
        try:
            panel_genes: set = set()
            for item in dashboard_data.get("health_risks", []):
                if item.get("gene"):
                    panel_genes.add(item["gene"])
            for item in dashboard_data.get("rare_mutations", []):
                if item.get("gene"):
                    panel_genes.add(item["gene"])
            for item in dashboard_data.get("drug_responses", []):
                if item.get("gene"):
                    panel_genes.add(item["gene"])
            for item in dashboard_data.get("uncommon_mutations", []):
                if item.get("gene"):
                    panel_genes.add(item["gene"])
            for item in dashboard_data.get("methylation_profiles", []):
                if item.get("gene"):
                    panel_genes.add(item["gene"])
            for item in dashboard_data.get("detoxification_profiles", []):
                if item.get("gene"):
                    panel_genes.add(item["gene"])
            for item in dashboard_data.get("carrier_status", []):
                # Use gene field directly (populated by carrier generator)
                if item.get("gene"):
                    panel_genes.add(item["gene"])
                else:
                    # Fallback: extract gene from parenthetical in condition name
                    import re as _re
                    condition_str = item.get("condition", "")
                    gene_match = _re.search(r'\(([A-Z][A-Z0-9]{1,9})\)\s*$', condition_str)
                    if gene_match:
                        panel_genes.add(gene_match.group(1))
                # Also resolve via gene_symbol_map using the associated_variants
                for v in (item.get("associated_variants") or []):
                    if isinstance(v, str) and v in gene_symbol_map:
                        panel_genes.add(gene_symbol_map[v])
                        if not item.get("gene"):
                            item["gene"] = gene_symbol_map[v]

            # Also add all gene symbols resolved via rsid → gene_symbol_map
            panel_genes.update(gene_symbol_map.values())

            gene_stats_map: Dict[str, Any] = {}
            if panel_genes:
                stats_rows_q = await db.execute(
                    select(ClinVarGeneStats).where(ClinVarGeneStats.gene.in_(panel_genes))
                )
                stats_by_gene = {s.gene: s for s in stats_rows_q.scalars().all()}

                cond_rows_q = await db.execute(
                    select(ClinVarGeneCondition).where(ClinVarGeneCondition.gene.in_(panel_genes))
                )
                conditions_by_gene: Dict[str, list] = {}
                for c in cond_rows_q.scalars().all():
                    conditions_by_gene.setdefault(c.gene, []).append({
                        "disease_name": c.disease_name,
                        "disease_mim": c.disease_mim,
                        "source_id": c.source_id,
                    })

                for gene in panel_genes:
                    stats = stats_by_gene.get(gene)
                    if stats:
                        gene_stats_map[gene] = {
                            "pathogenic_lp": stats.pathogenic_likely_pathogenic or 0,
                            "vus": stats.uncertain_significance or 0,
                            "total_submissions": stats.total_submissions or 0,
                            "total_alleles": stats.total_alleles or 0,
                            "with_conflicts": stats.with_conflicts or 0,
                            "gene_mim": stats.gene_mim,
                            "conditions": conditions_by_gene.get(gene, []),
                        }
            dashboard_data["gene_stats_map"] = gene_stats_map
        except Exception:
            logger.warning("Failed to build gene_stats_map – skipping")
            dashboard_data["gene_stats_map"] = {}

        # Persist to dashboard cache
        try:
            if cached:
                cached.dashboard_json = dashboard_data
                cached.analysis_fingerprint = fingerprint
                cached.refreshed_at = func.now()
            else:
                db.add(DashboardCache(
                    user_id=current_user.id,
                    dashboard_json=dashboard_data,
                    analysis_fingerprint=fingerprint,
                ))
            await db.commit()
        except Exception:
            await db.rollback()
            logger.warning("Failed to persist dashboard cache – returning fresh data")

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
            .where(
                GeneticAnalysis.user_id == current_user.id,
                GeneticAnalysis.deleted_at.is_(None),
            )
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



# Legacy stub kept for import compatibility — analysis is now handled by the worker process
async def background_analysis_task(analysis_id: int, user_id: int, strategy: str):
    pass