"""Methylation profile insight generator."""
from ...db.models import MethylationProfile
from .base import GeneratorContext, generate_from_maps, zygosity_adjust


async def generate_methylation_profiles(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        return MethylationProfile(
            analysis_id=aid, gene=info['gene'],
            variant=rsid,
            methylation_capacity=zygosity_adjust(info['capacity'], genotype, ref_allele=info.get('_ref_allele')),
            supplement_recommendations=info['supplements'],
            associated_variants=[rsid]
        )

    def from_gene(aid, rsid, gene, consequence, info):
        return MethylationProfile(
            analysis_id=aid, gene=info['gene'],
            variant=rsid, methylation_capacity=info['capacity'],
            supplement_recommendations=info['supplements'],
            associated_variants=[rsid]
        )

    rsid_map, gene_map = ctx.get_maps('methylation')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='gene',
        build_from_rsid=from_rsid, build_from_gene=from_gene
    )
