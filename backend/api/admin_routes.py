"""
Admin API routes for user management and panel marker configuration.
"""
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, text, update
from typing import List, Optional

from ..db.database import get_session
from ..db.models import User, GeneticAnalysis

# Imported before `router` is constructed so the require_admin guard can be
# baked into the router itself (see dependencies= below) -- this makes
# backend.api.admin's aggregate a plain re-export of this router rather than
# a second APIRouter that .include_router()'s a copy: with two objects, the
# copy step captures whatever routes existed at that exact import moment,
# which is empty if something imports admin_routes.py directly before the
# admin package (circular import, order-dependent). One router, mutated in
# place by every decorator below, has no such moment to get wrong.
from .admin.schemas import (
    require_admin,
    LATENCY_P95_THRESHOLD_SECONDS,
    AdminJobResponse,
    AdminJobsSummary,
    AdminJobsLatency,
    CategoryRuleCreate,
    CategoryRuleUpdate,
)
from .admin.users import router as _users_router
from .admin.variant_mappings import router as _variant_mappings_router
from .admin.discoveries import router as _discoveries_router
from .admin.annotation_sources import router as _annotation_sources_router
# Re-exported so backend/worker.py's `from backend.api.admin_routes import
# _extract_am_coords` keeps resolving after the annotation-source split.
from .admin.annotation_sources import _extract_am_coords  # noqa: F401

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])
logger = logging.getLogger(__name__)

router.include_router(_users_router)
router.include_router(_variant_mappings_router)
router.include_router(_discoveries_router)
router.include_router(_annotation_sources_router)


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

    from ..db.models import WorkerJob
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
    from ..services.job_logs import JobLogCollector
    collector = JobLogCollector.get_instance()
    logs = collector.get_logs(job_id, last_n=last_n)
    source = "memory"

    # Fall back to persisted DB logs when in-memory logs are empty
    if not logs:
        from ..db.database import async_session_factory
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


# ======================================================================
# ClinVar ETL endpoints
# ======================================================================

@router.get("/clinvar-etl/status")
async def clinvar_etl_status(admin: User = Depends(require_admin)):
    """Get current ClinVar import status (row counts + file availability)."""
    from ..services.clinvar_etl import ClinVarETL
    etl = ClinVarETL()
    return await etl.get_import_status()


@router.get("/clinvar-etl/progress")
async def clinvar_etl_progress(admin: User = Depends(require_admin)):
    """Return live progress of the running (or last) ClinVar ETL import."""
    from ..services.clinvar_etl import get_etl_progress
    return get_etl_progress()


@router.post("/clinvar-etl/import")
async def clinvar_etl_import(admin: User = Depends(require_admin)):
    """Kick off a ClinVar ETL import in the background and return immediately.
    Poll GET /clinvar-etl/progress for live status."""
    from ..services.clinvar_etl import ClinVarETL, get_etl_progress

    # Reject concurrent imports
    prog = get_etl_progress()
    if prog.get("running"):
        return {"status": "already_running", "step": prog.get("step"), "pct": prog.get("pct")}

    async def _run():
        etl = ClinVarETL()
        try:
            await etl.run_full_import()
            # Refresh the ClinVar local service cache count
            from ..services.clinvar_local import get_clinvar_local_service
            cv_svc = get_clinvar_local_service()
            await cv_svc.ensure_loaded()
        except Exception:
            pass  # errors are recorded in _etl_progress

    import asyncio as _asyncio
    _asyncio.create_task(_run())
    return {"status": "started"}


# ======================================================================
# GWAS Catalog ETL endpoints
# ======================================================================

@router.get("/gwas-catalog-etl/progress")
async def gwas_catalog_etl_progress(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_session)):
    from ..services.gwas_catalog_etl import get_etl_progress
    from sqlalchemy import text
    prog = get_etl_progress()
    if not prog.get("running"):
        result = await db.execute(text("SELECT COUNT(*) FROM gwas_catalog_associations"))
        prog = dict(prog)
        prog["rows"] = result.scalar() or 0
    return prog


@router.post("/gwas-catalog-etl/import")
async def gwas_catalog_etl_import(admin: User = Depends(require_admin)):
    from ..services.gwas_catalog_etl import run_gwas_etl, get_etl_progress
    prog = get_etl_progress()
    if prog.get("running"):
        return {"status": "already_running", "step": prog.get("step"), "pct": prog.get("pct")}

    async def _run():
        try:
            await run_gwas_etl()
            from ..services.gwas_catalog_local import get_gwas_catalog_service
            await get_gwas_catalog_service().ensure_loaded()
        except Exception:
            pass

    import asyncio as _asyncio
    _asyncio.create_task(_run())
    return {"status": "started"}


