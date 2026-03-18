"""Ancestry results insight generator.

Estimates ancestry composition using a genotype-likelihood model.
Uses a pre-computed Ancestry-Informative Markers (AIMs) panel — variants
with high allele-frequency differentiation (FST proxy > 0.40) across
the 5 1000G super-populations.  The panel is loaded once from the
``ancestry_aims_panel`` table into an in-memory dict, making subsequent
ancestry calls pure Python with zero heavy DB queries.
"""
import asyncio
import logging
import math
import time
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text

from ...db.models import AncestryResult
from ...db.database import async_session_factory
from .base import GeneratorContext

logger = logging.getLogger(__name__)

POP_CODES = ['afr', 'amr', 'eas', 'eur', 'sas']
POP_LABELS = {
    'afr': 'African',
    'amr': 'Admixed American',
    'eas': 'East Asian',
    'eur': 'European',
    'sas': 'South Asian',
}
POP_ORIGINS = {
    'afr': 'Sub-Saharan Africa',
    'amr': 'The Americas',
    'eas': 'East & Southeast Asia',
    'eur': 'Europe & Western Asia',
    'sas': 'South & Central Asia',
}

NEANDERTHAL_RSIDS = {
    'rs2066827', 'rs10166942', 'rs2298813', 'rs4792887', 'rs1534696',
    'rs3917862', 'rs10490770', 'rs2664280', 'rs12477142', 'rs11209026',
    'rs1800407', 'rs7214986', 'rs2066807', 'rs4988235', 'rs12913832',
    'rs1426654', 'rs16891982', 'rs1805007', 'rs1805008', 'rs6152',
}

FLOOR = 0.001

# Module-level cache: loaded once per server lifetime from ancestry_aims_panel.
# Dict[rsid, (af_afr, af_amr, af_eas, af_eur, af_sas)]
_AIMS_CACHE: Optional[Dict[str, Tuple[float, float, float, float, float]]] = None


async def _load_aims_panel() -> Dict[str, Tuple[float, float, float, float, float]]:
    """Load the pre-computed AIMs panel into memory (once per server lifetime)."""
    global _AIMS_CACHE
    if _AIMS_CACHE is not None:
        return _AIMS_CACHE

    t0 = time.monotonic()
    cache: Dict[str, Tuple[float, float, float, float, float]] = {}
    async with async_session_factory() as session:
        # Only load the most differentiated markers (FST ≥ 0.70).
        # This gives ~60K markers — ancestry panels in literature use ~5K.
        # Loading all 1.38M adds 87s of startup for marginal accuracy gain.
        result = await session.execute(text(
            "SELECT rsid, af_afr, af_amr, af_eas, af_eur, af_sas "
            "FROM ancestry_aims_panel WHERE fst_delta >= 0.70"
        ))
        for rsid, af_afr, af_amr, af_eas, af_eur, af_sas in result.fetchall():
            cache[rsid] = (af_afr, af_amr, af_eas, af_eur, af_sas)

    _AIMS_CACHE = cache
    logger.info(f"Loaded {len(cache)} ancestry-informative markers in {time.monotonic()-t0:.1f}s")
    return _AIMS_CACHE


def _genotype_log_likelihood(af: float, gt_type: str) -> float:
    p = max(min(af, 1 - FLOOR), FLOOR)
    q = 1 - p
    if gt_type == 'hom_ref':
        return math.log(q * q + 1e-30)
    elif gt_type == 'het':
        return math.log(2 * p * q + 1e-30)
    else:
        return math.log(p * p + 1e-30)


def _classify_genotype(gt_str: Optional[str], ref: Optional[str], alt: Optional[str]) -> Optional[str]:
    if not gt_str:
        return None
    gt = gt_str.strip().upper()
    if '/' in gt:
        alleles = gt.split('/')
    elif '|' in gt:
        alleles = gt.split('|')
    elif len(gt) == 2:
        alleles = [gt[0], gt[1]]
    else:
        return None
    if len(alleles) != 2:
        return None
    a1, a2 = alleles[0].strip(), alleles[1].strip()
    ref_u = (ref or '').strip().upper()
    alt_u = (alt or '').strip().upper()
    if ref_u and alt_u:
        is_ref = [a == ref_u for a in (a1, a2)]
        is_alt = [a == alt_u for a in (a1, a2)]
        if all(is_ref):
            return 'hom_ref'
        if all(is_alt):
            return 'hom_alt'
        if any(is_ref) and any(is_alt):
            return 'het'
        if a1 != a2:
            return 'het'
        return 'hom_ref'
    else:
        if a1 == a2:
            return 'hom_ref'
        return 'het'


