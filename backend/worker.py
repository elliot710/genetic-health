"""
Analysis Worker Process
=======================
Runs as a *completely separate process* from the FastAPI web server (see the
``worker`` service in docker-compose.yml).

Architecture rationale
----------------------
All previous attempts to run analysis inside the FastAPI process (background
tasks, asyncio.create_task, asyncio.to_thread, etc.) eventually led to the
same problem: the analysis touches Python-level CPU-heavy code (dict
construction, scoring, generator logic) that holds the GIL and blocks the
main event loop, making the site unresponsive.

This worker process:
  - Has its **own** event loop, completely isolated from FastAPI.
  - Has its **own** database connection pool (NullPool — fresh connections per
    job, no cross-loop sharing).
  - Polls the database every POLL_INTERVAL seconds for analyses in
    ``queued`` or ``processing`` status.
  - Runs up to MAX_CONCURRENT jobs concurrently using asyncio.gather (each
    job is already I/O-bound at the outermost level; the GIL is not held long
    by any single call once we are inside async DB/network I/O).
  - The FastAPI server never executes any analysis code.  It just writes a
    row to ``genetic_analyses`` and returns 200.

Status flow
-----------
  pending / processing (stale) → picked up by worker → processing → completed / failed
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Set

from sqlalchemy import select, text, update
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("worker")

# ── Config ─────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/genetic_health_db",
)
POLL_INTERVAL = float(os.getenv("WORKER_POLL_INTERVAL", "2"))   # seconds
MAX_CONCURRENT = int(os.getenv("WORKER_MAX_CONCURRENT", "2"))   # parallel jobs

# ── Database (NullPool — no cross-loop connection sharing) ─────────────────
engine = create_async_engine(DATABASE_URL, poolclass=NullPool, echo=False, future=True)
session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# ── Inject session factory so all services use this process's engine ───────
# This MUST happen before any backend service is imported.
from backend.db.database import _session_factory_ctx  # noqa: E402
_session_factory_ctx.set(session_factory)

# Backend service imports (after the ContextVar override is in place)
from backend.db.models import GeneticAnalysis, WorkerJob  # noqa: E402
from backend.services.analysis_service import ComprehensiveAnalysisService  # noqa: E402
from backend.services.job_logs import JobLogHandler  # noqa: E402

# ── Per-worker job log handler (same as in main.py) ────────────────────────
_job_handler = JobLogHandler()
_job_handler.setLevel(logging.INFO)
for _name in [
    "backend.services.analysis_service",
    "backend.services.genetic_api_service",
    "backend.services.ensembl_vep_local",
    "backend.services.clinvar_local",
    "backend.services.gnomad_local",
    "backend.services.thousand_genomes_local",
    "backend.services.local_annotation",
    "backend.services.shared_annotation_service",
]:
    logging.getLogger(_name).addHandler(_job_handler)


# ── Active job tracking ─────────────────────────────────────────────────────
_active: Set[int] = set()           # active analysis IDs
_active_jobs: Set[int] = set()      # active WorkerJob IDs
_shutdown = False


async def _flush_logs_to_db(analysis_id: int, interval: int = 5) -> None:
    """Periodically persist in-memory job logs to the DB so the admin UI can show live progress."""
    from backend.services.job_logs import JobLogCollector
    collector = JobLogCollector.get_instance()
    while True:
        await asyncio.sleep(interval)
        try:
            logs = collector.get_logs(analysis_id)
            if logs:
                async with session_factory() as sess:
                    await sess.execute(
                        update(GeneticAnalysis)
                        .where(GeneticAnalysis.id == analysis_id)
                        .values(job_logs=logs)
                    )
                    await sess.commit()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug(f"[job {analysis_id}] log flush error: {exc}")


async def _run_one(analysis_id: int, user_id: int, regen_only: bool = False) -> None:
    """Run a single analysis job and update DB status."""
    mode = "regen" if regen_only else "full"
    logger.info(f"[job {analysis_id}] starting ({mode}, user {user_id})")
    service = ComprehensiveAnalysisService(user_id=user_id)
    flush_task = asyncio.create_task(_flush_logs_to_db(analysis_id))
    try:
        if regen_only:
            await service.regenerate_insights(analysis_id)
        else:
            await service.process_analysis(analysis_id)
        logger.info(f"[job {analysis_id}] completed")
    except Exception as e:
        logger.error(f"[job {analysis_id}] failed: {e}", exc_info=True)
        try:
            async with session_factory() as sess:
                if regen_only:
                    # Restore to completed so user can retry
                    await sess.execute(
                        update(GeneticAnalysis)
                        .where(GeneticAnalysis.id == analysis_id)
                        .values(analysis_status="completed", current_step="completed", progress_percentage=100)
                    )
                else:
                    await sess.execute(
                        update(GeneticAnalysis)
                        .where(GeneticAnalysis.id == analysis_id)
                        .values(
                            analysis_status="failed",
                            current_step=f"failed: {str(e)[:200]}",
                        )
                    )
                await sess.commit()
        except Exception:
            pass
    finally:
        flush_task.cancel()
        try:
            await flush_task
        except asyncio.CancelledError:
            pass
        _active.discard(analysis_id)


# ── Generic WorkerJob handlers ──────────────────────────────────────────────

async def _execute_job(job_id: int, job_type: str, params: dict) -> dict:
    """Route a WorkerJob to the appropriate handler. Returns result dict."""
    if job_type == "auto_categorize":
        from backend.services.auto_categorizer import AutoCategorizer
        cat_list = (params or {}).get("categories")
        categorizer = AutoCategorizer()
        return await categorizer.run(categories=cat_list)
    elif job_type == "purge_deleted":
        return await _purge_deleted_analyses(params)
    else:
        raise ValueError(f"Unknown job type: {job_type}")


async def _purge_deleted_analyses(params: dict) -> dict:
    """Hard-delete soft-deleted analyses.

    Uses TRUNCATE + re-insert for large purges (>50% of table),
    otherwise direct DELETE per analysis.
    """
    ids = params.get("analysis_ids", [])
    if not ids:
        return {"purged": 0, "total": 0}

    # Check if TRUNCATE approach is faster (when deleting >50% of rows)
    async with session_factory() as sess:
        total_result = await sess.execute(text("SELECT count(*) FROM analysis_variants"))
        total_rows = total_result.scalar() or 0
        delete_result = await sess.execute(
            text("SELECT count(*) FROM analysis_variants WHERE analysis_id = ANY(:ids)"),
            {"ids": ids},
        )
        delete_rows = delete_result.scalar() or 0

    if total_rows > 0 and delete_rows > total_rows * 0.5:
        return await _purge_via_truncate(ids, delete_rows, total_rows)
    else:
        return await _purge_via_delete(ids)


async def _purge_via_truncate(ids: list[int], delete_rows: int, total_rows: int) -> dict:
    """Fast purge: save active rows, TRUNCATE, re-insert, delete parents."""
    keep_rows = total_rows - delete_rows
    logger.info(f"[purge] TRUNCATE approach: removing {delete_rows} rows, keeping {keep_rows}")
    async with session_factory() as sess:
        await sess.execute(text("SET LOCAL work_mem = '256MB'"))
        # Save rows to keep
        await sess.execute(text(
            "CREATE TEMP TABLE _keep_av ON COMMIT DROP AS "
            "SELECT * FROM analysis_variants WHERE analysis_id != ALL(:ids)"
        ), {"ids": ids})
        await sess.execute(text(
            "CREATE TEMP TABLE _keep_va ON COMMIT DROP AS "
            "SELECT * FROM variant_annotations WHERE analysis_id != ALL(:ids)"
        ), {"ids": ids})
        # TRUNCATE (instant, cascades to variant_annotations)
        await sess.execute(text("TRUNCATE analysis_variants CASCADE"))
        # Re-insert
        await sess.execute(text("INSERT INTO analysis_variants SELECT * FROM _keep_av"))
        await sess.execute(text("INSERT INTO variant_annotations SELECT * FROM _keep_va"))
        # Delete parent analyses (CASCADE handles small insight tables)
        await sess.execute(text("DELETE FROM genetic_analyses WHERE id = ANY(:ids)"), {"ids": ids})
        await sess.commit()
    logger.info(f"[purge] completed: {len(ids)} analyses purged via TRUNCATE")
    return {"purged": len(ids), "total": len(ids), "method": "truncate"}


async def _purge_via_delete(ids: list[int]) -> dict:
    """Standard purge: direct DELETE per analysis (for small purges)."""
    purged = 0
    for aid in ids:
        try:
            async with session_factory() as sess:
                await sess.execute(text("SET LOCAL synchronous_commit = off"))
                await sess.execute(text("SET LOCAL work_mem = '256MB'"))
                await sess.execute(
                    text("DELETE FROM variant_annotations WHERE analysis_id = :aid"),
                    {"aid": aid},
                )
                await sess.execute(
                    text("DELETE FROM analysis_variants WHERE analysis_id = :aid"),
                    {"aid": aid},
                )
                await sess.execute(
                    text("DELETE FROM genetic_analyses WHERE id = :aid"),
                    {"aid": aid},
                )
                await sess.commit()
            purged += 1
            logger.info(f"[purge] deleted analysis {aid} ({purged}/{len(ids)})")
        except Exception as e:
            logger.error(f"[purge] failed to delete analysis {aid}: {e}")
    return {"purged": purged, "total": len(ids), "method": "delete"}


async def _run_job(job_id: int, job_type: str, params: dict) -> None:
    """Run a single WorkerJob and update its DB row."""
    logger.info(f"[worker_job {job_id}] starting ({job_type})")
    try:
        result = await _execute_job(job_id, job_type, params)
        async with session_factory() as sess:
            await sess.execute(
                update(WorkerJob)
                .where(WorkerJob.id == job_id)
                .values(
                    status="completed",
                    result=result,
                    completed_at=func.now(),
                )
            )
            await sess.commit()
        logger.info(f"[worker_job {job_id}] completed")
    except Exception as e:
        logger.error(f"[worker_job {job_id}] failed: {e}", exc_info=True)
        try:
            async with session_factory() as sess:
                await sess.execute(
                    update(WorkerJob)
                    .where(WorkerJob.id == job_id)
                    .values(
                        status="failed",
                        error=str(e)[:2000],
                        completed_at=func.now(),
                    )
                )
                await sess.commit()
        except Exception:
            pass
    finally:
        _active_jobs.discard(job_id)


async def _poll_jobs() -> None:
    """Find pending WorkerJobs and dispatch them."""
    total_active = len(_active) + len(_active_jobs)
    if total_active >= MAX_CONCURRENT:
        return

    slots = MAX_CONCURRENT - total_active
    try:
        async with session_factory() as sess:
            rows = (
                await sess.execute(
                    select(WorkerJob.id, WorkerJob.job_type, WorkerJob.params)
                    .where(
                        WorkerJob.status == "pending",
                        WorkerJob.id.not_in(_active_jobs) if _active_jobs else True,
                    )
                    .order_by(WorkerJob.created_at)
                    .limit(slots)
                )
            ).all()

            if not rows:
                return

            ids = [r.id for r in rows]
            await sess.execute(
                update(WorkerJob)
                .where(WorkerJob.id.in_(ids))
                .values(status="processing", started_at=func.now())
            )
            await sess.commit()
    except Exception as e:
        logger.error(f"WorkerJob poll failed: {e}")
        return

    for row in rows:
        _active_jobs.add(row.id)
        logger.info(f"[worker_job {row.id}] dispatched ({row.job_type})")
        asyncio.create_task(_run_job(row.id, row.job_type, row.params or {}))


async def _recover_stale_jobs() -> None:
    """Reset any WorkerJobs stuck in 'processing' back to 'pending'."""
    try:
        async with session_factory() as sess:
            result = await sess.execute(
                select(WorkerJob.id).where(WorkerJob.status == "processing")
            )
            stale = result.all()
            if not stale:
                return
            ids = [r.id for r in stale]
            await sess.execute(
                update(WorkerJob)
                .where(WorkerJob.id.in_(ids))
                .values(status="pending", started_at=None)
            )
            await sess.commit()
            logger.info(f"Recovered {len(stale)} stale worker job(s)")
    except Exception as e:
        logger.error(f"WorkerJob recovery failed: {e}")


# ── Analysis polling ────────────────────────────────────────────────────────

async def _poll() -> None:
    """Find pending analyses and dispatch them as asyncio tasks."""
    if len(_active) >= MAX_CONCURRENT:
        return

    slots = MAX_CONCURRENT - len(_active)

    try:
        async with session_factory() as sess:
            rows = (
                await sess.execute(
                    select(
                        GeneticAnalysis.id,
                        GeneticAnalysis.user_id,
                        GeneticAnalysis.current_step,
                    )
                    .where(
                        GeneticAnalysis.analysis_status.in_(["pending", "queued"]),
                        GeneticAnalysis.deleted_at.is_(None),
                        GeneticAnalysis.id.not_in(_active) if _active else True,
                    )
                    .order_by(GeneticAnalysis.id)
                    .limit(slots)
                )
            ).all()

            if not rows:
                return

            # Mark as processing before releasing the session so another
            # worker instance (if any) does not pick the same job.
            ids = [r.id for r in rows]
            await sess.execute(
                update(GeneticAnalysis)
                .where(GeneticAnalysis.id.in_(ids))
                .values(analysis_status="processing")
            )
            await sess.commit()
    except Exception as e:
        logger.error(f"Poll query failed: {e}")
        return

    for row in rows:
        _active.add(row.id)
        # Detect regen-only jobs from the current_step flag set by the API
        regen_only = bool(row.current_step and "regenerating_insights" in (row.current_step or ""))
        logger.info(f"[job {row.id}] dispatched (regen_only={regen_only})")
        asyncio.create_task(_run_one(row.id, row.user_id, regen_only=regen_only))


async def _recover_stale() -> None:
    """On startup: reset any stale 'processing' jobs (from a prior worker crash)
    back to 'pending' so they are picked up cleanly."""
    try:
        async with session_factory() as sess:
            result = await sess.execute(
                select(GeneticAnalysis.id, GeneticAnalysis.user_id, GeneticAnalysis.current_step)
                .where(
                    GeneticAnalysis.analysis_status.in_(["processing"]),
                    GeneticAnalysis.deleted_at.is_(None),
                )
            )
            stale = result.all()
            if not stale:
                return
            for aid, uid, step in stale:
                # Don't touch regen jobs — reset them to completed so users can retry
                if step and "regenerat" in (step or "").lower():
                    logger.info(f"[job {aid}] stale regen job — resetting to completed")
                    await sess.execute(
                        update(GeneticAnalysis)
                        .where(GeneticAnalysis.id == aid)
                        .values(analysis_status="completed", current_step="completed", progress_percentage=100)
                    )
                else:
                    logger.info(f"[job {aid}] stale processing job — re-queuing")
                    await sess.execute(
                        update(GeneticAnalysis)
                        .where(GeneticAnalysis.id == aid)
                        .values(analysis_status="pending")
                    )
            await sess.commit()
            logger.info(f"Recovered {len(stale)} stale job(s)")
    except Exception as e:
        logger.error(f"Startup recovery failed: {e}")


async def _preload_local_services() -> None:
    """Preload compute-heavy local services before processing any jobs.

    These are all read-once, cache-forever operations.  Doing them at startup
    means the first job doesn't incur a cold-load penalty inline.
    """
    from backend.services.datasource_utils import log_data_source_availability
    log_data_source_availability()

    from backend.services.clinvar_local import get_clinvar_local_service
    cv = get_clinvar_local_service()
    ok = await cv.ensure_loaded()
    logger.info(f"ClinVar PG: {'%d rows' % cv.variant_count if ok else 'empty — run ETL'}")

    from backend.services.gnomad_local import get_gnomad_service
    gn = get_gnomad_service()
    ok = await gn.ensure_loaded()
    logger.info(f"gnomAD PG: {'%d variants' % (gn._variant_count or 0) if ok else 'empty — run ETL'}")

    from backend.services.gnomad_local import get_gnomad_cache_service
    gc = get_gnomad_cache_service()
    ok = await gc.ensure_loaded()
    if ok:
        logger.info(f"gnomAD cache: {gc.variant_count} variants cached")
    elif gc.has_tabix_files:
        logger.info(f"gnomAD CADD: {len(gc._tsv_files or [])} indexed TSV file(s) available — tabix queries enabled")
    else:
        logger.info("gnomAD cache: no CADD TSV files found — position queries unavailable")

    from backend.services.thousand_genomes_local import get_thousand_genomes_service
    tkg = get_thousand_genomes_service()
    ok = await tkg.ensure_loaded()
    logger.info(f"1000 Genomes PG: {'%d variants' % tkg.variant_count if ok else 'empty — run ETL'}")

    # VEP SQLite load can take several minutes — run in background so it's ready
    # for the first job without blocking the poll loop.
    from backend.services.ensembl_vep_local import get_ensembl_vep_service
    vep = get_ensembl_vep_service()
    async def _load_vep():
        ok = await vep.ensure_loaded()
        if ok and vep._db is not None:
            logger.info(f"Ensembl VEP: {vep.variant_count} variants loaded from SQLite cache")
        elif ok and vep._vcf_available:
            logger.info("Ensembl VEP: no SQLite cache — tabix position queries available")
        else:
            logger.info("Ensembl VEP: no VCF files found — annotation unavailable")
    asyncio.create_task(_load_vep())
    logger.info("Ensembl VEP: loading in background...")


async def _main() -> None:
    global _shutdown

    def _handle_signal(*_):
        global _shutdown
        logger.info("Shutdown signal received")
        _shutdown = True

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, _handle_signal)
    loop.add_signal_handler(signal.SIGINT, _handle_signal)

    logger.info(
        f"Analysis worker started — poll={POLL_INTERVAL}s, max_concurrent={MAX_CONCURRENT}"
    )

    await _recover_stale()
    await _recover_stale_jobs()
    await _preload_local_services()

    while not _shutdown:
        await _poll()
        await _poll_jobs()
        await asyncio.sleep(POLL_INTERVAL)

    # Wait for in-flight jobs
    if _active or _active_jobs:
        logger.info(f"Waiting for {len(_active)} analysis + {len(_active_jobs)} worker jobs to finish...")
        while _active or _active_jobs:
            await asyncio.sleep(1)

    await engine.dispose()
    logger.info("Worker stopped")


if __name__ == "__main__":
    # Ensure the backend package is importable (worker runs from /app)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    asyncio.run(_main())
