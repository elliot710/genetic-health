"""Cognitive profile insight generator."""
from ...db.models import CognitiveProfile
from .base import GeneratorContext, generate_from_maps


async def generate_cognitive_profiles(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        return CognitiveProfile(
            analysis_id=aid, cognitive_domain=info['domain'],
            genetic_score=info['score'], percentile=info['percentile'],
            associated_variants=[rsid],
            enhancement_suggestions=info['suggestions']
        )

    def from_gene(aid, rsid, gene, consequence, info):
        percentile = info['percentile']
        if consequence in ('missense_variant', 'stop_gained'):
            percentile = min(95, percentile + 10)
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
