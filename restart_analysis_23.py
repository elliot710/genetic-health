#!/usr/bin/env python3
"""
Restart analysis script for a specific analysis ID
"""
import asyncio
import sys

# Add backend to path
sys.path.append('/app')

async def restart_specific_analysis(analysis_id: int):
    """Restart a specific analysis by ID"""
    try:
        from backend.db.database import async_session_factory
        from backend.db.models import GeneticAnalysis
        from sqlalchemy import select
        
        print(f"Checking analysis {analysis_id}...")
        
        async with async_session_factory() as session:
            # Get the analysis
            stmt = select(GeneticAnalysis).where(GeneticAnalysis.id == analysis_id)
            result = await session.execute(stmt)
            analysis = result.scalar_one_or_none()
            
            if analysis:
                print(f"Found analysis {analysis.id}:")
                print(f"  Status: {analysis.analysis_status}")
                print(f"  Progress: {analysis.processed_variants}/{analysis.total_variants} ({analysis.progress_percentage}%)")
                print(f"  Current step: {analysis.current_step}")
                print()
                
                if str(analysis.analysis_status) == 'processing':
                    print("Manually restarting analysis job...")
                    
                    # Import analysis job and restart
                    from backend.services.analysis_job import AnalysisJob
                    
                    # Create new analysis job
                    job = AnalysisJob(int(analysis.user_id))
                    print("Starting analysis job in background...")
                    
                    # Start the analysis from where it left off
                    result = await job.process_analysis(analysis_id)
                    print(f"✅ Analysis completed: {result}")
                else:
                    print(f"Analysis status is '{analysis.analysis_status}', not restarting")
            else:
                print(f"❌ Analysis {analysis_id} not found")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analysis_id = int(sys.argv[1]) if len(sys.argv) > 1 else 23
    print(f"Restarting analysis {analysis_id}...")
    asyncio.run(restart_specific_analysis(analysis_id))