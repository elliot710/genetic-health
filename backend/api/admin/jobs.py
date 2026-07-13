"""
Admin analysis-job + worker-job management routes.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, text, update

from ...db.database import get_session
from ...db.models import User, GeneticAnalysis
from .schemas import (
    require_admin,
    LATENCY_P95_THRESHOLD_SECONDS,
    AdminJobResponse,
    AdminJobsSummary,
    AdminJobsLatency,
)

# No prefix here -- folded into the admin package's aggregated router (see
# admin/__init__.py), which carries "/api/admin"; baking it in twice
# double-prefixes.
router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)


@router.get("/jobs/summary", response_model=AdminJobsSummary)
async def get_jobs_summary(
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Get summary counts of all analysis jobs by status."""
    result = await db.execute(
        select(
            GeneticAnalysis.analysis_status,
            func.count(GeneticAnalysis.id)
        )
        .where(GeneticAnalysis.deleted_at.is_(None))
        .group_by(GeneticAnalysis.analysis_status)
    )
    counts = {row[0]: row[1] for row in result.all()}
    total = sum(counts.values())
    return AdminJobsSummary(
        total=total,
        pending=counts.get('pending', 0),
        processing=counts.get('processing', 0),
        completed=counts.get('completed', 0),
        failed=counts.get('failed', 0),
    )


def _percentile(sorted_data: List[float], pct: float) -> float:
    """Nearest-rank percentile over already-sorted data (pct in [0, 1])."""
    index = min(len(sorted_data) - 1, int(round(pct * (len(sorted_data) - 1))))
    return sorted_data[index]


