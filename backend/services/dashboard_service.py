import logging
from typing import Dict, Any, Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..db.models import (
    GeneticAnalysis, HealthRisk, DrugResponse, PhysicalTrait, NutritionTrait,
    SportsPerformance, CognitiveProfile, PersonalityTrait, AncestryResult,
    CarrierStatus, WellnessMetric, MethylationProfile, DetoxificationProfile,
    RareMutation, UncommonMutation, DashboardCache,
)
from .dashboard_serializers import serialize_insight_rows
from .dashboard_maps import (
    build_annotation_maps, build_genotype_and_gene_maps,
    build_alphafold_map, build_pathogenicity_map,
    backfill_clinvar_significance, build_gene_stats_map,
)

logger = logging.getLogger(__name__)

_INSIGHT_TABLES = (
    HealthRisk, DrugResponse, PhysicalTrait, NutritionTrait,
    SportsPerformance, CognitiveProfile, PersonalityTrait,
    AncestryResult, CarrierStatus, WellnessMetric,
    MethylationProfile, DetoxificationProfile, RareMutation, UncommonMutation,
)

EMPTY_DASHBOARD: Dict[str, Any] = {
    "summary": {"total_variants": 0, "analysis_id": None, "status": "no_data"},
    "health_risks": [], "ancestry_results": [], "sports_performance": [],
    "nutrition_traits": [], "metabolic": {}, "carrier_status": [],
    "drug_responses": [], "rare_mutations": [], "methylation_profiles": [],
    "detoxification_profiles": [], "physical_traits": [], "intelligence": [],
    "personality_traits": [], "wellness_traits": [], "uncommon_mutations": [],
}


def analysis_fingerprint(analyses) -> str:
    parts = sorted(f"{a.id}:{a.analysis_status}:{a.processed_variants or 0}" for a in analyses)
    return "|".join(parts)


async def count_insights(db: AsyncSession, analysis_ids: List[int]) -> int:
    total = 0
    for tbl in _INSIGHT_TABLES:
        result = await db.execute(
            select(func.count()).where(tbl.analysis_id.in_(analysis_ids))
        )
        total += result.scalar() or 0
    return total


async def fetch_insight_rows(db: AsyncSession, analysis_ids: List[int]) -> Dict[str, Any]:
    table_map = {
        'health': HealthRisk, 'drug': DrugResponse, 'ancestry': AncestryResult,
        'sports': SportsPerformance, 'nutrition': NutritionTrait,
        'carrier': CarrierStatus, 'methylation': MethylationProfile,
        'detox': DetoxificationProfile, 'rare': RareMutation,
        'wellness': WellnessMetric, 'physical': PhysicalTrait,
        'cognitive': CognitiveProfile, 'personality': PersonalityTrait,
        'uncommon': UncommonMutation,
    }
    rows: Dict[str, Any] = {}
    for key, model in table_map.items():
        result = await db.execute(select(model).where(model.analysis_id.in_(analysis_ids)))
        rows[key] = result.scalars().all()
    return rows


def extract_panel_rsids(dashboard_data: Dict[str, Any]) -> set:
    panel_rsids: set = set()
    insight_keys = (
        "health_risks", "sports_performance", "nutrition_traits",
        "carrier_status", "methylation_profiles", "detoxification_profiles",
        "rare_mutations", "physical_traits", "intelligence",
        "personality_traits", "wellness_traits", "uncommon_mutations",
    )
    for key in insight_keys:
        items = dashboard_data.get(key, [])
        if isinstance(items, dict):
            items = items.get("metrics", [])
        for item in items:
            _collect_rsids_from_item(item, panel_rsids)
    for dr_item in dashboard_data.get("drug_responses", []):
        for v in (dr_item.get("variants_involved") or []):
            if isinstance(v, str) and v.startswith("rs"):
                panel_rsids.add(v)
    return panel_rsids


def _collect_rsids_from_item(item: dict, out: set) -> None:
    for v in (item.get("associated_variants") or []):
        if isinstance(v, str) and v.startswith("rs"):
            out.add(v)
    for field in ("rsid", "variant", "gene", "marker"):
        val = item.get(field)
        if isinstance(val, str) and val.startswith("rs"):
            out.add(val)


def stale_or_placeholder(analyses, cached) -> Optional[Dict[str, Any]]:
    current_ids = {str(a.id) for a in analyses}
    cache_ids = set()
    if cached and cached.analysis_fingerprint:
        for part in cached.analysis_fingerprint.split("|"):
            cache_ids.add(part.split(":")[0])
    if cached and cached.dashboard_json and current_ids & cache_ids:
        stale = cached.dashboard_json
        if isinstance(stale.get("summary"), dict):
            stale["summary"]["status"] = "processing"
        return stale
    primary = analyses[0]
    return {
        "summary": {
            "total_variants": sum(getattr(a, 'total_variants', 0) or 0 for a in analyses),
            "processed_variants": sum(getattr(a, 'processed_variants', 0) or 0 for a in analyses),
            "analyzed_variants": 0, "insights_found": 0,
            "analysis_id": primary.id, "status": "processing",
            "filename": getattr(primary, 'filename', None),
        },
        **{k: v for k, v in EMPTY_DASHBOARD.items() if k != "summary"},
    }


