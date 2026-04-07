"""
Insight generation dispatch — extracted from analysis_service.py.

Handles:
- Phase 4: Running all 14 insight generators
- Standalone insight regeneration (no annotation / API calls)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import delete

from ..db.database import async_session_factory
from ..db.models import (
    HealthRisk, DrugResponse, PhysicalTrait, NutritionTrait,
    SportsPerformance, CognitiveProfile, PersonalityTrait,
    AncestryResult, CarrierStatus, WellnessMetric,
    MethylationProfile, DetoxificationProfile, RareMutation,
    UncommonMutation, DashboardCache,
)
from .insight_generators import ALL_GENERATORS, GeneratorContext, build_variant_profiles
from .insight_generators.gwas_enrichment import generate_gwas_enrichment

logger = logging.getLogger(__name__)


def _collect_existing_dedup_keys(ctx: GeneratorContext) -> Dict[str, set]:
    keys: Dict[str, set] = {}
    rsid_maps = {
        'cognitive': (ctx.registry.get('cognitive', {}).get('rsid', {}), 'domain'),
        'personality': (ctx.registry.get('personality', {}).get('rsid', {}), 'trait'),
        'sports': (ctx.registry.get('sports', {}).get('rsid', {}), 'category'),
        'physical': (ctx.registry.get('physical', {}).get('rsid', {}), 'trait'),
        'nutrition': (ctx.registry.get('nutrition', {}).get('rsid', {}), 'nutrient'),
        'wellness': (ctx.registry.get('wellness', {}).get('rsid', {}), 'metric'),
    }
    for cat, (rmap, field) in rsid_maps.items():
        cat_keys = set()
        for info in rmap.values():
            if field in info:
                cat_keys.add(info[field])
        keys[cat] = cat_keys
    return keys

# Re-use dataclasses from analysis_service
from .analysis_service import AnnotationResult, AnalysisProgress, AnalysisCancelled

# All insight tables for cleanup
INSIGHT_TABLES = [
    HealthRisk, DrugResponse, PhysicalTrait, NutritionTrait,
    SportsPerformance, CognitiveProfile, PersonalityTrait,
    AncestryResult, CarrierStatus, WellnessMetric,
    MethylationProfile, DetoxificationProfile, RareMutation,
    UncommonMutation,
]


async def generate_comprehensive_insights(
    variants: List,
    annotation_results: Dict[str, AnnotationResult],
    analysis_id: int,
    rsid_gene_map: Dict[str, str],
    registry: Dict[str, Dict[str, Dict]],
    progress: AnalysisProgress,
    *,
    check_cancelled_fn: Optional[Callable] = None,
    update_progress_fn: Optional[Callable] = None,
    inferred_sex: Optional[str] = None,
) -> int:
    """Generate comprehensive insights for all categories.

    Deletes any existing insights for this analysis first so that
    resume does not produce duplicates.

    Each generator runs in its own DB session so that a connection
    failure in one generator does not poison subsequent generators.
    """
    # Clean up any partial insights from a previous interrupted run
    async with async_session_factory() as cleanup_session:
        for tbl in INSIGHT_TABLES:
            await cleanup_session.execute(
                delete(tbl).where(tbl.analysis_id == analysis_id)
            )
        await cleanup_session.commit()
    logger.info(f"  Cleared {len(INSIGHT_TABLES)} insight tables for fresh generation")

    # Build variant profiles ONCE — all generators share these
    profile_start = time.time()
    variant_profiles = await build_variant_profiles(
        variants, annotation_results, rsid_gene_map
    )
    logger.info(f"  Built variant profiles in {time.time() - profile_start:.1f}s")

    # PERF-03: Pre-filter variants to only those that could match any
    # generator's rsid_map or gene_map.
    all_mapped_rsids: set = set()
    all_mapped_genes: set = set()
    for cat_data in registry.values():
        all_mapped_rsids.update(cat_data.get('rsid', {}).keys())
        all_mapped_genes.update(cat_data.get('gene', {}).keys())

    interesting_variants = []
    gwas_variants = []
    for v in variants:
        rsid = getattr(v, 'rsid', None)
        if not rsid:
            continue
        if rsid in all_mapped_rsids:
            interesting_variants.append(v)
            continue
        profile = variant_profiles.get(rsid)
        if profile and profile.gene and profile.gene in all_mapped_genes:
            interesting_variants.append(v)
            continue
        if profile and profile.clinical_significance:
            interesting_variants.append(v)
            continue
        ar = annotation_results.get(rsid)
        if ar and ar.annotation_data:
            gwas = ar.annotation_data.get('annotations', {}).get('gwas_catalog', {})
            if gwas and gwas.get('genome_wide_significant'):
                gwas_variants.append(v)

    logger.info(
        f"  PERF-03: pre-filtered {len(variants)} → {len(interesting_variants)} "
        f"potentially interesting variants ({len(all_mapped_rsids)} mapped rsids, "
        f"{len(all_mapped_genes)} mapped genes) + {len(gwas_variants)} GWAS-only"
    )

    insights_generated = 0
    total_generators = len(ALL_GENERATORS)
    failed_generators: list[str] = []

    for gen_idx, (gen_name, gen_func) in enumerate(ALL_GENERATORS):
        if check_cancelled_fn:
            await check_cancelled_fn(analysis_id)
        try:
            progress.current_step = f"generating_{gen_name}"
            progress.phase_progress = gen_idx / total_generators
            if update_progress_fn:
                await update_progress_fn(analysis_id, progress)

            async with async_session_factory() as gen_session:
                ctx = GeneratorContext(
                    analysis_id=analysis_id,
                    variants=interesting_variants,
                    annotation_results=annotation_results,
                    session=gen_session,
                    rsid_gene_map=rsid_gene_map,
                    registry=registry,
                    variant_profiles=variant_profiles,
                    inferred_sex=inferred_sex,
                )
                count = await gen_func(ctx)
                await gen_session.commit()
            insights_generated += count
            logger.info(f"  [{gen_idx + 1}/{total_generators}] {gen_name}: {count} insights")
        except AnalysisCancelled:
            raise
        except Exception as e:
            failed_generators.append(gen_name)
            logger.error(f"  [{gen_idx + 1}/{total_generators}] {gen_name}: FAILED — {e}")
            continue

    if failed_generators:
        logger.warning(f"  {len(failed_generators)} generator(s) failed: {', '.join(failed_generators)}")

    # GWAS enrichment pass: add insights from genome-wide significant
    # associations that weren't covered by registry-based generators
    if gwas_variants:
        try:
            all_gwas_pool = interesting_variants + gwas_variants
            async with async_session_factory() as gwas_session:
                gwas_ctx = GeneratorContext(
                    analysis_id=analysis_id,
                    variants=all_gwas_pool,
                    annotation_results=annotation_results,
                    session=gwas_session,
                    rsid_gene_map=rsid_gene_map,
                    registry=registry,
                    variant_profiles=variant_profiles,
                    inferred_sex=inferred_sex,
                )
                existing_keys = _collect_existing_dedup_keys(gwas_ctx)
                gwas_count = await generate_gwas_enrichment(gwas_ctx, existing_keys)
                await gwas_session.commit()
            insights_generated += gwas_count
            logger.info(f"  GWAS enrichment: {gwas_count} additional insights")
        except Exception as e:
            logger.error(f"  GWAS enrichment: FAILED — {e}")

    return insights_generated


async def regenerate_insights(analysis_id: int, user_id: Optional[int] = None) -> Dict[str, Any]:
    """Re-generate all insight tables using existing annotations.

    Skips Phases 1-3 entirely. Loads variants and cached annotations from DB,
    builds variant profiles, and runs all generators from scratch.
    """
    from .variant_loader import load_analysis_data, build_rsid_gene_map
    from .shared_annotation_service import SharedVariantAnnotationService
    from .job_logs import JobLogCollector
    from sqlalchemy import select

    start_time = time.time()
    log_collector = JobLogCollector.get_instance()
    log_collector.set_active_job(analysis_id)

    try:
        # Load registry
        from ..db.models import VariantMapping
        async with async_session_factory() as session:
            result = await session.execute(
                select(VariantMapping).where(VariantMapping.is_active)
            )
            rows = result.scalars().all()

        registry: Dict[str, Dict[str, Dict]] = {}
        for row in rows:
            cat = row.category
            if cat not in registry:
                registry[cat] = {'rsid': {}, 'gene': {}}
            registry[cat][row.map_type][row.key] = row.data

        # Load variants
        analysis, variants = await load_analysis_data(analysis_id, user_id)
        if not variants:
            return {
                "success": True, "analysis_id": analysis_id,
                "insights_generated": 0, "message": "No variants found",
            }

        inferred_sex = getattr(analysis, 'inferred_sex', None)
        if not inferred_sex:
            from ..utils.sex_inferrer import infer_biological_sex
            inferred_sex = infer_biological_sex(variants)
            async with async_session_factory() as upd_session:
                from sqlalchemy import update as sa_update
                from ..db.models import GeneticAnalysis
                await upd_session.execute(
                    sa_update(GeneticAnalysis)
                    .where(GeneticAnalysis.id == analysis_id)
                    .values(inferred_sex=inferred_sex)
                )
                await upd_session.commit()

        logger.info(f"═══ Insight regeneration for analysis {analysis_id} ═══")
        logger.info(f"  Variants: {len(variants)}")

        # Build gene map
        rsid_gene_map = await build_rsid_gene_map(variants)

        # Load existing annotations
        annotation_service = SharedVariantAnnotationService()
        rsids = [str(v.rsid) for v in variants if v.rsid]
        existing = await annotation_service.get_existing_annotations_fast(rsids)
        annotation_results: Dict[str, AnnotationResult] = {}
        for rsid, data in existing.items():
            annotation_results[rsid] = AnnotationResult(
                rsid=rsid, was_reused=True,
                annotation_data=data, source='existing',
            )
        logger.info(f"  Loaded {len(annotation_results)} cached annotations")

        progress = AnalysisProgress(
            total_variants=len(variants),
            processed_variants=0,
            annotated_variants=len(annotation_results),
            new_annotations=0,
            reused_annotations=len(annotation_results),
            current_step="generating_insights",
            status="processing",
            phase=4,
            phase_progress=0.0,
        )

        # Run Phase 4 only
        insights_generated = await generate_comprehensive_insights(
            variants, annotation_results, analysis_id,
            rsid_gene_map, registry, progress,
            inferred_sex=inferred_sex,
        )

        # Invalidate dashboard cache
        try:
            async with async_session_factory() as inv_session:
                await inv_session.execute(
                    DashboardCache.__table__.delete().where(
                        DashboardCache.user_id == analysis.user_id
                    )
                )
                await inv_session.commit()
        except Exception:
            pass

        elapsed = time.time() - start_time
        logger.info(f"═══ Insight regeneration complete: {insights_generated} insights in {elapsed:.1f}s ═══")

        return {
            "success": True,
            "analysis_id": analysis_id,
            "insights_generated": insights_generated,
            "variants_loaded": len(variants),
            "annotations_loaded": len(annotation_results),
            "processing_time": elapsed,
        }
    except Exception as e:
        logger.error(f"Insight regeneration failed for analysis {analysis_id}: {e}")
        raise
