"""
Annotation coordination — extracted from analysis_service.py.

Handles:
- Efficient variant annotation with reuse (Phase 2)
- BigQuery enrichment (Phase 3)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import select, func, text

from ..db.database import async_session_factory
from ..db.models import (
    SharedVariantAnnotation, VariantAnnotation,
)
from ..core.config import settings
from .analysis_service import AnalysisProgress
from .variant_types import AnnotationResult

logger = logging.getLogger(__name__)

_BQ_COL_MAP: Dict[str, str] = {
    'chembl': 'chembl_data',
    'fda_drug': 'fda_drug_data',
    'alphafold': 'alphafold_data',
}


def _truthy_data(d: Any) -> Optional[Dict]:
    return d if (d and d.get('found')) else None


def _build_annotation_link_values(
    rsid_to_variants: Dict[str, List],
    chunk_rsids: List[str],
    rsid_to_shared_id: Dict[str, int],
    analysis_id: int,
) -> List[Dict]:
    link_values = []
    for rsid in chunk_rsids:
        shared_id = rsid_to_shared_id.get(rsid)
        if shared_id is None:
            continue
        for v in rsid_to_variants[rsid]:
            link_values.append(dict(
                analysis_id=analysis_id,
                analysis_variant_id=getattr(v, 'id'),
                shared_annotation_id=shared_id,
                rsid=rsid,
            ))
    return link_values


async def _insert_annotation_links(session, link_values: List[Dict]) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    if not link_values:
        return
    link_stmt = pg_insert(VariantAnnotation).values(link_values)
    link_stmt = link_stmt.on_conflict_do_nothing(
        constraint='uq_variant_annotations_analysis_variant'
    )
    await session.execute(link_stmt)


async def _fetch_remote_api_data(rsids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Fetch only remote API columns from shared_variant_annotations.

    Only returns rows where at least one remote column is non-null —
    typically a small fraction of all variants.  Uses a single ANY() query
    per 100K chunk so this stays fast regardless of corpus size.
    """
    if not rsids:
        return {}

    sql = text("""
        SELECT rsid, clinvar_data, pharmgkb_data, snpedia_data, litvar_data
        FROM shared_variant_annotations
        WHERE rsid = ANY(:rsids)
          AND (clinvar_data IS NOT NULL
               OR pharmgkb_data IS NOT NULL
               OR snpedia_data IS NOT NULL
               OR litvar_data IS NOT NULL)
    """)

    result_map: Dict[str, Dict[str, Any]] = {}
    CHUNK = 100_000
    for i in range(0, len(rsids), CHUNK):
        chunk = rsids[i:i + CHUNK]
        if i:
            await asyncio.sleep(0)
        async with async_session_factory() as session:
            rows = (await session.execute(sql, {'rsids': chunk})).fetchall()
        for row in rows:
            remote: Dict[str, Any] = {}
            if row[1] is not None:
                remote['clinvar'] = row[1]
            if row[2] is not None:
                remote['clinpgx'] = row[2]
            if row[3] is not None:
                remote['snpedia'] = row[3]
            if row[4] is not None:
                remote['litvar'] = row[4]
            if remote:
                result_map[row[0]] = remote
    return result_map


