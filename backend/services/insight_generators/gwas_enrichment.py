"""GWAS Catalog enrichment for lifestyle insight generators.

Scans annotation_results for variants with genome-wide significant (p ≤ 5e-8)
GWAS associations and creates additional insights in the appropriate category
panels — filling gaps that the registry-based mappings miss.
"""
import asyncio
import logging
import math
from typing import Dict, List, Optional, Set

from ...db.models import (
    CognitiveProfile, PersonalityTrait, SportsPerformance,
    PhysicalTrait, NutritionTrait, WellnessMetric,
)
from .base import (
    GeneratorContext, extract_gwas_insights, classify_gwas_trait,
    get_user_genotype, is_no_call_genotype, is_homozygous_reference,
    is_heterozygous, get_annotation_allele_parts,
    _get_effective_ref_allele,
)

logger = logging.getLogger(__name__)

_GWS_THRESHOLD = 5e-8


def _gwas_confidence(p_value: float) -> str:
    if p_value <= 1e-30:
        return "very_strong"
    if p_value <= 1e-15:
        return "strong"
    if p_value <= _GWS_THRESHOLD:
        return "moderate"
    return "suggestive"


def _p_value_display(p_value: float) -> str:
    if p_value == 0 or p_value < 1e-308:
        return "< 1e-300"
    exp = int(math.floor(math.log10(abs(p_value))))
    mantissa = p_value / (10 ** exp)
    return f"{mantissa:.2f}e{exp}"


def _zygosity_label(genotype: Optional[str], ref: Optional[str]) -> str:
    if not genotype or not ref:
        return "variant_detected"
    if is_heterozygous(genotype):
        return "moderate"
    if is_homozygous_reference(genotype, ref):
        return "low"
    return "high"


_CATEGORY_BUILDERS = {}


def _build_cognitive(aid, rsid, trait, p_val, genotype, ref) -> CognitiveProfile:
    base_pct = 65 if p_val <= 1e-15 else 55
    if genotype and ref and not is_homozygous_reference(genotype, ref):
        if is_heterozygous(genotype):
            base_pct = min(99, base_pct + 5)
        else:
            base_pct = min(99, base_pct + 10)
    return CognitiveProfile(
        analysis_id=aid,
        cognitive_domain=trait,
        genetic_score=_gwas_confidence(p_val),
        percentile=base_pct,
        associated_variants=[rsid],
        enhancement_suggestions=f"GWAS: genome-wide significant association (p = {_p_value_display(p_val)})",
    )


def _build_personality(aid, rsid, trait, p_val, genotype, ref) -> PersonalityTrait:
    return PersonalityTrait(
        analysis_id=aid,
        trait_name=trait,
        genetic_tendency=_zygosity_label(genotype, ref),
        confidence_level=_gwas_confidence(p_val),
        associated_variants=[rsid],
        behavioral_insights=f"GWAS: genome-wide significant association (p = {_p_value_display(p_val)})",
    )


def _build_sports(aid, rsid, trait, p_val, genotype, ref) -> SportsPerformance:
    return SportsPerformance(
        analysis_id=aid,
        performance_category=trait,
        genetic_advantage=_zygosity_label(genotype, ref),
        sport_recommendations=f"GWAS association (p = {_p_value_display(p_val)})",
        associated_variants=[rsid],
        training_advice=f"Genome-wide significant association with {trait}",
    )


def _build_physical(aid, rsid, trait, p_val, genotype, ref) -> PhysicalTrait:
    return PhysicalTrait(
        analysis_id=aid,
        trait_name=trait,
        trait_category="gwas_association",
        genetic_result=_zygosity_label(genotype, ref),
        confidence=_gwas_confidence(p_val),
        associated_variants=[rsid],
        description=f"GWAS: genome-wide significant association (p = {_p_value_display(p_val)})",
    )


def _build_nutrition(aid, rsid, trait, p_val, genotype, ref) -> NutritionTrait:
    return NutritionTrait(
        analysis_id=aid,
        nutrient=trait,
        metabolism_type=_zygosity_label(genotype, ref),
        dietary_recommendations=f"GWAS association (p = {_p_value_display(p_val)})",
        associated_variants=[rsid],
        sensitivity_level=_gwas_confidence(p_val),
    )


def _build_wellness(aid, rsid, trait, p_val, genotype, ref) -> WellnessMetric:
    return WellnessMetric(
        analysis_id=aid,
        metric_name=trait,
        genetic_predisposition=_zygosity_label(genotype, ref),
        optimization_score=_gwas_confidence(p_val),
        lifestyle_recommendations=f"GWAS association (p = {_p_value_display(p_val)})",
        associated_variants=[rsid],
    )


_CATEGORY_BUILDERS = {
    'cognitive': _build_cognitive,
    'personality': _build_personality,
    'sports': _build_sports,
    'physical': _build_physical,
    'nutrition': _build_nutrition,
    'wellness': _build_wellness,
}


async def generate_gwas_enrichment(ctx: GeneratorContext, existing_dedup_keys: Dict[str, Set[str]]) -> int:
    items = []
    seen = {cat: set(keys) for cat, keys in existing_dedup_keys.items()}
    _DEDUP_FIELDS = {
        'cognitive': 'cognitive_domain',
        'personality': 'trait_name',
        'sports': 'performance_category',
        'physical': 'trait_name',
        'nutrition': 'nutrient',
        'wellness': 'metric_name',
    }

    for idx, variant in enumerate(ctx.variants):
        if idx > 0 and idx % 500 == 0:
            await asyncio.sleep(0)

        rsid = getattr(variant, 'rsid', None)
        if not rsid:
            continue

        genotype = get_user_genotype(variant)
        if is_no_call_genotype(genotype):
            continue

        annotation_result = ctx.annotation_results.get(rsid)
        if not annotation_result or not annotation_result.annotation_data:
            continue

        effective_ref = _get_effective_ref_allele(variant, annotation_result)
        _, ann_alt = get_annotation_allele_parts(annotation_result)
        if effective_ref and is_homozygous_reference(genotype, effective_ref, alt_allele=ann_alt):
            continue

        gwas_insights = extract_gwas_insights(annotation_result)
        if not gwas_insights:
            continue

        for gi in gwas_insights:
            category = gi['category']
            trait = gi['trait']
            p_value = gi['p_value']
            builder = _CATEGORY_BUILDERS.get(category)
            if not builder:
                continue
            cat_seen = seen.setdefault(category, set())
            if trait in cat_seen:
                continue
            cat_seen.add(trait)
            item = builder(ctx.analysis_id, rsid, trait, p_value, genotype, effective_ref)
            if item:
                items.append(item)

    for item in items:
        ctx.session.add(item)

    if items:
        logger.info(f"GWAS enrichment: {len(items)} additional insights across lifestyle panels")
    return len(items)
