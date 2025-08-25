#!/usr/bin/env python3
"""
Test all specialized genetic analyzers with comprehensive variant coverage
This test ensures all 10 specialized analyzer categories work correctly
"""
import asyncio
import logging

from backend.db.database import async_session_factory
from backend.db.models import GeneticAnalysis, GeneticVariant
from backend.services.specialized_analyzers import SpecializedAnalyzerManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Comprehensive test variants covering all analyzer categories
TEST_VARIANTS = [
    # Methylation pathway (MTHFR, COMT, MTR, MTRR)
    {'rsid': 'rs1801133', 'gene': 'MTHFR', 'chromosome': '1', 'position': 11796321, 'genotype': 'GA', 'ref': 'G', 'alt': 'A'},
    {'rsid': 'rs4680', 'gene': 'COMT', 'chromosome': '22', 'position': 19963748, 'genotype': 'AG', 'ref': 'G', 'alt': 'A'},
    {'rsid': 'rs1805087', 'gene': 'MTR', 'chromosome': '1', 'position': 236885200, 'genotype': 'AG', 'ref': 'A', 'alt': 'G'},
    
    # Detoxification (CYP2D6, CYP2C19, GSTM1, GSTT1, NAT2)
    {'rsid': 'rs1065852', 'gene': 'CYP2D6', 'chromosome': '22', 'position': 42526694, 'genotype': 'GA', 'ref': 'G', 'alt': 'A'},
    {'rsid': 'rs4244285', 'gene': 'CYP2C19', 'chromosome': '10', 'position': 96522463, 'genotype': 'GA', 'ref': 'G', 'alt': 'A'},
    {'rsid': 'rs1695', 'gene': 'GSTM1', 'chromosome': '1', 'position': 110230407, 'genotype': 'AG', 'ref': 'A', 'alt': 'G'},
    
    # Sports Performance (ACTN3, ACE, BDKRB2)
    {'rsid': 'rs1815739', 'gene': 'ACTN3', 'chromosome': '11', 'position': 66328095, 'genotype': 'CT', 'ref': 'C', 'alt': 'T'},
    {'rsid': 'rs1799752', 'gene': 'ACE', 'chromosome': '17', 'position': 61554424, 'genotype': 'ID', 'ref': 'I', 'alt': 'D'},
    
    # Nutrition (FTO, MC4R, CYP1A2, LCT)
    {'rsid': 'rs9939609', 'gene': 'FTO', 'chromosome': '16', 'position': 53820527, 'genotype': 'AT', 'ref': 'A', 'alt': 'T'},
    {'rsid': 'rs762551', 'gene': 'CYP1A2', 'chromosome': '15', 'position': 75041917, 'genotype': 'CA', 'ref': 'C', 'alt': 'A'},
    
    # Physical Traits (MC1R, HERC2, SLC45A2, EDAR)
    {'rsid': 'rs1805007', 'gene': 'MC1R', 'chromosome': '16', 'position': 89985940, 'genotype': 'CT', 'ref': 'C', 'alt': 'T'},
    {'rsid': 'rs12913832', 'gene': 'HERC2', 'chromosome': '15', 'position': 28365618, 'genotype': 'AG', 'ref': 'A', 'alt': 'G'},
    {'rsid': 'rs16891982', 'gene': 'SLC45A2', 'chromosome': '5', 'position': 33951693, 'genotype': 'CG', 'ref': 'C', 'alt': 'G'},
    
    # Cognitive (BDNF, DAT1, CACNA1C, KIBRA)
    {'rsid': 'rs6265', 'gene': 'BDNF', 'chromosome': '11', 'position': 27679916, 'genotype': 'CT', 'ref': 'C', 'alt': 'T'},
    {'rsid': 'rs1006737', 'gene': 'CACNA1C', 'chromosome': '12', 'position': 2233661, 'genotype': 'AG', 'ref': 'A', 'alt': 'G'},
    
    # Personality (DRD4, SLC6A4, MAOA, OXTR)
    {'rsid': 'rs1800955', 'gene': 'DRD4', 'chromosome': '11', 'position': 637273, 'genotype': 'CT', 'ref': 'C', 'alt': 'T'},
    {'rsid': 'rs53576', 'gene': 'OXTR', 'chromosome': '3', 'position': 8762685, 'genotype': 'AG', 'ref': 'A', 'alt': 'G'},
    
    # Ancestry markers
    {'rsid': 'rs1426654', 'gene': 'SLC24A5', 'chromosome': '15', 'position': 48426484, 'genotype': 'AA', 'ref': 'A', 'alt': 'G'},
    {'rsid': 'rs3827760', 'gene': 'EDAR', 'chromosome': '2', 'position': 109513601, 'genotype': 'CT', 'ref': 'C', 'alt': 'T'},
    
    # Carrier Status (CFTR, HBB)
    {'rsid': 'rs113993960', 'gene': 'CFTR', 'chromosome': '7', 'position': 117199644, 'genotype': 'CT', 'ref': 'C', 'alt': 'T'},
    {'rsid': 'rs334', 'gene': 'HBB', 'chromosome': '11', 'position': 5248232, 'genotype': 'AT', 'ref': 'A', 'alt': 'T'},
    
    # Wellness (CLOCK, PER3)
    {'rsid': 'rs1801260', 'gene': 'CLOCK', 'chromosome': '4', 'position': 56304650, 'genotype': 'CT', 'ref': 'C', 'alt': 'T'},
    {'rsid': 'rs57875989', 'gene': 'PER3', 'chromosome': '1', 'position': 7784947, 'genotype': 'GA', 'ref': 'G', 'alt': 'A'},
]

