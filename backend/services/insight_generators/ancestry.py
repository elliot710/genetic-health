"""Ancestry results insight generator — hierarchical model.

Estimates ancestry composition using a three-phase approach:

Phase 1 — **Super-population estimation** (always runs)
    Genotype-likelihood model against 5 super-populations (AFR, AMR, EAS,
    EUR, SAS) using the pre-computed AIMs panel from ``ancestry_aims_panel``.

Phase 2 — **European sub-population estimation** (runs when EUR > 50 %)
    When sub-population allele frequencies are available (the ``subpop_freqs``
    JSON column on ``ancestry_aims_panel``), runs a second genotype-likelihood
    pass to decompose the European component into finer sub-populations
    (e.g. East European, Balkan, Baltic, Nordic, …).

Phase 3 — **Neanderthal DNA estimation** (always runs)
    Counts matches against a curated set of Neanderthal-introgressed markers.

The AIMs panel is loaded **once** per server lifetime into an in-memory dict.
"""
import asyncio
import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from ...db.models import AncestryResult
from ...db.database import async_session_factory
from .base import GeneratorContext

logger = logging.getLogger(__name__)

# ── Super-population definitions ────────────────────────────────────
SUPER_POP_CODES = ["afr", "amr", "eas", "eur", "sas"]
SUPER_POP_LABELS: Dict[str, str] = {
    "afr": "African",
    "amr": "Admixed American",
    "eas": "East Asian",
    "eur": "European",
    "sas": "South Asian",
}
SUPER_POP_ORIGINS: Dict[str, str] = {
    "afr": "Sub-Saharan Africa",
    "amr": "The Americas",
    "eas": "East & Southeast Asia",
    "eur": "Europe & Western Asia",
    "sas": "South & Central Asia",
}

# ── European sub-population definitions ─────────────────────────────
# gnomAD-derived sub-populations (preferred when data available)
EUR_SUBPOP_GNOMAD: Dict[str, Dict[str, str]] = {
    "nfe_bgr": {
        "label": "Balkan",
        "origin": "Southeastern Europe",
        "description": "Bulgarian, Romanian, Serbian, Croatian",
    },
    "nfe_est": {
        "label": "East European",
        "origin": "Eastern Europe",
        "description": "Estonian, Latvian, Lithuanian, Polish, Ukrainian",
    },
    "nfe_nwe": {
        "label": "Northwestern European",
        "origin": "Northwestern Europe",
        "description": "Dutch, German, Belgian, Swiss",
    },
    "nfe_seu": {
        "label": "Southern European",
        "origin": "Southern Europe",
        "description": "Greek, Albanian, Southern Italian",
    },
    "nfe_swe": {
        "label": "Nordic",
        "origin": "Northern Europe",
        "description": "Swedish, Norwegian, Danish",
    },
    "nfe_onf": {
        "label": "Other European",
        "origin": "Europe",
        "description": "Other non-Finnish European",
    },
    "fin": {
        "label": "Finnish & Baltic",
        "origin": "Northern Europe",
        "description": "Finnish, Karelian",
    },
    "asj": {
        "label": "Ashkenazi Jewish",
        "origin": "Eastern Europe",
        "description": "Ashkenazi Jewish diaspora",
    },
}

# 1000G-derived European sub-populations (fallback)
EUR_SUBPOP_1KG: Dict[str, Dict[str, str]] = {
    "ceu": {
        "label": "Central & Western European",
        "origin": "Central Europe",
    },
    "fin": {
        "label": "Finnish & Baltic",
        "origin": "Northern Europe",
    },
    "gbr": {
        "label": "British & Northwestern",
        "origin": "Northwestern Europe",
    },
    "ibs": {
        "label": "Iberian & Mediterranean",
        "origin": "Southwestern Europe",
    },
    "tsi": {
        "label": "Italian & Southern European",
        "origin": "Southern Europe",
    },
}

# ── Neanderthal markers ─────────────────────────────────────────────
NEANDERTHAL_RSIDS = frozenset({
    "rs2066827", "rs10166942", "rs2298813", "rs4792887", "rs1534696",
    "rs3917862", "rs10490770", "rs2664280", "rs12477142", "rs11209026",
    "rs1800407", "rs7214986", "rs2066807", "rs4988235", "rs12913832",
    "rs1426654", "rs16891982", "rs1805007", "rs1805008", "rs6152",
})

FLOOR = 0.001
MIN_INFORMATIVE_VARIANTS = 10

