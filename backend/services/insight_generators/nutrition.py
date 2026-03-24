"""Nutrition traits insight generator."""
from ...db.models import NutritionTrait
from .base import GeneratorContext, generate_from_maps, zygosity_adjust, boost_if_pathogenic


async def generate_nutrition_traits(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        adjusted = zygosity_adjust(info['sensitivity'], genotype, ref_allele=info.get('_ref_allele'))
        return NutritionTrait(
            analysis_id=aid, nutrient=info['nutrient'],
            metabolism_type=info['metabolism'],
            dietary_recommendations=info['recommendations'],
            associated_variants=[rsid],
            sensitivity_level=boost_if_pathogenic(adjusted, info.get('_pathogenicity_score'))
        )

    def from_gene(aid, rsid, gene, consequence, info):
        genotype = info.get('_genotype', '')
        ref_allele = info.get('_ref_allele')
        adjusted = zygosity_adjust(info['sensitivity'], genotype, ref_allele=ref_allele) if genotype else info['sensitivity']
        return NutritionTrait(
            analysis_id=aid, nutrient=info['nutrient'],
            metabolism_type=info['metabolism'],
            dietary_recommendations=info['recommendations'],
            associated_variants=[rsid],
            sensitivity_level=boost_if_pathogenic(adjusted, info.get('_pathogenicity_score'))
        )

    rsid_map, gene_map = ctx.get_maps('nutrition')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='nutrient',
        build_from_rsid=from_rsid, build_from_gene=from_gene
    )