async def annotate_variants_efficiently(
    variants: List,
    analysis_id: int,
    progress: AnalysisProgress,
    *,
    api_service=None,
    enabled_sources: Optional[List[str]] = None,
    rsid_gene_map: Optional[Dict[str, str]] = None,
    update_progress_fn: Optional[Callable] = None,
    check_cancelled_fn: Optional[Callable] = None,
) -> Dict[str, AnnotationResult]:
    """Annotate variants using data_sources files as the primary authority.

    New flow (replaces the old PG-cache-first approach):
    1. Run all local sources FRESH from data_sources files for every RSID.
       Never reads local columns from shared_variant_annotations — the PG
       cache is sparse/incomplete and stale data would pollute results.
    2. Fetch ONLY remote API columns (pharmgkb, snpedia, litvar, clinvar)
       from shared_variant_annotations — these are expensive to re-fetch
       and safe to cache.  Uses a targeted ANY() query (not a full scan).
    3. Upsert fresh local data back to shared_variant_annotations so remote
       API enrichment (Phase 3) can add to the same rows.
    4. Build AnnotationResult objects combining local + remote.
    """
    from .local_annotation import (
        load_local_sources, build_rsid_variant_map,
        run_all_lookups, NOT_FOUND,
    )
    from .variant_loader import load_enabled_sources

    variants_with_rsid = [
        v for v in variants
        if v.rsid is not None and str(v.rsid).startswith('rs')
    ]
    if not variants_with_rsid:
        return {}

    # Deduplicate rsids
    rsid_to_variants: Dict[str, List] = {}
    for v in variants_with_rsid:
        rsid_to_variants.setdefault(str(v.rsid), []).append(v)
    unique_rsids = list(rsid_to_variants.keys())
    rsid_to_variant = {rsid: vlist[0] for rsid, vlist in rsid_to_variants.items()}

    skipped = len(variants) - len(variants_with_rsid)
    logger.info(
        f"Phase 2: {len(unique_rsids)} unique RSIDs "
        f"({len(variants_with_rsid)} variants{f', {skipped} skipped (no rsid)' if skipped else ''})"
    )

    if enabled_sources is None:
        enabled_sources = await load_enabled_sources()

    # ── Step 2a: local sources fresh from data_sources ─────────────────────
    t0 = time.time()
    logger.info("  2a: loading local sources from data_sources files (always-fresh)...")
    sources = await load_local_sources(enabled_sources)
    active = sources.active_names
    logger.info(f"     Sources ready: {', '.join(active) if active else 'none'}")

    results = await run_all_lookups(sources, unique_rsids, rsid_to_variant)

    # Update progress after lookups
    progress.processed_variants = len(unique_rsids)
    progress.phase_progress = 0.5
    if update_progress_fn:
        await update_progress_fn(analysis_id, progress)
    logger.info(f"  2a done: {time.time() - t0:.1f}s")

    # ── Step 2b: remote API cache from PG (small targeted query) ───────────
    t0 = time.time()
    logger.info("  2b: fetching remote API cache (clinvar/pharmgkb/snpedia/litvar)...")
    remote_data = await _fetch_remote_api_data(unique_rsids)
    logger.info(f"     {len(remote_data)} RSIDs have remote API data  ({time.time() - t0:.1f}s)")

    # ── Step 2c: upsert fresh local data + build AnnotationResult objects ──
    t0 = time.time()
    logger.info("  2c: upserting to shared_variant_annotations...")
    from sqlalchemy.dialects.postgresql import insert

    annotation_results: Dict[str, AnnotationResult] = {}
    BATCH = 500
    total = len(unique_rsids)
    saved_count = 0
    last_log = time.time()

    for i in range(0, total, BATCH):
        chunk_rsids = unique_rsids[i:i + BATCH]

        batch_rows = []
        for rsid in chunk_rsids:
            cv_val  = _truthy_data(results.clinvar.get(rsid))
            gn_val  = _truthy_data(results.gnomad.get(rsid))
            ens_val = _truthy_data(results.ensembl.get(rsid))
            tkg_val = _truthy_data(results.thousand_genomes.get(rsid))
            am_val  = _truthy_data(results.alpha_missense.get(rsid))
            gtx_val = _truthy_data(results.gnomad_tx.get(rsid))
            af_val  = _truthy_data(results.alphafold.get(rsid))
            gwas_val = _truthy_data(results.gwas_catalog.get(rsid))
            cg_val  = _truthy_data(results.clingen.get(rsid))
            first_v = rsid_to_variants[rsid][0]

            row: Dict[str, Any] = dict(
                rsid=rsid,
                annotation_status='partial',
                total_api_calls=0,
                usage_count=1,
                clinvar_local_data=cv_val,
                gnomad_data=gn_val,
                gnomad_tx_data=gtx_val,
                ensembl_data=ens_val,
                thousand_genomes_data=tkg_val,
                alpha_missense_data=am_val,
                alphafold_data=af_val,
                gwas_catalog_data=gwas_val,
                clingen_data=cg_val,
            )
            mid = getattr(first_v, 'marker_id', None)
            if mid is not None:
                row['marker_id'] = mid
            batch_rows.append(row)

        # Build ON CONFLICT SET — always overwrite local columns for loaded
        # sources; for unloaded sources fall back to coalesce (keep existing).
        conflict_set: Dict[str, Any] = {
            'usage_count': SharedVariantAnnotation.usage_count + 1,
            'last_updated_at': func.now(),
        }
        local_col_map = {
            'clinvar_local':    ('clinvar_local_data',    sources.clinvar),
            'gnomad':           ('gnomad_data',           sources.gnomad),
            'gnomad_tx':        ('gnomad_tx_data',        sources.gnomad_tx),
            'ensembl':          ('ensembl_data',          sources.ensembl_vep),
            'thousand_genomes': ('thousand_genomes_data', sources.thousand_genomes),
            'alpha_missense':   ('alpha_missense_data',   sources.alpha_missense),
            'alphafold':        ('alphafold_data',        sources.alphafold),
            'gwas_catalog':     ('gwas_catalog_data',     sources.gwas_catalog),
            'clingen':          ('clingen_data',          sources.clingen),
        }
        stmt = insert(SharedVariantAnnotation).values(batch_rows)
        for _src, (col, svc) in local_col_map.items():
            excl = getattr(stmt.excluded, col)
            existing = getattr(SharedVariantAnnotation, col)
            if svc:  # source was loaded → trust fresh data (overwrite)
                conflict_set[col] = excl
            else:    # source not loaded → keep existing PG value if any
                conflict_set[col] = func.coalesce(existing, excl)

        stmt = stmt.on_conflict_do_update(
            index_elements=['rsid'],
            set_=conflict_set,
        ).returning(SharedVariantAnnotation.id, SharedVariantAnnotation.rsid)

        async with async_session_factory() as session:
            db_result = await session.execute(stmt)
            rsid_to_shared_id = {row.rsid: row.id for row in db_result.all()}
            link_values = _build_annotation_link_values(
                rsid_to_variants, chunk_rsids, rsid_to_shared_id, analysis_id
            )
            await _insert_annotation_links(session, link_values)
            await session.commit()

        # Build annotation_results for this chunk
        for rsid in chunk_rsids:
            cv_val  = _truthy_data(results.clinvar.get(rsid))
            gn_val  = _truthy_data(results.gnomad.get(rsid))
            ens_val = _truthy_data(results.ensembl.get(rsid))
            tkg_val = _truthy_data(results.thousand_genomes.get(rsid))
            am_val  = _truthy_data(results.alpha_missense.get(rsid))
            gtx_val = _truthy_data(results.gnomad_tx.get(rsid))
            af_val  = _truthy_data(results.alphafold.get(rsid))
            gwas_val = _truthy_data(results.gwas_catalog.get(rsid))
            cg_val  = _truthy_data(results.clingen.get(rsid))
            remote  = remote_data.get(rsid, {})

            ann: Dict[str, Any] = {
                'rsid': rsid,
                'annotations': {},
                'sources_queried': [],
                'success_count': 0,
            }
            for key, val in [
                ('clinvar_local', cv_val),
                ('gnomad',        gn_val),
                ('ensembl',       ens_val),
                ('thousand_genomes', tkg_val),
                ('alpha_missense', am_val),
                ('gnomad_tx',     gtx_val),
                ('alphafold',     af_val),
                ('gwas_catalog',  gwas_val),
                ('clingen',       cg_val),
                ('clinvar',       remote.get('clinvar')),
                ('clinpgx',       remote.get('clinpgx')),
                ('snpedia',       remote.get('snpedia')),
                ('litvar',        remote.get('litvar')),
            ]:
                if val:
                    ann['annotations'][key] = val
                    ann['sources_queried'].append(key)
                    ann['success_count'] += 1

            annotation_results[rsid] = AnnotationResult(
                rsid=rsid, was_reused=bool(remote),
                annotation_data=ann, source='local'
            )
            saved_count += 1

        progress.annotated_variants += sum(len(rsid_to_variants[r]) for r in chunk_rsids)
        progress.new_annotations += len(chunk_rsids)
        progress.processed_variants = progress.annotated_variants
        progress.phase_progress = 0.5 + 0.5 * (i + BATCH) / max(1, total)
        if update_progress_fn:
            now = time.time()
            if now - last_log >= 5.0 or i + BATCH >= total:
                last_log = now
                await update_progress_fn(analysis_id, progress)

        chunk_num = i // BATCH + 1
        total_chunks = (total + BATCH - 1) // BATCH
        if chunk_num % 50 == 0 or chunk_num == total_chunks:
            elapsed = time.time() - t0
            logger.info(
                f"  2c: {saved_count}/{total} RSIDs upserted ({elapsed:.1f}s)"
            )

        await asyncio.sleep(0)

    progress.reused_annotations = len(annotation_results)
    progress.new_annotations = 0
    elapsed_upsert = time.time() - t0
    logger.info(
        f"  2c done: {saved_count} RSIDs upserted in {elapsed_upsert:.1f}s "
        f"| {len(remote_data)} with remote API cache"
    )
    return annotation_results


