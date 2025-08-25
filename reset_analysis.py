#!/usr/bin/env python3
"""
Reset the stuck analysis to allow it to restart
"""
import asyncio
import logging
from backend.db.database import get_session
from backend.db.models import GeneticAnalysis
from sqlalchemy import update

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def reset_stuck_analysis():
    """Reset analysis 25 to allow restart"""
    async for session in get_session():
        try:
            # Reset the analysis status
            update_query = update(GeneticAnalysis).where(
                GeneticAnalysis.id == 25
            ).values(
                analysis_status='pending',
                progress_percentage=0,
                current_step='Ready to start',
                processed_variants=0
            )
            
            await session.execute(update_query)
            await session.commit()
            
            logger.info("✅ Analysis 25 has been reset to 'pending' status")
            logger.info("🔄 You can now restart the analysis from the UI")
            
        except Exception as e:
            logger.error(f"❌ Failed to reset analysis: {e}")
            await session.rollback()

if __name__ == "__main__":
    asyncio.run(reset_stuck_analysis())