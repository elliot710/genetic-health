"""Wellness metrics insight generator."""
from ...db.models import WellnessMetric
from .base import GeneratorContext, generate_from_maps


async def generate_wellness_metrics(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        return WellnessMetric(
            analysis_id=aid, metric_name=info['metric'],
            genetic_predisposition=info['predisposition'],
            optimization_score=info['score'],
            lifestyle_recommendations=info['recommendations'],
            associated_variants=[rsid]
        )

    def from_gene(aid, rsid, gene, consequence, info):
        return WellnessMetric(
            analysis_id=aid, metric_name=info['metric'],
            genetic_predisposition=info['predisposition'],
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
