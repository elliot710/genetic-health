"""Detoxification profile insight generator."""
from ...db.models import DetoxificationProfile
from .base import GeneratorContext, generate_from_maps


async def generate_detox_profiles(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        return DetoxificationProfile(
            analysis_id=aid, detox_phase=info['phase'],
            gene=info['gene'], detox_capacity=info['capacity'],
            toxin_sensitivity=info['sensitivity'],
            support_recommendations=info['recommendations'],
            associated_variants=[rsid]
        )

    def from_gene(aid, rsid, gene, consequence, info):
        return DetoxificationProfile(
            analysis_id=aid, detox_phase=info['phase'],
            gene=info['gene'], detox_capacity=info['capacity'],
            toxin_sensitivity=info['sensitivity'],
            support_recommendations=info['recommendations'],
            associated_variants=[rsid]
        )

    rsid_map, gene_map = ctx.get_maps('detox')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='gene',
        build_from_rsid=from_rsid, build_from_gene=from_gene
    )
