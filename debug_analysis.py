#!/usr/bin/env python3
"""
Debug script to check analysis and variant data
"""
import asyncio
import logging
from backend.db.database import get_session
from backend.db.models import GeneticAnalysis, GeneticVariant
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_analysis():
    """Check analysis and variant data"""
    async for session in get_session():
        # Get all analyses
        result = await session.execute(
            select(GeneticAnalysis).options(selectinload(GeneticAnalysis.variants))
        )
        analyses = result.scalars().all()
        
        logger.info(f"📊 Found {len(analyses)} total analyses")
        
        for analysis in analyses:
            logger.info(f"\n🔍 Analysis {analysis.id}:")
            logger.info(f"  - Filename: {analysis.filename}")
            logger.info(f"  - Status: {analysis.analysis_status}")
            logger.info(f"  - Progress: {analysis.progress_percentage}%")
            logger.info(f"  - Current step: {analysis.current_step}")
            logger.info(f"  - Total variants in DB: {len(analysis.variants) if analysis.variants else 0}")
            logger.info(f"  - Recorded total_variants: {analysis.total_variants}")
            logger.info(f"  - Processed variants: {analysis.processed_variants}")
            
            if analysis.variants:
                sample_variants = analysis.variants[:3]
                logger.info(f"  - Sample variants:")
                for variant in sample_variants:
                    logger.info(f"    * {variant.rsid} on chr{variant.chromosome}:{variant.position}")
            
            # Check if this is the current analysis causing issues
            if str(analysis.analysis_status) == 'processing' and (analysis.progress_percentage or 0) == 0:
                logger.warning(f"⚠️ Analysis {analysis.id} appears to be stuck in processing with 0% progress")

if __name__ == "__main__":
    asyncio.run(debug_analysis())