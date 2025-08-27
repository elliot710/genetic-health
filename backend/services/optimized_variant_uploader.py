"""
Simplified variant upload service for denormalized schema
"""
import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from ..db.models import AnalysisVariant

logger = logging.getLogger(__name__)


class OptimizedVariantUploader:
    """Service for efficiently uploading variants to denormalized analysis_variants table"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def upload_variants(
        self, 
        analysis_id: int, 
        variants_data: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """
        Upload variants directly to analysis_variants table
        
        Args:
            analysis_id: ID of the genetic analysis
            variants_data: List of variant dictionaries with keys:
                - chromosome, position, rsid, ref_allele, alt_allele
                - genotype, quality, filter_status, info (optional)
        
        Returns:
            Tuple of (total_variants_processed, new_variants_created)
            Note: new_variants_created will always equal total_variants_processed in denormalized schema
        """
        if not variants_data:
            return 0, 0
        
        logger.info(f"Processing {len(variants_data)} variants for analysis {analysis_id}")
        
        # Batch process variants for efficiency
        batch_size = 1000
        total_processed = 0
        
        for i in range(0, len(variants_data), batch_size):
            batch = variants_data[i:i + batch_size]
            processed = await self._process_variant_batch(analysis_id, batch)
            total_processed += processed
            
            # Commit each batch to avoid huge transactions
            await self.session.commit()
            
            if i % (batch_size * 5) == 0:  # Log every 5 batches
                logger.info(f"Processed {i + len(batch)}/{len(variants_data)} variants")
        
        logger.info(f"Upload complete: {total_processed} variants processed")
        
        return total_processed, total_processed  # All variants are "new" in denormalized schema
    
    async def _process_variant_batch(
        self, 
        analysis_id: int, 
        batch: List[Dict[str, Any]]
    ) -> int:
        """Process a batch of variants efficiently"""
        
        # Prepare analysis_variants data directly
        analysis_variants_data = []
        
        for variant in batch:
            analysis_variant_data = {
                'analysis_id': analysis_id,
                # Variant identification fields
                'chromosome': str(variant.get('chromosome', '')),
                'position': int(variant.get('position', 0)),
                'rsid': variant.get('rsid'),
                'ref_allele': str(variant.get('ref_allele', variant.get('ref', ''))),
                'alt_allele': str(variant.get('alt_allele', variant.get('alt', ''))),
                # User-specific variant data
                'genotype': variant.get('genotype'),
                'quality': variant.get('quality'),
                'filter_status': variant.get('filter_status', variant.get('filter')),
                'info': variant.get('info', {}),
            }
            analysis_variants_data.append(analysis_variant_data)
        
        # Insert analysis variants directly
        await self._create_analysis_variants(analysis_variants_data)
        
        return len(batch)
    
    async def _create_analysis_variants(self, analysis_variants_data: List[Dict[str, Any]]):
        """Create analysis variants directly"""
        
        if not analysis_variants_data:
            return
        
        # Simple bulk insert since we're no longer normalizing
        stmt = insert(AnalysisVariant).values(analysis_variants_data)
        
        await self.session.execute(stmt)
    
    async def get_variant_count_for_analysis(self, analysis_id: int) -> int:
        """Get the number of variants for an analysis"""
        
        from sqlalchemy import select, func
        query = select(func.count(AnalysisVariant.id)).where(AnalysisVariant.analysis_id == analysis_id)
        result = await self.session.execute(query)
        return result.scalar() or 0