# ── Module-level caches ─────────────────────────────────────────────
# Super-population cache: rsid → (af_afr, af_amr, af_eas, af_eur, af_sas)
_SUPER_CACHE: Optional[Dict[str, Tuple[float, ...]]] = None
# Sub-population cache: rsid → {pop_code: af, ...}
_SUBPOP_CACHE: Optional[Dict[str, Dict[str, float]]] = None
# Which sub-pop system is loaded ("gnomad", "1kg", or None)
_SUBPOP_SYSTEM: Optional[str] = None


async def _load_aims_panel() -> Tuple[
    Dict[str, Tuple[float, ...]],
    Optional[Dict[str, Dict[str, float]]],
    Optional[str],
]:
    """Load the pre-computed AIMs panel into memory (once per server lifetime)."""
    global _SUPER_CACHE, _SUBPOP_CACHE, _SUBPOP_SYSTEM
    if _SUPER_CACHE is not None:
        return _SUPER_CACHE, _SUBPOP_CACHE, _SUBPOP_SYSTEM

    t0 = time.monotonic()
    super_cache: Dict[str, Tuple[float, ...]] = {}
    subpop_cache: Dict[str, Dict[str, float]] = {}
    subpop_system: Optional[str] = None

    async with async_session_factory() as session:
        result = await session.execute(text(
            "SELECT rsid, af_afr, af_amr, af_eas, af_eur, af_sas, subpop_freqs "
            "FROM ancestry_aims_panel WHERE fst_delta >= 0.70"
        ))
        for row in result.fetchall():
            rsid = row[0]
            super_cache[rsid] = (row[1], row[2], row[3], row[4], row[5])
            spf = row[6]
            if spf:
                if isinstance(spf, str):
                    import json as _json
                    try:
                        spf = _json.loads(spf)
                    except Exception:
                        spf = None
                if isinstance(spf, dict):
                    subpop_cache[rsid] = spf

    # Detect which sub-population system is loaded
    if subpop_cache:
        sample_keys: set = set()
        for v in list(subpop_cache.values())[:10]:
            sample_keys.update(v.keys())
        if any(k.startswith("nfe_") for k in sample_keys):
            subpop_system = "gnomad"
        elif sample_keys & {"ceu", "fin", "gbr", "ibs", "tsi"}:
            subpop_system = "1kg"

    _SUPER_CACHE = super_cache
    _SUBPOP_CACHE = subpop_cache if subpop_cache else None
    _SUBPOP_SYSTEM = subpop_system

    elapsed = time.monotonic() - t0
    logger.info(
        f"Loaded {len(super_cache)} ancestry AIMs "
        f"({len(subpop_cache)} with sub-pop [{subpop_system}]) in {elapsed:.1f}s"
    )
    return _SUPER_CACHE, _SUBPOP_CACHE, _SUBPOP_SYSTEM


def invalidate_aims_cache() -> None:
    """Force cache reload on next call (used after data loading)."""
    global _SUPER_CACHE, _SUBPOP_CACHE, _SUBPOP_SYSTEM
    _SUPER_CACHE = None
    _SUBPOP_CACHE = None
    _SUBPOP_SYSTEM = None


# ── Genotype classification ─────────────────────────────────────────

def _classify_genotype(
    gt_str: Optional[str], ref: Optional[str], alt: Optional[str],
) -> Optional[str]:
    """Classify a genotype string as hom_ref, het, or hom_alt."""
    if not gt_str:
        return None
    gt = gt_str.strip().upper()
    if "/" in gt:
        alleles = gt.split("/")
    elif "|" in gt:
        alleles = gt.split("|")
    elif len(gt) == 2:
        alleles = [gt[0], gt[1]]
    else:
        return None
    if len(alleles) != 2:
        return None

    a1, a2 = alleles[0].strip(), alleles[1].strip()
    ref_u = (ref or "").strip().upper()
    alt_u = (alt or "").strip().upper()

    if ref_u and alt_u:
        is_ref = [a == ref_u for a in (a1, a2)]
        is_alt = [a == alt_u for a in (a1, a2)]
        if all(is_ref):
            return "hom_ref"
        if all(is_alt):
            return "hom_alt"
        if any(is_ref) and any(is_alt):
            return "het"
        if a1 != a2:
            return "het"
        return "hom_ref"
    else:
        return "hom_ref" if a1 == a2 else "het"


