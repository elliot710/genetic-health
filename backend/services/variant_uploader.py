"""
Variant upload service with global marker deduplication.

Upload flow:
1. Extract unique markers (rsid/chr/pos/ref/alt) from the uploaded file
2. Upsert into genetic_markers (global catalog, never deleted)
3. Create analysis_variants linking the user's analysis to the markers + their genotype
"""
import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

from ..db.models import GeneticMarker, AnalysisVariant
from ..core.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class VariantUploader:
    """
    Uploads genetic variants with deduplication against a global marker catalog.
    
    - New markers are added to genetic_markers (never deleted).
    - Existing markers get their upload_count incremented.
    - User-specific genotype data is stored in analysis_variants linked to the marker.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def upload_variants(
        self, 
        analysis_id: int, 
        variants_data: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """
        Upload variants: upsert global markers, then link to this analysis.
        
        Returns:
            Tuple of (total_variants_processed, new_markers_created)
        """
        if not variants_data:
            return 0, 0
        
        with tracer.start_as_current_span("upload.variants") as span:
            span.set_attribute("analysis.id", analysis_id)
            span.set_attribute("variants.input", len(variants_data))

            logger.info(f"Processing {len(variants_data)} variants for analysis {analysis_id}")

            batch_size = 1000
            total_processed = 0
            total_new_markers = 0

            for i in range(0, len(variants_data), batch_size):
                batch = variants_data[i:i + batch_size]
                processed, new_markers = await self._process_variant_batch(analysis_id, batch)
                total_processed += processed
                total_new_markers += new_markers

                await self.session.commit()

                if i % (batch_size * 5) == 0:
                    logger.info(f"Processed {i + len(batch)}/{len(variants_data)} variants ({total_new_markers} new markers)")

            logger.info(f"Upload complete: {total_processed} variants, {total_new_markers} new markers, {total_processed - total_new_markers} reused")

            span.set_attribute("variants.processed", total_processed)
            span.set_attribute("markers.new", total_new_markers)
            span.set_attribute("markers.reused", total_processed - total_new_markers)

            return total_processed, total_new_markers
            
            alt = str(variant.get('alt_allele', variant.get('alt', '')))
            
            if rsid in marker_map:
                existing_alts = set(marker_map[rsid]['alt_alleles'].split(',')) if marker_map[rsid]['alt_alleles'] else set()
                existing_alts.add(alt)
                marker_map[rsid]['alt_alleles'] = ','.join(sorted(existing_alts))
            else:
                marker_map[rsid] = {
                    'rsid': rsid,
                    'chromosome': str(variant.get('chromosome', '')),
                    'position': int(variant.get('position', 0)),
                    'ref_allele': str(variant.get('ref_allele', variant.get('ref', ''))),
                    'alt_alleles': alt,
                }
        
        # 2. Upsert markers into global catalog
        new_marker_count = 0
        rsid_to_marker_id = {}
        
        if marker_map:
            new_marker_count = await self._upsert_markers(list(marker_map.values()))
            
            rsids = list(marker_map.keys())
            result = await self.session.execute(
                select(GeneticMarker.id, GeneticMarker.rsid).where(
                    GeneticMarker.rsid.in_(rsids)
                )
            )
            for row in result:
                rsid_to_marker_id[row.rsid] = row.id
        
        # 3. Create analysis_variant links
        analysis_variants_data = []
        for variant in batch:
            rsid = variant.get('rsid')
            marker_id = rsid_to_marker_id.get(rsid)
            if not marker_id:
                continue
            
            analysis_variants_data.append({
                'analysis_id': analysis_id,
                'marker_id': marker_id,
                'genotype': variant.get('genotype'),
                'quality': variant.get('quality'),
                'filter_status': variant.get('filter_status', variant.get('filter')),
                'info': variant.get('info', {}),
            })
        
        if analysis_variants_data:
            stmt = pg_insert(AnalysisVariant).values(analysis_variants_data)
            await self.session.execute(stmt)
        
        return len(analysis_variants_data), new_marker_count
    
    async def _upsert_markers(self, markers_data: List[Dict[str, Any]]) -> int:
        """
        Upsert markers into genetic_markers. On conflict (rsid already exists),
        increment upload_count and merge alt_alleles. Returns count of NEW markers.
        """
        if not markers_data:
            return 0
        
        rsids = [m['rsid'] for m in markers_data]
        result = await self.session.execute(
            select(GeneticMarker.rsid).where(GeneticMarker.rsid.in_(rsids))
        )
        existing_rsids = {row.rsid for row in result}
        new_count = len(set(rsids) - existing_rsids)
        
        stmt = pg_insert(GeneticMarker).values(markers_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=['rsid'],
            set_={
                'upload_count': GeneticMarker.upload_count + 1,
            }
        )
        await self.session.execute(stmt)
        
        return new_count
    
    async def get_variant_count_for_analysis(self, analysis_id: int) -> int:
        """Get the number of variants for an analysis."""
        from sqlalchemy import func
        query = select(func.count(AnalysisVariant.id)).where(AnalysisVariant.analysis_id == analysis_id)
        result = await self.session.execute(query)
        return result.scalar() or 0
