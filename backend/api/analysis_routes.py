"""
Analysis API routes
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Dict, Any

from ..db.database import get_session
from ..db.models import GeneticAnalysis, GeneticVariant, HealthRisk, DrugResponse
from ..services.genetic_analyzer import GeneticAnalyzer
from ..services.analysis_queue import queue_analysis, get_queue_status
from ..services.analysis_job import AnalysisJob  # Keep for legacy functions
from .auth_routes import get_current_user
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Legacy router (keeping for compatibility)
router = APIRouter(prefix="/analyze", tags=["analysis"])

# New API router with proper REST structure
api_router = APIRouter(prefix="/api/analysis", tags=["analysis-api"])

# Background task executor
executor = ThreadPoolExecutor(max_workers=2)

@router.post("/start/{analysis_id}")
async def start_analysis(
    analysis_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Start background analysis job for a specific analysis"""
    
    try:
        # Verify the analysis exists and belongs to the user
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found or access denied"
            )
        
        # Check if analysis is already in progress (but allow restarting completed ones)
        current_status = getattr(analysis, 'analysis_status', None)
        if current_status == 'processing':
            return {
                "message": f"Analysis is already {current_status}",
                "analysis_id": analysis_id,
                "status": current_status,
                "progress_percentage": getattr(analysis, 'progress_percentage', 0) or 0
            }
        
        # Reset progress for restart if it was completed
        if current_status == 'completed':
            await db.execute(
                update(GeneticAnalysis)
                .where(GeneticAnalysis.id == analysis_id)
                .values(
                    analysis_status="processing",
                    progress_percentage=0,
                    current_step="Restarting analysis...",
                    processed_variants=0
                )
            )
            await db.commit()
            # Refresh the analysis object after update
            await db.refresh(analysis)
        
        # Queue the analysis job for background processing
        success = await queue_analysis(analysis_id, current_user.id, priority=1)
        
        if not success:
            # Analysis is already running or user has reached limit
            result = await db.execute(
                select(GeneticAnalysis).where(
                    GeneticAnalysis.id == analysis_id,
                    GeneticAnalysis.user_id == current_user.id
                )
            )
            analysis = result.scalar_one_or_none()
            current_status = analysis.analysis_status if analysis else 'unknown'
            
            return {
                "message": "Analysis could not be queued - may already be running or user limit reached",
                "analysis_id": analysis_id,
                "status": current_status,
                "note": "Check queue status for more details"
            }
        
        return {
            "message": "Analysis started successfully",
            "analysis_id": analysis_id,
            "status": "processing",
            "progress_percentage": 0,
            "note": "Use the /progress/{analysis_id} endpoint to track progress"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start analysis: {str(e)}"
        )

@router.get("/queue-status")
async def get_analysis_queue_status(
    current_user = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get current analysis queue status"""
    
    try:
        queue_status = get_queue_status()
        
        # Filter running analyses to only show user's own analyses
        user_running_analyses = [
            analysis for analysis in queue_status.get("running_analyses", [])
            if analysis["user_id"] == current_user.id
        ]
        
        return {
            "queue_size": queue_status.get("queue_size", 0),
            "total_running_jobs": queue_status.get("running_jobs", 0),
            "max_concurrent": queue_status.get("max_concurrent", 3),
            "user_running_analyses": user_running_analyses,
            "user_running_count": queue_status.get("user_running_counts", {}).get(current_user.id, 0),
            "user_limit": 2  # Max concurrent analyses per user
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get queue status: {str(e)}"
        )

@router.get("/progress/{analysis_id}")
async def get_analysis_progress(
    analysis_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Get real-time analysis progress for a specific analysis"""
    
    try:
        # Get the analysis record with progress tracking
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found or access denied"
            )
        
        return {
            "analysis_id": analysis.id,
            "status": analysis.analysis_status or 'pending',
            "progress_percentage": analysis.progress_percentage or 0,
            "current_step": analysis.current_step or 'Initializing...',
            "total_variants": analysis.total_variants or 0,
            "processed_variants": analysis.processed_variants or 0,
            "estimated_completion": analysis.estimated_completion.isoformat() if analysis.estimated_completion is not None else None,
            "upload_date": analysis.upload_date.isoformat(),
            "filename": analysis.filename,
            "file_type": analysis.file_type,
            "analysis_results": analysis.analysis_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analysis progress: {str(e)}"
        )

