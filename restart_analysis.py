#!/usr/bin/env python3
"""
Script to restart genetic analysis manually
"""
import asyncio
import sys
import os

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.services.analysis_job import AnalysisJob
from backend.db.database import get_session
from backend.db.models import GeneticAnalysis
from sqlalchemy import select

async def restart_analysis(analysis_id: int):
    """Restart the analysis job for the given analysis ID"""
    
    # Create analysis job instance
    analysis_job = AnalysisJob()
    
    async for session in get_session():
        try:
            # Get the analysis
            result = await session.execute(
                select(GeneticAnalysis).where(GeneticAnalysis.id == analysis_id)
            )
            analysis = result.scalar_one_or_none()
            
            if not analysis:
                print(f"Analysis {analysis_id} not found")
                return
            
            print(f"Found analysis {analysis_id}: {analysis.filename}")
            print(f"Current status: {analysis.analysis_status}")
            print(f"Progress: {analysis.progress_percentage}%")
            print(f"Processed variants: {analysis.processed_variants}/{analysis.total_variants}")
            
            # Start the analysis
            print(f"\nStarting analysis job for analysis {analysis_id}...")
            result = await analysis_job.process_analysis(analysis_id)
            print(f"Analysis result: {result}")
            
        except Exception as e:
            print(f"Error restarting analysis: {e}")
        finally:
            await session.close()

if __name__ == "__main__":
    analysis_id = 11  # Analysis to restart
    print(f"Restarting analysis {analysis_id}...")
    asyncio.run(restart_analysis(analysis_id))