"""Health risk insight generator."""
from ...db.models import HealthRisk
from .base import (
    GeneratorContext, generate_from_maps, assess_risk_level,
    get_health_recommendations,
)


async def generate_health_risks(ctx: GeneratorContext) -> int:
    def from_rsid(aid, rsid, genotype, info):
        risk_level = assess_risk_level(genotype, info['risk_multiplier'])
        return HealthRisk(
            analysis_id=aid, condition=info['condition'],
            risk_level=risk_level, risk_score=f"{info['risk_multiplier']}x",
            associated_variants=[rsid],
            recommendations=get_health_recommendations(info['condition'], risk_level)
        )

    def from_gene(aid, rsid, gene, consequence, info):
        return HealthRisk(
            analysis_id=aid, condition=info['condition'],
            risk_level=info['risk_level'], risk_score=info['risk_score'],
            associated_variants=[rsid], recommendations=info['recommendations']
        )

    rsid_map, gene_map = ctx.get_maps('health')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='condition',
        build_from_rsid=from_rsid, build_from_gene=from_gene
    )
