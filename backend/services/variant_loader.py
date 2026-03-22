"""
Variant loading and correction utilities — extracted from analysis_service.py.

Handles:
- Efficient Core SQL loading of analysis variants (streaming, no ORM overhead)
- Bulk rsid→gene map building from ClinVar + Ensembl position lookup
- Ref/alt allele correction from authoritative annotation sources
- Enabled annotation source loading from DB config
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from sqlalchemy import select

from ..db.database import async_session_factory
from ..db.models import (
    AnalysisVariant, GeneticAnalysis, GeneticMarker,
    AnnotationSourceConfig, EnsemblGene,
)
from ..core.exceptions import AnalysisNotFoundException
from .analysis_service import _MarkerLite, VariantLite, AnnotationResult

logger = logging.getLogger(__name__)


async def load_analysis_data(
    analysis_id: int,
    user_id: Optional[int] = None,
) -> tuple:
    """Load analysis header + variants efficiently using Core SQL rows.

    Avoids ORM selectinload which blocks the event loop for 60-90 seconds
    while SQLAlchemy materialises 600k+ objects. Instead we stream rows
    from a JOIN query in chunks of 5000, yielding between chunks so HTTP
    handlers can run during the load.

    Returns (GeneticAnalysis, List[VariantLite]).
    """
    query = select(GeneticAnalysis).where(GeneticAnalysis.id == analysis_id)
    if user_id is not None:
        query = query.where(GeneticAnalysis.user_id == user_id)

    async with async_session_factory() as session:
        result = await session.execute(query)
        analysis = result.scalar_one_or_none()

    if not analysis:
        raise AnalysisNotFoundException(
            f"Analysis {analysis_id} not found for user {user_id}"
        )

    CHUNK = 5_000
    variants: list = []

    stmt = (
        select(
            AnalysisVariant.id,
            AnalysisVariant.analysis_id,
            AnalysisVariant.marker_id,
            AnalysisVariant.genotype,
            AnalysisVariant.quality,
            AnalysisVariant.filter_status,
            AnalysisVariant.info,
            GeneticMarker.rsid,
            GeneticMarker.chromosome,
            GeneticMarker.position,
            GeneticMarker.ref_allele,
            GeneticMarker.alt_alleles,
            GeneticMarker.gene_symbol,
        )
        .join(GeneticMarker, AnalysisVariant.marker_id == GeneticMarker.id)
        .where(AnalysisVariant.analysis_id == analysis_id)
        .execution_options(stream_results=True, yield_per=CHUNK)
    )

    async with async_session_factory() as session:
        stream = await session.stream(stmt)
        chunk_num = 0
        async for partition in stream.partitions(CHUNK):
            if chunk_num > 0:
                await asyncio.sleep(0)
            chunk_num += 1
            for row in partition:
                marker = _MarkerLite(
                    id=row.marker_id,
                    rsid=row.rsid,
                    chromosome=row.chromosome,
                    position=row.position,
                    ref_allele=row.ref_allele,
                    alt_alleles=row.alt_alleles,
                    gene_symbol=row.gene_symbol,
                )
                variants.append(VariantLite(
                    id=row.id,
                    analysis_id=row.analysis_id,
                    marker_id=row.marker_id,
                    genotype=row.genotype,
                    quality=row.quality,
                    filter_status=row.filter_status,
                    info=row.info,
                    marker=marker,
                ))

    return analysis, variants


# ---------------------------------------------------------------------------
# Gene coordinate cache — loaded once per process from ensembl_genes PG
# ---------------------------------------------------------------------------

_GENE_COORD_CACHE: Optional[Dict[str, List]] = None
_GENE_COORD_LOCK: Optional[asyncio.Lock] = None


def _get_gene_coord_lock() -> asyncio.Lock:
    global _GENE_COORD_LOCK
    if _GENE_COORD_LOCK is None:
        _GENE_COORD_LOCK = asyncio.Lock()
    return _GENE_COORD_LOCK


async def _load_gene_coordinate_table() -> Optional[Dict[str, List]]:
    """Load Ensembl gene coordinates into memory as sorted arrays per chromosome.

    Cached after first load — 49K genes fit comfortably in RAM.
    Returns {chrom: [(start, end, symbol, biotype), ...]} sorted by start.
    """
    global _GENE_COORD_CACHE
    if _GENE_COORD_CACHE is not None:
        return _GENE_COORD_CACHE
    async with _get_gene_coord_lock():
        if _GENE_COORD_CACHE is not None:
            return _GENE_COORD_CACHE
        try:
            table: Dict[str, List] = {}
            async with async_session_factory() as session:
                rows = (await session.execute(
                    select(
                        EnsemblGene.chromosome,
                        EnsemblGene.start_pos,
                        EnsemblGene.end_pos,
                        EnsemblGene.gene_symbol,
                        EnsemblGene.biotype,
                    ).order_by(EnsemblGene.chromosome, EnsemblGene.start_pos)
                )).all()
            for row in rows:
                table.setdefault(row.chromosome, []).append(
                    (row.start_pos, row.end_pos, row.gene_symbol, row.biotype)
                )
            _GENE_COORD_CACHE = table
            total = sum(len(v) for v in table.values())
            logger.info(f"  Gene coordinates loaded: {total} genes across {len(table)} chromosomes")
        except Exception as e:
            logger.warning(f"  Gene coordinate table load failed: {e}")
            return None
    return _GENE_COORD_CACHE


def _find_gene_at_position(
    chrom_table: Dict[str, List],
    chrom: str,
    pos: int,
) -> Optional[str]:
    """Binary search for smallest gene overlapping pos on chrom.

    Prefers protein_coding genes; picks smallest when multiple overlap.
    """
    import bisect
    genes = chrom_table.get(chrom)
    if not genes:
        return None
    # genes = [(start, end, symbol, biotype)] sorted by start_pos.
    # Find first index where start_pos > pos (everything before has start <= pos).
    hi = bisect.bisect_left(genes, (pos + 1,))
    best: Optional[str] = None
    best_coding = False
    best_size = float('inf')
    for i in range(hi - 1, -1, -1):
        start, end, symbol, biotype = genes[i]
        # No gene this far back can still span to pos
        if pos - start > 2_000_000:
            break
        if end < pos:
            continue
        is_coding = (biotype == 'protein_coding')
        size = end - start
        if (
            best is None
            or (is_coding and not best_coding)
            or (is_coding == best_coding and size < best_size)
        ):
            best = symbol
            best_coding = is_coding
            best_size = size
    return best


async def build_rsid_gene_map(variants: List) -> Dict[str, str]:
    """Build rsid→gene map from data_sources files + in-memory gene coordinates.

    Sources (in order):
    0. Cached genetic_markers.gene_symbol (PERF-04 warm cache)
    1. ClinVar variant_summary.txt.gz (data_sources file) — rsid→gene for clinical variants
    2. Ensembl gene coordinate in-memory binary search — position-based for remainder

    Never uses the sparse PG clinvar_variants table as primary source.
    """
    gene_map: Dict[str, str] = {}
    rsids = [str(v.rsid) for v in variants if v.rsid]

    # Step 0: use cached gene_symbol on genetic_markers (PERF-04)
    for v in variants:
        if v.rsid and getattr(v.marker, 'gene_symbol', None):
            gene_map[str(v.rsid)] = v.marker.gene_symbol

    cached_count = len(gene_map)
    if cached_count:
        logger.info(f"  gene_symbol cache: {cached_count}/{len(rsids)} "
                    f"({100 * cached_count / max(1, len(rsids)):.1f}%)")

    # Step 1: ClinVar data_sources file (variant_summary.txt.gz)
    # Primary source — covers clinical variants with GeneSymbol column from ClinVar TSV.
    # Uses ClinVarDirectService which reads directly from data_sources, not PG.
    unmapped = [r for r in rsids if r not in gene_map]
    if unmapped:
        try:
            from .clinvar_local import get_clinvar_direct_service
            cv_svc = get_clinvar_direct_service()
            if not cv_svc.is_loaded:
                await cv_svc.ensure_loaded()
            if cv_svc.is_loaded:
                BATCH = 5_000
                for i in range(0, len(unmapped), BATCH):
                    batch = unmapped[i:i + BATCH]
                    if i:
                        await asyncio.sleep(0)
                    results = await cv_svc.lookup_batch(batch)
                    for rsid, data in results.items():
                        if data and data.get('found'):
                            genes = data.get('genes', [])
                            if genes and genes[0]:
                                gene_map[rsid] = genes[0]
                clinvar_count = len(gene_map)
                logger.info(
                    f"  ClinVar file rsid→gene: {clinvar_count}/{len(rsids)} "
                    f"({100 * clinvar_count / max(1, len(rsids)):.1f}%)"
                )
            else:
                logger.debug("  ClinVar direct service not available")
        except Exception as e:
            logger.debug(f"  ClinVar file gene lookup skipped: {e}")

    # Step 2: In-memory position-based lookup using Ensembl gene coordinates.
    # Loads all 49K ensembl_genes into memory once (process-level cache),
    # then does binary search per position — much faster than 579K PG queries.
    unmapped_with_pos = [
        v for v in variants
        if v.rsid and str(v.rsid) not in gene_map
        and v.chromosome and v.position
    ]
    if unmapped_with_pos:
        try:
            chrom_table = await _load_gene_coordinate_table()
            if chrom_table:
                pre = len(gene_map)
                for v in unmapped_with_pos:
                    gs = _find_gene_at_position(
                        chrom_table,
                        str(v.chromosome).replace('chr', ''),
                        int(v.position),
                    )
                    if gs:
                        gene_map[str(v.rsid)] = gs
                added = len(gene_map) - pre
                logger.info(
                    f"  Ensembl position→gene: {added} added "
                    f"(total: {len(gene_map)}/{len(rsids)}, "
                    f"{100 * len(gene_map) / max(1, len(rsids)):.1f}%)"
                )
        except Exception as e:
            logger.debug(f"  Ensembl position gene lookup skipped: {e}")

    # Write-back new gene_symbol discoveries to genetic_markers (PERF-04)
    # Only write for markers that had no cached gene_symbol yet
    to_update = {
        str(v.rsid): gene_map[str(v.rsid)]
        for v in variants
        if v.rsid
        and str(v.rsid) in gene_map
        and not getattr(v.marker, 'gene_symbol', None)
    }
    if to_update:
        from sqlalchemy import bindparam as _bp
        CHUNK = 5_000
        params = [{'b_rsid': rsid, 'b_gene': gene[:50]} for rsid, gene in to_update.items()]
        try:
            for i in range(0, len(params), CHUNK):
                async with async_session_factory() as session:
                    await session.execute(
                        GeneticMarker.__table__.update()
                        .where(GeneticMarker.__table__.c.rsid == _bp('b_rsid'))
                        .values(gene_symbol=_bp('b_gene')),
                        params[i:i + CHUNK],
                    )
                    await session.commit()
            logger.info(f"  Cached gene_symbol for {len(to_update)} markers (PERF-04)")
        except Exception as e:
            logger.warning(f"  gene_symbol write-back skipped: {e}")

    return gene_map


async def load_enabled_sources() -> Optional[List[str]]:
    """Load enabled annotation sources from the database.

    Returns a list of enabled source names, or None if the table
    doesn't exist yet / is empty (meaning use all sources).
    """
    LOCAL_SOURCES = {'alpha_missense', 'clinvar_local', 'thousand_genomes', 'ensembl'}
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(AnnotationSourceConfig.source_name, AnnotationSourceConfig.is_enabled)
            )
            rows = result.all()
        if not rows:
            return None

        enabled = set()
        explicitly_disabled = set()
        for name, is_enabled in rows:
            if is_enabled:
                enabled.add(name)
            else:
                explicitly_disabled.add(name)

        if 'ensembl_vep' in enabled:
            enabled.add('ensembl')
        if 'ensembl_vep' in explicitly_disabled and 'ensembl' not in enabled:
            explicitly_disabled.add('ensembl')

        for src in LOCAL_SOURCES:
            if src not in explicitly_disabled:
                enabled.add(src)

        enabled.discard('ensembl_vep')
        names = sorted(enabled)
        logger.info(f"Enabled annotation sources: {names}")
        return names
    except Exception as e:
        logger.warning(f"Could not load annotation source config: {e} — using all sources")
        return None


async def correct_ref_alleles(
    variants: List,
    annotation_results: Dict[str, AnnotationResult],
):
    """Correct genetic_markers.ref_allele and alt_alleles from authoritative
    annotation sources (gnomAD, Ensembl VEP, ClinVar, 1000 Genomes).
    """
    from sqlalchemy import bindparam

    ref_corrections: Dict[int, str] = {}
    alt_corrections: Dict[int, str] = {}

    for _idx, variant in enumerate(variants):
        if _idx > 0 and _idx % 1000 == 0:
            await asyncio.sleep(0)
        rsid = getattr(variant, 'rsid', None)
        if not rsid:
            continue

        marker = getattr(variant, 'marker', None)
        if not marker:
            continue

        ar = annotation_results.get(rsid)
        if not ar or not ar.annotation_data:
            continue

        annotations = ar.annotation_data.get('annotations', {})
        true_ref = None
        true_alt = None

        # 1. gnomAD ref_allele (highest confidence — from VCF)
        gnomad = annotations.get('gnomad', {})
        if gnomad and gnomad.get('found'):
            ref = gnomad.get('ref_allele') or gnomad.get('ref')
            if ref and ref not in ('N', '-', '.', ''):
                true_ref = ref.strip().upper()
            alt = gnomad.get('alt_allele') or gnomad.get('alt')
            if alt and alt not in ('N', '-', '.', ''):
                true_alt = alt.strip().upper()

        # 2. Ensembl VEP allele_string
        if not true_ref:
            ensembl = annotations.get('ensembl', {})
            if ensembl and ensembl.get('found') and ensembl.get('data'):
                data_list = ensembl['data']
                if isinstance(data_list, list) and data_list:
                    allele_str = data_list[0].get('allele_string', '')
                    if '/' in allele_str:
                        parts = allele_str.split('/')
                        ref = parts[0].strip().upper()
                        if ref and ref not in ('N', '-', '.', ''):
                            true_ref = ref
                        if len(parts) > 1:
                            alts = parts[1].split(',')
                            alt = alts[0].strip().upper()
                            if alt and alt not in ('N', '-', '.', ''):
                                true_alt = true_alt or alt

        # 3. ClinVar local ref_allele
        if not true_ref:
            cv = annotations.get('clinvar_local', {})
            if cv and cv.get('found'):
                ref = cv.get('ref_allele')
                if ref and ref not in ('N', '-', '.', ''):
                    true_ref = ref.strip().upper()
                alt = cv.get('alt_allele') or cv.get('alternate_allele')
                if alt and alt not in ('N', '-', '.', ''):
                    true_alt = true_alt or alt.strip().upper()

        # 4. 1000 Genomes ref_allele
        if not true_ref:
            tkg = annotations.get('thousand_genomes', {})
            if tkg and tkg.get('found'):
                ref = tkg.get('ref_allele')
                if ref and ref not in ('N', '-', '.', ''):
                    true_ref = ref.strip().upper()

        if not true_ref:
            continue

        current_ref = (getattr(marker, 'ref_allele', '') or '').strip().upper()
        current_alt = (getattr(marker, 'alt_alleles', '') or '').strip().upper()

        if current_ref != true_ref:
            ref_corrections[marker.id] = true_ref

        if true_alt and true_alt != true_ref:
            if current_alt == current_ref or current_alt in ('N', '-', '.', ''):
                alt_corrections[marker.id] = true_alt

    if not ref_corrections and not alt_corrections:
        logger.info("ref/alt allele correction: all markers already correct")
        return

    CHUNK = 5000

    if ref_corrections:
        update_params = [{'b_id': mid, 'b_ref': ref} for mid, ref in ref_corrections.items()]
        for i in range(0, len(update_params), CHUNK):
            chunk = update_params[i:i + CHUNK]
            async with async_session_factory() as session:
                conn = await session.connection()
                await conn.execute(
                    GeneticMarker.__table__.update()
                    .where(GeneticMarker.__table__.c.id == bindparam('b_id'))
                    .values(ref_allele=bindparam('b_ref')),
                    chunk
                )
                await session.commit()

    if alt_corrections:
        update_params = [{'b_id': mid, 'b_alt': alt} for mid, alt in alt_corrections.items()]
        for i in range(0, len(update_params), CHUNK):
            chunk = update_params[i:i + CHUNK]
            async with async_session_factory() as session:
                conn = await session.connection()
                await conn.execute(
                    GeneticMarker.__table__.update()
                    .where(GeneticMarker.__table__.c.id == bindparam('b_id'))
                    .values(alt_alleles=bindparam('b_alt')),
                    chunk
                )
                await session.commit()

    logger.info(
        f"ref/alt allele correction: {len(ref_corrections)} ref + "
        f"{len(alt_corrections)} alt updates from authoritative sources "
        f"(gnomAD/Ensembl/ClinVar/1000G)"
    )