async def test_all_specialized_analyzers():
    """Test all specialized analyzers with comprehensive variant coverage"""
    logger.info("🧪 Testing all specialized analyzers with comprehensive coverage...")
    
    async with async_session_factory() as session:
        # Get or create test analysis
        analysis = await session.get(GeneticAnalysis, 23)
        if not analysis:
            logger.error("❌ Analysis 23 not found. Please run the basic test first.")
            return
        
        # Clear existing specialized data
        logger.info("🧹 Clearing existing specialized analysis data...")
        tables_to_clear = [
            'methylation_profiles', 'detoxification_profiles', 'sports_performance', 
            'nutrition_traits', 'physical_traits', 'cognitive_profiles', 
            'personality_traits', 'ancestry_results', 'carrier_status', 'wellness_metrics'
        ]
        
        for table in tables_to_clear:
            await session.execute(f"DELETE FROM {table} WHERE analysis_id = {analysis.id}")
        
        # Create comprehensive test variants
        logger.info("🧬 Adding comprehensive test variants...")
        variants = []
        for var_data in TEST_VARIANTS:
            variant = GeneticVariant(
                analysis_id=analysis.id,
                chromosome=var_data['chromosome'],
                position=var_data['position'],
                rsid=var_data['rsid'],
                ref_allele=var_data['ref'],
                alt_allele=var_data['alt'],
                genotype=var_data['genotype'],
                quality='.',
                filter_status='PASS',
                info={}
            )
            session.add(variant)
            variants.append(variant)
        
        await session.commit()
        logger.info(f"✅ Added {len(variants)} comprehensive test variants")
        
        # Test specialized analyzers
        logger.info("🔬 Running comprehensive specialized analysis...")
        analyzer_manager = SpecializedAnalyzerManager()
        
        total_results = {
            'methylation_profiles': [],
            'detox_profiles': [],
            'sports_profiles': [],
            'nutrition_profiles': [],
            'physical_traits': [],
            'cognitive_profiles': [],
            'personality_traits': [],
            'ancestry_results': [],
            'carrier_status': [],
            'wellness_metrics': []
        }
        
        for variant in variants:
            try:
                logger.info(f"🔬 Analyzing variant {variant.rsid}...")
                annotation = {'annotations': {}}  # Mock annotation
                
                results = await analyzer_manager.generate_all_specialized_profiles(
                    variant, annotation, analysis.id, session
                )
                
                # Aggregate results
                for category, profiles in results.items():
                    total_results[category].extend(profiles)
                    
            except Exception as e:
                logger.error(f"❌ Error analyzing {variant.rsid}: {e}")
                continue
        
        logger.info("✅ Comprehensive specialized analysis completed!")
        
        # Report results
        logger.info("📊 Generated profiles by category:")
        for category, profiles in total_results.items():
            if profiles:
                logger.info(f"   - {category}: {len(profiles)}")
        
        # Verify in database
        logger.info("🔍 Verifying all categories in database...")
        category_queries = {
            'methylation_profiles': 'SELECT COUNT(*) as count FROM methylation_profiles WHERE analysis_id = 23',
            'detoxification_profiles': 'SELECT COUNT(*) as count FROM detoxification_profiles WHERE analysis_id = 23',
            'sports_performance': 'SELECT COUNT(*) as count FROM sports_performance WHERE analysis_id = 23',
            'nutrition_traits': 'SELECT COUNT(*) as count FROM nutrition_traits WHERE analysis_id = 23',
            'physical_traits': 'SELECT COUNT(*) as count FROM physical_traits WHERE analysis_id = 23',
            'cognitive_profiles': 'SELECT COUNT(*) as count FROM cognitive_profiles WHERE analysis_id = 23',
            'personality_traits': 'SELECT COUNT(*) as count FROM personality_traits WHERE analysis_id = 23',
            'ancestry_results': 'SELECT COUNT(*) as count FROM ancestry_results WHERE analysis_id = 23',
            'carrier_status': 'SELECT COUNT(*) as count FROM carrier_status WHERE analysis_id = 23',
            'wellness_metrics': 'SELECT COUNT(*) as count FROM wellness_metrics WHERE analysis_id = 23'
        }
        
        database_counts = {}
        for category, query in category_queries.items():
            result = await session.execute(query)
            count = result.scalar()
            database_counts[category] = count
            
            if count > 0:
                logger.info(f"📊 {category}: {count} records")
        
        # Summary
        working_categories = [cat for cat, count in database_counts.items() if count > 0]
        logger.info(f"🎉 Comprehensive test completed!")
        logger.info(f"✅ {len(working_categories)}/10 specialized analyzer categories working:")
        for category in working_categories:
            logger.info(f"   ✓ {category}")
        
        # Show examples from each working category
        logger.info("📝 Sample profiles from each category:")
        for category in working_categories:
            table_name = category
            result = await session.execute(f"SELECT * FROM {table_name} WHERE analysis_id = 23 LIMIT 1")
            row = result.fetchone()
            if row:
                logger.info(f"   {category}: {dict(row)}")

if __name__ == "__main__":
    asyncio.run(test_all_specialized_analyzers())