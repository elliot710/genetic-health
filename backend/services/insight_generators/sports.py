"""Sports performance insight generator."""
from ...db.models import SportsPerformance
from .base import GeneratorContext, generate_from_maps, zygosity_adjust


async def generate_sports_performance(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        return SportsPerformance(
            analysis_id=aid, performance_category=info['category'],
            genetic_advantage=zygosity_adjust(info['advantage'], genotype, ref_allele=info.get('_ref_allele')),
            sport_recommendations=info['recommendations'],
            associated_variants=[rsid],
            training_advice=info['advice']
        )

    def from_gene(aid, rsid, gene, consequence, info):
        genotype = info.get('_genotype', '')
        ref_allele = info.get('_ref_allele')
        return SportsPerformance(
            analysis_id=aid, performance_category=info['category'],
            genetic_advantage=zygosity_adjust(info['advantage'], genotype, ref_allele=ref_allele) if genotype else info['advantage'],
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
