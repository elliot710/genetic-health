"""
Shared context, helpers, and generic map-driven generator used by all
insight generator modules.

This package is the public import surface for `insight_generators.base` —
every name below is re-exported so existing `from .base import X` call
sites (generators, tests) keep working unchanged after the base.py -> base/
package split.

NOTE: build_variant_profiles() and its two bulk-load helpers are defined
directly in this __init__ (rather than in a submodule) because tests patch
them as `backend.services.insight_generators.base._bulk_load_gene_constraints`
/ `..._bulk_load_clinvar_gene_stats`. mock.patch replaces the attribute on
the module whose *namespace* the patched function is resolved through at
call time — that must be this module's own globals, so the callee and the
callables it patches have to live together here.
"""
import asyncio
import logging
from typing import Any, Dict

from .context import GeneratorContext, VariantProfile
from .alleles import (
    STRAND_COMPLEMENT,
    get_ref_allele,
    get_annotation_ref_allele,
    get_annotation_allele_parts,
    indel_d_is_ref,
    _get_effective_ref_allele,
    get_user_genotype,
    is_indel_genotype,
    is_no_call_genotype,
    _parse_alleles,
    is_homozygous_reference,
    is_heterozygous,
)
from .frequency import extract_gene_and_consequence, extract_frequency
from .zygosity import (
    risk_level_to_score,
    zygosity_adjust,
    cap_risk_for_rarity,
    boost_if_pathogenic,
    assess_risk_level,
    assess_drug_response,
    get_health_recommendations,
    get_drug_recommendations,
    get_trait_description,
)
from .clinical import (
    is_clinvar_benign,
    _get_all_clinvar_significances,
    _has_computational_pathogenicity,
    should_skip_sex_linked,
    classify_gwas_trait,
    extract_gwas_insights,
    get_clingen_validity,
)
from .map_generation import generate_from_maps

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Variant profile builder — runs ONCE before all generators
# ---------------------------------------------------------------------------

async def build_variant_profiles(
    variants,
    annotation_results: Dict[str, Any],
    rsid_gene_map: Dict[str, str],
) -> Dict[str, VariantProfile]:
    """Build pre-computed profiles for all variants in one pass.

    ARCH-06: Pathogenicity scores are computed HERE (lazily) rather than
    during Phase 2 annotation.  This means updated scoring logic always
    applies without re-annotating, and the annotation cache doesn't need
    to store pre-computed scores.
    """
    from ...scoring_engine import get_scoring_engine, ScoringEngine
    scorer = get_scoring_engine()
    profiles: Dict[str, VariantProfile] = {}

    gene_constraints = await _bulk_load_gene_constraints(rsid_gene_map)
    clinvar_gene_stats = await _bulk_load_clinvar_gene_stats(rsid_gene_map)

    for idx, variant in enumerate(variants):
        if idx > 0 and idx % 200 == 0:
            await asyncio.sleep(0)

        rsid = getattr(variant, 'rsid', None)
        if not rsid:
            continue

        genotype = get_user_genotype(variant)
        annotation_result = annotation_results.get(rsid)
        effective_ref = _get_effective_ref_allele(variant, annotation_result)

        gene, consequence, impact = extract_gene_and_consequence(
            annotation_result, rsid_gene_map
        )
        # U5: fill consequence from the offline caches (dbSNP MC / VEP / SnpEff)
        # when the primary annotation has none — this is the coverage that lets
        # the consequence-based gates (reliability predicate, health U14) fire.
        if not consequence:
            from backend.services.annotation_sources.consequence_resolver import (
                get_consequence_resolver,
            )
            consequence = get_consequence_resolver().resolve(rsid)

        # Extract frequency — None means "no data available" (not 0%)
        raw_freq = extract_frequency(annotation_result)
        pop_freq = raw_freq if raw_freq > 0 else None

        # Pre-compute zygosity
        no_call = is_no_call_genotype(genotype)
        # Get full allele parts for indel D/I interpretation
        _, ann_alt = get_annotation_allele_parts(annotation_result)
        hom_ref = (not no_call and effective_ref is not None
                   and is_homozygous_reference(genotype, effective_ref, alt_allele=ann_alt))
        het = not no_call and not hom_ref and is_heterozygous(genotype)

        clinvar_benign = is_clinvar_benign(annotation_result)

        # Pathogenicity score — always compute fresh (ARCH-06).
        # Lazy scoring ensures updated scoring logic applies without re-annotating.
        annotations_dict: dict = {}
        if annotation_result and annotation_result.annotation_data:
            annotations_dict = annotation_result.annotation_data.get('annotations', {})
        if gene and gene in gene_constraints:
            annotations_dict = {**annotations_dict, 'gene_constraint': gene_constraints[gene]}
        if gene and gene in clinvar_gene_stats:
            annotations_dict = {**annotations_dict, 'clinvar_gene_stats': clinvar_gene_stats[gene]}
        pscore = scorer.score_variant(annotations_dict)
        composite = pscore.get('composite_score', 0.0)

        # Resolved clinical significance from ClinVar local
        clin_sig = None
        if annotation_result and annotation_result.annotation_data:
            cv_local = annotation_result.annotation_data.get(
                'annotations', {}
            ).get('clinvar_local', {})
            if cv_local and cv_local.get('found'):
                sigs = cv_local.get('clinical_significances', [])
                if sigs:
                    clin_sig = sigs[0].lower().replace('_', ' ')

        # is_benign: True when ClinVar unanimously says benign OR when the
        # composite pathogenicity score classifies as benign/likely_benign.
        # This covers variants with no ClinVar data that still score benign
        # from other evidence (e.g. VEP-only intron variants).
        score_benign = composite < ScoringEngine.BENIGN_THRESHOLD
        is_benign_flag = clinvar_benign or score_benign

        chromosome = getattr(variant, 'chromosome', None)

        profiles[rsid] = VariantProfile(
            rsid=rsid,
            genotype=genotype,
            effective_ref=effective_ref,
            gene=gene,
            consequence=consequence,
            impact=impact,
            chromosome=chromosome,
            population_frequency=pop_freq,
            clinical_significance=clin_sig,
            is_benign=is_benign_flag,
            is_hom_ref=hom_ref,
            is_het=het,
            is_no_call=no_call,
            composite_score=composite,
            pathogenicity_score=pscore,
            annotation_result=annotation_result,
            variant=variant,
        )

    logger.info(f"Built {len(profiles)} variant profiles")
    return profiles