def _genotype_log_likelihood(af: float, gt_type: str) -> float:
    """Compute log P(genotype | allele frequency)."""
    p = max(min(af, 1 - FLOOR), FLOOR)
    q = 1 - p
    if gt_type == "hom_ref":
        return math.log(q * q + 1e-30)
    elif gt_type == "het":
        return math.log(2 * p * q + 1e-30)
    else:  # hom_alt
        return math.log(p * p + 1e-30)


# ── Phase 1: Super-population estimation ────────────────────────────

def _compute_super_pop(
    user_rows: List[Tuple[str, Optional[str], Optional[str], Optional[str]]],
    super_cache: Dict[str, Tuple[float, ...]],
) -> Tuple[Dict[str, float], int, Dict[str, List[str]]]:
    """Compute super-population percentages via genotype-likelihood model.

    Returns (percentages, informative_count, contributing_rsids).
    """
    log_lls: Dict[str, float] = {p: 0.0 for p in SUPER_POP_CODES}
    informative = 0
    contributing: Dict[str, List[str]] = {p: [] for p in SUPER_POP_CODES}

    for rsid, genotype, ref_allele, alt_alleles in user_rows:
        afs_tuple = super_cache.get(rsid)
        if afs_tuple is None:
            continue

        afs = {pc: (v or 0.0) for pc, v in zip(SUPER_POP_CODES, afs_tuple)}
        vals = list(afs.values())

        # Skip uninformative / fixed variants
        if max(vals) - min(vals) < 0.05:
            continue
        if min(vals) > 0.95 or max(vals) < 0.005:
            continue

        gt_type = _classify_genotype(genotype, ref_allele, alt_alleles)
        if not gt_type:
            continue

        informative += 1
        for pc in SUPER_POP_CODES:
            log_lls[pc] += _genotype_log_likelihood(afs[pc], gt_type)

        best_pop = max(afs, key=lambda p: afs[p])
        if afs[best_pop] > 0.3:
            contributing[best_pop].append(rsid)

    if informative < MIN_INFORMATIVE_VARIANTS:
        return {p: 0.0 for p in SUPER_POP_CODES}, informative, contributing

    # Softmax with temperature scaling
    max_ll = max(log_lls.values())
    temperature = max(informative / 500, 1.0)
    exp_lls = {p: math.exp((log_lls[p] - max_ll) / temperature) for p in SUPER_POP_CODES}
    total = sum(exp_lls.values()) or 1.0
    pcts = {p: round((exp_lls[p] / total) * 100, 1) for p in SUPER_POP_CODES}

    return pcts, informative, contributing


# ── Phase 2: European sub-population estimation ─────────────────────

def _compute_eur_subpop(
    user_rows: List[Tuple[str, Optional[str], Optional[str], Optional[str]]],
    subpop_cache: Dict[str, Dict[str, float]],
    pop_codes: List[str],
) -> Tuple[Dict[str, float], int]:
    """Compute European sub-population percentages via genotype-likelihood model.

    Returns (percentages, informative_count).
    """
    log_lls: Dict[str, float] = {p: 0.0 for p in pop_codes}
    informative = 0

    for rsid, genotype, ref_allele, alt_alleles in user_rows:
        freqs = subpop_cache.get(rsid)
        if not freqs:
            continue

        # Need at least 3 sub-pop frequencies for a useful comparison
        avail = {k: v for k, v in freqs.items() if k in pop_codes and v is not None}
        if len(avail) < 3:
            continue

        # Skip if all sub-pop frequencies are essentially the same
        vals = list(avail.values())
        if max(vals) - min(vals) < 0.03:
            continue

        gt_type = _classify_genotype(genotype, ref_allele, alt_alleles)
        if not gt_type:
            continue

        informative += 1
        for pc in pop_codes:
            af = freqs.get(pc)
            if af is not None:
                log_lls[pc] += _genotype_log_likelihood(af, gt_type)

    if informative < MIN_INFORMATIVE_VARIANTS:
        return {p: 0.0 for p in pop_codes}, informative

    # Softmax with gentler temperature for sub-populations
    max_ll = max(log_lls.values())
    temperature = max(informative / 300, 1.0)
    exp_lls = {p: math.exp((log_lls[p] - max_ll) / temperature) for p in pop_codes}
    total = sum(exp_lls.values()) or 1.0
    pcts = {p: round((exp_lls[p] / total) * 100, 1) for p in pop_codes}

    return pcts, informative


# ── Phase 3: Neanderthal estimation ─────────────────────────────────

