#!/usr/bin/env python3
"""
Run enhanced analysis on full dataset (1,987 variants) to test specialized analyzers
"""
import asyncio
import logging
import sys
from sqlalchemy.ext.asyncio import AsyncSession

# Add backend to Python path
sys.path.append('/Users/victoriatco/dna-tools/dna_toolkit/backend')

from backend.db.database import get_session
from backend.db.models import (
    GeneticAnalysis, 
    MethylationProfile, DetoxificationProfile, 
    SportsPerformance, NutritionTrait
)
from backend.services.analysis_job import AnalysisJob

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """Run enhanced analysis on full dataset"""
    
    # Get async database session
    session_generator = get_session()
    session = await session_generator.__anext__()
    
    try:
        # Validate user owns analysis
        from sqlalchemy import select
        result = await session.execute(
            select(GeneticAnalysis).where(
                GeneticAnalysis.id == 23,
                GeneticAnalysis.user_id == 1
            )
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            logger.error("Analysis 23 not found for user 1")
            return
        
        logger.info(f"🚀 Starting enhanced analysis on full dataset: {analysis.filename}")
        
        # Run the enhanced analysis job
        analysis_job = AnalysisJob(user_id=1)
        results = await analysis_job.process_analysis(23)
        
        logger.info("✅ Enhanced analysis completed!")
        logger.info("📊 Results summary:")
        logger.info(f"   - Health risks: {results.get('insights_generated', 0)}")
        logger.info(f"   - Drug responses: {results.get('drug_responses_generated', 0)}")
        
        specialized = results.get('specialized_profiles_generated', {})
        logger.info(f"   - Methylation profiles: {specialized.get('methylation', 0)}")
        logger.info(f"   - Detox profiles: {specialized.get('detox', 0)}")
        logger.info(f"   - Sports profiles: {specialized.get('sports', 0)}")
        logger.info(f"   - Nutrition profiles: {specialized.get('nutrition', 0)}")
        
        logger.info(f"   - Variants processed: {results.get('total_variants_processed', 0)}")
        logger.info(f"   - API calls made: {results.get('api_calls_made', 0)}")
        logger.info(f"   - Processing time: {results.get('processing_time', 0)} seconds")
        
        # Check database for specialized profiles using async queries
        logger.info("🔍 Checking database for specialized profiles...")
        
        from sqlalchemy import func
        
        methylation_result = await session.execute(
            select(func.count(MethylationProfile.id)).where(MethylationProfile.analysis_id == 23)
        )
        methylation_count = methylation_result.scalar()
        logger.info(f"📊 Found {methylation_count} methylation profiles in database")
        
        detox_result = await session.execute(
            select(func.count(DetoxificationProfile.id)).where(DetoxificationProfile.analysis_id == 23)
        )
        detox_count = detox_result.scalar()
        logger.info(f"🧼 Found {detox_count} detoxification profiles in database")
        
        sports_result = await session.execute(
            select(func.count(SportsPerformance.id)).where(SportsPerformance.analysis_id == 23)
        )
        sports_count = sports_result.scalar()
        logger.info(f"🏃 Found {sports_count} sports performance profiles in database")
        
        nutrition_result = await session.execute(
            select(func.count(NutritionTrait.id)).where(NutritionTrait.analysis_id == 23)
        )
        nutrition_count = nutrition_result.scalar()
        logger.info(f"🍎 Found {nutrition_count} nutrition traits in database")
        
        # Show some sample profiles if any exist
        if methylation_count > 0:
            sample_result = await session.execute(
                select(MethylationProfile).where(MethylationProfile.analysis_id == 23).limit(1)
            )
            sample_methylation = sample_result.scalar_one_or_none()
            if sample_methylation:
                logger.info(f"📝 Sample methylation profile: {sample_methylation.gene} - {sample_methylation.methylation_capacity}")
        
        if detox_count > 0:
            sample_result = await session.execute(
                select(DetoxificationProfile).where(DetoxificationProfile.analysis_id == 23).limit(1)
            )
            sample_detox = sample_result.scalar_one_or_none()
            if sample_detox:
                logger.info(f"📝 Sample detox profile: {sample_detox.gene} - {sample_detox.detox_capacity}")
        
        logger.info("🎉 Enhanced analysis pipeline test completed successfully!")
        
    except Exception as e:
        logger.error(f"Error running enhanced analysis: {e}")
        raise
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(main())