async def _bulk_load_gene_constraints(rsid_gene_map: Dict[str, str]) -> Dict[str, dict]:
    """Pre-load gene constraint data for all genes in one query."""
    unique_genes = list(set(rsid_gene_map.values()))
    if not unique_genes:
        return {}
    try:
        from ....db.database import async_session_factory
        from sqlalchemy import text
        async with async_session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT gene, pli, loeuf, mis_z, syn_z "
                    "FROM gnomad_gene_constraints WHERE gene = ANY(:genes)"
                ),
                {"genes": unique_genes},
            )
            return {
                row[0]: {"pli": row[1], "loeuf": row[2], "mis_z": row[3], "syn_z": row[4]}
                for row in result.all()
            }
    except Exception:
        return {}


async def _bulk_load_clinvar_gene_stats(rsid_gene_map: Dict[str, str]) -> Dict[str, dict]:
    """Pre-load ClinVar gene-level stats for all genes in one query."""
    unique_genes = list(set(rsid_gene_map.values()))
    if not unique_genes:
        return {}
    try:
        from ....db.database import async_session_factory
        from sqlalchemy import text
        async with async_session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT gene, total_submissions, pathogenic_likely_pathogenic, "
                    "uncertain_significance, with_conflicts "
                    "FROM clinvar_gene_stats WHERE gene = ANY(:genes)"
                ),
                {"genes": unique_genes},
            )
            return {
                row[0]: {
                    "total_submissions": row[1],
                    "pathogenic_count": row[2],
                    "uncertain_count": row[3],
                    "conflict_count": row[4],
                }
                for row in result.all()
            }
    except Exception:
        return {}


__all__ = [
    'GeneratorContext', 'VariantProfile',
    'STRAND_COMPLEMENT',
    'get_ref_allele', 'get_annotation_ref_allele', 'get_annotation_allele_parts',
    'indel_d_is_ref', 'get_user_genotype', 'is_indel_genotype', 'is_no_call_genotype',
    'is_homozygous_reference', 'is_heterozygous',
    'extract_gene_and_consequence', 'extract_frequency',
    'risk_level_to_score', 'zygosity_adjust', 'cap_risk_for_rarity', 'boost_if_pathogenic',
    'assess_risk_level', 'assess_drug_response',
    'get_health_recommendations', 'get_drug_recommendations', 'get_trait_description',
    'is_clinvar_benign', 'should_skip_sex_linked',
    'classify_gwas_trait', 'extract_gwas_insights', 'get_clingen_validity',
    'generate_from_maps',
    'build_variant_profiles',
]
