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
from datetime import UTC, datetime
from typing import Optional, Set

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
            # regenerate_insights recomputes insights but never touches
            # analysis_status, so mark the job complete here. Without this the
            # analysis sits at 'processing'/90% until a worker restart (the only
            # other place _recover_stale would fix it), and the dashboard won't
            # surface the freshly generated insights.
            async with session_factory() as sess:
                await sess.execute(
                    update(GeneticAnalysis)
                    .where(GeneticAnalysis.id == analysis_id)
                    .values(
                        analysis_status="completed",
                        current_step="completed",
                        progress_percentage=100,
                    )
                )
                await sess.commit()
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
        except Exception as bookkeeping_error:
            logger.error(
                f"[job {analysis_id}] could not record failed status: {bookkeeping_error}",
                exc_info=True,
            )
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
    elif job_type == "etl_vep":
        from backend.services.ensembl_vep_etl import EnsemblVepETL
        p = params or {}
        etl = EnsemblVepETL()
        return await etl.run_import(
            filter_to_known=True,
            force_reload=p.get("force_reload", False),
            chromosomes=p.get("chromosomes"),
        )
    elif job_type == "etl_gnomad":
        from backend.services.gnomad_etl import GnomadETL
        return await GnomadETL().run_full_import()
    elif job_type == "gnomad_build_cadd_cache":
        from backend.services.gnomad_local import get_gnomad_service
        svc = get_gnomad_service()
        if not svc.is_loaded:
            await svc.ensure_loaded()
        return await svc.build_cadd_cache()
    elif job_type == "gnomad_refresh_ancestry_afs":
        from backend.services.gnomad_v2_local import get_gnomad_v2_service
        svc = get_gnomad_v2_service()
        if not svc.is_loaded:
            await svc.ensure_loaded()
        p = params or {}
        if p.get("index_first"):
            index_result = await svc.index_all_files()
            logger.info("gnomAD v2 indexing: %s", index_result)
        return await svc.bulk_refresh_ancestry_panel(fst_threshold=p.get("fst_threshold", 0.70))
    elif job_type == "etl_ensembl":
        from backend.services.ensembl_etl import EnsemblETL
        return await EnsemblETL().run_full_import()
    elif job_type == "etl_1kg":
        from backend.services.thousand_genomes_etl import ThousandGenomesETL
        return await ThousandGenomesETL().run_full_import()
    elif job_type == "etl_gnomad_v2":
        from backend.services.gnomad_v2_etl import GnomadV2ETL
        result = await GnomadV2ETL().run_full_import()
        # Refresh PG count in the singleton so next analysis uses PG path
        from backend.services.gnomad_v2_local import get_gnomad_v2_service
        await get_gnomad_v2_service().refresh_pg_count()
        return result
    elif job_type == "etl_alphafold":
        from backend.scripts.build_alphafold_local import run_etl
        p = params or {}
        result_path = await asyncio.to_thread(run_etl, force=p.get("force", False))
        return {"db_path": str(result_path)}
    elif job_type == "backfill_source":
        return await _backfill_source(params or {}, job_id=job_id)
    else:
        raise ValueError(f"Unknown job type: {job_type}")


