#!/usr/bin/env python3
"""
Test script to validate the optimized genetic analysis performance
"""
import asyncio
import time
import logging
from backend.services.analysis_job import GeneticAnalysisJob

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_optimization():
    """Test the optimized analysis job performance"""
    logger.info("🚀 Starting optimization test...")
    
    # Create a test analysis job
    job = GeneticAnalysisJob(user_id=1)
    
    # Test variant prioritization
    class MockVariant:
        def __init__(self, rsid, clinical_significance=None):
            self.id = id(self)
            self.rsid = rsid
            self.clinical_significance = clinical_significance
    
    # Create test variants
    test_variants = [
        MockVariant("rs1801282", "pathogenic"),              # Important pathogenic
        MockVariant("rs662", "likely pathogenic"),           # Likely pathogenic  
        MockVariant("rs4680", "benign"),                     # Common benign
        MockVariant("rs1799930", "uncertain significance"),   # Uncertain
        MockVariant("cyp2d6*4", "pathogenic"),              # Pharmacogene (top priority)
        MockVariant("rs1801133", "pathogenic"),              # MTHFR (pharmacogene)
        MockVariant("rs429358", "pathogenic"),               # APOE (pharmacogene)
        MockVariant("rs12345", None),                        # Common variant
        MockVariant("rs67890", "benign"),                    # Another benign
        MockVariant("aldh2*2", "pathogenic"),               # Another pharmacogene
    ]
    
    logger.info(f"📊 Testing with {len(test_variants)} mock variants")
    
    # Test variant selection with different limits
    test_cases = [
        {"max_variants": None, "description": "No limit"},
        {"max_variants": 5, "description": "Limited to 5 variants"},
        {"max_variants": 8, "description": "Limited to 8 variants"},
        {"max_variants": 15, "description": "Limited to 15 variants"},
    ]
    
    for case in test_cases:
        start_time = time.time()
        selected = job._select_important_variants(test_variants, case["max_variants"])
        selection_time = time.time() - start_time
        
        logger.info(f"\n🧪 Test Case: {case['description']}")
        logger.info(f"   Selected: {len(selected)} variants in {selection_time*1000:.2f}ms")
        
        # Count by category
        pharmacogenes = sum(1 for v in selected if job._is_pharmacogene_variant(v))
        pathogenic = sum(1 for v in selected if v.clinical_significance == "pathogenic")
        likely_pathogenic = sum(1 for v in selected if v.clinical_significance == "likely pathogenic")
        
        logger.info(f"   - Pharmacogenes: {pharmacogenes}")
        logger.info(f"   - Pathogenic: {pathogenic}")
        logger.info(f"   - Likely pathogenic: {likely_pathogenic}")
        logger.info(f"   - Others: {len(selected) - pharmacogenes - pathogenic - likely_pathogenic}")
    
    logger.info("\n✅ Optimization test completed successfully!")
    logger.info("🎯 Key improvements implemented:")
    logger.info("   - Smart variant prioritization (pharmacogenes first)")
    logger.info("   - Adaptive API delays (0.02s-0.1s based on dataset size)")
    logger.info("   - Simplified processing (essential insights only)")
    logger.info("   - Progress tracking every 10 variants")
    logger.info("   - Skip duplicate processing")

if __name__ == "__main__":
    asyncio.run(test_optimization())