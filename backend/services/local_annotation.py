"""
Shared local-source annotation logic.

Extracts the duplicated service loading, batch lookup, and variant-tuple
building from analysis_service.py into a single reusable module.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import bindparam

from ..db.models import SharedVariantAnnotation

logger = logging.getLogger(__name__)


# Sentinel dicts written to DB for sources that found no data — prevents
# the backfill from re-querying the same rsids on every run.
NOT_FOUND = {
    'clinvar_local': {"found": False, "source": "clinvar_local"},
    'gnomad':        {"found": False, "source": "gnomad_local"},
    'ensembl':       {"found": False, "source": "ensembl_vep_local"},
    'thousand_genomes': {"found": False, "source": "1000genomes_local"},
    'alpha_missense':   {"found": False, "source": "alpha_missense"},
    'gnomad_tx':     {"found": False, "source": "gnomad_tx"},
}

# DB column names for each source
COL_MAP = {
    'clinvar_local':    'clinvar_local_data',
    'gnomad':           'gnomad_data',
    'ensembl':          'ensembl_data',
    'thousand_genomes': 'thousand_genomes_data',
    'alpha_missense':   'alpha_missense_data',
    'gnomad_tx':        'gnomad_tx_data',
}


@dataclass
class LoadedSources:
    """Holds references to all loaded local annotation services."""
    clinvar: Any = None
    gnomad: Any = None
    ensembl_vep: Any = None
    thousand_genomes: Any = None
    alpha_missense: Any = None
    gnomad_tx: Any = None

    @property
    def active_names(self) -> List[str]:
        names = []
        if self.clinvar:
            names.append('clinvar_local')
        if self.gnomad:
            names.append('gnomad')
        if self.ensembl_vep:
            names.append('ensembl')
        if self.thousand_genomes:
            names.append('thousand_genomes')
        if self.alpha_missense:
            names.append('alpha_missense')
        if self.gnomad_tx:
            names.append('gnomad_tx')
        return names


async def load_local_sources(enabled_sources: Optional[List[str]]) -> LoadedSources:
    """Load and validate all enabled local annotation services.

    Returns a LoadedSources with only services that are ready to use.
    """
    sources = LoadedSources()

    if enabled_sources is None or 'clinvar_local' in enabled_sources:
        from .clinvar_local import get_clinvar_direct_service
        svc = get_clinvar_direct_service()
        if not svc.is_loaded:
            await svc.ensure_loaded()
        if svc.is_loaded:
            sources.clinvar = svc

    if enabled_sources is None or 'gnomad' in enabled_sources:
        from .gnomad_local import get_gnomad_service
        svc = get_gnomad_service()
        if not svc.is_loaded:
            await svc.ensure_loaded()
        if svc.is_loaded:
            sources.gnomad = svc

    if enabled_sources is None or 'ensembl' in enabled_sources:
        from .ensembl_vep_local import get_ensembl_vep_service
        svc = get_ensembl_vep_service()
        if not svc.is_loaded:
            logger.info("VEP cache still loading, waiting...")
            await svc.ensure_loaded()
        if svc.is_loaded:
            sources.ensembl_vep = svc

    if enabled_sources is None or 'thousand_genomes' in enabled_sources:
        from .thousand_genomes_local import get_thousand_genomes_direct_service
        svc = get_thousand_genomes_direct_service()
        if not svc.is_loaded:
            await svc.ensure_loaded()
        if svc.is_loaded:
            sources.thousand_genomes = svc

    if enabled_sources is None or 'alpha_missense' in enabled_sources:
        from ..utils.alpha_missense import get_alpha_missense_service
        svc = get_alpha_missense_service()
        if svc.available:
            sources.alpha_missense = svc

    if enabled_sources is None or 'gnomad_tx' in enabled_sources:
        from .gnomad_local import get_gnomad_tx_service
        svc = get_gnomad_tx_service()
        if svc.available:
            sources.gnomad_tx = svc

    return sources


def build_rsid_variant_map(variants) -> Dict[str, Any]:
    """Build rsid → first variant mapping (used for position-based lookups)."""
    return {str(v.rsid): v for v in variants if v.rsid}


def build_gnomad_pos_tuples(
    rsids: List[str],
    rsid_to_variant: Dict[str, Any],
) -> List[Tuple]:
    """Build (rsid, chrom, pos, ref, alt) tuples for gnomAD position fallback."""
    return _build_pos_tuples(rsids, rsid_to_variant)


def _build_pos_tuples(
    rsids: List[str],
    rsid_to_variant: Dict[str, Any],
) -> List[Tuple]:
    """Build (rsid, chrom, pos, ref, alt) tuples for position-based tabix fallback."""
    tuples = []
    for rsid in rsids:
        v = rsid_to_variant.get(rsid)
        if v:
            marker = getattr(v, 'marker', None)
            if marker and marker.chromosome and marker.position and marker.ref_allele:
                tuples.append((
                    rsid,
                    marker.chromosome,
                    marker.position,
                    marker.ref_allele,
                    marker.alt_alleles or '',
                ))
    return tuples


def build_am_batch(
    rsids: List[str],
    rsid_to_variant: Dict[str, Any],
) -> List[Dict]:
    """Build AlphaMissense batch lookup dicts from variant data."""
    batch = []
    for rsid in rsids:
        v = rsid_to_variant.get(rsid)
        if not v:
            continue
        marker = getattr(v, 'marker', None)
        if not (marker and marker.chromosome and marker.position
                and marker.ref_allele and marker.alt_alleles):
            continue
        for alt in str(marker.alt_alleles).split(','):
            alt = alt.strip()
            if alt:
                batch.append({
                    'rsid': rsid,
                    'chromosome': str(marker.chromosome),
                    'position': int(marker.position),
                    'ref_allele': str(marker.ref_allele),
                    'alt_allele': alt,
                })
                break  # one alt per rsid
    return batch


def build_gtx_tuples(
    rsids: List[str],
    rsid_to_variant: Dict[str, Any],
) -> List[Tuple]:
    """Build gnomAD-tx lookup tuples from variant data."""
    tuples = []
    for rsid in rsids:
        v = rsid_to_variant.get(rsid)
        if not v:
            continue
        marker = getattr(v, 'marker', None)
        if not (marker and marker.chromosome and marker.position
                and marker.ref_allele and marker.alt_alleles):
            continue
        tuples.append((
            rsid,
            str(marker.chromosome),
            int(marker.position),
            str(marker.ref_allele),
            str(marker.alt_alleles),
        ))
    return tuples


@dataclass
class LookupResults:
    """Results from all local source lookups."""
    clinvar: Dict[str, Optional[Dict]] = field(default_factory=dict)
    gnomad: Dict[str, Optional[Dict]] = field(default_factory=dict)
    ensembl: Dict[str, Optional[Dict]] = field(default_factory=dict)
    thousand_genomes: Dict[str, Optional[Dict]] = field(default_factory=dict)
    alpha_missense: Dict[str, Optional[Dict]] = field(default_factory=dict)
    gnomad_tx: Dict[str, Optional[Dict]] = field(default_factory=dict)

    def items(self):
        """Iterate (source_name, results_dict) for all sources."""
        yield 'clinvar_local', self.clinvar
        yield 'gnomad', self.gnomad
        yield 'ensembl', self.ensembl
        yield 'thousand_genomes', self.thousand_genomes
        yield 'alpha_missense', self.alpha_missense
        yield 'gnomad_tx', self.gnomad_tx


async def run_all_lookups(
    sources: LoadedSources,
    rsids: List[str],
    rsid_to_variant: Dict[str, Any],
    per_source_rsids: Optional[Dict[str, List[str]]] = None,
) -> LookupResults:
    """Run batch lookups for all loaded sources.

    Args:
        sources: Loaded service references.
        rsids: Default rsid list (used when per_source_rsids is None or
               doesn't contain a key for a given source).
        rsid_to_variant: rsid → variant mapping for position-based lookups.
        per_source_rsids: Optional dict mapping source name → rsid list.
            When provided, each source only queries its own rsids instead
            of the full list. Sources with an empty list are skipped.

    Yields to the event loop between each source lookup to prevent starvation.
    """
    def _rsids_for(source_name: str) -> List[str]:
        if per_source_rsids is not None:
            return per_source_rsids.get(source_name, [])
        return rsids

    results = LookupResults()
    t_total = time.monotonic()

    cv_rsids = _rsids_for('clinvar_local')
    if sources.clinvar and cv_rsids:
        t0 = time.monotonic()
        logger.info(f"  ClinVar: starting lookup for {len(cv_rsids)} RSIDs...")
        results.clinvar = await sources.clinvar.lookup_batch(cv_rsids)
        found = sum(1 for v in results.clinvar.values() if v and v.get('found'))
        logger.info(f"  ClinVar: {found}/{len(cv_rsids)} found ({time.monotonic() - t0:.1f}s)")
        await asyncio.sleep(0)

    gn_rsids = _rsids_for('gnomad')
    if sources.gnomad and gn_rsids:
        t0 = time.monotonic()
        logger.info(f"  gnomAD: starting lookup for {len(gn_rsids)} RSIDs...")
        results.gnomad = await sources.gnomad.lookup_batch(gn_rsids)
        gn_found = sum(1 for v in results.gnomad.values() if v and v.get('found'))
        # Position fallback for rsid misses — skipped when lookup_batch already
        # exhausted tabix (same GRCh38 bridge + same files → identical results).
        gn_misses = [
            r for r in gn_rsids
            if not (results.gnomad.get(r) and results.gnomad[r].get('found'))
        ]
        if gn_misses and not getattr(sources.gnomad, 'lookup_batch_uses_tabix', False):
            pos_tuples = build_gnomad_pos_tuples(gn_misses, rsid_to_variant)
            if pos_tuples:
                pos_results = await sources.gnomad.lookup_batch_by_position(pos_tuples)
                for rsid, data in pos_results.items():
                    if data and data.get('found'):
                        results.gnomad[rsid] = data
        elif gn_misses and getattr(sources.gnomad, 'lookup_batch_uses_tabix', False):
            logger.info(f"  gnomAD: skipping pos fallback — tabix already queried in rsid lookup ({len(gn_misses)} misses)")
        total_found = sum(1 for v in results.gnomad.values() if v and v.get('found'))
        logger.info(f"  gnomAD: {total_found}/{len(gn_rsids)} found "
                     f"(rsid: {gn_found}, pos fallback: {total_found - gn_found}) "
                     f"({time.monotonic() - t0:.1f}s)")
        await asyncio.sleep(0)

    ens_rsids = _rsids_for('ensembl')
    if sources.ensembl_vep and ens_rsids:
        t0 = time.monotonic()
        logger.info(f"  Ensembl VEP: starting lookup for {len(ens_rsids)} RSIDs...")
        results.ensembl = await sources.ensembl_vep.lookup_batch(ens_rsids)
        ens_found = sum(1 for v in results.ensembl.values() if v and v.get('found'))
        # Position fallback for rsid misses (handles cases where SQLite cache is absent
        # or was built from a different upload set)
        ens_misses = [
            r for r in ens_rsids
            if not (results.ensembl.get(r) and results.ensembl[r].get('found'))
        ]
        if ens_misses and hasattr(sources.ensembl_vep, 'lookup_batch_by_position'):
            pos_tuples = _build_pos_tuples(ens_misses, rsid_to_variant)
            if pos_tuples:
                pos_results = await sources.ensembl_vep.lookup_batch_by_position(pos_tuples)
                for rsid, data in pos_results.items():
                    if data and data.get('found'):
                        results.ensembl[rsid] = data
        total_found = sum(1 for v in results.ensembl.values() if v and v.get('found'))
        logger.info(f"  Ensembl VEP: {total_found}/{len(ens_rsids)} found "
                    f"(rsid: {ens_found}, pos fallback: {total_found - ens_found}) "
                    f"({time.monotonic() - t0:.1f}s)")
        await asyncio.sleep(0)

    tkg_rsids = _rsids_for('thousand_genomes')
    if sources.thousand_genomes and tkg_rsids:
        t0 = time.monotonic()
        logger.info(f"  1000G: starting lookup for {len(tkg_rsids)} RSIDs...")
        results.thousand_genomes = await sources.thousand_genomes.lookup_batch(tkg_rsids)
        tkg_found = sum(1 for v in results.thousand_genomes.values() if v and v.get('found'))
        # Position fallback for rsid misses — VCF tabix is fast for this (sequential
        # seeks via pysam, not a full scan). No cap needed.
        tkg_misses = [
            r for r in tkg_rsids
            if not (results.thousand_genomes.get(r) and results.thousand_genomes[r].get('found'))
        ]
        if tkg_misses and hasattr(sources.thousand_genomes, 'lookup_batch_by_position'):
            pos_tuples = _build_pos_tuples(tkg_misses, rsid_to_variant)
            if pos_tuples:
                pos_results = await sources.thousand_genomes.lookup_batch_by_position(pos_tuples)
                for rsid, data in pos_results.items():
                    if data and data.get('found'):
                        results.thousand_genomes[rsid] = data
        total_found = sum(1 for v in results.thousand_genomes.values() if v and v.get('found'))
        logger.info(f"  1000G: {total_found}/{len(tkg_rsids)} found "
                    f"(rsid: {tkg_found}, pos fallback: {total_found - tkg_found}) "
                    f"({time.monotonic() - t0:.1f}s)")
        await asyncio.sleep(0)

    am_rsids = _rsids_for('alpha_missense')
    if sources.alpha_missense and am_rsids:
        t0 = time.monotonic()
        logger.info(f"  AlphaMissense: starting lookup for {len(am_rsids)} RSIDs...")
        am_batch = build_am_batch(am_rsids, rsid_to_variant)
        if am_batch:
            results.alpha_missense = await asyncio.get_event_loop().run_in_executor(
                None, sources.alpha_missense.lookup_variants_batch, am_batch
            )
        found = sum(1 for v in results.alpha_missense.values() if v and v.get('found'))
        logger.info(f"  AlphaMissense: {found}/{len(am_rsids)} found ({time.monotonic() - t0:.1f}s)")
        await asyncio.sleep(0)

    # gnomAD-tx: bulk batch via chromosome-range scans — NOT per-variant tabix seeks.
    # _lookup_batch_sync reads one range per chromosome, so 609K variants = ~25 fetches.
    if sources.gnomad_tx:
        t0 = time.monotonic()
        tx_variants = [
            (str(v.rsid), str(v.chromosome).replace('chr', ''), int(v.position),
             str(v.ref_allele or ''), str(v.alt_alleles or ''))
            for v in rsid_to_variant.values()
            if v.rsid and v.chromosome and v.position
        ]
        if tx_variants:
            logger.info(f"  gnomAD-tx: starting lookup for {len(tx_variants)} variants...")
            tx_results = await sources.gnomad_tx.lookup_batch(tx_variants)
            results.gnomad_tx = tx_results
            found_tx = sum(1 for v in tx_results.values() if v and v.get('found'))
            logger.info(f"  gnomAD-tx: {found_tx}/{len(tx_variants)} found ({time.monotonic() - t0:.1f}s)")
            await asyncio.sleep(0)

    logger.info(f"  All source lookups: {time.monotonic() - t_total:.1f}s total")
    return results


async def chunked_db_write(
    col_name: str,
    params: List[Dict],
    chunk_size: int = 5000,
):
    """Write annotation updates to DB in small chunks with yields between."""
    from ..db.database import async_session_factory

    if not params:
        return 0

    table = SharedVariantAnnotation.__table__
    total = 0
    total_params = len(params)
    total_chunks = (total_params + chunk_size - 1) // chunk_size
    t0 = time.monotonic()

    for ci in range(0, total_params, chunk_size):
        chunk = params[ci:ci + chunk_size]
        chunk_num = ci // chunk_size + 1
        async with async_session_factory() as sess:
            conn = await sess.connection()
            await conn.execute(
                table.update()
                .where(table.c.rsid == bindparam('b_rsid'))
                .values(**{col_name: bindparam('b_data')}),
                chunk
            )
            await sess.commit()
        total += len(chunk)
        # Yield between chunks so HTTP handlers can run
        if ci > 0:
            await asyncio.sleep(0.02)
        if total_chunks > 1 and (chunk_num % 5 == 0 or chunk_num == total_chunks):
            elapsed = time.monotonic() - t0
            logger.info(
                f"    {col_name} write {chunk_num}/{total_chunks}: "
                f"{total}/{total_params} ({elapsed:.1f}s)"
            )
    return total
