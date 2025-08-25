#!/usr/bin/env python3
"""
Run only specialized analyzers on existing analysis data
"""
import asyncio
import sys
import os

# Add backend to path
sys.path.append('/app')

async def run_specialized_analyzers(analysis_id: int):
    """Run specialized analyzers on existing analysis"""
    try:
        from backend.db.database import async_session_factory
        from backend.db.models import GeneticAnalysis, GeneticVariant
        from backend.services.specialized_analyzers import SpecializedAnalyzerManager
        from sqlalchemy import select
        
        print(f"Running specialized analyzers for analysis {analysis_id}...")
        
        async with async_session_factory() as session:
            # Get the analysis
            stmt = select(GeneticAnalysis).where(GeneticAnalysis.id == analysis_id)
            result = await session.execute(stmt)
            analysis = result.scalar_one_or_none()
            
            if not analysis:
                print(f"❌ Analysis {analysis_id} not found")
                return
                
            print(f"Found analysis {analysis.id}:")
            print(f"  Status: {analysis.analysis_status}")
            print(f"  Variants: {analysis.total_variants}")
            
            # Get all variants for this analysis
            stmt = select(GeneticVariant).where(GeneticVariant.analysis_id == analysis_id)
            variants_result = await session.execute(stmt)
            variants = variants_result.scalars().all()
            
            print(f"Found {len(variants)} variants to analyze")
            
            # Run specialized analyzers
            analyzer_manager = SpecializedAnalyzerManager()
            await analyzer_manager.run_all_analyzers(session, analysis_id, variants)
            
            print("✅ Specialized analyzers completed successfully")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analysis_id = int(sys.argv[1]) if len(sys.argv) > 1 else 23
    asyncio.run(run_specialized_analyzers(analysis_id))