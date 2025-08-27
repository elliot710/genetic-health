"""
Health check routes for the genetic analysis API.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..db.database import get_session

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health_check():
    """Basic health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "service": "Genetic Health Analysis Toolkit",
        "version": "1.0.0"
    })


@router.get("/database")
async def database_health_check(session: AsyncSession = Depends(get_session)):
    """Health check that includes database connectivity."""
    try:
        # Test database connection
        result = await session.execute(text("SELECT 1"))
        db_status = "connected" if result.scalar() == 1 else "error"
        
        return JSONResponse({
            "status": "healthy",
            "service": "Genetic Health Analysis Toolkit",
            "version": "1.0.0",
            "database": db_status,
            "checks": {
                "database_connection": db_status == "connected"
            }
        })
    except Exception as e:
        return JSONResponse({
            "status": "unhealthy",
            "service": "Genetic Health Analysis Toolkit", 
            "version": "1.0.0",
            "database": "error",
            "error": str(e),
            "checks": {
                "database_connection": False
            }
        }, status_code=503)