async def generate_ancestry_results(ctx: GeneratorContext) -> int:
    t0 = time.monotonic()

    # Load pre-computed AIMs panel (cached after first call)
    aims = await _load_aims_panel()
    if not aims:
        logger.warning("ancestry_aims_panel is empty — run migration 010")
        return 0

    # Fetch user variants that overlap with the AIMs panel
    # Push the filter to SQL rather than fetching all 609K and intersecting in Python
    aims_rsids = list(aims.keys())
    rows: list = []
    BATCH = 10000
    async with async_session_factory() as read_session:
        for bi in range(0, len(aims_rsids), BATCH):
            batch = aims_rsids[bi:bi + BATCH]
            result = await read_session.execute(text("""
                SELECT DISTINCT ON (gm.rsid)
                    gm.rsid, av.genotype, gm.ref_allele, gm.alt_alleles
                FROM analysis_variants av
                JOIN genetic_markers gm ON av.marker_id = gm.id
                WHERE av.analysis_id = :aid
                  AND gm.rsid = ANY(:rsids)
            """), {'aid': ctx.analysis_id, 'rsids': batch})
            for rsid, genotype, ref_allele, alt_alleles in result.fetchall():
                afs = aims.get(rsid)
                if afs is not None:
                    rows.append((rsid, genotype, ref_allele, alt_alleles, *afs))
            await asyncio.sleep(0)

    logger.info(f"Ancestry: {len(rows)} AIMs matched "
                f"({len(aims)} panel size) in {time.monotonic()-t0:.1f}s")

    log_likelihoods = {p: 0.0 for p in POP_CODES}
    informative_count = 0
    contributing_rsids: Dict[str, List[str]] = {p: [] for p in POP_CODES}

    for rsid, genotype, ref_allele, alt_alleles, af_afr, af_amr, af_eas, af_eur, af_sas in rows:
        afs = {
            'afr': af_afr or 0.0,
            'amr': af_amr or 0.0,
            'eas': af_eas or 0.0,
            'eur': af_eur or 0.0,
            'sas': af_sas or 0.0,
        }

        af_vals = list(afs.values())
        # Skip uninformative variants (all AFs very similar)
        if max(af_vals) - min(af_vals) < 0.05:
            continue
        # Skip fixed variants
        if min(af_vals) > 0.95 or max(af_vals) < 0.005:
            continue

        gt_type = _classify_genotype(genotype, ref_allele, alt_alleles)
        if not gt_type:
            continue

        informative_count += 1

        for pc in POP_CODES:
            ll = _genotype_log_likelihood(afs[pc], gt_type)
            log_likelihoods[pc] += ll

        best_pop = max(afs, key=lambda p: afs[p])
        if afs[best_pop] > 0.3:
            contributing_rsids[best_pop].append(rsid)

    logger.info(f"Ancestry: {informative_count} informative variants out of {len(rows)} matched")

    # Convert log-likelihoods to percentages
    if informative_count < 10:
        result = AncestryResult(
            analysis_id=ctx.analysis_id,
            population='Undetermined',
            percentage='0',
            confidence='low',
            geographic_origin='Insufficient data',
            associated_variants=[getattr(v, 'rsid', '') for v in ctx.variants[:5] if getattr(v, 'rsid', None)],
            composition=[{'region': 'Undetermined', 'percentage': 0}],
        )
        ctx.session.add(result)
        return 1

    max_ll = max(log_likelihoods.values())
    # Temperature scaling: with many variants, raw log-likelihoods
    # produce extreme softmax concentrations.  Scale by a factor
    # proportional to the number of informative variants so that the
    # resulting distribution has realistic spread (similar to using a
    # curated panel of ~1-2 K ancestry-informative markers).
    temperature = max(informative_count / 500, 1.0)
    exp_lls = {p: math.exp((log_likelihoods[p] - max_ll) / temperature) for p in POP_CODES}
    total_exp = sum(exp_lls.values()) or 1.0
    percentages = {p: round((exp_lls[p] / total_exp) * 100, 1) for p in POP_CODES}

    dominant_pop = max(percentages, key=lambda p: percentages[p])
    confidence = 'high' if percentages[dominant_pop] > 60 else 'moderate' if percentages[dominant_pop] > 35 else 'low'

    composition = sorted(
        [
            {'region': POP_LABELS[p], 'percentage': percentages[p]}
            for p in POP_CODES if percentages[p] >= 0.5
        ],
        key=lambda x: x['percentage'],
        reverse=True,
    )

    # Neanderthal estimation
    user_rsids = {getattr(v, 'rsid', '') for v in ctx.variants}
    neanderthal_hits = user_rsids & NEANDERTHAL_RSIDS
    neanderthal_pct = round(len(neanderthal_hits) / max(len(NEANDERTHAL_RSIDS), 1) * 3.5, 1)
    neanderthal_pct = min(neanderthal_pct, 4.0)

    neanderthal_data = {
        'percentage': neanderthal_pct,
        'variants': len(neanderthal_hits),
        'moreOrLess': 'more' if neanderthal_pct > 2.0 else 'less' if neanderthal_pct < 1.5 else 'about average',
        'comparison': f'than the average of ~2% for non-African populations ({informative_count} variants analyzed)',
    }

    logger.info(f"Ancestry result: {', '.join(f'{POP_LABELS[p]} {percentages[p]}%' for p in POP_CODES)} "
                f"(dominant={POP_LABELS[dominant_pop]}, confidence={confidence})")

    result = AncestryResult(
        analysis_id=ctx.analysis_id,
        population=POP_LABELS[dominant_pop],
        percentage=str(percentages[dominant_pop]),
        confidence=confidence,
        geographic_origin=POP_ORIGINS[dominant_pop],
        associated_variants=contributing_rsids.get(dominant_pop, [])[:20],
        composition=composition,
        neanderthal_variants=neanderthal_data,
    )
    ctx.session.add(result)
    return 1