async def _backfill_source(params: dict, job_id: Optional[int] = None) -> dict:
    """Backfill annotations for a single source on variants that are missing it.

    Runs entirely inside the worker process so it never blocks the API server.
    Commits in batches of BATCH_SIZE to avoid long-running transactions.
    """
    from sqlalchemy import select, func
    from backend.db.models import SharedVariantAnnotation
    from backend.services.annotation_constants import SOURCE_TO_COLUMN

    source_name = params.get("source_name")
    limit = int(params.get("limit", 5000))

    if not source_name or source_name not in SOURCE_TO_COLUMN:
        raise ValueError(f"Unknown source_name: {source_name!r}")

    col_name = SOURCE_TO_COLUMN[source_name]
    col = getattr(SharedVariantAnnotation, f'{col_name}_data')

    async with session_factory() as sess:
        rows = (await sess.execute(
            select(SharedVariantAnnotation)
            .where(col.is_(None))
            .order_by(SharedVariantAnnotation.usage_count.desc())
            .limit(limit)
        )).scalars().all()

    if not rows:
        return {"source": source_name, "completed": 0, "confirmed_no_data": 0,
                "failed": 0, "total": 0}

    api_service = None
    is_api_source = source_name not in ('alpha_missense', 'clinvar_local', 'ensembl')
    if is_api_source:
        from backend.services.genetic_api_service import OptimizedGeneticAPIService
        api_service = OptimizedGeneticAPIService()
        await api_service.initialize()

    completed = failed = confirmed_no_data = 0
    BATCH_SIZE = 200
    LOG_INTERVAL = 50
    DB_LOG_FLUSH_INTERVAL = 50
    start_ts = asyncio.get_event_loop().time()
    _log_buffer: list[dict] = []

    def _append_log(msg: str) -> None:
        _log_buffer.append({"ts": datetime.now(UTC).strftime("%H:%M:%S"), "level": "INFO", "msg": msg})

    async def _flush_logs_to_db() -> None:
        if job_id is None or not _log_buffer:
            return
        snapshot = list(_log_buffer)
        try:
            async with session_factory() as sess:
                await sess.execute(
                    update(WorkerJob).where(WorkerJob.id == job_id).values(job_logs=snapshot)
                )
                await sess.commit()
        except Exception as bookkeeping_error:
            logger.error(
                f"[worker_job {job_id}] could not flush job logs: {bookkeeping_error}",
                exc_info=True,
            )

    source_type = "API (rate-limited)" if is_api_source else "local"
    start_msg = f"[backfill {source_name}] starting {len(rows)} rows via {source_type}"
    logger.info(start_msg)
    _append_log(start_msg)

    try:
        for idx, ann in enumerate(rows):
            if idx > 0 and idx % LOG_INTERVAL == 0:
                await asyncio.sleep(0)
                elapsed = asyncio.get_event_loop().time() - start_ts
                rate = idx / elapsed if elapsed > 0 else 0
                remaining = len(rows) - idx
                eta_s = int(remaining / rate) if rate > 0 else 0
                eta_str = f"{eta_s // 3600}h {(eta_s % 3600) // 60}m" if eta_s >= 60 else f"{eta_s}s"
                pct = 100 * idx // len(rows)
                progress_msg = (
                    f"[backfill {source_name}] {idx}/{len(rows)} ({pct}%) "
                    f"— updated={completed} no-data={confirmed_no_data} failed={failed} "
                    f"| {rate * 60:.1f}/min | ETA {eta_str}"
                )
                logger.info(progress_msg)
                _append_log(progress_msg)
                if idx % DB_LOG_FLUSH_INTERVAL == 0:
                    await _flush_logs_to_db()

            try:
                if source_name == 'alpha_missense':
                    from backend.api.admin.annotation_sources import _extract_am_coords
                    from backend.utils.alpha_missense import get_alpha_missense_service
                    coords = _extract_am_coords(ann.ensembl_data)
                    if coords:
                        am_svc = get_alpha_missense_service()
                        result_data = am_svc.lookup_comprehensive(*coords)
                        if result_data:
                            ann.alpha_missense_data = result_data
                            completed += 1
                        else:
                            ann.alpha_missense_data = {'found': False, 'confirmed_no_data': True,
                                                       'source': 'alpha_missense', 'reason': 'not_missense'}
                            confirmed_no_data += 1
                    else:
                        ann.alpha_missense_data = {'found': False, 'confirmed_no_data': True,
                                                   'source': 'alpha_missense', 'reason': 'not_missense'}
                        confirmed_no_data += 1

                elif source_name == 'clinvar_local':
                    from backend.services.clinvar_local import get_clinvar_local_service
                    cv_svc = get_clinvar_local_service()
                    if not cv_svc.is_loaded:
                        await cv_svc.ensure_loaded()
                    if cv_svc.is_loaded:
                        result_data = await cv_svc.lookup(ann.rsid)
                        if result_data:
                            ann.clinvar_local_data = result_data
                            completed += 1
                        else:
                            ann.clinvar_local_data = {'found': False, 'confirmed_no_data': True,
                                                      'source': 'clinvar_local'}
                            confirmed_no_data += 1
                    else:
                        failed += 1

                elif source_name == 'ensembl':
                    from backend.services.ensembl_vep_local import get_ensembl_vep_service
                    vep_svc = get_ensembl_vep_service()
                    if await vep_svc.ensure_loaded():
                        result_data = await vep_svc.lookup(ann.rsid)
                        if result_data and result_data.get('found'):
                            ann.ensembl_data = result_data
                            completed += 1
                        else:
                            ann.ensembl_data = {'found': False, 'confirmed_no_data': True, 'source': 'ensembl'}
                            confirmed_no_data += 1
                    else:
                        failed += 1

                else:
                    if idx > 0:
                        await asyncio.sleep(0.5)  # rate limit: 2 req/s max
                    method = getattr(api_service, f'_get_{source_name}_annotation', None)
                    if not method:
                        failed += 1
                        continue
                    result_data = await method(ann.rsid)
                    if result_data and isinstance(result_data, dict) and result_data.get('found', False):
                        setattr(ann, f'{col_name}_data', result_data)
                        completed += 1
                    else:
                        setattr(ann, f'{col_name}_data', {'found': False, 'confirmed_no_data': True,
                                                          'source': source_name})
                        confirmed_no_data += 1

                ann.total_api_calls = (ann.total_api_calls or 0) + 1

            except Exception as e:
                logger.error("[backfill %s] error for %s: %s", source_name, ann.rsid, e)
                failed += 1

            if (idx + 1) % BATCH_SIZE == 0:
                async with session_factory() as sess:
                    for r in rows[max(0, idx + 1 - BATCH_SIZE):idx + 1]:
                        await sess.merge(r)
                    await sess.commit()
                commit_msg = f"[backfill {source_name}] committed batch {idx + 1}/{len(rows)}"
                logger.info(commit_msg)
                _append_log(commit_msg)
                await _flush_logs_to_db()

    finally:
        if api_service:
            await api_service.close()

    committed_count = (len(rows) // BATCH_SIZE) * BATCH_SIZE
    if committed_count < len(rows):
        async with session_factory() as sess:
            for r in rows[committed_count:]:
                await sess.merge(r)
            await sess.commit()

    elapsed_total = asyncio.get_event_loop().time() - start_ts
    done_msg = (
        f"[backfill {source_name}] done in {elapsed_total:.1f}s "
        f"— updated={completed} no-data={confirmed_no_data} failed={failed} / total={len(rows)}"
    )
    logger.info(done_msg)
    _append_log(done_msg)
    await _flush_logs_to_db()
    return {
        "source": source_name,
        "completed": completed,
        "confirmed_no_data": confirmed_no_data,
        "failed": failed,
        "total": len(rows),
    }


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
        except Exception as bookkeeping_error:
            logger.error(
                f"[worker_job {job_id}] could not record failed status: {bookkeeping_error}",
                exc_info=True,
            )
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

    from backend.services.gnomad_v2_local import get_gnomad_v2_service
    gn2 = get_gnomad_v2_service()
    await gn2.ensure_loaded()
    if gn2.is_loaded:
        logger.info(f"gnomAD v2: {gn2.file_count} VCF files, {gn2.indexed_count} tabix-indexed")
    else:
        logger.info("gnomAD v2: no VCF files found")

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
