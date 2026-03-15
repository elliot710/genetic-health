"""
Genetic Health Analysis Toolkit - FastAPI Backend
"""
import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth_routes, upload_routes, annotation_routes, variant_routes
from .api.analysis_routes import router as analysis_router
from .api.admin_routes import router as admin_router
from .api.insights_routes import router as insights_router
from .db.database import init_db
from .services.analysis_queue import get_analysis_queue

# Configure logging — show INFO from our services
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

# Create FastAPI app
app = FastAPI(
    title="Genetic Health Analysis Toolkit",
    description="A comprehensive toolkit for genetic health analysis",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001"],
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

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Genetic Health Analysis Toolkit API"}

@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and monitoring"""
    try:
        # Test database connection
        from .db.database import async_session_factory
        async with async_session_factory() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        
        return {
            "status": "healthy",
            "message": "Genetic Health Analysis Toolkit API is running",
            "database": "connected",
            "version": "1.0.0"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "message": "Database connection failed",
            "error": str(e)
        }

@app.on_event("startup")
async def startup_event():
    """Initialize database and analysis queue on startup"""
    await init_db()
    
    # Install per-job log handler on analysis-related loggers
    from .services.job_logs import JobLogHandler
    job_handler = JobLogHandler()
    job_handler.setLevel(logging.INFO)
    for name in ['backend.services.analysis_service', 'backend.services.genetic_api_service']:
        logging.getLogger(name).addHandler(job_handler)
    
    # Start the analysis queue processor
    analysis_queue = get_analysis_queue()
    await analysis_queue.start()
    print("🚀 Analysis queue processor started")

    # Detect and re-queue stale analyses left in 'processing' state
    # (e.g. from a server restart or container hot-reload)
    try:
        from .db.database import async_session_factory
        from sqlalchemy import select, update as sa_update
        from .db.models import GeneticAnalysis
        async with async_session_factory() as session:
            result = await session.execute(
                select(GeneticAnalysis.id, GeneticAnalysis.user_id, GeneticAnalysis.current_step)
                .where(GeneticAnalysis.analysis_status == 'processing')
            )
            stale = result.all()
            if stale:
                for analysis_id, user_id, step in stale:
                    print(f"🔄 Re-queuing stale analysis {analysis_id} (was at step: {step})")
                    await analysis_queue.enqueue_analysis(analysis_id, user_id)
                print(f"🔄 Re-queued {len(stale)} stale analyses for resume")
            else:
                print("✅ No stale analyses found")
    except Exception as e:
        print(f"⚠️ Stale analysis check failed: {e}")

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
        print(f"✅ gnomAD PG: {gnomad_svc.variant_count} variants, {gnomad_svc.constraint_count} gene constraints")
    else:
        print("⚠️ gnomAD PG: table empty — run ETL import via admin panel")

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

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown of analysis queue"""
    analysis_queue = get_analysis_queue()
    await analysis_queue.stop()
    print("🛑 Analysis queue processor stopped")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)