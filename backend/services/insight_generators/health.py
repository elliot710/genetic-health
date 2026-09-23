"""Health risk insight generator."""
from ...db.models import HealthRisk
from .base import (
    GeneratorContext, generate_from_maps, assess_risk_level,
    get_health_recommendations, extract_gene_and_consequence,
    risk_level_to_score, zygosity_adjust, cap_risk_for_rarity, get_clingen_validity,
    is_heterozygous,
)
from ..mapping_reliability import is_non_damaging_consequence


def _population_frequency(ctx, rsid):
    prof = ctx.variant_profiles.get(rsid)
    return getattr(prof, 'population_frequency', None) if prof else None


def _is_hom_indel_code(genotype) -> bool:
    """Consumer-array homozygous indel codes (DD/II) are too ambiguous to assert
    a homozygous-affected rare-disease genotype — the D/I → ref/alt direction is
    not reliable enough on consumer data to claim someone is affected."""
    return bool(genotype) and genotype.strip().upper() in ('DD', 'II')


def _is_recessive_condition(condition, inheritance) -> bool:
    text = f"{condition or ''} {inheritance or ''}".lower()
    if 'dominant' in text:
        return False
    return 'recessive' in text or 'x-linked' in text or 'x linked' in text


def _affirmatively_weak_review(review_status) -> bool:
    rs = (review_status or '').lower()
    return bool(rs) and any(
        b in rs for b in ('no_assertion', 'no assertion', 'no classification', 'no_classification')
    )


def _skip_strict_clinical(ctx, rsid, genotype, info, consequence=None) -> bool:
    """U14: the health panel shows only conditions the user is plausibly
    AFFECTED by. Drop non-damaging consequences, ambiguous hom-indel codes,
    affirmatively-weak ClinVar review status, and recessive conditions where the
    user is only heterozygous (a carrier, not affected — the carrier panel
    covers those)."""
    prof = ctx.variant_profiles.get(rsid)
    cons = consequence if consequence is not None else getattr(prof, 'consequence', None)
    if is_non_damaging_consequence(cons):
        return True
    if _is_hom_indel_code(genotype):
        return True
    if _affirmatively_weak_review(info.get('review_status')):
        return True
    if _is_recessive_condition(info.get('condition'), info.get('inheritance')) and is_heterozygous(genotype):
        return True
    return False


_CLINGEN_SKIP = frozenset({'Disputed', 'Refuted'})


async def generate_health_risks(ctx: GeneratorContext) -> int:
    # NOTE: a LOW health-risk count can be legitimate — health uses conservative
    # clinical gates (generate_from_maps with max_population_af=0.05 +
    # alt-allele-carry verification + benign exclusion), stricter than the drug
    # panel (which filters only hom-ref/no-call/benign). Don't loosen the gates
    # to inflate the count — that reintroduces false-positive health scares.
    # But distinguish a legitimately-empty result from a *failed* generator:
    # "could not be generated" is a real error to fix (e.g. the indel_d_is_ref
    # NameError in map_generation that crashed this panel on indel genotypes),
    # not a no-findings outcome.
    def _is_clingen_disputed(rsid):
        ar = ctx.annotation_results.get(rsid)
        validity = get_clingen_validity(ar)
        return validity in _CLINGEN_SKIP

    def from_rsid(aid, rsid, genotype, info):
        if _is_clingen_disputed(rsid):
            return None
        if _skip_strict_clinical(ctx, rsid, genotype, info):
            return None
        # Use the composite pathogenicity score computed in build_variant_profiles
        # (threaded via info['_pathogenicity_score']). The annotation cache does
        # not store a top-level 'pathogenicity_score' (ARCH-06 computes it lazily),
        # so reading annotation_data here always yielded None and silently capped
        # every health risk at the multiplier-only 'moderate' fallback.
        _ps = info.get('_pathogenicity_score')
        path_score = _ps if isinstance(_ps, dict) else None
        risk_level = assess_risk_level(
            genotype, info['risk_multiplier'],
            ref_allele=info.get('_ref_allele'),
            pathogenicity_score=path_score,
            population_frequency=_population_frequency(ctx, rsid),
        )
        recommendations = info.get('recommendations')
        if not recommendations or recommendations == ['Consult with healthcare provider']:
            recommendations = get_health_recommendations(info['condition'], risk_level)
        _classification = _ps.get('classification') if isinstance(_ps, dict) else None
        return HealthRisk(
            analysis_id=aid, condition=info['condition'],
            risk_level=risk_level, risk_score=risk_level_to_score(risk_level),
            associated_variants=[rsid],
            recommendations=recommendations,
            gene=info.get('gene') or None,
            review_status=info.get('review_status') or None,
            pathogenicity_classification=_classification,
            provenance='variant',
        )

    def from_gene(aid, rsid, gene, consequence, info):
        if _is_clingen_disputed(rsid):
            return None
        genotype = info.get('_genotype', '')
        if _skip_strict_clinical(ctx, rsid, genotype, info, consequence=consequence):
            return None
        ref_allele = info.get('_ref_allele')
        risk_level = zygosity_adjust(info['risk_level'], genotype, ref_allele=ref_allele)
        risk_level = cap_risk_for_rarity(risk_level, _population_frequency(ctx, rsid))
        _ps = info.get('_pathogenicity_score')
        _classification = _ps.get('classification') if isinstance(_ps, dict) else None
        return HealthRisk(
            analysis_id=aid, condition=info['condition'],
            risk_level=risk_level, risk_score=risk_level_to_score(risk_level),
            associated_variants=[rsid], recommendations=info['recommendations'],
            gene=gene or info.get('gene') or None,
            review_status=info.get('review_status') or None,
            pathogenicity_classification=_classification,
            provenance='gene',
        )

    rsid_map, gene_map = ctx.get_maps('health')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='condition',
        build_from_rsid=from_rsid, build_from_gene=from_gene,
        filter_benign=True,
        max_population_af=0.05,
    )
