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


def _count_found(result_dict: Dict[str, Optional[Dict]]) -> int:
    return sum(1 for v in result_dict.values() if v and v.get('found'))


def _rsids_for(
    source_name: str, rsids: List[str], per_source_rsids: Optional[Dict[str, List[str]]]
) -> List[str]:
    if per_source_rsids is not None:
        return per_source_rsids.get(source_name, [])
    return rsids


async def _apply_position_fallback(
    svc,
    src_rsids: List[str],
    result_dict: Dict[str, Optional[Dict]],
    rsid_to_variant: Dict[str, Any],
) -> None:
    misses = [
        r for r in src_rsids
        if not (result_dict.get(r) and result_dict[r].get('found'))
    ]
    if not (misses and hasattr(svc, 'lookup_batch_by_position')):
        return
    pos_tuples = _build_pos_tuples(misses, rsid_to_variant)
    if not pos_tuples:
        return
    pos_results = await svc.lookup_batch_by_position(pos_tuples)
    for rsid, data in pos_results.items():
        if data and data.get('found'):
            result_dict[rsid] = data


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
    gnomad_v2: Any = None
    ensembl_vep: Any = None
    thousand_genomes: Any = None
    alpha_missense: Any = None
    gnomad_tx: Any = None
    alphafold: Any = None

    @property
    def active_names(self) -> List[str]:
        names = []
        if self.clinvar:
            names.append('clinvar_local')
        if self.gnomad:
            names.append('gnomad')
        if self.gnomad_v2:
            names.append('gnomad_v2')
        if self.ensembl_vep:
            names.append('ensembl')
        if self.thousand_genomes:
            names.append('thousand_genomes')
        if self.alpha_missense:
            names.append('alpha_missense')
        if self.gnomad_tx:
            names.append('gnomad_tx')
        if self.alphafold:
            names.append('alphafold')
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

    if enabled_sources is None or 'alphafold' in enabled_sources:
        from .alphafold_local import get_alphafold_local_service
        svc = get_alphafold_local_service()
        if svc.available:
            sources.alphafold = svc

    # gnomAD v2 exome data (GRCh37, per-population AFs) — always load when
    # gnomad is enabled. Used as a fallback for SNPs that the CADD indel file
    # can't cover.
    if enabled_sources is None or 'gnomad' in enabled_sources:
        from .gnomad_v2_local import get_gnomad_v2_service
        svc = get_gnomad_v2_service()
        if not svc.is_loaded:
            await svc.ensure_loaded()
        if svc.is_loaded and (svc.has_pg_data or svc.indexed_count > 0):
            sources.gnomad_v2 = svc

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
    alphafold: Dict[str, Optional[Dict]] = field(default_factory=dict)  # rsid → AF data (gene-keyed internally)

    def items(self):
        """Iterate (source_name, results_dict) for all sources."""
        yield 'clinvar_local', self.clinvar
        yield 'gnomad', self.gnomad
        yield 'ensembl', self.ensembl
        yield 'thousand_genomes', self.thousand_genomes
        yield 'alpha_missense', self.alpha_missense
        yield 'gnomad_tx', self.gnomad_tx
        yield 'alphafold', self.alphafold


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
    results = LookupResults()
    t_total = time.monotonic()

    cv_rsids = _rsids_for('clinvar_local', rsids, per_source_rsids)
    if sources.clinvar and cv_rsids:
        t0 = time.monotonic()
        logger.info(f"  ClinVar: starting lookup for {len(cv_rsids)} RSIDs...")
        results.clinvar = await sources.clinvar.lookup_batch(cv_rsids)
        logger.info(f"  ClinVar: {_count_found(results.clinvar)}/{len(cv_rsids)} found ({time.monotonic() - t0:.1f}s)")
        await asyncio.sleep(0)

    gn_rsids = _rsids_for('gnomad', rsids, per_source_rsids)
    if sources.gnomad and gn_rsids:
        t0 = time.monotonic()
        logger.info(f"  gnomAD: starting lookup for {len(gn_rsids)} RSIDs...")
        results.gnomad = await sources.gnomad.lookup_batch(gn_rsids)
        rsid_found = _count_found(results.gnomad)
        if not getattr(sources.gnomad, 'lookup_batch_uses_tabix', False):
            await _apply_position_fallback(sources.gnomad, gn_rsids, results.gnomad, rsid_to_variant)
        else:
            gn_misses = len(gn_rsids) - rsid_found
            if gn_misses:
                logger.info(f"  gnomAD: skipping pos fallback — tabix already queried ({gn_misses} misses)")
        total_found = _count_found(results.gnomad)
        logger.info(f"  gnomAD: {total_found}/{len(gn_rsids)} found "
                     f"(rsid: {rsid_found}, pos fallback: {total_found - rsid_found}) "
                     f"({time.monotonic() - t0:.1f}s)")
        await asyncio.sleep(0)

    # gnomAD v2 exome fallback — GRCh37 per-population AFs for rsids not found
    # in the main gnomAD CADD data (which is typically indel-only on GRCh38).
    gn_rsids_v2 = _rsids_for('gnomad', rsids, per_source_rsids)
    if sources.gnomad_v2 and gn_rsids_v2:
        # Only look up rsids that weren't already found by main gnomAD
        v2_candidates = [
            r for r in gn_rsids_v2
            if not (results.gnomad.get(r) and results.gnomad[r].get('found'))
        ]
        if v2_candidates:
            t0 = time.monotonic()
            v2_afs: Dict[str, Any] = {}

            # Strategy 1: PG batch lookup (fast — indexed rsid query)
            if sources.gnomad_v2.has_pg_data:
                logger.info(f"  gnomAD v2: PG batch lookup for {len(v2_candidates)} RSIDs...")
                v2_afs = await sources.gnomad_v2.batch_lookup_pg(v2_candidates)
                pg_found = len(v2_afs)
                logger.info(f"  gnomAD v2: PG found {pg_found}/{len(v2_candidates)} "
                            f"({time.monotonic() - t0:.1f}s)")
            else:
                # Strategy 2: tabix position lookup (slower — per-variant seeks)
                pos_tuples = _build_pos_tuples(v2_candidates, rsid_to_variant)
                logger.info(f"  gnomAD v2: tabix position lookup for {len(pos_tuples)} variants "
                            f"({len(v2_candidates)} unfound RSIDs)...")
                if pos_tuples:
                    v2_afs = await sources.gnomad_v2.batch_lookup_by_position(pos_tuples)

            v2_found = 0
            for rsid, afs in v2_afs.items():
                if afs:
                    results.gnomad[rsid] = {
                        "found": True,
                        "source": "gnomad_v2_exome",
                        "rsid": rsid,
                        "af": afs.get("af_nfe"),
                        "population_afs": {
                            pop: afs.get(f"af_{pop}")
                            for pop in ("afr", "amr", "eas", "nfe", "sas")
                            if afs.get(f"af_{pop}") is not None
                        },
                        "subpop_freqs": afs.get("subpop_freqs", {}),
                    }
                    v2_found += 1
            logger.info(f"  gnomAD v2: {v2_found}/{len(v2_candidates)} found total "
                        f"({time.monotonic() - t0:.1f}s)")
            await asyncio.sleep(0)

    ens_rsids = _rsids_for('ensembl', rsids, per_source_rsids)
    if sources.ensembl_vep and ens_rsids:
        t0 = time.monotonic()
        logger.info(f"  Ensembl VEP: starting lookup for {len(ens_rsids)} RSIDs...")
        results.ensembl = await sources.ensembl_vep.lookup_batch(ens_rsids)
        rsid_found = _count_found(results.ensembl)
        await _apply_position_fallback(sources.ensembl_vep, ens_rsids, results.ensembl, rsid_to_variant)
        total_found = _count_found(results.ensembl)
        logger.info(f"  Ensembl VEP: {total_found}/{len(ens_rsids)} found "
                    f"(rsid: {rsid_found}, pos fallback: {total_found - rsid_found}) "
                    f"({time.monotonic() - t0:.1f}s)")
        await asyncio.sleep(0)

    tkg_rsids = _rsids_for('thousand_genomes', rsids, per_source_rsids)
    if sources.thousand_genomes and tkg_rsids:
        t0 = time.monotonic()
        logger.info(f"  1000G: starting lookup for {len(tkg_rsids)} RSIDs...")
        results.thousand_genomes = await sources.thousand_genomes.lookup_batch(tkg_rsids)
        rsid_found = _count_found(results.thousand_genomes)
        await _apply_position_fallback(sources.thousand_genomes, tkg_rsids, results.thousand_genomes, rsid_to_variant)
        total_found = _count_found(results.thousand_genomes)
        logger.info(f"  1000G: {total_found}/{len(tkg_rsids)} found "
                    f"(rsid: {rsid_found}, pos fallback: {total_found - rsid_found}) "
                    f"({time.monotonic() - t0:.1f}s)")
        await asyncio.sleep(0)

    am_rsids = _rsids_for('alpha_missense', rsids, per_source_rsids)
    if sources.alpha_missense and am_rsids:
        t0 = time.monotonic()
        logger.info(f"  AlphaMissense: starting lookup for {len(am_rsids)} RSIDs...")
        am_batch = build_am_batch(am_rsids, rsid_to_variant)
        if am_batch:
            results.alpha_missense = await asyncio.get_event_loop().run_in_executor(
                None, sources.alpha_missense.lookup_variants_batch, am_batch
            )
        logger.info(f"  AlphaMissense: {_count_found(results.alpha_missense)}/{len(am_rsids)} found ({time.monotonic() - t0:.1f}s)")
        await asyncio.sleep(0)

    # gnomAD-tx: bulk batch via chromosome-range scans — NOT per-variant tabix seeks.
    # _lookup_batch_sync reads one range per chromosome, so 609K variants = ~25 fetches.
    if sources.gnomad_tx:
        t0 = time.monotonic()
        tx_variants = [
            (str(v.rsid), str(v.chromosome).replace('chr', ''), int(v.position),
             str(v.ref_allele or ''), str(v.alt_allele or ''))
            for v in rsid_to_variant.values()
            if v.rsid and v.chromosome and v.position
        ]
        if tx_variants:
            logger.info(f"  gnomAD-tx: starting lookup for {len(tx_variants)} variants...")
            tx_results = await sources.gnomad_tx.lookup_batch(tx_variants)
            results.gnomad_tx = tx_results
            found_tx = _count_found(tx_results)
            logger.info(f"  gnomAD-tx: {found_tx}/{len(tx_variants)} found ({time.monotonic() - t0:.1f}s)")
            await asyncio.sleep(0)

    # AlphaFold local: gene-keyed lookup. Extract gene symbols from genetic_markers
    # table first (best coverage), then fall back to annotation results.
    if sources.alphafold:
        t0 = time.monotonic()
        # Build rsid → gene_symbol map — try marker.gene_symbol first (363k+ coverage),
        # then fall back to annotation results for any gaps.
        rsid_gene: Dict[str, str] = {}
        for rsid in (rsids or list(rsid_to_variant.keys())):
            # Primary: marker.gene_symbol from genetic_markers table
            v = rsid_to_variant.get(rsid)
            if v:
                marker = getattr(v, 'marker', None)
                if marker and getattr(marker, 'gene_symbol', None):
                    rsid_gene[rsid] = marker.gene_symbol
                    continue
            # Fallback: Ensembl VEP transcript_consequences
            ens = results.ensembl.get(rsid) or {}
            if ens.get('found'):
                ens_data = ens.get('data', {})
                if isinstance(ens_data, list) and ens_data:
                    ens_data = ens_data[0]
                tcs = ens_data.get('transcript_consequences', [])
                if tcs and tcs[0].get('gene_symbol'):
                    rsid_gene[rsid] = tcs[0]['gene_symbol']
                    continue
            # Fallback: ClinVar gene
            cv = results.clinvar.get(rsid) or {}
            if cv.get('found'):
                gene = cv.get('gene_symbol') or cv.get('gene')
                if gene:
                    rsid_gene[rsid] = gene
                    continue
            # Fallback: gnomAD gene
            gn = results.gnomad.get(rsid) or {}
            if gn.get('found') and gn.get('gene'):
                rsid_gene[rsid] = gn['gene']

        unique_genes = list(set(rsid_gene.values()))
        if unique_genes:
            logger.info(f"  AlphaFold: looking up {len(unique_genes)} unique genes for {len(rsid_gene)} RSIDs...")
            gene_results = sources.alphafold.bulk_lookup_genes(unique_genes)
            # Map results back to rsids
            for rsid, gene in rsid_gene.items():
                af_data = gene_results.get(gene)
                if af_data and af_data.get('found'):
                    results.alphafold[rsid] = af_data
            found_af = _count_found(results.alphafold)
            logger.info(f"  AlphaFold: {found_af}/{len(rsid_gene)} RSIDs enriched ({time.monotonic() - t0:.1f}s)")
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
