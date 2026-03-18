"""Wellness metrics insight generator."""
from ...db.models import WellnessMetric
from .base import GeneratorContext, generate_from_maps, zygosity_adjust, boost_if_pathogenic


async def generate_wellness_metrics(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        base = boost_if_pathogenic(info['predisposition'], info.get('_pathogenicity_score'))
        return WellnessMetric(
            analysis_id=aid, metric_name=info['metric'],
            genetic_predisposition=zygosity_adjust(base, genotype, ref_allele=info.get('_ref_allele')),
            optimization_score=info['score'],
            lifestyle_recommendations=info['recommendations'],
            associated_variants=[rsid]
        )

    def from_gene(aid, rsid, gene, consequence, info):
        genotype = info.get('_genotype', '')
        ref_allele = info.get('_ref_allele')
        base = boost_if_pathogenic(info['predisposition'], info.get('_pathogenicity_score'))
        return WellnessMetric(
            analysis_id=aid, metric_name=info['metric'],
            genetic_predisposition=zygosity_adjust(base, genotype, ref_allele=ref_allele) if genotype else base,
            optimization_score=info['score'],
            lifestyle_recommendations=info['recommendations'],
            associated_variants=[rsid]
        )

    rsid_map, gene_map = ctx.get_maps('wellness')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='metric',
        build_from_rsid=from_rsid, build_from_gene=from_gene
    )
