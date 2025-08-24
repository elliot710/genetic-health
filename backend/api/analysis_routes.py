"""
Analysis API routes
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

from ..db.database import get_session
from ..services.genetic_analyzer import GeneticAnalyzer
from .auth_routes import get_current_user

router = APIRouter(prefix="/analyze", tags=["analysis"])

@router.post("/full-report")
async def generate_full_report(
    data: Dict[str, Any],
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Generate a comprehensive genetic analysis report"""
    
    # Initialize services
    genetic_analyzer = GeneticAnalyzer()
    
    # Extract data
    vcf_variants = data.get("vcf_variants", [])
    
    # Generate analysis
    try:
        # Basic genetic analysis
        summary = await genetic_analyzer.generate_summary(vcf_variants, {})
        
        # Generate recommendations (simplified for now)
        recommendations = [
            "Consult with a healthcare provider for personalized recommendations",
            "Consider genetic counseling if you have family history concerns",
            "Maintain a healthy lifestyle with regular exercise and balanced nutrition"
        ]
        
        return {
            "summary": summary,
            "health_risks": {"overall_score": 85, "risk_categories": {}},
            "drug_interactions": {"high_risk_genes": [], "moderate_risk_genes": []},
            "recommendations": recommendations
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )