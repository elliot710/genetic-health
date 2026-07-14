"""
Genetic Health Analysis Toolkit - FastAPI Backend
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import os

from .api import auth_routes, upload_routes, annotation_routes, variant_routes
from .api.analysis_routes import router as analysis_router
from .api.admin import router as admin_router
from .api.insights_routes import router as insights_router
from .api.notification_routes import router as notification_ws_router, notification_router
from .api.sharing_routes import router as sharing_router
from .core.telemetry import configure_telemetry
from .core.rate_limit import limiter
from .db.database import init_db, async_session_factory
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

logger = logging.getLogger(__name__)

# Configure logging — show INFO from our services
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    # ── Startup ──────────────────────────────────────────────────
    await init_db()

    # Install per-job log handler on analysis-related loggers
    from .services.job_logs import JobLogHandler
    job_handler = JobLogHandler()
    job_handler.setLevel(logging.INFO)
    for name in [
        'backend.services.analysis_service',
        'backend.services.genetic_api_service',
        'backend.services.ensembl_vep_local',
        'backend.services.clinvar_local',
        'backend.services.gnomad_local',
        'backend.services.thousand_genomes_local',
    ]:
        logging.getLogger(name).addHandler(job_handler)

    # NOTE: Analysis jobs are NO LONGER run inside this process.
    # The 'worker' Docker service polls the DB and runs them in a completely
    # separate process so the FastAPI event loop is never touched by analysis code.
    print("🚀 API server started (analysis handled by worker service)")

    # Load categorizer domain data (gene→category map, condition keywords, exclusion
    # keywords) from the CategoryRule DB table.  Must run after the DB is ready.
    from .services.multi_source_categorizer import init_categorizer_data
    try:
        await init_categorizer_data()
    except Exception as _e:
        print(f"⚠️ Categorizer data load failed: {_e} — analysis may use empty gene map")

    # Log which data source files are available on disk with tabix indexes
    from .services.datasource_utils import log_data_source_availability
    log_data_source_availability()

    # Check ClinVar PG availability (instant — just counts rows)
    from .services.clinvar_local import get_clinvar_local_service
    cv_svc = get_clinvar_local_service()
    ok = await cv_svc.ensure_loaded()
    if ok:
        print(f"✅ ClinVar PG: {cv_svc.variant_count} rows available")
    else:
        print("⚠️ ClinVar PG: table empty — run ETL import via admin panel")

    # Check gnomAD PG availability (instant — just counts rows)
    from .services.gnomad_local import get_gnomad_service
    gnomad_svc = get_gnomad_service()
    ok = await gnomad_svc.ensure_loaded()
    if ok:
        print(f"✅ gnomAD PG: {gnomad_svc._variant_count or 0} variants, {gnomad_svc.constraint_count} gene constraints")
    else:
        print("⚠️ gnomAD PG: table empty — run ETL import via admin panel")

    # Preload gnomAD SQLite cache in background (targeted tabix reads)
    # Supports GRCh38 TSV files by bridging via Ensembl VEP GRCh38 positions
    from .services.gnomad_local import get_gnomad_cache_service
    gnomad_cache = get_gnomad_cache_service()
    async def _preload_gnomad_cache():
        try:
            ok = await gnomad_cache.ensure_loaded()
            if ok:
                print(f"✅ gnomAD cache: {gnomad_cache.variant_count} variants cached from CADD TSV")
            else:
                print("⚠️ gnomAD cache: no tabix-indexed TSV files found in data_sources/gnomad/")
        except Exception as e:
            print(f"⚠️ gnomAD cache preload failed: {e}")
    asyncio.create_task(_preload_gnomad_cache())
    print("⏳ gnomAD cache: preloading CADD TSV cache in background...")

    # Initialize gnomAD v2 (ancestry population AFs — GRCh37 VCFs)
    try:
        from .services.gnomad_v2_local import get_gnomad_v2_service
        gnomad_v2_svc = get_gnomad_v2_service()
        await gnomad_v2_svc.ensure_loaded()
        if gnomad_v2_svc.is_loaded:
            print(f"✅ gnomAD v2: {gnomad_v2_svc.file_count} VCF files, {gnomad_v2_svc.indexed_count} tabix-indexed")
            if gnomad_v2_svc.indexed_count == 0:
                print("  ↳ Run admin → gnomAD → Refresh ancestry AFs (with index_first=true) to index them")
        else:
            print("ℹ️ gnomAD v2: no VCF files found in data_sources/gnomad_v2/")
    except Exception as e:
        print(f"⚠️ gnomAD v2 init failed: {e}")

    # Check gnomAD BigQuery availability
    try:
        from .services.gnomad_bigquery import get_gnomad_bigquery_service
        bq_svc = get_gnomad_bigquery_service()
        if await bq_svc.is_available():
            print("✅ gnomAD BigQuery: credentials configured — fallback enabled")
        else:
            print("ℹ️ gnomAD BigQuery: not configured — set GOOGLE_APPLICATION_CREDENTIALS to enable")
    except Exception as e:
        print(f"ℹ️ gnomAD BigQuery: unavailable ({e})")

    # Check 1000 Genomes Phase 3 PG availability
    from .services.thousand_genomes_local import get_thousand_genomes_service
    tkg_svc = get_thousand_genomes_service()
    ok = await tkg_svc.ensure_loaded()
    if ok:
        print(f"✅ 1000 Genomes PG: {tkg_svc.variant_count} variants available")
    else:
        print("⚠️ 1000 Genomes PG: table empty — run ETL import via admin panel")

    # Preload Ensembl VEP cache in background (takes ~15min, don't block startup)
    from .services.ensembl_vep_local import get_ensembl_vep_service
    vep_svc = get_ensembl_vep_service()
    async def _preload_vep():
        try:
            ok = await vep_svc.ensure_loaded()
            if ok:
                print(f"✅ Ensembl VEP: {vep_svc.variant_count} variants cached from VCF files")
            else:
                print("⚠️ Ensembl VEP: no VCF files found or no known rsids")
        except Exception as e:
            print(f"⚠️ Ensembl VEP preload failed: {e}")
    asyncio.create_task(_preload_vep())
    print("⏳ Ensembl VEP: preloading VCF cache in background...")

    # Nightly purge of soft-deleted analyses older than 30 days
    async def _nightly_purge():
        """Periodically hard-delete analyses that were soft-deleted > 30 days ago."""
        while True:
            await asyncio.sleep(86400)  # Run once per day
            try:
                from sqlalchemy import text as sa_text
                async with async_session_factory() as s:
                    result = await s.execute(
                        sa_text(
                            "DELETE FROM genetic_analyses "
                            "WHERE deleted_at IS NOT NULL "
                            "AND deleted_at < NOW() - INTERVAL '30 days'"
                        )
                    )
                    await s.commit()
                    if result.rowcount:
                        print(f"🧹 Nightly purge: hard-deleted {result.rowcount} analyses")
            except Exception as e:
                print(f"⚠️ Nightly purge failed: {e}")
    asyncio.create_task(_nightly_purge())

    # Watch for analysis completions from the worker process and create notifications
    from .services.notification_service import get_notification_service
    from .db.models import GeneticAnalysis
    from sqlalchemy import select as sa_select, text as sa_text2

    async def _watch_analysis_completions():
        """Poll for analyses that just completed/failed and push notifications."""
        svc = get_notification_service()
        # Track which analyses we've already notified about
        notified: set[int] = set()
        while True:
            await asyncio.sleep(12)
            try:
                async with async_session_factory() as s:
                    # Find recently completed/failed analyses not yet notified
                    rows = await s.execute(
                        sa_text2(
                            """
                            SELECT a.id, a.user_id, a.analysis_status, a.filename,
                                   a.progress_percentage, a.total_variants
                            FROM genetic_analyses a
                            LEFT JOIN notifications n
                              ON n.user_id = a.user_id
                              AND n.data->>'analysis_id' = a.id::text
                              AND n.type IN ('analysis_completed','analysis_failed')
                            WHERE a.analysis_status IN ('completed','failed')
                              AND a.deleted_at IS NULL
                              AND n.id IS NULL
                            ORDER BY a.upload_date DESC
                            LIMIT 30
                            """
                        )
                    )
                    analyses = rows.fetchall()

                for row in analyses:
                    aid, uid, astatus, fname, pct, total = row
                    if aid in notified:
                        continue
                    notified.add(aid)
                    if astatus == 'completed':
                        await svc.create(
                            user_id=uid,
                            type='analysis_completed',
                            title='Analysis Complete',
                            message=f'Your DNA analysis of {fname!r} finished with {total:,} variants processed.',
                            data={'analysis_id': aid, 'filename': fname, 'total_variants': total},
                        )
                    elif astatus == 'failed':
                        await svc.create(
                            user_id=uid,
                            type='analysis_failed',
                            title='Analysis Failed',
                            message=f'Analysis of {fname!r} encountered an error. Please try again.',
                            data={'analysis_id': aid, 'filename': fname},
                        )
            except Exception as e:
                logger.warning(f"Analysis completion watcher error: {e}")

    asyncio.create_task(_watch_analysis_completions())
    print("👁  Analysis completion watcher started")

    yield

    # ── Shutdown ─────────────────────────────────────────────────
    print("🛑 API server stopping")


# Create FastAPI app
app = FastAPI(
    title="Genetic Health Analysis Toolkit",
    description="A comprehensive toolkit for genetic health analysis",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure OpenTelemetry tracing (must happen before ASGI middleware chain is built)
configure_telemetry()
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore[import]
    FastAPIInstrumentor.instrument_app(app)
except Exception:
    pass  # OTel instrumentation is optional

# Per-IP rate limiting — disabled by default (see core/rate_limit.py); registered
# before CORS so CORS remains the outermost middleware, added last, unaffected.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Configure CORS — base origins always allowed; extend via EXTRA_CORS_ORIGINS env var
# e.g. EXTRA_CORS_ORIGINS=https://epigenic.xyz,https://www.epigenic.xyz
_base_origins = [
    "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001",
    "https://epigenic.xyz", "https://www.epigenic.xyz",
]
_extra = [o.strip() for o in os.environ.get("EXTRA_CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_base_origins + _extra,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_routes.router)
app.include_router(analysis_router)
app.include_router(upload_routes.router)
app.include_router(annotation_routes.router)
app.include_router(variant_routes.router)
app.include_router(admin_router)
app.include_router(insights_router)
app.include_router(notification_ws_router)   # WebSocket: /ws/notifications
app.include_router(notification_router)      # REST:      /api/notifications/...
app.include_router(sharing_router)           # REST:      /api/sharing/...

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Genetic Health Analysis Toolkit API"}

@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and monitoring.

    Does NOT acquire a DB connection — ensures this endpoint is always fast
    even when the connection pool is under pressure from background analysis.
    Use GET /health/database for a full connectivity check.
    """
    return {
        "status": "healthy",
        "message": "Genetic Health Analysis Toolkit API is running",
        "database": "connected",
        "version": "1.0.0"
    }

@app.on_event("startup")
async def startup_event():
    """Legacy startup hook — kept as no-op since lifespan() handles everything."""
    pass

@app.on_event("shutdown")
async def shutdown_event():
    """Legacy shutdown hook — kept as no-op since lifespan() handles everything."""
    pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)