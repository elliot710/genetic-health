"""Nutrition traits insight generator."""
from ...db.models import NutritionTrait
from .base import GeneratorContext, generate_from_maps, zygosity_adjust


async def generate_nutrition_traits(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        return NutritionTrait(
            analysis_id=aid, nutrient=info['nutrient'],
            metabolism_type=info['metabolism'],
            dietary_recommendations=info['recommendations'],
            associated_variants=[rsid],
            sensitivity_level=zygosity_adjust(info['sensitivity'], genotype, ref_allele=info.get('_ref_allele'))
        )

    def from_gene(aid, rsid, gene, consequence, info):
        genotype = info.get('_genotype', '')
        ref_allele = info.get('_ref_allele')
        return NutritionTrait(
            analysis_id=aid, nutrient=info['nutrient'],
            metabolism_type=info['metabolism'],
            dietary_recommendations=info['recommendations'],
            associated_variants=[rsid],
            sensitivity_level=zygosity_adjust(info['sensitivity'], genotype, ref_allele=ref_allele) if genotype else info['sensitivity']
        )

    rsid_map, gene_map = ctx.get_maps('nutrition')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='nutrient',
        build_from_rsid=from_rsid, build_from_gene=from_gene
    )
