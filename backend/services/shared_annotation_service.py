"""
Shared variant annotation service — manages the deduplication cache of
external API results (shared_variant_annotations table).
"""
import asyncio
import logging
import time
from typing import Dict, List, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func

from ..db.models import SharedVariantAnnotation, VariantAnnotation
from ..utils.alpha_missense import get_alpha_missense_service

logger = logging.getLogger(__name__)


class SharedVariantAnnotationService:
    """Service for managing shared variant annotations across users.
    
    Uses short-lived sessions per operation to avoid holding DB connections
    for extended periods during long-running analyses.
    """

    def __init__(self, session: AsyncSession = None):
        self.session = session  # Legacy: only used by remote API path (save_annotation)
        self._annotation_cache: Dict[str, Dict[str, Any]] = {}

    async def get_existing_annotations(self, rsids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get existing annotations for a list of RSIDs from shared annotations table.
        
        Uses short-lived sessions per batch to release connections back to the
        pool between iterations, preventing pool exhaustion during long analyses.
        """
        if not rsids:
            return {}

        from ..db.database import async_session_factory

        batch_size = 500
        annotation_map = {}

        total_batches = (len(rsids) + batch_size - 1) // batch_size
        logger.info(f"Checking for existing shared annotations for {len(rsids)} RSIDs in {total_batches} batches")
        lookup_start = time.time()

        from .scoring_engine import get_scoring_engine
        scorer = get_scoring_engine()

        for i in range(0, len(rsids), batch_size):
            batch_rsids = rsids[i:i + batch_size]
            batch_num = i // batch_size + 1
            if batch_num % 200 == 0 or batch_num == total_batches:
                elapsed = time.time() - lookup_start
                logger.info(f"📊 Annotation lookup batch {batch_num}/{total_batches} ({elapsed:.1f}s elapsed, {len(annotation_map)} found so far)")

            await asyncio.sleep(0.01)

            # Short-lived session per batch — releases connection between batches
            async with async_session_factory() as session:
                result = await session.execute(
                    select(SharedVariantAnnotation).where(
                        SharedVariantAnnotation.rsid.in_(batch_rsids),
                        SharedVariantAnnotation.annotation_status.in_(['completed', 'partial'])
                    )
                )
                existing_annotations = result.scalars().all()

            # Process results outside of session (pure CPU, no DB connection held).
            # Yield every 20 rows — score_variant is heavy enough that 20 calls
            # per yield keeps latency below ~5ms for other requests.
            for row_idx, annotation in enumerate(existing_annotations):
                if row_idx > 0 and row_idx % 20 == 0:
                    await asyncio.sleep(0)
                merged_data: Dict[str, Any] = {
                    'rsid': annotation.rsid,
                    'annotations': {},
                    'sources_queried': [],
                    'success_count': 0
                }

                for source in ('ensembl', 'clinvar', 'clinpgx', 'snpedia', 'litvar'):
                    data = getattr(annotation, f'{source}_data', None)
                    if data is None and source == 'clinpgx':
                        # DB column is still named pharmgkb_data for backward compat
                        data = getattr(annotation, 'pharmgkb_data', None)
                    if data is not None:
                        merged_data['annotations'][source] = data
                        merged_data['sources_queried'].append(source)
                        merged_data['success_count'] += 1

                # Include AlphaMissense data (local, not an API source)
                am_data = getattr(annotation, 'alpha_missense_data', None)
                if am_data is not None:
                    merged_data['annotations']['alpha_missense'] = am_data

                # Include ClinVar Local data (PG-backed, not an API source)
                cv_local = getattr(annotation, 'clinvar_local_data', None)
                if cv_local is not None:
                    merged_data['annotations']['clinvar_local'] = cv_local

                # Include gnomAD data (PG-backed, not an API source)
                gnomad = getattr(annotation, 'gnomad_data', None)
                if gnomad is not None:
                    merged_data['annotations']['gnomad'] = gnomad

                # Include 1000 Genomes Phase 3 data (PG-backed)
                tkg = getattr(annotation, 'thousand_genomes_data', None)
                if tkg is not None:
                    merged_data['annotations']['thousand_genomes'] = tkg

                # Include BigQuery data (ChEMBL, FDA Drug, AlphaFold)
                for bq_src, bq_col in (('chembl', 'chembl_data'), ('fda_drug', 'fda_drug_data'), ('alphafold', 'alphafold_data')):
                    bq_data = getattr(annotation, bq_col, None)
                    if bq_data is not None:
                        merged_data['annotations'][bq_src] = bq_data

                # Compute composite pathogenicity score
                merged_data['pathogenicity_score'] = scorer.score_variant(
                    merged_data['annotations']
                )

                if merged_data['success_count'] > 0:
                    annotation_map[annotation.rsid] = merged_data

        if annotation_map:
            # Chunk usage_count updates to stay under PostgreSQL's 32767 parameter limit.
            # Use one short-lived session per chunk so connections are released between
            # batches rather than held for the entire update (can be 10s+ for large analyses).
            found_rsids = list(annotation_map.keys())
            UPDATE_BATCH = 30000
            for j in range(0, len(found_rsids), UPDATE_BATCH):
                batch = found_rsids[j:j + UPDATE_BATCH]
                async with async_session_factory() as update_session:
                    await update_session.execute(
                        update(SharedVariantAnnotation)
                        .where(SharedVariantAnnotation.rsid.in_(batch))
                        .values(
                            usage_count=SharedVariantAnnotation.usage_count + 1,
                            last_updated_at=func.now()
                        )
                    )
                    await update_session.commit()
                await asyncio.sleep(0)
        elapsed = time.time() - lookup_start
        logger.info(f"Found {len(annotation_map)} existing shared annotations for {len(rsids)} requested RSIDs ({elapsed:.1f}s)")
        return annotation_map

    async def save_annotation(
        self,
        rsid: str,
        annotation_data: Dict[str, Any],
        analysis_id: int,
        analysis_variant_id: int,
        marker_id: int = None,
        enabled_sources: Optional[List[str]] = None,
        rsid_gene_map: Optional[Dict[str, str]] = None
    ) -> bool:
        """Save new annotation data to shared system and create user reference."""
        try:
            annotations = annotation_data.get('annotations', {})
            sources_queried = annotation_data.get('sources_queried', ['ensembl', 'clinvar', 'clinpgx', 'snpedia'])
            success_count = annotation_data.get('success_count', 0)

            # Determine which sources failed (queried but threw errors / returned None)
            # A response with found=False means the API confirmed no data exists — that's not a failure
            failed = []
            for src in sources_queried:
                src_data = annotations.get(src)
                if src_data is None:
                    # Source was queried but returned nothing (error/timeout)
                    failed.append(src)
                # found=False with a dict response = confirmed absence, NOT a failure

            total_sources = len(sources_queried)
            if failed:
                status = 'partial' if success_count > 0 else 'failed'
            else:
                status = 'completed'

            # Look up AlphaMissense prediction from local data (comprehensive)
            am_data = None
            if enabled_sources is None or 'alpha_missense' in enabled_sources:
                ensembl_ann = annotations.get('ensembl', {})
            if ensembl_ann and ensembl_ann.get('found') and ensembl_ann.get('data'):
                e_entry = ensembl_ann['data'][0] if isinstance(ensembl_ann['data'], list) else ensembl_ann['data']
                chrom = e_entry.get('seq_region_name')
                pos = e_entry.get('start')
                allele_str = e_entry.get('allele_string', '')
                parts = allele_str.split('/') if allele_str else []
                if chrom and pos and len(parts) == 2:
                    ref, alt = parts[0], parts[1]
                    if len(ref) == 1 and len(alt) == 1:
                        am_svc = get_alpha_missense_service()
                        am_data = am_svc.lookup_comprehensive(str(chrom), int(pos), ref, alt)

            # Look up ClinVar local data (PostgreSQL-backed)
            cv_local_data = None
            if enabled_sources is None or 'clinvar_local' in enabled_sources:
                from .clinvar_local import get_clinvar_local_service
                cv_svc = get_clinvar_local_service()
                if cv_svc.is_loaded:
                    cv_local_data = await cv_svc.lookup(rsid)

            # Look up gnomAD data (PG-only during bulk analysis — no BQ fallback)
            gnomad_data_val = None
            if enabled_sources is None or 'gnomad' in enabled_sources:
                from .gnomad_local import get_gnomad_service
                gnomad_svc = get_gnomad_service()
                if gnomad_svc.is_loaded:
                    gnomad_data_val = await gnomad_svc.lookup(rsid, local_only=True)

            # Look up 1000 Genomes Phase 3 data
            thousand_genomes_data_val = None
            if enabled_sources is None or 'thousand_genomes' in enabled_sources:
                from .thousand_genomes_local import get_thousand_genomes_service
                tkg_svc = get_thousand_genomes_service()
                if tkg_svc.is_loaded:
                    thousand_genomes_data_val = await tkg_svc.lookup(rsid)
                    if thousand_genomes_data_val and not thousand_genomes_data_val.get('found'):
                        thousand_genomes_data_val = None

            # Look up gnomAD tx_annotated data (gene/csq/LoF/tissue expression)
            gnomad_tx_data_val = None
            if enabled_sources is None or 'gnomad_tx' in enabled_sources:
                ensembl_for_tx = annotations.get('ensembl', {})
                if ensembl_for_tx and ensembl_for_tx.get('found') and ensembl_for_tx.get('data'):
                    e_tx = ensembl_for_tx['data'][0] if isinstance(ensembl_for_tx['data'], list) else ensembl_for_tx['data']
                    tx_chrom = e_tx.get('seq_region_name')
                    tx_pos = e_tx.get('start')
                    tx_allele_str = e_tx.get('allele_string', '')
                    tx_parts = tx_allele_str.split('/') if tx_allele_str else []
                    if tx_chrom and tx_pos and len(tx_parts) == 2:
                        tx_ref, tx_alt = tx_parts[0], tx_parts[1]
                        if len(tx_ref) == 1 and len(tx_alt) == 1:
                            from .gnomad_tx import get_gnomad_tx_service
                            gtx_svc = get_gnomad_tx_service()
                            if gtx_svc.available:
                                gnomad_tx_data_val = await gtx_svc.lookup(str(tx_chrom), int(tx_pos), tx_ref, tx_alt)

            # BigQuery enrichment (ChEMBL, FDA Drug, AlphaFold) is deferred to
            # backfill / on-demand variant-detail to avoid blocking bulk analysis.
            chembl_data_val = None
            fda_drug_data_val = None
            alphafold_data_val = None

            from sqlalchemy.dialects.postgresql import insert
            values = dict(
                rsid=rsid,
                ensembl_data=annotations.get('ensembl'),
                clinvar_data=annotations.get('clinvar'),
                pharmgkb_data=annotations.get('clinpgx'),
                snpedia_data=annotations.get('snpedia'),
                litvar_data=annotations.get('litvar'),
                annotation_status=status,
                failed_sources=failed if failed else None,
                total_api_calls=success_count,
                usage_count=1
            )
            # Only set local source columns when there's actual data (not None).
            # Leaving them out of the INSERT keeps SQL NULL → backfill will
            # populate them later.  Previously, None was written as JSON null
            # which is NOT the same as SQL NULL.
            if am_data is not None:
                values['alpha_missense_data'] = am_data
            if cv_local_data is not None:
                values['clinvar_local_data'] = cv_local_data
            if gnomad_data_val is not None:
                values['gnomad_data'] = gnomad_data_val
            if thousand_genomes_data_val is not None:
                values['thousand_genomes_data'] = thousand_genomes_data_val
            if gnomad_tx_data_val is not None:
                values['gnomad_tx_data'] = gnomad_tx_data_val
            if chembl_data_val is not None:
                values['chembl_data'] = chembl_data_val
            if fda_drug_data_val is not None:
                values['fda_drug_data'] = fda_drug_data_val
            if alphafold_data_val is not None:
                values['alphafold_data'] = alphafold_data_val
            if marker_id is not None:
                values['marker_id'] = marker_id
            stmt = insert(SharedVariantAnnotation).values(**values)
            # Build the conflict-update dict — always bump usage_count and
            # back-fill any columns that were previously NULL.
            conflict_set = dict(
                usage_count=SharedVariantAnnotation.usage_count + 1,
                last_updated_at=func.now(),
                total_api_calls=func.greatest(
                    SharedVariantAnnotation.total_api_calls,
                    stmt.excluded.total_api_calls
                ),
            )
            # Back-fill NULL data columns with new values (coalesce keeps existing)
            for col_name, ann_key in [
                ('ensembl_data', 'ensembl'),
                ('clinvar_data', 'clinvar'),
                ('pharmgkb_data', 'clinpgx'),
                ('snpedia_data', 'snpedia'),
                ('litvar_data', 'litvar'),
            ]:
                val = annotations.get(ann_key)
                if val is not None:
                    col = getattr(SharedVariantAnnotation, col_name)
                    conflict_set[col_name] = func.coalesce(col, stmt.excluded[col_name])
            if am_data:
                conflict_set['alpha_missense_data'] = func.coalesce(
                    SharedVariantAnnotation.alpha_missense_data,
                    stmt.excluded.alpha_missense_data,
                )
            if cv_local_data:
                conflict_set['clinvar_local_data'] = func.coalesce(
                    SharedVariantAnnotation.clinvar_local_data,
                    stmt.excluded.clinvar_local_data,
                )
            if gnomad_data_val:
                conflict_set['gnomad_data'] = func.coalesce(
                    SharedVariantAnnotation.gnomad_data,
                    stmt.excluded.gnomad_data,
                )
            if thousand_genomes_data_val:
                conflict_set['thousand_genomes_data'] = func.coalesce(
                    SharedVariantAnnotation.thousand_genomes_data,
                    stmt.excluded.thousand_genomes_data,
                )
            if gnomad_tx_data_val:
                conflict_set['gnomad_tx_data'] = func.coalesce(
                    SharedVariantAnnotation.gnomad_tx_data,
                    stmt.excluded.gnomad_tx_data,
                )
            if chembl_data_val:
                conflict_set['chembl_data'] = func.coalesce(
                    SharedVariantAnnotation.chembl_data,
                    stmt.excluded.chembl_data,
                )
            if fda_drug_data_val:
                conflict_set['fda_drug_data'] = func.coalesce(
                    SharedVariantAnnotation.fda_drug_data,
                    stmt.excluded.fda_drug_data,
                )
            if alphafold_data_val:
                conflict_set['alphafold_data'] = func.coalesce(
                    SharedVariantAnnotation.alphafold_data,
                    stmt.excluded.alphafold_data,
                )

            # Recalculate annotation_status & failed_sources after the merge.
            # A source is "failed" only when its column is still NULL after
            # merging old + new data.  found=false is a confirmed absence, not
            # a failure.
            merged_ensembl  = func.coalesce(SharedVariantAnnotation.ensembl_data,  stmt.excluded.ensembl_data)
            merged_clinvar  = func.coalesce(SharedVariantAnnotation.clinvar_data,  stmt.excluded.clinvar_data)
            merged_pharmgkb = func.coalesce(SharedVariantAnnotation.pharmgkb_data, stmt.excluded.pharmgkb_data)
            merged_snpedia  = func.coalesce(SharedVariantAnnotation.snpedia_data,  stmt.excluded.snpedia_data)

            # Status: 'completed' when all 4 core columns are non-NULL
            from sqlalchemy import case, literal
            conflict_set['annotation_status'] = case(
                (
                    (merged_ensembl.isnot(None))
                    & (merged_clinvar.isnot(None))
                    & (merged_pharmgkb.isnot(None))
                    & (merged_snpedia.isnot(None)),
                    literal('completed')
                ),
                else_=literal('partial'),
            )
            # Clear failed_sources when completed
            conflict_set['failed_sources'] = case(
                (
                    (merged_ensembl.isnot(None))
                    & (merged_clinvar.isnot(None))
                    & (merged_pharmgkb.isnot(None))
                    & (merged_snpedia.isnot(None)),
                    None
                ),
                else_=stmt.excluded.failed_sources,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=['rsid'],
                set_=conflict_set,
            ).returning(SharedVariantAnnotation.id)

            # Use a short-lived session for each save operation
            from ..db.database import async_session_factory
            async with async_session_factory() as save_session:
                result = await save_session.execute(stmt)
                shared_annotation_id = result.scalar_one()

                # Use INSERT ... ON CONFLICT DO NOTHING to handle resume/retry
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                va_stmt = pg_insert(VariantAnnotation).values(
                    analysis_id=analysis_id,
                    analysis_variant_id=analysis_variant_id,
                    shared_annotation_id=shared_annotation_id,
                    rsid=rsid
                ).on_conflict_do_nothing(
                    constraint='uq_variant_annotations_analysis_variant'
                )
                await save_session.execute(va_stmt)
                await save_session.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to save annotation for {rsid}: {e}")
            return False
