#!/usr/bin/env python3
"""
Test script to run the enhanced analysis pipeline with specialized analyzers
This will reprocess analysis 23 to populate the specialized category tables
"""
import asyncio
import logging
from sqlalchemy import select

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    """Test the enhanced analysis pipeline"""
    try:
        # Import the services
        from backend.services.analysis_job import AnalysisJob
        
        logger.info("🧪 Starting enhanced analysis pipeline test")
        
        # Initialize analysis job with enhanced capabilities
        analysis_job = AnalysisJob(user_id=1)  # Using user 1 based on database check
        
        # Run the enhanced analysis on analysis ID 23
        analysis_id = 23
        logger.info(f"🔄 Running enhanced analysis for analysis_id: {analysis_id}")
        
        # Process with a limit first to test the pipeline
        test_limit = 50  # Process 50 variants to test the new pipeline
        results = await analysis_job.process_analysis(analysis_id, max_variants=test_limit)
        
        logger.info("✅ Enhanced analysis completed!")
        logger.info("📊 Results summary:")
        logger.info(f"   - Health risks: {len(results.get('health_risks', []))}")
        logger.info(f"   - Drug responses: {len(results.get('drug_responses', []))}")
        
        # Log specialized profile results
        specialized = results.get('specialized_profiles', {})
        logger.info(f"   - Methylation profiles: {specialized.get('methylation', 0)}")
        logger.info(f"   - Detox profiles: {specialized.get('detox', 0)}")
        logger.info(f"   - Sports profiles: {specialized.get('sports', 0)}")
        logger.info(f"   - Nutrition profiles: {specialized.get('nutrition', 0)}")
        
        logger.info(f"   - Variants processed: {results.get('variants_processed', 0)}")
        logger.info(f"   - API calls made: {results.get('api_calls_made', 0)}")
        logger.info(f"   - Processing time: {results.get('processing_time', 0):.2f} seconds")
        
        # Now check the database to see what was populated
        logger.info("🔍 Checking database for specialized profiles...")
        
        # Import the database session and models
        from backend.db.database import get_session
        
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Check each specialized table for new data
            from backend.db.models import (
                MethylationProfile, DetoxificationProfile, 
                SportsPerformance, NutritionTrait
            )
            
            # Count methylation profiles
            methylation_result = await session.execute(
                select(MethylationProfile).where(MethylationProfile.analysis_id == analysis_id)
            )
            methylation_profiles = list(methylation_result.scalars().all())
            logger.info(f"📊 Found {len(methylation_profiles)} methylation profiles in database")
            
            # Count detox profiles
            detox_result = await session.execute(
                select(DetoxificationProfile).where(DetoxificationProfile.analysis_id == analysis_id)
            )
            detox_profiles = list(detox_result.scalars().all())
            logger.info(f"🧼 Found {len(detox_profiles)} detoxification profiles in database")
            
            # Count sports profiles
            sports_result = await session.execute(
                select(SportsPerformance).where(SportsPerformance.analysis_id == analysis_id)
            )
            sports_profiles = list(sports_result.scalars().all())
            logger.info(f"🏃 Found {len(sports_profiles)} sports performance profiles in database")
            
            # Count nutrition profiles
            nutrition_result = await session.execute(
                select(NutritionTrait).where(NutritionTrait.analysis_id == analysis_id)
            )
            nutrition_profiles = list(nutrition_result.scalars().all())
            logger.info(f"🍎 Found {len(nutrition_profiles)} nutrition traits in database")
            
            # Show some examples if we have data
            if methylation_profiles:
                logger.info("🧬 Sample methylation profiles:")
                for profile in methylation_profiles[:3]:  # Show first 3
                    logger.info(f"   - {profile.gene}: {profile.variant} -> {profile.methylation_capacity}")
            
            if detox_profiles:
                logger.info("🧼 Sample detox profiles:")
                for profile in detox_profiles[:3]:  # Show first 3
                    logger.info(f"   - {profile.gene} ({profile.detox_phase}): {profile.detox_capacity}")
            
            if sports_profiles:
                logger.info("🏃 Sample sports profiles:")
                for profile in sports_profiles[:3]:  # Show first 3
                    logger.info(f"   - {profile.performance_category}: {profile.genetic_advantage}")
            
            if nutrition_profiles:
                logger.info("🍎 Sample nutrition traits:")
                for trait in nutrition_profiles[:3]:  # Show first 3
                    logger.info(f"   - {trait.nutrient}: {trait.metabolism_type}")
            
        finally:
            await session.close()
        
        logger.info("🎉 Enhanced analysis pipeline test completed successfully!")
        
        if any([specialized.get('methylation', 0), specialized.get('detox', 0), 
                specialized.get('sports', 0), specialized.get('nutrition', 0)]):
            logger.info("✅ Specialized analyzers are working! Category data is being generated.")
        else:
            logger.warning("⚠️  No specialized profiles were generated. This might be expected if the test variants don't match known genetic markers.")
        
    except Exception as e:
        logger.error(f"❌ Enhanced analysis test failed: {e}")
        import traceback
        logger.error(f"📍 Error details:\n{traceback.format_exc()}")
        raise

if __name__ == "__main__":
    asyncio.run(main())