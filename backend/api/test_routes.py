"""
Test endpoint to check personality and wellness data availability
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any

from ..db.database import get_session
from ..db.models import PersonalityTrait, WellnessMetric, GeneticAnalysis
from .auth_routes import get_current_user

test_router = APIRouter(prefix="/test", tags=["test"])

@test_router.get("/personality-wellness-data")
async def get_personality_wellness_data(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Test endpoint to check personality and wellness data"""
    
    try:
        user_id = current_user.id
        
        # Get all analyses for this user
        analyses_result = await db.execute(
            select(GeneticAnalysis).where(GeneticAnalysis.user_id == user_id)
        )
        analyses = analyses_result.scalars().all()
        
        # Get personality traits for all analyses
        all_personality_traits = []
        for analysis in analyses:
            personality_result = await db.execute(
                select(PersonalityTrait).where(PersonalityTrait.analysis_id == analysis.id)
            )
            personality_traits = personality_result.scalars().all()
            all_personality_traits.extend(personality_traits)
        
        # Get wellness metrics for all analyses
        all_wellness_metrics = []
        for analysis in analyses:
            wellness_result = await db.execute(
                select(WellnessMetric).where(WellnessMetric.analysis_id == analysis.id)
            )
            wellness_metrics = wellness_result.scalars().all()
            all_wellness_metrics.extend(wellness_metrics)
        
        return {
            "user_id": user_id,
            "total_analyses": len(analyses),
            "personality_traits_count": len(all_personality_traits),
            "wellness_metrics_count": len(all_wellness_metrics),
            "personality_traits": [
                {
                    "trait": trait.trait_name,
                    "tendency": trait.genetic_tendency,
                    "confidence": trait.confidence_level,
                    "insights": trait.behavioral_insights
                }
                for trait in all_personality_traits
            ],
            "wellness_traits": [
                {
                    "metric": metric.metric_name,
                    "predisposition": metric.genetic_predisposition,
                    "score": metric.optimization_score,
                    "recommendations": metric.lifestyle_recommendations
                }
                for metric in all_wellness_metrics
            ]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get test data: {str(e)}"
        )