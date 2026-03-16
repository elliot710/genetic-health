"""Sports performance insight generator."""
from ...db.models import SportsPerformance
from .base import GeneratorContext, generate_from_maps


async def generate_sports_performance(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        return SportsPerformance(
            analysis_id=aid, performance_category=info['category'],
            genetic_advantage=info['advantage'],
            sport_recommendations=info['recommendations'],
            associated_variants=[rsid],
            training_advice=info['advice']
        )

    def from_gene(aid, rsid, gene, consequence, info):
        return SportsPerformance(
            analysis_id=aid, performance_category=info['category'],
            genetic_advantage=info['advantage'],
            sport_recommendations=info['recommendations'],
            associated_variants=[rsid],
            training_advice=info['advice']
        )

    rsid_map, gene_map = ctx.get_maps('sports')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='category',
        build_from_rsid=from_rsid, build_from_gene=from_gene
    )