async def bulk_enrich_bigquery(
    annotation_results: Dict[str, AnnotationResult],
    analysis_id: int,
    rsid_gene_map: Dict[str, str],
    progress: Optional[AnalysisProgress] = None,
    *,
    enabled_sources: Optional[List[str]] = None,
    check_cancelled_fn: Optional[Callable] = None,
    update_progress_fn: Optional[Callable] = None,
):
    """Bulk-enrich annotations with BigQuery data (ChEMBL, FDA Drug).
    AlphaFold is handled locally via alphafold_local.py when the DB is available.
    """
    from .variant_loader import load_enabled_sources as _load_enabled_sources

    if enabled_sources is None:
        enabled_sources = await _load_enabled_sources()

    bq_source_names = {'chembl', 'fda_drug'}  # alphafold moved to local
    # If alphafold was explicitly requested and local DB is not present, fall back to BQ
    if 'alphafold' in (enabled_sources or []):
        from .alphafold_local import get_alphafold_local_service
        af_svc = get_alphafold_local_service()
        if not af_svc.available:
            logger.info("AlphaFold local DB not available — adding to BigQuery fallback")
            bq_source_names = bq_source_names | {'alphafold'}

    enabled_bq = bq_source_names & set(enabled_sources) if enabled_sources else bq_source_names
    if not enabled_bq:
        return

    gene_to_rsids: Dict[str, List[str]] = {}
    for rsid, ar in annotation_results.items():
        gene = rsid_gene_map.get(rsid)
        if not gene and ar.annotation_data:
            cv = ar.annotation_data.get('annotations', {}).get('clinvar_local', {})
            if cv and cv.get('found'):
                genes = cv.get('genes', [])
                gene = genes[0] if genes else None
        if not gene and ar.annotation_data:
            gn = ar.annotation_data.get('annotations', {}).get('gnomad', {})
            if gn and gn.get('found') and gn.get('gene'):
                gene = gn['gene']
        if gene:
            gene_to_rsids.setdefault(gene, []).append(rsid)

    if not gene_to_rsids:
        logger.info("BigQuery enrichment: no genes found, skipping")
        return

    unique_genes = list(gene_to_rsids.keys())
    total_genes = len(unique_genes)
    logger.info(f"BigQuery enrichment: {total_genes} unique genes covering "
                 f"{sum(len(v) for v in gene_to_rsids.values())} variants")

    # Determine which genes are already enriched
    already_enriched: set = set()
    try:
        all_gene_rsids = []
        for rsids_list in gene_to_rsids.values():
            all_gene_rsids.extend(rsids_list)

        async with async_session_factory() as session:
            from sqlalchemy import and_
            bq_columns = [getattr(SharedVariantAnnotation, _BQ_COL_MAP[s]) for s in enabled_bq]
            filters = [col.isnot(None) for col in bq_columns]

            BATCH_SIZE = 30000
            enriched_rsids: set = set()
            for batch_start in range(0, len(all_gene_rsids), BATCH_SIZE):
                batch = all_gene_rsids[batch_start:batch_start + BATCH_SIZE]
                result = await session.execute(
                    select(SharedVariantAnnotation.rsid)
                    .where(
                        SharedVariantAnnotation.rsid.in_(batch),
                        and_(*filters)
                    )
                )
                enriched_rsids.update(r[0] for r in result.all())

        for gene, rsids_for_gene in gene_to_rsids.items():
            if all(r in enriched_rsids for r in rsids_for_gene):
                already_enriched.add(gene)

        if already_enriched:
            logger.info(f"BigQuery enrichment: skipping {len(already_enriched)} already-enriched genes")

            for gene in already_enriched:
                rsids_for_gene = gene_to_rsids[gene]
                async with async_session_factory() as session:
                    result = await session.execute(
                        select(SharedVariantAnnotation)
                        .where(SharedVariantAnnotation.rsid.in_(rsids_for_gene))
                    )
                    rows = result.scalars().all()
                for sa in rows:
                    ar = annotation_results.get(sa.rsid)
                    if ar and ar.annotation_data:
                        for src, col in _BQ_COL_MAP.items():
                            data = getattr(sa, col, None)
                            if data:
                                ar.annotation_data.setdefault('annotations', {})[src] = data
                await asyncio.sleep(0)
    except Exception as e:
        logger.warning(f"BQ enrichment skip-check failed (will re-enrich all): {e}")

    genes_to_process = [g for g in unique_genes if g not in already_enriched]
    if not genes_to_process:
        logger.info("BigQuery enrichment: all genes already enriched — nothing to do")
        return

    logger.info(f"BigQuery enrichment: processing {len(genes_to_process)}/{total_genes} genes")

    try:
        from .bq_public import get_bq_public_service
        bq_svc = get_bq_public_service()

        enriched_genes = 0
        updated_variants = 0
        commit_interval = 50

        pending_updates: List[Tuple[List[str], Dict]] = []
        pending_mem: List[Tuple[List[str], Dict]] = []

        _sva_tbl = SharedVariantAnnotation.__table__

        async def _flush_pending():
            nonlocal pending_updates, pending_mem
            if not pending_updates:
                return
            async with async_session_factory() as session:
                conn = await session.connection()
                for rsids_list, vals in pending_updates:
                    await conn.execute(
                        _sva_tbl.update()
                        .where(_sva_tbl.c.rsid.in_(rsids_list))
                        .values(**vals)
                    )
                await session.commit()
            for rsids_list, mem_upd in pending_mem:
                for rsid in rsids_list:
                    ar = annotation_results.get(rsid)
                    if ar and ar.annotation_data:
                        for src, src_data in mem_upd.items():
                            ar.annotation_data.setdefault('annotations', {})[src] = src_data
            pending_updates = []
            pending_mem = []

        try:
            total_to_process = len(genes_to_process)
            for idx, gene in enumerate(genes_to_process, 1):
                if idx % 20 == 0:
                    if check_cancelled_fn:
                        await check_cancelled_fn(analysis_id)
                    if progress and update_progress_fn:
                        progress.phase_progress = idx / total_to_process
                        await update_progress_fn(analysis_id, progress)

                if idx % 100 == 0 or idx == len(genes_to_process):
                    logger.info(f"BQ enriching gene {idx}/{len(genes_to_process)}: {gene} "
                                f"({enriched_genes} enriched, {updated_variants} variants updated)")
                try:
                    bq_result = await asyncio.wait_for(
                        bq_svc.enrich_variant(gene, enabled_bq, analysis_id=analysis_id),
                        timeout=90,
                    )
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    logger.warning(f"BigQuery enrichment timed out for gene {gene}")
                    continue
                except Exception as e:
                    logger.warning(f"BigQuery enrichment failed for gene {gene}: {e}")
                    continue

                update_vals = {}
                mem_updates = {}
                for src, src_data in bq_result.items():
                    if src in _BQ_COL_MAP and src_data and src_data.get('found'):
                        update_vals[_BQ_COL_MAP[src]] = src_data
                        mem_updates[src] = src_data

                if not update_vals:
                    if idx % commit_interval == 0 and pending_updates:
                        await _flush_pending()
                        logger.info(f"  BQ commit checkpoint at gene {idx}/{len(genes_to_process)}")
                    await asyncio.sleep(0)
                    continue

                enriched_genes += 1
                rsids_for_gene = gene_to_rsids[gene]
                updated_variants += len(rsids_for_gene)

                pending_updates.append((rsids_for_gene, update_vals))
                pending_mem.append((rsids_for_gene, mem_updates))

                if idx % commit_interval == 0:
                    await _flush_pending()
                    logger.info(f"  BQ commit checkpoint at gene {idx}/{len(genes_to_process)}")

                await asyncio.sleep(0.01)

            await _flush_pending()

        except Exception as inner_e:
            # Best-effort: try to save whatever enrichment was pending before
            # propagating the original error below — a failure of this last-
            # chance flush must not mask inner_e, so it's only logged here.
            try:
                await _flush_pending()
            except Exception as flush_error:
                logger.warning(f"BigQuery enrichment retry-flush failed: {flush_error}")
            raise inner_e

        logger.info(f"BigQuery enrichment complete: {enriched_genes}/{len(genes_to_process)} genes "
                    f"enriched, {updated_variants} variants updated "
                    f"({len(already_enriched)} skipped as already enriched)")

    except Exception as e:
        logger.warning(f"BigQuery bulk enrichment failed: {e}")
