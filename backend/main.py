"""
Genetic Health Analysis Toolkit - FastAPI Backend
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth_routes, analysis_routes, upload_routes, annotation_routes
from .db.database import init_db  # Re-enabled

# Create FastAPI app
app = FastAPI(
    title="Genetic Health Analysis Toolkit",
    description="A comprehensive toolkit for genetic health analysis",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_routes.router)
app.include_router(analysis_routes.router)  # Legacy endpoints
app.include_router(analysis_routes.api_router)  # New API endpoints
app.include_router(upload_routes.router)
app.include_router(annotation_routes.router)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Genetic Health Analysis Toolkit API"}

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    await init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)