async def persist_dashboard_cache(
    db: AsyncSession, user_id: int, dashboard_data: Dict[str, Any],
    fingerprint: str, cached,
) -> None:
    try:
        if cached:
            cached.dashboard_json = dashboard_data
            cached.analysis_fingerprint = fingerprint
            cached.refreshed_at = func.now()
        else:
            db.add(DashboardCache(
                user_id=user_id,
                dashboard_json=dashboard_data,
                analysis_fingerprint=fingerprint,
            ))
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("Failed to persist dashboard cache – returning fresh data")


async def build_dashboard_for_user(db: AsyncSession, user_id: int) -> Optional[Dict[str, Any]]:
    result = await db.execute(
        select(GeneticAnalysis)
        .where(GeneticAnalysis.user_id == user_id, GeneticAnalysis.deleted_at.is_(None))
        .order_by(GeneticAnalysis.upload_date.desc())
    )
    analyses = result.scalars().all()
    if not analyses:
        return None

    completed = [a for a in analyses if getattr(a, 'analysis_status', '') == 'completed']
    if not completed:
        return None

    primary_analysis = completed[0]
    analysis_ids = [a.id for a in analyses]
    dashboard_data = await _assemble_dashboard(db, analyses, primary_analysis, analysis_ids)

    fingerprint = analysis_fingerprint(analyses)
    cache_row = await db.execute(select(DashboardCache).where(DashboardCache.user_id == user_id))
    cached = cache_row.scalar_one_or_none()
    await persist_dashboard_cache(db, user_id, dashboard_data, fingerprint, cached)
    return dashboard_data


def _analysis_coverage(insight_status, processed_variants, total_variants) -> Dict[str, Any]:
    """Honest per-analysis completeness: the mean of the variant-annotation rate
    and the insight-category success rate, each 0-1. Either input may be missing
    (older analyses have no insight_status); score is None only when neither is
    available."""
    processed_variants = processed_variants or 0
    total_variants = total_variants or 0
    variant_rate = (processed_variants / total_variants) if total_variants else None

    category_rate = None
    categories = None
    if isinstance(insight_status, dict):
        generators_total = insight_status.get("generators_total") or 0
        generators_succeeded = insight_status.get("generators_succeeded")
        if generators_total and generators_succeeded is not None:
            category_rate = generators_succeeded / generators_total
            categories = {"succeeded": generators_succeeded, "total": generators_total}

    rates = [r for r in (variant_rate, category_rate) if r is not None]
    score = round(100 * sum(rates) / len(rates)) if rates else None
    return {
        "score": score,
        "variant_annotation": {"processed": processed_variants, "total": total_variants},
        "insight_categories": categories,
    }


async def _assemble_dashboard(
    db: AsyncSession, analyses, primary_analysis, analysis_ids: List[int],
) -> Dict[str, Any]:
    total_variants = sum(getattr(a, 'total_variants', 0) or 0 for a in analyses)
    processed_variants = sum(getattr(a, 'processed_variants', 0) or 0 for a in analyses)
    insights_found = await count_insights(db, analysis_ids)
    upload_date = getattr(primary_analysis, 'upload_date', None)

    dashboard_data: Dict[str, Any] = {
        "summary": {
            "total_variants": total_variants,
            "processed_variants": processed_variants,
            "analyzed_variants": processed_variants,
            "insights_found": insights_found,
            "analysis_id": primary_analysis.id,
            "status": primary_analysis.analysis_status,
            "upload_date": upload_date.isoformat() if upload_date else None,
            "filename": getattr(primary_analysis, 'filename', None),
            "insight_status": getattr(primary_analysis, 'insight_status', None),
            "coverage": _analysis_coverage(
                getattr(primary_analysis, 'insight_status', None),
                processed_variants, total_variants,
            ),
        },
    }

    insight_rows = await fetch_insight_rows(db, analysis_ids)
    dashboard_data.update(serialize_insight_rows(insight_rows))

    ann_maps = await build_annotation_maps(db, primary_analysis.id)
    annotation_rows = ann_maps.pop('annotation_rows')
    dashboard_data.update(ann_maps)
    dashboard_data["_allele_map_version"] = 2

    panel_rsids = extract_panel_rsids(dashboard_data)
    genotype_map, gene_symbol_map = await build_genotype_and_gene_maps(db, analysis_ids, panel_rsids)
    dashboard_data["genotype_map"] = genotype_map
    dashboard_data["gene_symbol_map"] = gene_symbol_map

    dashboard_data["alphafold_map"] = build_alphafold_map(gene_symbol_map, panel_rsids)
    dashboard_data["pathogenicity_map"] = await build_pathogenicity_map(
        db, primary_analysis.id, panel_rsids,
    )
    backfill_clinvar_significance(dashboard_data, annotation_rows)
    dashboard_data["gene_stats_map"] = await build_gene_stats_map(
        db, dashboard_data, gene_symbol_map,
    )
    return dashboard_data
