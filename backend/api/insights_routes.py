"""
Smart Insights API routes — LLM-powered genetic analysis insights.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models import GeneticAnalysis
from .auth_routes import get_current_user
from ..services.insights_service import generate_insight, get_llm_status, set_insights_enabled
from ..services.knowledge_graph import build_knowledge_graph

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/status")
async def insights_status(user=Depends(get_current_user)):
    """Return LLM provider configuration status."""
    return get_llm_status()


@router.post("/toggle")
async def toggle_insights(
    enabled: bool,
    user=Depends(get_current_user),
):
    """Enable or disable AI insights for all users. Admin-only."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return set_insights_enabled(enabled)


@router.post("/generate/{section}")
async def generate_section_insight(
    section: str,
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Generate an LLM-powered insight for a dashboard section.
    
    Sections: overview, health, drug_responses, carrier_status, ancestry,
    personality, intelligence, wellness, methylation, detox
    """
    allowed_sections = {
        "overview", "health", "drug_responses", "carrier_status",
        "ancestry", "personality", "intelligence", "wellness",
        "methylation", "detox", "nutrition", "sports",
    }
    if section not in allowed_sections:
        raise HTTPException(status_code=400, detail=f"Invalid section. Allowed: {', '.join(sorted(allowed_sections))}")

    # Get the user's latest analysis
    from sqlalchemy import select, desc
    result = await session.execute(
        select(GeneticAnalysis)
        .where(
            GeneticAnalysis.user_id == user.id,
            GeneticAnalysis.deleted_at.is_(None),
        )
        .order_by(desc(GeneticAnalysis.upload_date))
        .limit(1)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis found")

    # Fetch dashboard data by calling the existing route handler
    from .analysis_routes import get_dashboard_data as _get_dashboard_data
    dashboard_data = await _get_dashboard_data(db=session, current_user=user)

    insight = await generate_insight(analysis.id, section, dashboard_data)
    return insight


@router.get("/knowledge-graph")
async def get_knowledge_graph(
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Build and return the knowledge graph for the user's latest analysis."""
    return await build_knowledge_graph(user.id, session)