def _compute_neanderthal(
    user_rsids: set,
    informative_count: int,
) -> Dict[str, Any]:
    """Estimate Neanderthal DNA percentage from marker overlap."""
    hits = user_rsids & NEANDERTHAL_RSIDS
    pct = round(len(hits) / max(len(NEANDERTHAL_RSIDS), 1) * 3.5, 1)
    pct = min(pct, 4.0)
    return {
        "percentage": pct,
        "variants": len(hits),
        "moreOrLess": (
            "more" if pct > 2.0 else "less" if pct < 1.5 else "about average"
        ),
        "comparison": (
            f"than the average of ~2% for non-African populations "
            f"({informative_count} variants analyzed)"
        ),
    }


# ── Composition builders ────────────────────────────────────────────

def _build_subpop_composition(
    eur_pcts: Dict[str, float],
    eur_total_pct: float,
    subpop_defs: Dict[str, Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Scale sub-pop percentages so they sum to the EUR fraction of the total."""
    raw_sum = sum(eur_pcts.values()) or 1.0
    entries: List[Dict[str, Any]] = []
    for code, pct in eur_pcts.items():
        if pct < 0.3:
            continue
        defn = subpop_defs.get(code, {})
        scaled_pct = round((pct / raw_sum) * eur_total_pct, 1)
        if scaled_pct < 0.5:
            continue
        entries.append({
            "region": defn.get("label", code),
            "percentage": scaled_pct,
            "origin": defn.get("origin", ""),
            "description": defn.get("description", ""),
        })

    # Preserve any European mass dropped by the per-entry thresholds as an
    # "Other European" remainder so the composition still sums to the European
    # total. Without this the breakdown shrinks to whatever few sub-populations
    # survived — the "collapsed to one population" symptom. Only applies when at
    # least one sub-pop survived; when none do, returning [] lets the super-pop
    # fallback in _build_full_composition keep the European fraction.
    if entries:
        remainder = round(eur_total_pct - sum(e["percentage"] for e in entries), 1)
        if remainder >= 0.5:
            entries.append({
                "region": "Other European",
                "percentage": remainder,
                "origin": "Europe",
                "description": "Other European sub-populations",
            })
    return sorted(entries, key=lambda x: x["percentage"], reverse=True)


def _build_full_composition(
    super_pcts: Dict[str, float],
    eur_subpop_entries: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Merge super-population + sub-population composition.

    When European sub-pops are available, replace the single "European"
    entry with the detailed breakdown.
    """
    composition: List[Dict[str, Any]] = []

    if eur_subpop_entries:
        composition.extend(eur_subpop_entries)
        for p in SUPER_POP_CODES:
            if p == "eur":
                continue
            if super_pcts.get(p, 0) >= 0.5:
                composition.append({
                    "region": SUPER_POP_LABELS[p],
                    "percentage": super_pcts[p],
                })
    else:
        composition = sorted(
            [
                {"region": SUPER_POP_LABELS[p], "percentage": super_pcts[p]}
                for p in SUPER_POP_CODES
                if super_pcts.get(p, 0) >= 0.5
            ],
            key=lambda x: x["percentage"],
            reverse=True,
        )

    return sorted(composition, key=lambda x: x["percentage"], reverse=True)


def _confidence_band(primary_pct: float) -> str:
    """Confidence for the dominant population: a ~40 % primary is 'moderate',
    not 'high' — the dominant share must be clearly majority to claim high."""
    return (
        "high" if primary_pct > 60
        else "moderate" if primary_pct > 35
        else "low"
    )


# ── Main generator ──────────────────────────────────────────────────

async def generate_ancestry_results(ctx: GeneratorContext) -> int:
    """Generate ancestry composition results for a single analysis."""
    t0 = time.monotonic()

    # Load AIMs panel (cached after first call)
    super_cache, subpop_cache, subpop_system = await _load_aims_panel()
    if not super_cache:
        logger.warning("ancestry_aims_panel is empty — run migration 010 + populate")
        return 0

    # Fetch user variants overlapping the AIMs panel via batched SQL
    aims_rsids = list(super_cache.keys())
    user_rows: List[Tuple[str, Optional[str], Optional[str], Optional[str]]] = []
    BATCH = 10_000

    async with async_session_factory() as read_session:
        for bi in range(0, len(aims_rsids), BATCH):
            batch = aims_rsids[bi : bi + BATCH]
            result = await read_session.execute(
                text("""
                    SELECT DISTINCT ON (gm.rsid)
                        gm.rsid, av.genotype, gm.ref_allele, gm.alt_alleles
                    FROM analysis_variants av
                    JOIN genetic_markers gm ON av.marker_id = gm.id
                    WHERE av.analysis_id = :aid
                      AND gm.rsid = ANY(:rsids)
                """),
                {"aid": ctx.analysis_id, "rsids": batch},
            )
            for rsid, genotype, ref_allele, alt_alleles in result.fetchall():
                if rsid in super_cache:
                    user_rows.append((rsid, genotype, ref_allele, alt_alleles))
            await asyncio.sleep(0)

    logger.info(
        f"Ancestry: {len(user_rows)} AIMs matched "
        f"({len(super_cache)} panel) in {time.monotonic() - t0:.1f}s"
    )

    # ── Phase 1: Super-population estimation ────────────────────────
    super_pcts, informative_count, contributing = _compute_super_pop(
        user_rows, super_cache,
    )

    if informative_count < MIN_INFORMATIVE_VARIANTS:
        undetermined = AncestryResult(
            analysis_id=ctx.analysis_id,
            population="Undetermined",
            percentage="0",
            confidence="low",
            geographic_origin="Insufficient data",
            associated_variants=[
                getattr(v, "rsid", "")
                for v in ctx.variants[:5]
                if getattr(v, "rsid", None)
            ],
            composition=[{"region": "Undetermined", "percentage": 0}],
        )
        ctx.session.add(undetermined)
        return 1

    dominant_super = max(super_pcts, key=lambda p: super_pcts[p])
    logger.info(
        f"Phase 1: {', '.join(f'{SUPER_POP_LABELS[p]} {super_pcts[p]}%' for p in SUPER_POP_CODES)} "
        f"(informative={informative_count})"
    )

    # ── Phase 2: European sub-population estimation ─────────────────
    eur_subpop_entries: Optional[List[Dict[str, Any]]] = None

    if super_pcts.get("eur", 0) > 50 and subpop_cache:
        subpop_defs: Dict[str, Dict[str, str]]
        if subpop_system == "gnomad":
            pop_codes = list(EUR_SUBPOP_GNOMAD.keys())
            subpop_defs = EUR_SUBPOP_GNOMAD
        else:
            pop_codes = list(EUR_SUBPOP_1KG.keys())
            subpop_defs = EUR_SUBPOP_1KG

        eur_pcts, eur_informative = _compute_eur_subpop(
            user_rows, subpop_cache, pop_codes,
        )

        if eur_informative >= MIN_INFORMATIVE_VARIANTS:
            eur_total = super_pcts["eur"]
            eur_subpop_entries = _build_subpop_composition(
                eur_pcts, eur_total, subpop_defs,
            )
            logger.info(
                f"Phase 2 [{subpop_system}]: "
                + ", ".join(
                    f"{e['region']} {e['percentage']}%"
                    for e in eur_subpop_entries[:6]
                )
                + f" (informative={eur_informative})"
            )

    # ── Phase 3: Neanderthal estimation ─────────────────────────────
    user_rsids = {getattr(v, "rsid", "") for v in ctx.variants}
    neanderthal = _compute_neanderthal(user_rsids, informative_count)

    # ── Build final composition ─────────────────────────────────────
    composition = _build_full_composition(super_pcts, eur_subpop_entries)

    # Determine primary population and confidence
    if eur_subpop_entries and len(eur_subpop_entries) > 0:
        primary_pop = eur_subpop_entries[0]["region"]
        primary_pct = eur_subpop_entries[0]["percentage"]
        primary_origin = eur_subpop_entries[0].get(
            "origin", SUPER_POP_ORIGINS.get(dominant_super, ""),
        )
    else:
        primary_pop = SUPER_POP_LABELS[dominant_super]
        primary_pct = super_pcts[dominant_super]
        primary_origin = SUPER_POP_ORIGINS.get(dominant_super, "")

    confidence = _confidence_band(primary_pct)

    logger.info(
        f"Ancestry: {primary_pop} {primary_pct}% ({confidence}) | "
        f"Neanderthal {neanderthal['percentage']}%"
    )

    ancestry_result = AncestryResult(
        analysis_id=ctx.analysis_id,
        population=primary_pop,
        percentage=str(primary_pct),
        confidence=confidence,
        geographic_origin=primary_origin,
        associated_variants=contributing.get(dominant_super, [])[:20],
        composition=composition,
        neanderthal_variants=neanderthal,
    )
    ctx.session.add(ancestry_result)
    return 1
