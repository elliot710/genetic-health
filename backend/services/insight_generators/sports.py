"""Sports performance insight generator."""
from ...db.models import SportsPerformance
from .base import GeneratorContext, generate_from_maps, zygosity_adjust, boost_if_pathogenic


async def generate_sports_performance(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        adjusted = zygosity_adjust(info['advantage'], genotype, ref_allele=info.get('_ref_allele'))
        return SportsPerformance(
            analysis_id=aid, performance_category=info['category'],
            genetic_advantage=boost_if_pathogenic(adjusted, info.get('_pathogenicity_score')),
            sport_recommendations=info['recommendations'],
            associated_variants=[rsid],
            training_advice=info['advice']
        )

    def from_gene(aid, rsid, gene, consequence, info):
        genotype = info.get('_genotype', '')
        ref_allele = info.get('_ref_allele')
        adjusted = zygosity_adjust(info['advantage'], genotype, ref_allele=ref_allele) if genotype else info['advantage']
        return SportsPerformance(
            analysis_id=aid, performance_category=info['category'],
            genetic_advantage=boost_if_pathogenic(adjusted, info.get('_pathogenicity_score')),
            sport_recommendations=info['recommendations'],
            associated_variants=[rsid],
            training_advice=info['advice']
        )

    rsid_map, gene_map = ctx.get_maps('sports')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='category',
        build_from_rsid=from_rsid, build_from_gene=from_gene,
        max_population_af=0.20,
    )
