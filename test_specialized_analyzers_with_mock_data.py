#!/usr/bin/env python3
"""
Test specialized analyzers by temporarily adding mock genetic variants
"""
import asyncio
import logging
import sys
from sqlalchemy.ext.asyncio import AsyncSession

# Add backend to Python path
sys.path.append('/Users/victoriatco/dna-tools/dna_toolkit/backend')

from backend.db.database import get_session
from backend.db.models import (
    GeneticAnalysis, GeneticVariant,
    MethylationProfile, DetoxificationProfile, 
    SportsPerformance, NutritionTrait
)
from backend.services.specialized_analyzers import SpecializedAnalyzerManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """Test specialized analyzers with mock genetic data"""
    
    # Get async database session
    session_generator = get_session()
    session = await session_generator.__anext__()
    
    try:
        # Validate user owns analysis
        from sqlalchemy import select, delete
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
        
        logger.info("🧪 Testing specialized analyzers with mock genetic variants...")
        
        # Clean up any existing specialized profiles for this analysis
        await session.execute(delete(MethylationProfile).where(MethylationProfile.analysis_id == 23))
        await session.execute(delete(DetoxificationProfile).where(DetoxificationProfile.analysis_id == 23))
        await session.execute(delete(SportsPerformance).where(SportsPerformance.analysis_id == 23))
        await session.execute(delete(NutritionTrait).where(NutritionTrait.analysis_id == 23))
        
        # Add mock genetic variants that the analyzers will recognize
        mock_variants = [
            # MTHFR C677T (methylation)
            GeneticVariant(
                analysis_id=23,
                chromosome="1",
                position=11796321,
                rsid="rs1801133",
                ref_allele="G",
                alt_allele="A", 
                genotype="GA",
                quality=".",
                filter_status="PASS",
                info={}
            ),
            # COMT Val158Met (methylation)  
            GeneticVariant(
                analysis_id=23,
                chromosome="22",
                position=19963748,
                rsid="rs4680",
                ref_allele="G",
                alt_allele="A",
                genotype="AG",
                quality=".",
                filter_status="PASS", 
                info={}
            ),
            # CYP1A2 (caffeine metabolism - nutrition)
            GeneticVariant(
                analysis_id=23,
                chromosome="15",
                position=75041917,
                rsid="rs762551",
                ref_allele="C",
                alt_allele="A",
                genotype="CA",
                quality=".",
                filter_status="PASS",
                info={}
            ),
            # ACTN3 R577X (sports performance)
            GeneticVariant(
                analysis_id=23,
                chromosome="11", 
                position=66328095,
                rsid="rs1815739",
                ref_allele="C",
                alt_allele="T",
                genotype="CT",
                quality=".",
                filter_status="PASS",
                info={}
            ),
            # GSTM1 deletion (detoxification)
            GeneticVariant(
                analysis_id=23,
                chromosome="1",
                position=110230407,
                rsid="rs1695",
                ref_allele="A",
                alt_allele="G", 
                genotype="AG",
                quality=".",
                filter_status="PASS",
                info={}
            )
        ]
        
        # Add mock variants to database
        session.add_all(mock_variants)
        await session.commit()
        logger.info(f"✅ Added {len(mock_variants)} mock genetic variants")
        
        # Initialize and run specialized analyzers
        analyzer_manager = SpecializedAnalyzerManager()
        
        # Get only our mock variants for testing
        variants_result = await session.execute(
            select(GeneticVariant).where(
                GeneticVariant.analysis_id == 23,
                GeneticVariant.rsid.in_(['rs1801133', 'rs4680', 'rs762551', 'rs1815739', 'rs1695'])
            )
        )
        test_variants = list(variants_result.scalars().all())
        
        logger.info(f"🧬 Processing {len(test_variants)} mock variants with specialized analyzers...")
        
        # Run specialized analysis on each variant
        specialized_counts = {'methylation': 0, 'detox': 0, 'sports': 0, 'nutrition': 0}
        
        for variant in test_variants:
            logger.info(f"🔬 Analyzing variant {variant.rsid}...")
            
            # Mock annotation data for each variant
            mock_annotation = {
                'annotations': {
                    'clinvar': {
                        'found': True,
                        'entries': [{'clinical_significance': ['pathogenic']}]
                    },
                    'snpedia': {'found': True, 'entries': [{'summary': 'Test variant'}]},
                    'ensembl': {'found': True, 'data': {'gene': 'TEST'}}
                }
            }
            
            # Process variant through specialized analyzers
            results = await analyzer_manager.generate_all_specialized_profiles(
                variant=variant,
                annotation=mock_annotation,
                analysis_id=23,
                session=session
            )
            
            # Count generated profiles
            specialized_counts['methylation'] += len(results.get('methylation_profiles', []))
            specialized_counts['detox'] += len(results.get('detox_profiles', []))
            specialized_counts['sports'] += len(results.get('sports_profiles', []))
            specialized_counts['nutrition'] += len(results.get('nutrition_profiles', []))
        
        # Commit all the generated profiles
        await session.commit()
        
        logger.info("✅ Specialized analysis completed!")
        logger.info("📊 Generated profiles:")
        for profile_type, count in specialized_counts.items():
            logger.info(f"   - {profile_type}: {count}")
        
        # Check database for generated profiles
        logger.info("🔍 Verifying profiles in database...")
        
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
        
        # Show sample generated profiles
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
        
        if sports_count > 0:
            sample_result = await session.execute(
                select(SportsPerformance).where(SportsPerformance.analysis_id == 23).limit(1)
            )
            sample_sports = sample_result.scalar_one_or_none()
            if sample_sports:
                logger.info(f"📝 Sample sports profile: {sample_sports.performance_category} - {sample_sports.genetic_advantage}")
        
        if nutrition_count > 0:
            sample_result = await session.execute(
                select(NutritionTrait).where(NutritionTrait.analysis_id == 23).limit(1)
            )
            sample_nutrition = sample_result.scalar_one_or_none()
            if sample_nutrition:
                logger.info(f"📝 Sample nutrition profile: {sample_nutrition.nutrient} - {sample_nutrition.metabolism_type}")
        
        logger.info("🎉 Specialized analyzer test completed successfully!")
        
        if sum(specialized_counts.values()) > 0:
            logger.info("✅ Specialized analyzers are working correctly and generating profiles!")
        else:
            logger.warning("⚠️  No profiles were generated - check analyzer logic")
        
    except Exception as e:
        logger.error(f"Error testing specialized analyzers: {e}")
        raise
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(main())