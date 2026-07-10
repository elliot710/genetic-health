"""Methylation profile insight generator."""
from ...db.models import MethylationProfile
from .base import GeneratorContext, generate_from_maps, zygosity_adjust, boost_if_pathogenic


async def generate_methylation_profiles(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        capacity = info.get('capacity', 'variant_detected')
        adjusted = zygosity_adjust(capacity, genotype, ref_allele=info.get('_ref_allele'))
        return MethylationProfile(
            analysis_id=aid, gene=info['gene'],
            variant=rsid,
            methylation_capacity=boost_if_pathogenic(adjusted, info.get('_pathogenicity_score')),
            supplement_recommendations=info.get('supplements', f"Support {info['gene']} methylation pathway"),
            associated_variants=[rsid]
        )

    def from_gene(aid, rsid, gene, consequence, info):
        genotype = info.get('_genotype', '')
        ref_allele = info.get('_ref_allele')
        capacity = info.get('capacity', 'variant_detected')
        adjusted = zygosity_adjust(capacity, genotype, ref_allele=ref_allele) if genotype else capacity
        return MethylationProfile(
            analysis_id=aid, gene=info['gene'],
            variant=rsid,
            methylation_capacity=boost_if_pathogenic(adjusted, info.get('_pathogenicity_score')),
            supplement_recommendations=info.get('supplements', f"Support {info['gene']} methylation pathway"),
            associated_variants=[rsid]
        )

    rsid_map, gene_map = ctx.get_maps('methylation')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='gene',
        build_from_rsid=from_rsid, build_from_gene=from_gene,
        max_population_af=0.20,
    )
