"""
Annotation coordination — extracted from analysis_service.py.

Handles:
- Efficient variant annotation with reuse (Phase 2)
- Local source backfill for existing annotations
- Bulk local-only annotation (no HTTP API calls)
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
from .analysis_service import AnnotationResult, AnalysisProgress

logger = logging.getLogger(__name__)


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
    annotation_service,
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

    def _found(d: Any) -> Optional[Dict]:
        return d if (d and d.get('found')) else None

    annotation_results: Dict[str, AnnotationResult] = {}
    BATCH = 500
    total = len(unique_rsids)
    saved_count = 0
    last_log = time.time()

    for i in range(0, total, BATCH):
        chunk_rsids = unique_rsids[i:i + BATCH]

        batch_rows = []
        for rsid in chunk_rsids:
            cv_val  = _found(results.clinvar.get(rsid))
            gn_val  = _found(results.gnomad.get(rsid))
            ens_val = _found(results.ensembl.get(rsid))
            tkg_val = _found(results.thousand_genomes.get(rsid))
            am_val  = _found(results.alpha_missense.get(rsid))
            gtx_val = _found(results.gnomad_tx.get(rsid))
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

            # Create variant_annotation links (no-op if already linked)
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
            if link_values:
                link_stmt = insert(VariantAnnotation).values(link_values)
                link_stmt = link_stmt.on_conflict_do_nothing(
                    constraint='uq_variant_annotations_analysis_variant'
                )
                await session.execute(link_stmt)
            await session.commit()

        # Build annotation_results for this chunk
        for rsid in chunk_rsids:
            cv_val  = _found(results.clinvar.get(rsid))
            gn_val  = _found(results.gnomad.get(rsid))
            ens_val = _found(results.ensembl.get(rsid))
            tkg_val = _found(results.thousand_genomes.get(rsid))
            am_val  = _found(results.alpha_missense.get(rsid))
            gtx_val = _found(results.gnomad_tx.get(rsid))
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


async def _backfill_local_sources(
    existing_annotations: Dict[str, Dict[str, Any]],
    enabled_sources: Optional[List[str]],
    variants: List,
    analysis_id: int = 0,
):
    """Re-query all local sources for all existing annotations.

    Always queries local files for every RSID — does not rely on
    shared_variant_annotations as a skip gate. Results overwrite cached
    columns so analysis always reflects current local data.
    """
    from .local_annotation import (
        load_local_sources, build_rsid_variant_map,
        run_all_lookups, chunked_db_write, NOT_FOUND, COL_MAP,
    )

    sources = await load_local_sources(enabled_sources)
    active = sources.active_names
    all_configured = set(enabled_sources or []) & {
        'clinvar_local', 'gnomad', 'ensembl', 'thousand_genomes',
        'alpha_missense', 'gnomad_tx',
    }
    not_loaded = all_configured - set(active)
    logger.info(
        f"Local data sources: {', '.join(sorted(active)) or 'none'} loaded"
        + (f" | not available: {', '.join(sorted(not_loaded))}" if not_loaded else "")
    )
    if not active:
        logger.info("Local source refresh: no local sources loaded")
        return

    all_rsids = list(existing_annotations.keys())

    # Always re-query all local sources for every RSID.
    # Do not treat shared_variant_annotations as authoritative — always cross-reference
    # local files directly so analysis reflects current local data, not stale cache.
    missing: Dict[str, List[str]] = {s: list(all_rsids) for s in active}

    import time as _time
    backfill_t0 = _time.monotonic()
    parts = ', '.join(f"{s}: {len(missing[s])}" for s in active)
    logger.info(f"Local source refresh starting (always-fresh mode) — {parts}")

    rsid_to_variant = build_rsid_variant_map(variants)

    results = await run_all_lookups(
        sources, [], rsid_to_variant, per_source_rsids=missing,
    )

    logger.info(f"Lookups done in {_time.monotonic() - backfill_t0:.1f}s, writing to DB...")

    ann_key_map = {
        'clinvar_local': 'clinvar_local',
        'gnomad': 'gnomad',
        'ensembl': 'ensembl',
        'thousand_genomes': 'thousand_genomes',
        'alpha_missense': 'alpha_missense',
        'gnomad_tx': 'gnomad_tx',
    }

    for src_name, src_results in results.items():
        col = COL_MAP[src_name]
        needed_rsids = set(missing.get(src_name, []))
        if not needed_rsids:
            continue

        params = []
        for rsid, data in src_results.items():
            if rsid not in needed_rsids:
                continue
            if data and data.get('found'):
                params.append({'b_rsid': rsid, 'b_data': data})
                ann_key = ann_key_map[src_name]
                if rsid in existing_annotations:
                    existing_annotations[rsid]['annotations'][ann_key] = data
            else:
                params.append({'b_rsid': rsid, 'b_data': NOT_FOUND[src_name]})

        if params:
            updated = await chunked_db_write(col, params)
            found = sum(1 for p in params if p['b_data'].get('found'))
            logger.info(f"  {src_name}: {found} found, "
                        f"{len(params) - found} not-found, {updated} written")

    elapsed = _time.monotonic() - backfill_t0
    logger.info(f"Local source refresh complete in {elapsed:.1f}s")

    # BigQuery backfill (ChEMBL, FDA Drug, AlphaFold)
    bq_source_names = {'chembl', 'fda_drug', 'alphafold'}
    enabled_bq = bq_source_names & set(enabled_sources) if enabled_sources else bq_source_names
    bq_col_map = {'chembl': 'chembl_data', 'fda_drug': 'fda_drug_data', 'alphafold': 'alphafold_data'}
    if enabled_bq:
        missing_bq = {}
        for rsid, data in existing_annotations.items():
            anns = data.get('annotations', {})
            missing_for_rsid = {s for s in enabled_bq if s not in anns}
            if missing_for_rsid:
                ensembl_ann = anns.get('ensembl', {})
                gene = None
                if ensembl_ann and ensembl_ann.get('found') and ensembl_ann.get('data'):
                    e_entry = ensembl_ann['data'][0] if isinstance(ensembl_ann['data'], list) else ensembl_ann['data']
                    tcs = e_entry.get('transcript_consequences', [])
                    if tcs:
                        gene = tcs[0].get('gene_symbol')
                if not gene:
                    cv = anns.get('clinvar_local', {})
                    if cv and cv.get('found'):
                        gene = cv.get('gene_symbol') or cv.get('gene')
                if gene:
                    missing_bq[rsid] = (gene, missing_for_rsid)

        if missing_bq:
            logger.info(f"Backfilling BigQuery sources for {len(missing_bq)} existing annotations")
            try:
                from .bq_public import get_bq_public_service
                bq_svc = get_bq_public_service()
                bq_updated = 0
                bq_total = len(missing_bq)
                bq_start = time.time()
                commit_interval = 50

                pending_updates: List[Tuple[str, Dict]] = []

                _sva_t = SharedVariantAnnotation.__table__

                async def _flush_bq_backfill():
                    nonlocal pending_updates
                    if not pending_updates:
                        return
                    async with async_session_factory() as session:
                        conn = await session.connection()
                        for rsid, vals in pending_updates:
                            await conn.execute(
                                _sva_t.update()
                                .where(_sva_t.c.rsid == rsid)
                                .values(**vals)
                            )
                        await session.commit()
                    pending_updates = []

                for idx, (rsid, (gene, needed)) in enumerate(missing_bq.items(), 1):
                    bq_result = await bq_svc.enrich_variant(gene, needed, analysis_id=analysis_id)
                    update_vals = {}
                    for src, src_data in bq_result.items():
                        if src in bq_col_map and src_data:
                            update_vals[bq_col_map[src]] = src_data
                            existing_annotations[rsid]['annotations'][src] = src_data
                    if update_vals:
                        pending_updates.append((rsid, update_vals))
                        bq_updated += 1

                    if idx % commit_interval == 0:
                        await _flush_bq_backfill()

                    if idx % 100 == 0 or idx == bq_total:
                        elapsed = time.time() - bq_start
                        logger.info(f"  BQ backfill progress: {idx}/{bq_total} ({bq_updated} enriched, {elapsed:.1f}s)")

                    await asyncio.sleep(0)

                await _flush_bq_backfill()
                logger.info(f"Backfilled BigQuery data for {bq_updated}/{bq_total} annotations ({time.time() - bq_start:.1f}s)")
            except Exception as e:
                logger.warning(f"BigQuery backfill failed: {e}")


async def bulk_annotate_locally(
    variants: List,
    analysis_id: int,
    annotation_service,
    progress: AnalysisProgress,
    enabled_sources: Optional[List[str]],
) -> Dict[str, AnnotationResult]:
    """Annotate variants using only local data sources — no HTTP API calls."""
    from sqlalchemy.dialects.postgresql import insert
    from .local_annotation import load_local_sources, run_all_lookups

    rsid_to_variants: Dict[str, List] = {}
    for v in variants:
        rsid_to_variants.setdefault(str(v.rsid), []).append(v)

    unique_rsids = list(rsid_to_variants.keys())
    total = len(unique_rsids)
    logger.info(f"Bulk local annotation: {total} unique RSIDs ({len(variants)} variants)")
    bulk_start = time.time()

    logger.info("  Loading local annotation sources (ClinVar, gnomAD, Ensembl VEP, ...)")
    _src_t0 = time.time()
    sources = await load_local_sources(enabled_sources)
    logger.info(
        f"  Local sources loaded in {time.time() - _src_t0:.1f}s: "
        f"{', '.join(sources.active_names) if sources.active_names else 'none'}"
    )
    rsid_to_variant = {rsid: vlist[0] for rsid, vlist in rsid_to_variants.items()}
    logger.info(f"  Running all source lookups for {total} RSIDs...")
    results = await run_all_lookups(sources, unique_rsids, rsid_to_variant)

    cv_map = results.clinvar
    gn_map = results.gnomad
    ens_map = results.ensembl
    tkg_map = results.thousand_genomes
    am_map = results.alpha_missense
    gtx_map = results.gnomad_tx

    await asyncio.sleep(0)

    annotation_results: Dict[str, AnnotationResult] = {}
    batch_size = 500
    saved_count = 0

    def _val(data):
        return data if data and data.get('found') else None

    last_progress_update = time.time()

    for i in range(0, len(unique_rsids), batch_size):
        chunk_rsids = unique_rsids[i:i + batch_size]

        batch_values = []
        for rsid in chunk_rsids:
            cv_val = _val(cv_map.get(rsid))
            gn_val = _val(gn_map.get(rsid))
            ens_val = _val(ens_map.get(rsid))
            tkg_val = _val(tkg_map.get(rsid))
            am_val = _val(am_map.get(rsid))
            gtx_val = _val(gtx_map.get(rsid))
            first_variant = rsid_to_variants[rsid][0]
            marker_id = getattr(first_variant, 'marker_id', None)

            row = dict(
                rsid=rsid,
                clinvar_local_data=cv_val,
                gnomad_data=gn_val,
                gnomad_tx_data=gtx_val,
                ensembl_data=ens_val,
                thousand_genomes_data=tkg_val,
                alpha_missense_data=am_val,
                annotation_status='partial',
                total_api_calls=0,
                usage_count=1,
            )
            if marker_id is not None:
                row['marker_id'] = marker_id
            batch_values.append(row)

        async with async_session_factory() as session:
            stmt = insert(SharedVariantAnnotation).values(batch_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=['rsid'],
                set_=dict(
                    usage_count=SharedVariantAnnotation.usage_count + 1,
                    last_updated_at=func.now(),
                    clinvar_local_data=func.coalesce(
                        SharedVariantAnnotation.clinvar_local_data,
                        stmt.excluded.clinvar_local_data,
                    ),
                    gnomad_data=func.coalesce(
                        SharedVariantAnnotation.gnomad_data,
                        stmt.excluded.gnomad_data,
                    ),
                    ensembl_data=func.coalesce(
                        SharedVariantAnnotation.ensembl_data,
                        stmt.excluded.ensembl_data,
                    ),
                    thousand_genomes_data=func.coalesce(
                        SharedVariantAnnotation.thousand_genomes_data,
                        stmt.excluded.thousand_genomes_data,
                    ),
                    alpha_missense_data=func.coalesce(
                        SharedVariantAnnotation.alpha_missense_data,
                        stmt.excluded.alpha_missense_data,
                    ),
                    gnomad_tx_data=func.coalesce(
                        SharedVariantAnnotation.gnomad_tx_data,
                        stmt.excluded.gnomad_tx_data,
                    ),
                ),
            ).returning(SharedVariantAnnotation.id, SharedVariantAnnotation.rsid)

            result = await session.execute(stmt)
            rsid_to_shared_id = {row.rsid: row.id for row in result.all()}

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
            if link_values:
                link_stmt = insert(VariantAnnotation).values(link_values)
                link_stmt = link_stmt.on_conflict_do_nothing(
                    constraint='uq_variant_annotations_analysis_variant'
                )
                await session.execute(link_stmt)

            await session.commit()

        for idx_in_chunk, rsid in enumerate(chunk_rsids):
            if idx_in_chunk > 0 and idx_in_chunk % 50 == 0:
                await asyncio.sleep(0)
            cv_val = _val(cv_map.get(rsid))
            gn_val = _val(gn_map.get(rsid))
            ens_val = _val(ens_map.get(rsid))
            tkg_val = _val(tkg_map.get(rsid))
            am_val = _val(am_map.get(rsid))
            gtx_val = _val(gtx_map.get(rsid))

            ann_data: Dict[str, Any] = {
                'rsid': rsid,
                'annotations': {},
                'sources_queried': [],
                'success_count': 0,
            }
            if cv_val:
                ann_data['annotations']['clinvar_local'] = cv_val
                ann_data['success_count'] += 1
            if gn_val:
                ann_data['annotations']['gnomad'] = gn_val
                ann_data['success_count'] += 1
            if ens_val:
                ann_data['annotations']['ensembl'] = ens_val
                ann_data['success_count'] += 1
            if tkg_val:
                ann_data['annotations']['thousand_genomes'] = tkg_val
                ann_data['success_count'] += 1
            if am_val:
                ann_data['annotations']['alpha_missense'] = am_val
                ann_data['success_count'] += 1
            if gtx_val:
                ann_data['annotations']['gnomad_tx'] = gtx_val
                ann_data['success_count'] += 1

            # ARCH-06: pathogenicity_score is NOT computed here.
            # build_variant_profiles() computes it fresh so scoring logic
            # updates apply without re-annotating.

            annotation_results[rsid] = AnnotationResult(
                rsid=rsid, was_reused=False,
                annotation_data=ann_data, source='local'
            )
            saved_count += 1

        progress.annotated_variants += sum(
            len(rsid_to_variants[r]) for r in chunk_rsids
        )
        progress.new_annotations += len(chunk_rsids)
        progress.processed_variants = progress.annotated_variants
        progress.phase_progress = progress.processed_variants / max(1, progress.total_variants)

        now = time.time()
        chunk_num = i // batch_size + 1
        total_chunks = (total + batch_size - 1) // batch_size
        if now - last_progress_update >= 2.0 or chunk_num == total_chunks:
            last_progress_update = now

        if chunk_num % 20 == 0 or chunk_num == total_chunks:
            elapsed = time.time() - bulk_start
            logger.info(
                f"  Bulk annotation: {saved_count}/{total} RSIDs "
                f"({progress.annotated_variants} variants, {elapsed:.1f}s)"
            )

        await asyncio.sleep(0.01)

    elapsed = time.time() - bulk_start
    logger.info(f"Bulk local annotation complete: {saved_count} RSIDs in {elapsed:.1f}s")
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
    """Bulk-enrich annotations with BigQuery data (ChEMBL, FDA Drug, AlphaFold)."""
    from .variant_loader import load_enabled_sources as _load_enabled_sources

    if enabled_sources is None:
        enabled_sources = await _load_enabled_sources()

    bq_source_names = {'chembl', 'fda_drug', 'alphafold'}
    enabled_bq = bq_source_names & set(enabled_sources) if enabled_sources else bq_source_names
    if not enabled_bq:
        return

    bq_col_map = {'chembl': 'chembl_data', 'fda_drug': 'fda_drug_data', 'alphafold': 'alphafold_data'}

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
            bq_columns = [getattr(SharedVariantAnnotation, bq_col_map[s]) for s in enabled_bq]
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
                        for src, col in bq_col_map.items():
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
                    if src in bq_col_map and src_data and src_data.get('found'):
                        update_vals[bq_col_map[src]] = src_data
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
            try:
                await _flush_pending()
            except Exception:
                pass
            raise inner_e

        logger.info(f"BigQuery enrichment complete: {enriched_genes}/{len(genes_to_process)} genes "
                    f"enriched, {updated_variants} variants updated "
                    f"({len(already_enriched)} skipped as already enriched)")

    except Exception as e:
        logger.warning(f"BigQuery bulk enrichment failed: {e}")
