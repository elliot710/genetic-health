"""Cognitive profile insight generator."""
from ...db.models import CognitiveProfile
from .base import GeneratorContext, generate_from_maps, is_heterozygous, is_homozygous_reference, is_no_call_genotype


async def generate_cognitive_profiles(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        percentile = info['percentile']
        if is_homozygous_reference(genotype, info.get('_ref_allele')) or not genotype:
            percentile = max(1, percentile - 10)
        elif not is_heterozygous(genotype):
            # Homozygous alternate — stronger effect
            percentile = min(99, percentile + 10)
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
        # Apply zygosity adjustment to percentile
        if genotype and ref_allele:
            if is_homozygous_reference(genotype, ref_allele):
                percentile = max(1, percentile - 10)
            elif not is_heterozygous(genotype):
                percentile = min(99, percentile + 10)
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