@router.get("/dashboard-data")
async def get_dashboard_data(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Get comprehensive dashboard data for the current user"""
    
    try:
        user_id = current_user.id
        
        # Get all analyses for this user
        analyses_result = await db.execute(
            select(GeneticAnalysis).where(GeneticAnalysis.user_id == user_id).order_by(GeneticAnalysis.upload_date.desc())
        )
        analyses = analyses_result.scalars().all()
        
        if not analyses:
            return {
                "summary": {
                    "total_variants": 0,
                    "analysis_id": None,
                    "processed_at": None,
                    "uploaded_files": 0
                },
                "real_data": {
                    "variants": []
                },
                "health_risks": {
                    "overall_score": 85,
                    "risk_categories": {}
                },
                "drug_interactions": {
                    "high_risk_genes": []
                },
                "insights": [],
                "analysis_results": {
                    "insights": []
                }
            }
        
        # Get the most recent analysis
        latest_analysis = analyses[0]
        
        # Get all variants for all analyses
        all_variants = []
        total_variants = 0
        
        for analysis in analyses:
            variants_result = await db.execute(
                select(GeneticVariant).where(GeneticVariant.analysis_id == analysis.id)
            )
            variants = variants_result.scalars().all()
            total_variants += len(variants)
            
            # Add analysis info to variants
            for variant in variants:
                all_variants.append({
                    "rsid": variant.rsid,
                    "chromosome": variant.chromosome,
                    "position": variant.position,
                    "ref_allele": variant.ref_allele,
                    "alt_allele": variant.alt_allele,
                    "genotype": variant.genotype,
                    "quality": variant.quality,
                    "filter_status": variant.filter_status,
                    "analysis_id": variant.analysis_id,
                    "info": variant.info or {}
                })
        
        # Get health risks for all analyses
        all_health_risks = []
        for analysis in analyses:
            health_risks_result = await db.execute(
                select(HealthRisk).where(HealthRisk.analysis_id == analysis.id)
            )
            health_risks = health_risks_result.scalars().all()
            all_health_risks.extend(health_risks)
        
        # Get drug responses for all analyses
        all_drug_responses = []
        for analysis in analyses:
            drug_responses_result = await db.execute(
                select(DrugResponse).where(DrugResponse.analysis_id == analysis.id)
            )
            drug_responses = drug_responses_result.scalars().all()
            all_drug_responses.extend(drug_responses)
        
        # Process health risks into categories
        risk_categories = {}
        overall_risk_scores = []
        
        for risk in all_health_risks:
            condition = risk.condition.lower()
            risk_score = 0
            
            # Convert risk levels to numeric scores
            if risk.risk_level == 'high':
                risk_score = 85
            elif risk.risk_level == 'moderate':
                risk_score = 65
            elif risk.risk_level == 'low':
                risk_score = 35
            
            # Group by condition type
            if 'diabetes' in condition or 'glucose' in condition:
                risk_categories['diabetes'] = {"score": risk_score, "risk_level": risk.risk_level}
            elif 'cardiovascular' in condition or 'heart' in condition or 'cardiac' in condition:
                risk_categories['cardiovascular'] = {"score": risk_score, "risk_level": risk.risk_level}
            elif 'alzheimer' in condition or 'dementia' in condition or 'cognitive' in condition:
                risk_categories['alzheimer'] = {"score": risk_score, "risk_level": risk.risk_level}
            elif 'cancer' in condition:
                risk_categories['cancer'] = {"score": risk_score, "risk_level": risk.risk_level}
            else:
                # Generic condition
                risk_categories[condition.replace(' ', '_')] = {"score": risk_score, "risk_level": risk.risk_level}
            
            overall_risk_scores.append(risk_score)
        
        # Calculate overall health score (inverse of average risk)
        if overall_risk_scores:
            avg_risk = sum(overall_risk_scores) / len(overall_risk_scores)
            overall_score = max(20, 100 - avg_risk)  # Ensure minimum score of 20
        else:
            overall_score = 85  # Default good score when no risks identified
        
        # Get high-risk genes from drug responses
        high_risk_genes = list(set([dr.gene for dr in all_drug_responses if dr.response_type in ['poor', 'ultrarapid']]))
        
        # Generate insights
        insights = []
        
        if all_health_risks:
            high_risk_count = len([r for r in all_health_risks if r.risk_level == 'high'])
            if high_risk_count > 0:
                insights.append(f"Found {high_risk_count} high-risk genetic variant(s) requiring attention")
        
        if all_drug_responses:
            poor_metabolizers = len([dr for dr in all_drug_responses if dr.response_type == 'poor'])
            if poor_metabolizers > 0:
                insights.append(f"Identified {poor_metabolizers} gene(s) affecting drug metabolism")
        
        if total_variants > 0:
            with_rsid = len([v for v in all_variants if v.get('rsid') and v['rsid'] != '-'])
            coverage = round((with_rsid / total_variants) * 100)
            insights.append(f"{coverage}% of variants have reference IDs for clinical analysis")
        
        if not insights:
            insights = ["Analysis complete - check individual categories for detailed results"]
        
        return {
            "summary": {
                "total_variants": total_variants,
                "analysis_id": latest_analysis.id,
                "processed_at": latest_analysis.upload_date.isoformat(),
                "uploaded_files": len(analyses),
                "data_sources": [analysis.filename for analysis in analyses],
                "upload_info": {
                    "filename": latest_analysis.filename,
                    "file_type": latest_analysis.file_type
                }
            },
            "real_data": {
                "variants": all_variants,
                "upload_result": {
                    "filename": latest_analysis.filename
                }
            },
            "health_risks": {
                "overall_score": round(overall_score),
                "risk_categories": risk_categories,
                "details": [
                    {
                        "condition": risk.condition,
                        "risk_level": risk.risk_level,
                        "risk_score": risk.risk_score,
                        "recommendations": risk.recommendations
                    }
                    for risk in all_health_risks
                ]
            },
            "drug_interactions": {
                "high_risk_genes": high_risk_genes,
                "details": [
                    {
                        "gene": dr.gene,
                        "drug": dr.drug,
                        "response_type": dr.response_type,
                        "recommendations": dr.recommendations,
                        "variants_involved": dr.variants_involved
                    }
                    for dr in all_drug_responses
                ]
            },
            "insights": insights,
            "analysis_results": {
                "insights": insights,
                "total_analyses": len(analyses),
                "latest_analysis_date": latest_analysis.upload_date.isoformat()
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dashboard data: {str(e)}"
        )

@router.get("/latest")
async def get_latest_analysis(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Get the latest analysis for the current user"""
    
    try:
        user_id = current_user.id
        
        # Get the most recent analysis
        result = await db.execute(
            select(GeneticAnalysis)
            .where(GeneticAnalysis.user_id == user_id)
            .order_by(GeneticAnalysis.upload_date.desc())
            .limit(1)
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No analysis found for user"
            )
        
        # Get variants for this analysis
        variants_result = await db.execute(
            select(GeneticVariant).where(GeneticVariant.analysis_id == analysis.id)
        )
        variants = variants_result.scalars().all()
        
        # Get health risks
        health_risks_result = await db.execute(
            select(HealthRisk).where(HealthRisk.analysis_id == analysis.id)
        )
        health_risks = health_risks_result.scalars().all()
        
        # Get drug responses
        drug_responses_result = await db.execute(
            select(DrugResponse).where(DrugResponse.analysis_id == analysis.id)
        )
        drug_responses = drug_responses_result.scalars().all()
        
        return {
            "analysis": {
                "id": analysis.id,
                "filename": analysis.filename,
                "file_type": analysis.file_type,
                "upload_date": analysis.upload_date.isoformat(),
                "results": analysis.analysis_results
            },
            "variants": [
                {
                    "rsid": v.rsid,
                    "chromosome": v.chromosome,
                    "position": v.position,
                    "ref_allele": v.ref_allele,
                    "alt_allele": v.alt_allele,
                    "genotype": v.genotype,
                    "quality": v.quality,
                    "filter_status": v.filter_status,
                    "info": v.info
                }
                for v in variants
            ],
            "health_risks": [
                {
                    "condition": hr.condition,
                    "risk_level": hr.risk_level,
                    "risk_score": hr.risk_score,
                    "associated_variants": hr.associated_variants,
                    "recommendations": hr.recommendations
                }
                for hr in health_risks
            ],
            "drug_responses": [
                {
                    "gene": dr.gene,
                    "drug": dr.drug,
                    "response_type": dr.response_type,
                    "recommendations": dr.recommendations,
                    "variants_involved": dr.variants_involved
                }
                for dr in drug_responses
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get latest analysis: {str(e)}"
        )

@router.get("/health-risks")
async def get_health_risks(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Get health risk assessments for the current user"""
    
    try:
        user_id = current_user.id
        
        # Get all analyses for this user
        analyses_result = await db.execute(
            select(GeneticAnalysis).where(GeneticAnalysis.user_id == user_id)
        )
        analyses = analyses_result.scalars().all()
        
        if not analyses:
            return {"health_risks": [], "summary": {"total_risks": 0, "high_risk": 0, "moderate_risk": 0, "low_risk": 0}}
        
        # Get health risks for all analyses
        all_health_risks = []
        for analysis in analyses:
            health_risks_result = await db.execute(
                select(HealthRisk).where(HealthRisk.analysis_id == analysis.id)
            )
            health_risks = health_risks_result.scalars().all()
            all_health_risks.extend(health_risks)
        
        # Format health risks
        formatted_risks = []
        risk_counts = {"high": 0, "moderate": 0, "low": 0}
        
        for risk in all_health_risks:
            formatted_risks.append({
                "condition": risk.condition,
                "risk_level": risk.risk_level,
                "risk_score": risk.risk_score,
                "associated_variants": risk.associated_variants,
                "recommendations": risk.recommendations,
                "analysis_id": risk.analysis_id
            })
            risk_counts[risk.risk_level] = risk_counts.get(risk.risk_level, 0) + 1
        
        return {
            "health_risks": formatted_risks,
            "summary": {
                "total_risks": len(formatted_risks),
                "high_risk": risk_counts["high"],
                "moderate_risk": risk_counts["moderate"], 
                "low_risk": risk_counts["low"]
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get health risks: {str(e)}"
        )

@router.get("/drug-responses")
async def get_drug_responses(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Get drug response predictions for the current user"""
    
    try:
        user_id = current_user.id
        
        # Get all analyses for this user
        analyses_result = await db.execute(
            select(GeneticAnalysis).where(GeneticAnalysis.user_id == user_id)
        )
        analyses = analyses_result.scalars().all()
        
        if not analyses:
            return {"drug_responses": [], "summary": {"total_responses": 0, "poor_metabolizers": 0, "normal_metabolizers": 0}}
        
        # Get drug responses for all analyses
        all_drug_responses = []
        for analysis in analyses:
            drug_responses_result = await db.execute(
                select(DrugResponse).where(DrugResponse.analysis_id == analysis.id)
            )
            drug_responses = drug_responses_result.scalars().all()
            all_drug_responses.extend(drug_responses)
        
        # Format drug responses
        formatted_responses = []
        response_counts = {"poor": 0, "intermediate": 0, "normal": 0, "ultrarapid": 0}
        
        for response in all_drug_responses:
            formatted_responses.append({
                "gene": response.gene,
                "drug": response.drug,
                "response_type": response.response_type,
                "recommendations": response.recommendations,
                "variants_involved": response.variants_involved,
                "analysis_id": response.analysis_id
            })
            response_counts[response.response_type] = response_counts.get(response.response_type, 0) + 1
        
        return {
            "drug_responses": formatted_responses,
            "summary": {
                "total_responses": len(formatted_responses),
                "poor_metabolizers": response_counts["poor"],
                "normal_metabolizers": response_counts["normal"],
                "intermediate_metabolizers": response_counts["intermediate"],
                "ultrarapid_metabolizers": response_counts["ultrarapid"]
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get drug responses: {str(e)}"
        )

@router.post("/stop/{analysis_id}")
async def stop_analysis(
    analysis_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Stop a running analysis"""
    
    try:
        # Verify the analysis exists and belongs to the user
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found or access denied"
            )
        
        # Update analysis status to stopped
        await db.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(
                analysis_status="stopped",
                current_step="Analysis stopped by user"
            )
        )
        await db.commit()
        
        return {
            "message": "Analysis stopped successfully",
            "analysis_id": analysis_id,
            "status": "stopped"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop analysis: {str(e)}"
        )

@router.post("/resume/{analysis_id}")
async def resume_analysis(
    analysis_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Resume a stopped analysis"""
    
    try:
        # Verify the analysis exists and belongs to the user
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found or access denied"
            )
        
        # Check if analysis can be resumed
        if analysis.analysis_status not in ['stopped', 'failed', 'pending']:
            return {
                "message": f"Analysis cannot be resumed from status: {analysis.analysis_status}",
                "analysis_id": analysis_id,
                "status": analysis.analysis_status
            }
        
        # Resume the analysis job in background
        analysis_job = AnalysisJob(user_id=current_user.id)
        
        async def run_analysis():
            """Background task to resume the analysis"""
            try:
                result = await analysis_job.process_analysis(analysis_id)
                return result
            except Exception as e:
                # Update analysis status to failed
                async for session in get_session():
                    await session.execute(
                        update(GeneticAnalysis)
                        .where(
                            GeneticAnalysis.id == analysis_id,
                            GeneticAnalysis.user_id == current_user.id  # Ensure user ownership
                        )
                        .values(analysis_status="failed", current_step=f"Error: {str(e)}")
                    )
                    await session.commit()
                raise e
        
        asyncio.create_task(run_analysis())
        
        return {
            "message": "Analysis resumed successfully",
            "analysis_id": analysis_id,
            "status": "processing",
            "progress_percentage": analysis.progress_percentage or 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume analysis: {str(e)}"
        )

@router.post("/reset-status/{analysis_id}")
async def reset_analysis_status(
    analysis_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Reset analysis status based on actual completion state"""
    
    try:
        # Verify the analysis exists and belongs to the user
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found or access denied"
            )
        
        # Check if analysis has results and should be marked as completed
        has_results = bool(
            analysis.analysis_results and 
            isinstance(analysis.analysis_results, dict) and
            analysis.analysis_results.get('status') == 'completed'
        )
        
        # Check if progress is 100% (should be completed regardless of results)
        progress_complete = bool((analysis.progress_percentage or 0) >= 100)
        
        if has_results or progress_complete:
            # Analysis is actually completed, update status
            await db.execute(
                update(GeneticAnalysis)
                .where(GeneticAnalysis.id == analysis_id)
                .values(
                    analysis_status="completed",
                    progress_percentage=100,
                    current_step="Analysis completed"
                )
            )
            await db.commit()
            
            return {
                "message": "Analysis status corrected to completed",
                "analysis_id": analysis_id,
                "status": "completed",
                "progress_percentage": 100
            }
        else:
            # Analysis is incomplete, can be resumed
            await db.execute(
                update(GeneticAnalysis)
                .where(GeneticAnalysis.id == analysis_id)
                .values(
                    analysis_status="stopped",
                    current_step="Ready to resume"
                )
            )
            await db.commit()
            
            return {
                "message": "Analysis status reset to stopped - ready to resume",
                "analysis_id": analysis_id,
                "status": "stopped",
                "progress_percentage": analysis.progress_percentage or 0
            }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset analysis status: {str(e)}"
        )

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


# NEW API ENDPOINTS WITH PROPER REST STRUCTURE AND PAUSE/RESUME

@api_router.post("/{analysis_id}/start")
async def start_analysis_v2(
    analysis_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Start or restart background analysis job for a specific analysis (API v2)"""
    
    try:
        # Verify the analysis exists and belongs to the user
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found or access denied"
            )
        
        # Check current status
        current_status = getattr(analysis, 'analysis_status', None)
        
        # If already processing, return current state
        if current_status == 'processing':
            return {
                "message": f"Analysis is already {current_status}",
                "analysis_id": analysis_id,
                "status": current_status,
                "progress_percentage": getattr(analysis, 'progress_percentage', 0) or 0
            }
        
        # Reset progress for restart if it was completed
        if current_status == 'completed':
            await db.execute(
                update(GeneticAnalysis)
                .where(GeneticAnalysis.id == analysis_id)
                .values(
                    analysis_status="processing",
                    progress_percentage=0,
                    current_step="Restarting analysis...",
                    processed_variants=0
                )
            )
            await db.commit()
            # Refresh the analysis object after update
            await db.refresh(analysis)
            
            return {
                "message": "Analysis restarted successfully",
                "analysis_id": analysis_id,
                "status": "processing",
                "progress_percentage": 0
            }
        
        # Start from current position if paused/stopped
        await db.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(
                analysis_status="processing",
                current_step="Starting analysis..."
            )
        )
        await db.commit()
        
        # Queue the analysis job for background processing
        success = await queue_analysis(analysis_id, current_user.id, priority=1)
        
        if not success:
            # Analysis is already running or user has reached limit
            result = await db.execute(
                select(GeneticAnalysis).where(
                    GeneticAnalysis.id == analysis_id,
                    GeneticAnalysis.user_id == current_user.id
                )
            )
            analysis = result.scalar_one_or_none()
            current_status = analysis.analysis_status if analysis else 'unknown'
            
            return {
                "message": "Analysis could not be queued - may already be running or user limit reached",
                "analysis_id": analysis_id,
                "status": current_status,
                "note": "Check queue status for more details"
            }
        
        return {
            "message": "Analysis started successfully",
            "analysis_id": analysis_id,
            "status": "processing",
            "progress_percentage": getattr(analysis, 'progress_percentage', 0) or 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start analysis: {str(e)}"
        )

@api_router.post("/{analysis_id}/pause")
async def pause_analysis(
    analysis_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Pause a running analysis"""
    
    try:
        # Verify the analysis exists and belongs to the user
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found or access denied"
            )
        
        # Check if analysis can be paused
        current_status = getattr(analysis, 'analysis_status', None)
        if current_status != 'processing':
            return {
                "message": f"Analysis is not running (status: {current_status})",
                "analysis_id": analysis_id,
                "status": current_status
            }
        
        # Update analysis status to paused
        await db.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(
                analysis_status="paused",
                current_step="Analysis paused by user"
            )
        )
        await db.commit()
        
        return {
            "message": "Analysis paused successfully",
            "analysis_id": analysis_id,
            "status": "paused",
            "progress_percentage": analysis.progress_percentage or 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause analysis: {str(e)}"
        )

@api_router.post("/{analysis_id}/resume")
async def resume_analysis_v2(
    analysis_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Resume a paused analysis"""
    
    try:
        # Verify the analysis exists and belongs to the user
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found or access denied"
            )
        
        # Check if analysis can be resumed
        current_status = getattr(analysis, 'analysis_status', None)
        if current_status not in ['paused', 'stopped', 'failed']:
            return {
                "message": f"Analysis cannot be resumed from status: {current_status}",
                "analysis_id": analysis_id,
                "status": current_status
            }
        
        # Resume the analysis job in background
        analysis_job = AnalysisJob(user_id=current_user.id)
        
        async def run_analysis():
            """Background task to resume the analysis"""
            try:
                result = await analysis_job.process_analysis(analysis_id)
                return result
            except Exception as e:
                # Update analysis status to failed
                async for session in get_session():
                    await session.execute(
                        update(GeneticAnalysis)
                        .where(
                            GeneticAnalysis.id == analysis_id,
                            GeneticAnalysis.user_id == current_user.id  # Ensure user ownership
                        )
                        .values(analysis_status="failed", current_step=f"Error: {str(e)}")
                    )
                    await session.commit()
                raise e
        
        asyncio.create_task(run_analysis())
        
        return {
            "message": "Analysis resumed successfully",
            "analysis_id": analysis_id,
            "status": "processing",
            "progress_percentage": analysis.progress_percentage or 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume analysis: {str(e)}"
        )

@api_router.post("/{analysis_id}/stop")
async def stop_analysis_v2(
    analysis_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Stop a running analysis"""
    
    try:
        # Verify the analysis exists and belongs to the user
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found or access denied"
            )
        
        # Update analysis status to stopped
        await db.execute(
            update(GeneticAnalysis)
            .where(GeneticAnalysis.id == analysis_id)
            .values(
                analysis_status="stopped",
                current_step="Analysis stopped by user"
            )
        )
        await db.commit()
        
        return {
            "message": "Analysis stopped successfully",
            "analysis_id": analysis_id,
            "status": "stopped",
            "progress_percentage": analysis.progress_percentage or 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop analysis: {str(e)}"
        )

@api_router.get("/dashboard-data")
async def get_dashboard_data_v2(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Get comprehensive dashboard data for the current user (API v2)"""
    
    # Use the same logic as the original function
    try:
        user_id = current_user.id
        
        # Get all analyses for this user
        analyses_result = await db.execute(
            select(GeneticAnalysis).where(GeneticAnalysis.user_id == user_id).order_by(GeneticAnalysis.upload_date.desc())
        )
        analyses = analyses_result.scalars().all()
        
        if not analyses:
            return {
                "summary": {
                    "total_variants": 0,
                    "analysis_id": None,
                    "processed_at": None,
                    "uploaded_files": 0
                },
                "real_data": {
                    "variants": []
                },
                "health_risks": {
                    "overall_score": 85,
                    "risk_categories": {}
                },
                "drug_interactions": {
                    "high_risk_genes": []
                },
                "insights": [],
                "analysis_results": {
                    "insights": []
                }
            }
        
        # Get the most recent analysis
        latest_analysis = analyses[0]
        
        # Get all variants for all analyses
        all_variants = []
        total_variants = 0
        
        for analysis in analyses:
            variants_result = await db.execute(
                select(GeneticVariant).where(GeneticVariant.analysis_id == analysis.id)
            )
            variants = variants_result.scalars().all()
            total_variants += len(variants)
            
            # Add analysis info to variants
            for variant in variants:
                all_variants.append({
                    "rsid": variant.rsid,
                    "chromosome": variant.chromosome,
                    "position": variant.position,
                    "ref_allele": variant.ref_allele,
                    "alt_allele": variant.alt_allele,
                    "genotype": variant.genotype,
                    "quality": variant.quality,
                    "filter_status": variant.filter_status,
                    "analysis_id": variant.analysis_id,
                    "info": variant.info or {}
                })
        
        # Get health risks for all analyses
        all_health_risks = []
        for analysis in analyses:
            health_risks_result = await db.execute(
                select(HealthRisk).where(HealthRisk.analysis_id == analysis.id)
            )
            health_risks = health_risks_result.scalars().all()
            all_health_risks.extend(health_risks)
        
        # Get drug responses for all analyses
        all_drug_responses = []
        for analysis in analyses:
            drug_responses_result = await db.execute(
                select(DrugResponse).where(DrugResponse.analysis_id == analysis.id)
            )
            drug_responses = drug_responses_result.scalars().all()
            all_drug_responses.extend(drug_responses)
        
        # Process health risks into categories
        risk_categories = {}
        overall_risk_scores = []
        
        for risk in all_health_risks:
            condition = risk.condition.lower()
            risk_score = 0
            
            # Convert risk levels to numeric scores
            if risk.risk_level == 'high':
                risk_score = 85
            elif risk.risk_level == 'moderate':
                risk_score = 65
            elif risk.risk_level == 'low':
                risk_score = 35
            
            # Group by condition type
            if 'diabetes' in condition or 'glucose' in condition:
                risk_categories['diabetes'] = {"score": risk_score, "risk_level": risk.risk_level}
            elif 'cardiovascular' in condition or 'heart' in condition or 'cardiac' in condition:
                risk_categories['cardiovascular'] = {"score": risk_score, "risk_level": risk.risk_level}
            elif 'alzheimer' in condition or 'dementia' in condition or 'cognitive' in condition:
                risk_categories['alzheimer'] = {"score": risk_score, "risk_level": risk.risk_level}
            elif 'cancer' in condition:
                risk_categories['cancer'] = {"score": risk_score, "risk_level": risk.risk_level}
            else:
                # Generic condition
                risk_categories[condition.replace(' ', '_')] = {"score": risk_score, "risk_level": risk.risk_level}
            
            overall_risk_scores.append(risk_score)
        
        # Calculate overall health score (inverse of average risk)
        if overall_risk_scores:
            avg_risk = sum(overall_risk_scores) / len(overall_risk_scores)
            overall_score = max(20, 100 - avg_risk)  # Ensure minimum score of 20
        else:
            overall_score = 85  # Default good score when no risks identified
        
        # Get high-risk genes from drug responses
        high_risk_genes = list(set([dr.gene for dr in all_drug_responses if dr.response_type in ['poor', 'ultrarapid']]))
        
        # Generate insights
        insights = []
        
        if all_health_risks:
            high_risk_count = len([r for r in all_health_risks if r.risk_level == 'high'])
            if high_risk_count > 0:
                insights.append(f"Found {high_risk_count} high-risk genetic variant(s) requiring attention")
        
        if all_drug_responses:
            poor_metabolizers = len([dr for dr in all_drug_responses if dr.response_type == 'poor'])
            if poor_metabolizers > 0:
                insights.append(f"Identified {poor_metabolizers} gene(s) affecting drug metabolism")
        
        if total_variants > 0:
            with_rsid = len([v for v in all_variants if v.get('rsid') and v['rsid'] != '-'])
            coverage = round((with_rsid / total_variants) * 100)
            insights.append(f"{coverage}% of variants have reference IDs for clinical analysis")
        
        if not insights:
            insights = ["Analysis complete - check individual categories for detailed results"]
        
        return {
            "summary": {
                "total_variants": total_variants,
                "analysis_id": latest_analysis.id,
                "processed_at": latest_analysis.upload_date.isoformat(),
                "uploaded_files": len(analyses),
                "data_sources": [analysis.filename for analysis in analyses],
                "upload_info": {
                    "filename": latest_analysis.filename,
                    "file_type": latest_analysis.file_type
                }
            },
            "real_data": {
                "variants": all_variants,
                "upload_result": {
                    "filename": latest_analysis.filename
                }
            },
            "health_risks": {
                "overall_score": round(overall_score),
                "risk_categories": risk_categories,
                "details": [
                    {
                        "condition": risk.condition,
                        "risk_level": risk.risk_level,
                        "risk_score": risk.risk_score,
                        "recommendations": risk.recommendations
                    }
                    for risk in all_health_risks
                ]
            },
            "drug_interactions": {
                "high_risk_genes": high_risk_genes,
                "details": [
                    {
                        "gene": dr.gene,
                        "drug": dr.drug,
                        "response_type": dr.response_type,
                        "recommendations": dr.recommendations,
                        "variants_involved": dr.variants_involved
                    }
                    for dr in all_drug_responses
                ]
            },
            "insights": insights,
            "analysis_results": {
                "insights": insights,
                "total_analyses": len(analyses),
                "latest_analysis_date": latest_analysis.upload_date.isoformat()
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dashboard data: {str(e)}"
        )
@api_router.get("/{analysis_id}/progress")
async def get_analysis_progress_v2(
    analysis_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Get real-time analysis progress for a specific analysis (API v2)"""
    
    try:
        # Get the analysis record with progress tracking
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found or access denied"
            )
        
        return {
            "analysis_id": analysis.id,
            "status": analysis.analysis_status or 'pending',
            "progress_percentage": analysis.progress_percentage or 0,
            "current_step": analysis.current_step or 'Initializing...',
            "total_variants": analysis.total_variants or 0,
            "processed_variants": analysis.processed_variants or 0,
            "estimated_completion": analysis.estimated_completion.isoformat() if analysis.estimated_completion is not None else None,
            "upload_date": analysis.upload_date.isoformat(),
            "filename": analysis.filename,
            "file_type": analysis.file_type,
            "analysis_results": analysis.analysis_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analysis progress: {str(e)}"
        )

@api_router.post("/{analysis_id}/reset-status")
async def reset_analysis_status_v2(
    analysis_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Reset analysis status based on actual completion state (API v2)"""
    
    try:
        # Verify the analysis exists and belongs to the user
        result = await db.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == analysis_id,
                GeneticAnalysis.user_id == current_user.id
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found or access denied"
            )
        
        # Check if analysis has results and should be marked as completed
        has_results = bool(
            analysis.analysis_results and 
            isinstance(analysis.analysis_results, dict) and
            analysis.analysis_results.get('status') == 'completed'
        )
        
        # Check if progress is 100% (should be completed regardless of results)
        progress_complete = bool((analysis.progress_percentage or 0) >= 100)
        
        if has_results or progress_complete:
            # Analysis is actually completed, update status
            await db.execute(
                update(GeneticAnalysis)
                .where(GeneticAnalysis.id == analysis_id)
                .values(
                    analysis_status="completed",
                    progress_percentage=100,
                    current_step="Analysis completed"
                )
            )
            await db.commit()
            
            return {
                "message": "Analysis status corrected to completed",
                "analysis_id": analysis_id,
                "status": "completed",
                "progress_percentage": 100
            }
        else:
            # Analysis is incomplete, can be resumed
            await db.execute(
                update(GeneticAnalysis)
                .where(GeneticAnalysis.id == analysis_id)
                .values(
                    analysis_status="stopped",
                    current_step="Ready to resume"
                )
            )
            await db.commit()
            
            return {
                "message": "Analysis status reset to stopped - ready to resume",
                "analysis_id": analysis_id,
                "status": "stopped",
                "progress_percentage": analysis.progress_percentage or 0
            }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset analysis status: {str(e)}"
        )