# ======================================================================
# ClinGen ETL endpoints
# ======================================================================

@router.get("/clingen-etl/progress")
async def clingen_etl_progress(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_session)):
    from ..services.clingen_etl import get_etl_progress
    from sqlalchemy import text
    prog = get_etl_progress()
    if not prog.get("running"):
        result = await db.execute(text("SELECT COUNT(*) FROM clingen_gene_validity"))
        prog = dict(prog)
        prog["rows"] = result.scalar() or 0
    return prog


@router.post("/clingen-etl/import")
async def clingen_etl_import(admin: User = Depends(require_admin)):
    from ..services.clingen_etl import run_clingen_etl, get_etl_progress
    prog = get_etl_progress()
    if prog.get("running"):
        return {"status": "already_running", "step": prog.get("step"), "pct": prog.get("pct")}

    async def _run():
        try:
            await run_clingen_etl()
            from ..services.clingen_local import get_clingen_service
            await get_clingen_service().ensure_loaded()
        except Exception:
            pass

    import asyncio as _asyncio
    _asyncio.create_task(_run())
    return {"status": "started"}


# ======================================================================
# Open Targets test endpoint
# ======================================================================

@router.get("/open-targets/test")
async def open_targets_test(admin: User = Depends(require_admin)):
    from ..services.open_targets_service import get_open_targets_service
    svc = get_open_targets_service()
    try:
        result = await svc.lookup_by_gene("BRCA1")
        return {
            "status": "ok",
            "reachable": True,
            "test_gene": "BRCA1",
            "found": result.get("found", False),
            "association_count": len(result.get("associations", [])),
            "top_disease": result.get("top_disease"),
            "max_score": result.get("max_score"),
        }
    except Exception as exc:
        return {"status": "error", "reachable": False, "error": str(exc)}


# ======================================================================
# Category Rules endpoints
# ======================================================================

