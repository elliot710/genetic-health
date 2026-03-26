"""Detoxification profile insight generator."""
from ...db.models import DetoxificationProfile
from .base import GeneratorContext, generate_from_maps, zygosity_adjust, boost_if_pathogenic


async def generate_detox_profiles(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        path_score = info.get('_pathogenicity_score')
        ref_allele = info.get('_ref_allele')
        cap_adj = zygosity_adjust(info['capacity'], genotype, ref_allele=ref_allele)
        sen_adj = zygosity_adjust(info['sensitivity'], genotype, ref_allele=ref_allele)
        return DetoxificationProfile(
            analysis_id=aid, detox_phase=info['phase'],
            gene=info['gene'],
            detox_capacity=boost_if_pathogenic(cap_adj, path_score),
            toxin_sensitivity=boost_if_pathogenic(sen_adj, path_score),
            support_recommendations=info['recommendations'],
            associated_variants=[rsid]
        )

    def from_gene(aid, rsid, gene, consequence, info):
        genotype = info.get('_genotype', '')
        ref_allele = info.get('_ref_allele')
        path_score = info.get('_pathogenicity_score')
        cap_adj = zygosity_adjust(info['capacity'], genotype, ref_allele=ref_allele) if genotype else info['capacity']
        sen_adj = zygosity_adjust(info['sensitivity'], genotype, ref_allele=ref_allele) if genotype else info['sensitivity']
        return DetoxificationProfile(
            analysis_id=aid, detox_phase=info['phase'],
            gene=info['gene'],
            detox_capacity=boost_if_pathogenic(cap_adj, path_score),
            toxin_sensitivity=boost_if_pathogenic(sen_adj, path_score),
            support_recommendations=info['recommendations'],
            associated_variants=[rsid]
        )

    rsid_map, gene_map = ctx.get_maps('detox')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='gene',
        build_from_rsid=from_rsid, build_from_gene=from_gene,
        skip_benign_filter=True,
    )
