"""
Analysis API routes – thin wrappers delegating to services.
"""
import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from starlette.responses import StreamingResponse
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

from ..db.database import get_session, async_session_factory
from ..db.models import GeneticAnalysis, DashboardCache
from .auth_routes import get_current_user
from ..services.notification_service import get_notification_service
from ..services.dashboard_service import (
    EMPTY_DASHBOARD, analysis_fingerprint, stale_or_placeholder,
    build_dashboard_for_user, persist_dashboard_cache,
    _assemble_dashboard,
)

logger = logging.getLogger(__name__)


class AnalysisRequest(BaseModel):
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


router = APIRouter(prefix="/api/analysis", tags=["analysis"])


async def _get_user_analysis(
    db: AsyncSession, analysis_id: int, user_id: int
) -> GeneticAnalysis:
    result = await db.execute(
        select(GeneticAnalysis).where(
            GeneticAnalysis.id == analysis_id,
            GeneticAnalysis.user_id == user_id,
            GeneticAnalysis.deleted_at.is_(None),
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return analysis


@router.post("/start/{analysis_id}", response_model=AnalysisResponse)
async def start_analysis(
    analysis_id: int,
    request: Optional[AnalysisRequest] = None,
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    try:
        analysis = await _get_user_analysis(db, analysis_id, current_user.id)

        current_status = getattr(analysis, 'analysis_status', None)
        if current_status in ('processing', 'queued', 'pending'):
            return AnalysisResponse(
                analysis_id=analysis_id,
                status=current_status,
                message="Analysis is already queued or in progress",
                total_variants=getattr(analysis, 'total_variants', 0) or 0
            )

        await db.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(analysis_status="pending", progress_percentage=0, current_step="queued", job_logs=None)
        )
        await db.commit()

        try:
            fname = getattr(analysis, 'filename', 'your file')
            svc = get_notification_service()
            await svc.create(
                user_id=current_user.id, type="analysis_queued",
                title="Analysis Queued",
                message=f"Analysis of {fname!r} queued — the worker will start shortly.",
                data={"analysis_id": analysis_id, "filename": fname},
            )
        except Exception:
            pass

        return AnalysisResponse(
            analysis_id=analysis_id, status="pending",
            message="Analysis queued — worker will start shortly",
            total_variants=getattr(analysis, 'total_variants', 0) or 0
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting analysis {analysis_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to queue analysis")


@router.post("/regenerate-insights/{analysis_id}")
async def regenerate_insights(
    analysis_id: int,
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    try:
        analysis = await _get_user_analysis(db, analysis_id, current_user.id)
        if getattr(analysis, 'analysis_status', None) in ('processing', 'queued', 'pending'):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Analysis is currently processing")

        await db.execute(
            update(GeneticAnalysis).where(GeneticAnalysis.id == analysis_id)
            .values(analysis_status="pending", progress_percentage=90, current_step="regenerating_insights", job_logs=None)
        )
        await db.commit()
        return {"analysis_id": analysis_id, "status": "pending", "message": "Insight regeneration queued"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting insight regeneration for {analysis_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to start insight regeneration")


@router.get("/status/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis_status(
    analysis_id: int,
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    try:
        analysis = await _get_user_analysis(db, analysis_id, current_user.id)
        return AnalysisResponse(
            analysis_id=analysis_id,
            status=getattr(analysis, 'analysis_status', 'pending') or 'pending',
            message=getattr(analysis, 'current_step', 'Waiting to start') or 'Waiting to start',
            progress_percentage=getattr(analysis, 'progress_percentage', 0) or 0,
            processed_variants=getattr(analysis, 'processed_variants', 0) or 0,
            total_variants=getattr(analysis, 'total_variants', 0) or 0,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analysis status {analysis_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get analysis status")


@router.get("/stream/{analysis_id}")
async def stream_analysis_progress(
    analysis_id: int, request: Request, current_user=Depends(get_current_user),
):
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
                ec = getattr(analysis, 'estimated_completion', None)
                data = {
                    "analysis_id": analysis_id,
                    "status": getattr(analysis, 'analysis_status', 'pending') or 'pending',
                    "message": getattr(analysis, 'current_step', 'Waiting to start') or 'Waiting to start',
                    "current_step": getattr(analysis, 'current_step', 'Waiting to start') or 'Waiting to start',
                    "progress_percentage": getattr(analysis, 'progress_percentage', 0) or 0,
                    "processed_variants": getattr(analysis, 'processed_variants', 0) or 0,
                    "total_variants": getattr(analysis, 'total_variants', 0) or 0,
                    "filename": getattr(analysis, 'filename', '') or '',
                    "estimated_completion": ec.isoformat() if ec else None,
                }
                yield f"data: {json.dumps(data)}\n\n"
                if data['status'] in terminal_statuses:
                    break
            except Exception as e:
                logger.error(f"SSE stream error for analysis {analysis_id}: {e}")
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


def _analysis_coverage(insight_status, processed_variants, total_variants) -> Dict[str, Any]:
    """Honest per-analysis completeness: the mean of the variant-annotation rate
    and the insight-category success rate, each 0-1. Either input may be missing
    (older analyses have no insight_status); score is None only when neither is
    available."""
    processed_variants = processed_variants or 0
    total_variants = total_variants or 0
    variant_rate = (processed_variants / total_variants) if total_variants else None

    category_rate = None
    categories = None
    if isinstance(insight_status, dict):
        generators_total = insight_status.get("generators_total") or 0
        generators_succeeded = insight_status.get("generators_succeeded")
        if generators_total and generators_succeeded is not None:
            category_rate = generators_succeeded / generators_total
            categories = {"succeeded": generators_succeeded, "total": generators_total}

    rates = [r for r in (variant_rate, category_rate) if r is not None]
    score = round(100 * sum(rates) / len(rates)) if rates else None
    return {
        "score": score,
        "variant_annotation": {"processed": processed_variants, "total": total_variants},
        "insight_categories": categories,
    }


@router.get("/results/{analysis_id}", response_model=Dict[str, Any])
async def get_analysis_results(
    analysis_id: int, db: AsyncSession = Depends(get_session), current_user=Depends(get_current_user),
):
    try:
        analysis = await _get_user_analysis(db, analysis_id, current_user.id)
        if getattr(analysis, 'analysis_status', 'pending') != "completed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Analysis is not completed")
        upload_date = getattr(analysis, 'upload_date', None)
        return {
            "analysis_id": analysis_id, "status": "completed",
            "processed_variants": getattr(analysis, 'processed_variants', 0) or 0,
            "total_variants": getattr(analysis, 'total_variants', 0) or 0,
            "upload_date": upload_date.isoformat() if upload_date else None,
            "insight_status": getattr(analysis, 'insight_status', None),
            "coverage": _analysis_coverage(
                getattr(analysis, 'insight_status', None),
                getattr(analysis, 'processed_variants', 0),
                getattr(analysis, 'total_variants', 0),
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analysis results {analysis_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get analysis results")


@router.post("/cancel/{analysis_id}")
async def cancel_analysis(
    analysis_id: int, db: AsyncSession = Depends(get_session), current_user=Depends(get_current_user),
):
    try:
        await _get_user_analysis(db, analysis_id, current_user.id)
        await db.execute(
            update(GeneticAnalysis).where(GeneticAnalysis.id == analysis_id)
            .values(analysis_status="stopped", current_step="stopped by user")
        )
        await db.commit()
        return {"message": "Analysis stopped successfully", "analysis_id": analysis_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling analysis {analysis_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to cancel analysis")


@router.post("/pause/{analysis_id}")
async def pause_analysis(
    analysis_id: int, db: AsyncSession = Depends(get_session), current_user=Depends(get_current_user),
):
    try:
        analysis = await _get_user_analysis(db, analysis_id, current_user.id)
        if getattr(analysis, 'analysis_status', 'pending') not in ['processing', 'running']:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot pause analysis with this status")
        await db.execute(
            update(GeneticAnalysis).where(GeneticAnalysis.id == analysis_id)
            .values(analysis_status="paused", current_step="paused by user")
        )
        await db.commit()
        return {"message": "Analysis paused successfully", "analysis_id": analysis_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing analysis {analysis_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to pause analysis")


@router.post("/resume/{analysis_id}")
async def resume_analysis(
    analysis_id: int, db: AsyncSession = Depends(get_session), current_user=Depends(get_current_user),
):
    try:
        analysis = await _get_user_analysis(db, analysis_id, current_user.id)
        if getattr(analysis, 'analysis_status', 'pending') not in ['paused', 'stopped', 'failed', 'processing']:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot resume analysis with this status")
        await db.execute(
            update(GeneticAnalysis).where(GeneticAnalysis.id == analysis_id)
            .values(analysis_status="pending",
                    current_step=f"queued (resume from {analysis.processed_variants or 0} variants)",
                    job_logs=None)
        )
        await db.commit()
        return {"message": "Analysis queued for resume", "analysis_id": analysis_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming analysis {analysis_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to resume analysis")


@router.get("/dashboard-data")
async def get_dashboard_data(
    db: AsyncSession = Depends(get_session), current_user=Depends(get_current_user),
):
    try:
        result = await db.execute(
            select(GeneticAnalysis)
            .where(GeneticAnalysis.user_id == current_user.id, GeneticAnalysis.deleted_at.is_(None))
            .order_by(GeneticAnalysis.upload_date.desc())
        )
        analyses = result.scalars().all()
        if not analyses:
            return EMPTY_DASHBOARD

        fingerprint = analysis_fingerprint(analyses)
        cache_row = await db.execute(select(DashboardCache).where(DashboardCache.user_id == current_user.id))
        cached = cache_row.scalar_one_or_none()
        if cached and cached.analysis_fingerprint == fingerprint:
            cached_json = cached.dashboard_json
            if (isinstance(cached_json, dict)
                    and "allele_string_map" in cached_json
                    and cached_json.get("_allele_map_version", 1) >= 2):
                return cached_json

        any_running = any(getattr(a, 'analysis_status', '') in ('processing', 'pending') for a in analyses)
        if any_running:
            stale = stale_or_placeholder(analyses, cached)
            if stale:
                return stale

        primary_analysis = next(
            (a for a in analyses if getattr(a, 'analysis_status', '') == 'completed'), analyses[0],
        )
        analysis_ids = [a.id for a in analyses]
        dashboard_data = await _assemble_dashboard(db, analyses, primary_analysis, analysis_ids)
        await persist_dashboard_cache(db, current_user.id, dashboard_data, fingerprint, cached)
        return dashboard_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get dashboard data")


@router.get("/list", response_model=List[AnalysisListItem])
async def list_user_analyses(
    skip: int = 0, limit: int = 50,
    db: AsyncSession = Depends(get_session), current_user=Depends(get_current_user),
):
    try:
        result = await db.execute(
            select(GeneticAnalysis)
            .where(GeneticAnalysis.user_id == current_user.id, GeneticAnalysis.deleted_at.is_(None))
            .order_by(GeneticAnalysis.upload_date.desc())
            .offset(skip).limit(limit)
        )
        analyses = result.scalars().all()
        analysis_list = []
        for a in analyses:
            upload_date = getattr(a, 'upload_date', None)
            analysis_list.append(AnalysisListItem(
                id=getattr(a, 'id', 0),
                status=getattr(a, 'analysis_status', 'pending') or 'pending',
                upload_date=upload_date.isoformat() if upload_date else None,
                processed_variants=getattr(a, 'processed_variants', 0) or 0,
                total_variants=getattr(a, 'total_variants', 0) or 0,
                strategy_used=getattr(a, 'current_step', None),
            ))
        return analysis_list
    except Exception as e:
        logger.error(f"Error listing user analyses: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list analyses")
    pass