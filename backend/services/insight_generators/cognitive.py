"""Cognitive profile insight generator."""
from ...db.models import CognitiveProfile
from .base import GeneratorContext, generate_from_maps, is_heterozygous, is_homozygous_reference, is_no_call_genotype


def _adjust_percentile(percentile: int, genotype, ref_allele) -> int:
    """Apply zygosity-aware percentile adjustment.

    - hom-ref / missing: -10 (user carries no risk allele)
    - het (one copy): +5 (intermediate dosage effect)
    - hom-alt (two copies): +10 (full dosage effect)

    Using a step ratio of 0.5/1.0 between het and hom-alt is consistent
    with additive genetic models: one copy confers half the effect of two.
    """
    if not genotype or is_homozygous_reference(genotype, ref_allele):
        return max(1, percentile - 10)
    elif is_heterozygous(genotype):
        return min(99, percentile + 5)
    else:
        return min(99, percentile + 10)


async def generate_cognitive_profiles(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        percentile = _adjust_percentile(
            info['percentile'], genotype, info.get('_ref_allele')
        )
        return CognitiveProfile(
            analysis_id=aid, cognitive_domain=info['domain'],
            genetic_score=info['score'], percentile=percentile,
            associated_variants=[rsid],
            enhancement_suggestions=info['suggestions']
        )

    def from_gene(aid, rsid, gene, consequence, info):
        genotype = info.get('_genotype', '')
        ref_allele = info.get('_ref_allele')
        percentile = info['percentile']
        if consequence in ('missense_variant', 'stop_gained'):
            percentile = min(95, percentile + 10)
        percentile = _adjust_percentile(percentile, genotype or None, ref_allele)
        return CognitiveProfile(
            analysis_id=aid, cognitive_domain=info['domain'],
            genetic_score=info['score'], percentile=percentile,
            associated_variants=[rsid],
            enhancement_suggestions=info['suggestions']
        )

    rsid_map, gene_map = ctx.get_maps('cognitive')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='domain',
        build_from_rsid=from_rsid, build_from_gene=from_gene
    )
