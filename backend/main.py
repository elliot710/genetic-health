"""
Genetic Health Analysis Toolkit - FastAPI Backend
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth_routes, upload_routes, annotation_routes, variant_routes
from .api.analysis_routes import router as analysis_router
from .api.admin_routes import router as admin_router
from .db.database import init_db
from .services.analysis_queue import get_analysis_queue

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
    
    # Start the analysis queue processor
    analysis_queue = get_analysis_queue()
    await analysis_queue.start()
    print("🚀 Analysis queue processor started")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown of analysis queue"""
    analysis_queue = get_analysis_queue()
    await analysis_queue.stop()
    print("🛑 Analysis queue processor stopped")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)