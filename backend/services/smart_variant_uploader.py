"""
Smart variant uploader that reuses existing shared variant data and annotations.
Only creates user-specific references to shared variants, avoiding any duplication.
"""
import asyncio
import logging
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert

from ..db.models import (
    GeneticAnalysis, AnalysisVariant, SharedVariantAnnotation
)

logger = logging.getLogger(__name__)


@dataclass
class VariantUploadStats:
    """Statistics for variant upload process."""
    total_variants: int
    reused_shared_variants: int
    new_shared_variants: int
    created_user_references: int
    skipped_duplicates: int
    processing_time: float


class SharedVariantSystem:
    """
    System for managing shared variants across all users.
    Ensures no duplication of variant data or annotations.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def process_variants_for_analysis(
        self, 
        analysis_id: int, 
        variants_data: List[Dict[str, Any]]
    ) -> VariantUploadStats:
        """
        Process variants for an analysis using shared variant system.
        Reuses existing shared variants and annotations, only creates user references.
        """
        start_time = asyncio.get_event_loop().time()
        
        if not variants_data:
            return VariantUploadStats(0, 0, 0, 0, 0, 0.0)
        
        # Get analysis info
        analysis = await self._get_analysis(analysis_id)
        user_id = analysis.user_id
        
        logger.info(f"Processing {len(variants_data)} variants for analysis {analysis_id} (user {user_id})")
        
        # Check for existing user references to avoid duplicates
        existing_user_variants = await self._get_existing_user_variants(analysis_id)
        
        # Filter out variants that already exist for this analysis
        new_variants = []
        skipped_count = 0
        
        for variant_data in variants_data:
            variant_key = self._get_variant_key(variant_data)
            if variant_key not in existing_user_variants:
                new_variants.append(variant_data)
            else:
                skipped_count += 1
        
        if skipped_count > 0:
            logger.info(f"Skipped {skipped_count} variants that already exist for this analysis")
        
        if not new_variants:
            processing_time = asyncio.get_event_loop().time() - start_time
            return VariantUploadStats(
                total_variants=len(variants_data),
                reused_shared_variants=0,
                new_shared_variants=0,
                created_user_references=0,
                skipped_duplicates=skipped_count,
                processing_time=processing_time
            )
        
        # Check which variants already exist in shared annotations across ALL users
        reused_count = await self._count_existing_shared_annotations(new_variants)
        
        # Create user-specific references to variants (whether shared or new)
        created_refs = await self._create_user_references(analysis_id, new_variants)
        
        processing_time = asyncio.get_event_loop().time() - start_time
        
        stats = VariantUploadStats(
            total_variants=len(variants_data),
            reused_shared_variants=reused_count,
            new_shared_variants=len(new_variants) - reused_count,
            created_user_references=created_refs,
            skipped_duplicates=skipped_count,
            processing_time=processing_time
        )
        
        logger.info(f"Upload complete: {reused_count} reused shared annotations, "
                   f"{len(new_variants) - reused_count} new variants, "
                   f"{created_refs} user references, {skipped_count} skipped")
        
        return stats
    
    async def _get_analysis(self, analysis_id: int) -> GeneticAnalysis:
        """Get analysis by ID."""
        result = await self.session.execute(
            select(GeneticAnalysis).where(GeneticAnalysis.id == analysis_id)
        )
        analysis = result.scalar_one_or_none()
        if not analysis:
            raise ValueError(f"Analysis {analysis_id} not found")
        return analysis
    
    async def _get_existing_user_variants(self, analysis_id: int) -> set:
        """Get existing variant keys for this analysis to avoid duplicates."""
        result = await self.session.execute(
            select(AnalysisVariant.chromosome, AnalysisVariant.position, 
                   AnalysisVariant.ref_allele, AnalysisVariant.alt_allele)
            .where(AnalysisVariant.analysis_id == analysis_id)
        )
        
        existing_keys = set()
        for row in result:
            key = f"{row.chromosome}:{row.position}:{row.ref_allele}:{row.alt_allele}"
            existing_keys.add(key)
        
        return existing_keys
    
    def _get_variant_key(self, variant_data: Dict[str, Any]) -> str:
        """Generate unique key for variant."""
        return f"{variant_data['chromosome']}:{variant_data['position']}:" \
               f"{variant_data['ref_allele']}:{variant_data['alt_allele']}"
    
    async def _count_existing_shared_annotations(self, variants_data: List[Dict[str, Any]]) -> int:
        """Count how many variants already have shared annotations."""
        if not variants_data:
            return 0
        
        # Get RSIDs from variants
        rsids = []
        for variant_data in variants_data:
            rsid = variant_data.get('rsid') or variant_data.get('id')
            if rsid and rsid.startswith('rs'):
                rsids.append(rsid)
        
        if not rsids:
            return 0
        
        # Check how many already exist in shared annotations
        result = await self.session.execute(
            select(func.count(SharedVariantAnnotation.id))
            .where(SharedVariantAnnotation.rsid.in_(rsids))
        )
        
        return result.scalar() or 0
    
    async def _create_user_references(self, analysis_id: int, variants_data: List[Dict[str, Any]]) -> int:
        """Create user-specific references to variants."""
        if not variants_data:
            return 0
        
        # Prepare analysis variants (user references)
        user_variants = []
        
        for variant_data in variants_data:
            # Extract user-specific data (genotype, quality, etc.)
            user_variant = {
                'analysis_id': analysis_id,
                'chromosome': variant_data['chromosome'],
                'position': variant_data['position'],
                'rsid': variant_data.get('rsid') or variant_data.get('id'),
                'ref_allele': variant_data['ref_allele'],
                'alt_allele': variant_data['alt_allele'],
                'genotype': variant_data.get('genotype'),
                'quality': variant_data.get('quality'),
                'filter_status': variant_data.get('filter', 'PASS'),
                'info': variant_data.get('info', {})
            }
            
            user_variants.append(user_variant)
        
        # Batch insert user variants
        if user_variants:
            stmt = insert(AnalysisVariant).values(user_variants)
            await self.session.execute(stmt)
            await self.session.commit()
        
        return len(user_variants)


class SmartVariantUploader:
    """
    Smart uploader that uses the shared variant system.
    Backwards compatible with the existing OptimizedVariantUploader interface.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.shared_system = SharedVariantSystem(session)
    
    async def upload_variants(
        self, 
        analysis_id: int, 
        variants_data: List[Dict[str, Any]]
    ) -> Tuple[int, VariantUploadStats]:
        """
        Upload variants using shared variant system.
        Returns (processed_count, upload_stats) for backwards compatibility.
        """
        stats = await self.shared_system.process_variants_for_analysis(
            analysis_id, variants_data
        )
        
        # Return processed count and stats
        processed_count = stats.created_user_references + stats.skipped_duplicates
        
        return processed_count, stats