@router.get("/category-rules")
async def list_category_rules(
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """List all category rules, optionally filtered by category."""
    from ..db.models import CategoryRule
    q = select(CategoryRule).order_by(CategoryRule.category, CategoryRule.priority)
    if category:
        q = q.where(CategoryRule.category == category)
    result = await db.execute(q)
    rules = result.scalars().all()
    return [
        {
            "id": r.id, "category": r.category, "rule_type": r.rule_type,
            "rule_value": r.rule_value, "priority": r.priority,
            "is_active": r.is_active, "mapping_data_template": r.mapping_data_template,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rules
    ]


@router.post("/category-rules")
async def create_category_rule(
    rule: CategoryRuleCreate,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Create a new category rule."""
    from ..db.models import CategoryRule
    new_rule = CategoryRule(
        category=rule.category,
        rule_type=rule.rule_type,
        rule_value=rule.rule_value,
        priority=rule.priority,
        is_active=rule.is_active,
        mapping_data_template=rule.mapping_data_template,
    )
    db.add(new_rule)
    await db.commit()
    await db.refresh(new_rule)
    return {"id": new_rule.id, "category": new_rule.category, "rule_type": new_rule.rule_type}


@router.put("/category-rules/{rule_id}")
async def update_category_rule(
    rule_id: int,
    update: CategoryRuleUpdate,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Update a category rule."""
    from ..db.models import CategoryRule
    result = await db.execute(select(CategoryRule).where(CategoryRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await db.commit()
    return {"detail": "Rule updated"}


@router.delete("/category-rules/{rule_id}")
async def delete_category_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Delete a category rule."""
    from ..db.models import CategoryRule
    result = await db.execute(select(CategoryRule).where(CategoryRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.commit()
    return {"detail": "Rule deleted"}


@router.post("/category-rules/seed")
async def seed_rules(
    force: bool = Query(False, description="Delete existing rules before seeding"),
    admin: User = Depends(require_admin),
):
    """Seed default category rules (idempotent unless force=true)."""
    from ..services.auto_categorizer import seed_category_rules
    return await seed_category_rules(force=force)


# ======================================================================
# gnomAD ETL endpoints
# ======================================================================

@router.get("/gnomad-etl/status")
async def gnomad_etl_status(admin: User = Depends(require_admin)):
    """Get current gnomAD import status (row counts + file availability)."""
    from ..services.gnomad_etl import GnomadETL
    etl = GnomadETL()
    return await etl.get_import_status()


@router.post("/gnomad-etl/import")
async def gnomad_etl_import(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch gnomAD ETL to the background worker and return immediately."""
    from ..db.models import WorkerJob
    job = WorkerJob(job_type="etl_gnomad", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"gnomAD ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"gnomAD ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


@router.post("/gnomad/build-cadd-cache")
async def gnomad_build_cadd_cache(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Queue a worker job to build the gnomAD CADD SQLite cache via sequential scan.

    After this completes, all analysis gnomAD lookups hit SQLite (sub-second)
    instead of doing 609K per-variant tabix seeks (~14 min).
    """
    from ..db.models import WorkerJob
    job = WorkerJob(job_type="gnomad_build_cadd_cache", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"gnomAD CADD cache build job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"gnomAD CADD cache build queued as worker job #{job.id}"}


@router.post("/gnomad/refresh-ancestry-afs")
async def gnomad_refresh_ancestry_afs(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
    fst_threshold: float = 0.70,
    index_first: bool = False,
):
    """Queue a worker job to refresh ancestry_aims_panel with gnomAD v2 AFs.

    Reads from local GRCh37 VCF files — no network calls needed.
    Replaces the data previously loaded via the gnomAD GraphQL API.

    index_first=true will create .tbi indexes for any unindexed VCF files first.
    """
    from ..db.models import WorkerJob
    job = WorkerJob(
        job_type="gnomad_refresh_ancestry_afs",
        status="pending",
        params={"fst_threshold": fst_threshold, "index_first": index_first},
        requested_by=admin.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"gnomAD ancestry AF refresh job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"gnomAD ancestry AF refresh queued as worker job #{job.id}"}


@router.get("/gnomad/v2-status")
async def gnomad_v2_status(admin: User = Depends(require_admin)):
    """Get gnomAD v2 VCF file availability and index status."""
    from ..services.gnomad_v2_local import get_gnomad_v2_service
    svc = get_gnomad_v2_service()
    if not svc.is_loaded:
        await svc.ensure_loaded()
    return {
        "file_count": svc.file_count,
        "indexed_count": svc.indexed_count,
        "pg_rows": svc._pg_count,
        "ready": svc.has_pg_data or svc.indexed_count > 0,
    }


# ======================================================================
# gnomAD v2 exome ETL endpoints
# ======================================================================

@router.get("/gnomad-v2-etl/status")
async def gnomad_v2_etl_status(admin: User = Depends(require_admin)):
    """Get current gnomAD v2 exome import status (row counts + file availability)."""
    from ..services.gnomad_v2_etl import GnomadV2ETL
    etl = GnomadV2ETL()
    return await etl.get_import_status()


@router.post("/gnomad-v2-etl/import")
async def gnomad_v2_etl_import(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch gnomAD v2 exome ETL to the background worker and return immediately."""
    from ..db.models import WorkerJob
    # Prevent duplicate pending/processing jobs
    existing = (await db.execute(
        select(WorkerJob).where(
            WorkerJob.job_type == "etl_gnomad_v2",
            WorkerJob.status.in_(["pending", "processing"]),
        )
    )).scalars().first()
    if existing:
        return {"job_id": existing.id, "status": existing.status,
                "detail": f"gnomAD v2 ETL already {existing.status} (job #{existing.id})"}
    job = WorkerJob(job_type="etl_gnomad_v2", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"gnomAD v2 ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"gnomAD v2 ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


# ======================================================================
# AlphaFold ETL endpoints
# ======================================================================

@router.get("/alphafold-etl/status")
async def alphafold_etl_status(admin: User = Depends(require_admin)):
    """Get AlphaFold local data status (SQLite DB protein count)."""
    from ..services.alphafold_local import get_alphafold_local_service
    svc = get_alphafold_local_service()
    if not svc.available:
        svc.ensure_loaded()
    return {
        "alphafold_proteins": svc.protein_count,
        "loaded": svc.available,
        "db_exists": svc._db_path.exists(),
        "db_path": str(svc._db_path),
    }


@router.post("/alphafold-etl/import")
async def alphafold_etl_import(
    force: bool = Query(False, description="Rebuild even if DB already exists"),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch AlphaFold ETL (download + build SQLite) to the background worker."""
    from ..db.models import WorkerJob
    # Prevent duplicate pending/processing jobs
    existing = (await db.execute(
        select(WorkerJob).where(
            WorkerJob.job_type == "etl_alphafold",
            WorkerJob.status.in_(["pending", "processing"]),
        )
    )).scalars().first()
    if existing:
        return {"job_id": existing.id, "status": existing.status,
                "detail": f"AlphaFold ETL already {existing.status} (job #{existing.id})"}
    job = WorkerJob(
        job_type="etl_alphafold",
        status="pending",
        params={"force": force},
        requested_by=admin.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"AlphaFold ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"AlphaFold ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


@router.get("/ensembl-etl/status")
async def ensembl_etl_status(admin: User = Depends(require_admin)):
    """Get current Ensembl gene model import status (row counts + file availability)."""
    import os
    from pathlib import Path
    from sqlalchemy import text as sa_text
    from ..db.database import async_session_factory
    async with async_session_factory() as session:
        total = (await session.execute(sa_text("SELECT COUNT(*) FROM ensembl_genes"))).scalar() or 0
        protein_coding = (await session.execute(
            sa_text("SELECT COUNT(*) FROM ensembl_genes WHERE biotype = 'protein_coding'")
        )).scalar() or 0
        chromosomes = (await session.execute(
            sa_text("SELECT COUNT(DISTINCT chromosome) FROM ensembl_genes")
        )).scalar() or 0
    data_dir = Path(os.environ.get(
        "ENSEMBL_DATA_DIR",
        os.path.join(os.path.dirname(__file__), "..", "..", "data_sources", "ensembl", "homo_sapiens"),
    ))
    fasta_base = data_dir / "fasta"
    cdna_path = fasta_base / "cdna" / "Homo_sapiens.GRCh38.cdna.all.fa.gz"
    ncrna_path = fasta_base / "ncrna" / "Homo_sapiens.GRCh38.ncrna.fa.gz"
    if not cdna_path.exists():
        cdna_path = data_dir / "cdna" / "Homo_sapiens.GRCh38.cdna.all.fa.gz"
    if not ncrna_path.exists():
        ncrna_path = data_dir / "ncrna" / "Homo_sapiens.GRCh38.ncrna.fa.gz"
    return {
        "ensembl_genes": total,
        "protein_coding_genes": protein_coding,
        "chromosomes": chromosomes,
        "cdna_file_exists": cdna_path.exists(),
        "ncrna_file_exists": ncrna_path.exists(),
    }


@router.post("/ensembl-etl/import")
async def ensembl_etl_import(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch Ensembl gene model ETL to the background worker and return immediately."""
    from ..db.models import WorkerJob
    job = WorkerJob(job_type="etl_ensembl", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"Ensembl ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"Ensembl ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


# ======================================================================
# 1000 Genomes Phase 3 ETL endpoints
# ======================================================================

@router.get("/1kg-etl/status")
async def thousand_genomes_etl_status(admin: User = Depends(require_admin)):
    """Get current 1000 Genomes import status (row count + file availability)."""
    from ..services.thousand_genomes_etl import ThousandGenomesETL
    etl = ThousandGenomesETL()
    return await etl.get_import_status()


@router.post("/1kg-etl/import")
async def thousand_genomes_etl_import(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch 1000 Genomes ETL to the background worker and return immediately."""
    from ..db.models import WorkerJob
    job = WorkerJob(job_type="etl_1kg", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"1000 Genomes ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"1000 Genomes ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


# ======================================================================
# gnomAD BigQuery backfill endpoints
# ======================================================================

@router.get("/gnomad-bigquery/status")
async def gnomad_bigquery_status(admin: User = Depends(require_admin)):
    """Get BigQuery backfill status — enrichment progress, BQ availability."""
    from ..services.gnomad_bigquery import GnomadBackfillService
    svc = GnomadBackfillService()
    return await svc.get_backfill_status()


@router.post("/gnomad-bigquery/backfill")
async def gnomad_bigquery_backfill(
    batch_size: int = Query(200, ge=10, le=1000, description="Variants per BigQuery query"),
    max_variants: int = Query(10000, ge=100, le=1000000, description="Max variants to process"),
    chromosome: Optional[str] = Query(None, description="Only backfill this chromosome (1-22, X, Y)"),
    admin: User = Depends(require_admin),
):
    """Run BigQuery backfill — enrich local CADD variants with population AFs.
    This queries Google BigQuery and may incur costs. Uses 10 GB byte budget per query."""
    from ..services.gnomad_bigquery import GnomadBackfillService
    svc = GnomadBackfillService()
    return await svc.backfill(
        batch_size=batch_size,
        max_variants=max_variants,
        chromosome=chromosome,
    )


# ======================================================================
# Auto-categorization endpoint
# ======================================================================

@router.post("/auto-categorize")
async def run_auto_categorize(
    categories: Optional[str] = Query(None, description="Comma-separated category filter"),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Queue auto-categorization as a background worker job.

    Returns immediately with a job ID that can be polled via
    GET /api/admin/jobs/{job_id}.
    """
    from ..db.models import WorkerJob
    cat_list = [c.strip() for c in categories.split(",")] if categories else None
    job = WorkerJob(
        job_type="auto_categorize",
        status="pending",
        params={"categories": cat_list} if cat_list else None,
        requested_by=admin.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"Auto-categorize job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": "Queued for worker processing"}


# --- Worker Job status ---

@router.get("/worker-jobs/{job_id}")
async def get_worker_job_status(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Poll the status of a background worker job."""
    from ..db.models import WorkerJob
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
    from ..db.models import WorkerJob
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