@router.get("/jobs/latency", response_model=AdminJobsLatency)
async def get_jobs_latency(
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """p50/p95 analysis completion latency, derived from completed_at - upload_date.

    Measurement only — see LATENCY_P95_THRESHOLD_SECONDS above.
    """
    result = await db.execute(
        select(GeneticAnalysis.upload_date, GeneticAnalysis.completed_at)
        .where(
            GeneticAnalysis.analysis_status == 'completed',
            GeneticAnalysis.completed_at.isnot(None),
            GeneticAnalysis.upload_date.isnot(None),
        )
    )
    durations = sorted(
        (completed_at - upload_date).total_seconds()
        for upload_date, completed_at in result.all()
    )
    if not durations:
        return AdminJobsLatency(sample_size=0)

    p95 = _percentile(durations, 0.95)
    return AdminJobsLatency(
        sample_size=len(durations),
        p50_seconds=round(_percentile(durations, 0.50), 1),
        p95_seconds=round(p95, 1),
        exceeds_threshold=p95 > LATENCY_P95_THRESHOLD_SECONDS,
    )


@router.get("/jobs", response_model=List[AdminJobResponse])
async def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """List all analysis jobs with user info. Optionally filter by status."""
    query = (
        select(GeneticAnalysis, User.email, User.username)
        .join(User, GeneticAnalysis.user_id == User.id)
        .where(GeneticAnalysis.deleted_at.is_(None))
        .order_by(GeneticAnalysis.upload_date.desc())
    )
    if status_filter and status_filter in ('pending', 'processing', 'completed', 'failed'):
        query = query.where(GeneticAnalysis.analysis_status == status_filter)

    result = await db.execute(query)
    rows = result.all()
    return [
        AdminJobResponse(
            id=analysis.id,
            user_id=analysis.user_id,
            user_email=email,
            username=username,
            filename=analysis.filename,
            file_type=analysis.file_type,
            analysis_status=analysis.analysis_status or 'pending',
            progress_percentage=analysis.progress_percentage or 0,
            total_variants=analysis.total_variants or 0,
            processed_variants=analysis.processed_variants or 0,
            current_step=analysis.current_step,
            upload_date=analysis.upload_date,
            estimated_completion=analysis.estimated_completion,
        )
        for analysis, email, username in rows
    ]


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Cancel a running or pending analysis job."""
    from sqlalchemy import update
    result = await db.execute(
        select(GeneticAnalysis).where(GeneticAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")
    if analysis.analysis_status not in ('pending', 'processing', 'paused'):
        raise HTTPException(status_code=400, detail=f"Cannot cancel job with status '{analysis.analysis_status}'")

    await db.execute(
        update(GeneticAnalysis)
        .where(GeneticAnalysis.id == job_id)
        .values(analysis_status="failed", current_step="cancelled_by_admin")
    )
    await db.commit()
    return {"detail": f"Job {job_id} cancelled"}


@router.post("/jobs/{job_id}/pause")
async def pause_job(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Pause a running analysis job. The background task will stop at the next checkpoint."""
    from sqlalchemy import update
    result = await db.execute(
        select(GeneticAnalysis).where(GeneticAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")
    if analysis.analysis_status not in ('processing', 'pending'):
        raise HTTPException(status_code=400, detail=f"Cannot pause job with status '{analysis.analysis_status}'")

    await db.execute(
        update(GeneticAnalysis)
        .where(GeneticAnalysis.id == job_id)
        .values(analysis_status="paused")
    )
    await db.commit()
    return {"detail": f"Job {job_id} paused — will stop at next checkpoint"}


@router.post("/jobs/{job_id}/resume")
async def resume_job(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Resume a paused analysis job from where it left off."""
    from sqlalchemy import update
    result = await db.execute(
        select(GeneticAnalysis).where(GeneticAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")
    if analysis.analysis_status != 'paused':
        raise HTTPException(status_code=400, detail=f"Cannot resume job with status '{analysis.analysis_status}'")

    await db.execute(
        update(GeneticAnalysis)
        .where(GeneticAnalysis.id == job_id)
        .values(analysis_status="pending", current_step="queued (resume)", job_logs=None)
    )
    await db.commit()
    return {"detail": f"Job {job_id} queued for resume"}


@router.post("/jobs/{job_id}/restart")
async def restart_job(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Restart a failed or completed analysis job (full re-analysis)."""
    from sqlalchemy import update

    result = await db.execute(
        select(GeneticAnalysis).where(GeneticAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")
    if analysis.analysis_status in ('processing', 'pending', 'queued'):
        raise HTTPException(status_code=400, detail="Job is already processing or queued")

    await db.execute(
        update(GeneticAnalysis)
        .where(GeneticAnalysis.id == job_id)
        .values(
            analysis_status="pending",
            progress_percentage=0,
            processed_variants=0,
            current_step="queued (restart)",
            estimated_completion=None,
            job_logs=None,
        )
    )
    await db.commit()
    return {"detail": f"Job {job_id} queued for restart"}


@router.post("/jobs/{job_id}/regenerate-insights")
async def regenerate_insights_admin(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Queue insight regeneration for a job (worker picks it up)."""
    from sqlalchemy import update

    result = await db.execute(
        select(GeneticAnalysis).where(GeneticAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")
    if analysis.analysis_status in ('processing', 'pending', 'queued'):
        raise HTTPException(status_code=400, detail="Job is already processing or queued")

    await db.execute(
        update(GeneticAnalysis)
        .where(GeneticAnalysis.id == job_id)
        .values(
            analysis_status="pending",
            progress_percentage=90,
            current_step="regenerating_insights",
            job_logs=None,
        )
    )
    await db.commit()
    return {"detail": f"Insight regeneration queued for job {job_id}"}


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Delete an analysis job and all its associated data (cascade)."""
    result = await db.execute(
        select(GeneticAnalysis).where(GeneticAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")

    # Soft-delete so background tasks see the record is gone
    analysis.analysis_status = 'deleted'
    from sqlalchemy import func as sa_func
    analysis.deleted_at = sa_func.now()
    await db.commit()

    return {"detail": f"Job {job_id} deleted"}


@router.post("/purge-deleted")
async def purge_deleted_analyses(
    older_than_days: int = Query(0, ge=0, description="Hard-delete analyses soft-deleted more than N days ago (0 = all)"),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Queue hard-deletion of soft-deleted analyses as a background worker job."""
    filters = [GeneticAnalysis.deleted_at.isnot(None)]
    if older_than_days > 0:
        cutoff = func.now() - text(f"interval '{int(older_than_days)} days'")
        filters.append(GeneticAnalysis.deleted_at < cutoff)

    result = await db.execute(select(GeneticAnalysis.id).where(*filters))
    ids = [row[0] for row in result.all()]

    if not ids:
        if older_than_days > 0:
            total = await db.execute(
                select(func.count()).select_from(GeneticAnalysis).where(GeneticAnalysis.deleted_at.isnot(None))
            )
            pending = total.scalar() or 0
            if pending:
                return {
                    "detail": f"No analyses deleted more than {older_than_days} days ago. "
                              f"{pending} soft-deleted analyse(s) exist but are newer. Use 0 days to purge all.",
                    "purged": 0,
                }
        return {"detail": "No analyses to purge", "purged": 0}

    from ...db.models import WorkerJob
    job = WorkerJob(
        job_type="purge_deleted",
        status="pending",
        params={"analysis_ids": ids, "older_than_days": older_than_days},
        requested_by=admin.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"Purge job {job.id} queued by admin {admin.id}: {len(ids)} analyses")
    return {
        "job_id": job.id,
        "status": "pending",
        "detail": f"Queued purge of {len(ids)} analyses for background processing",
        "count": len(ids),
    }


@router.get("/jobs/{job_id}/logs")
async def get_job_logs(
    job_id: int,
    last_n: Optional[int] = Query(None, description="Return only the last N log entries"),
    admin: User = Depends(require_admin),
):
    """Get log entries for a specific analysis job.
    
    Returns in-memory logs if the job is still running, otherwise
    falls back to persisted logs from the database.
    """
    from ...services.job_logs import JobLogCollector
    collector = JobLogCollector.get_instance()
    logs = collector.get_logs(job_id, last_n=last_n)
    source = "memory"

    # Fall back to persisted DB logs when in-memory logs are empty
    if not logs:
        from ...db.database import async_session_factory
        async with async_session_factory() as session:
            result = await session.execute(
                select(GeneticAnalysis.job_logs).where(GeneticAnalysis.id == job_id)
            )
            row = result.scalar_one_or_none()
            if row:
                logs = row if isinstance(row, list) else []
                if last_n and logs:
                    logs = logs[-last_n:]
                source = "database"

    return {"job_id": job_id, "count": len(logs), "logs": logs, "source": source}


# --- Worker Job status ---

@router.get("/worker-jobs/{job_id}")
async def get_worker_job_status(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Poll the status of a background worker job."""
    from ...db.models import WorkerJob
    result = await db.execute(
        select(WorkerJob).where(WorkerJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "params": job.params,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/worker-jobs")
async def list_worker_jobs(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """List recent worker jobs (auto_categorize, purge_deleted, etc.)."""
    from ...db.models import WorkerJob
    q = (
        select(WorkerJob, User.email, User.username)
        .outerjoin(User, WorkerJob.requested_by == User.id)
        .order_by(WorkerJob.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        q = q.where(WorkerJob.status == status_filter)
    result = await db.execute(q)
    rows = result.all()
    return [
        {
            "job_id": j.id,
            "job_type": j.job_type,
            "status": j.status,
            "params": j.params,
            "result": j.result,
            "error": j.error,
            "job_logs": j.job_logs,
            "requested_by_email": email,
            "requested_by_username": uname,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j, email, uname in rows
    ]


# --- Annotation sentinel reset ---

