#!/usr/bin/env python3
"""
Test script to manually run analysis job for debugging
"""
import asyncio
import sys
import os

# Add the backend directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from backend.services.analysis_job import run_analysis_job

async def test_analysis():
    """Test the analysis job for analysis ID 11 with realistic processing"""
    print("Starting analysis job test for analysis ID 11 (full dataset)...")
    
    try:
        # Run analysis without variant limit to process based on intelligent batching
        # This will process ~4000 variants total (pharmacogenes + disease variants + common + other)
        result = await run_analysis_job(analysis_id=11, max_variants=None)
        print(f"Analysis result: {result}")
        
        # Print summary statistics
        if 'health_risks' in result:
            print(f"\nGenerated {len(result['health_risks'])} health risk assessments")
        if 'drug_responses' in result:
            print(f"Generated {len(result['drug_responses'])} drug response predictions")
        if 'api_calls_made' in result:
            print(f"Made {result['api_calls_made']} API calls")
        if 'processing_time' in result:
            print(f"Processing time: {result['processing_time']:.2f} seconds")
        
    except Exception as e:
        print(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_analysis())