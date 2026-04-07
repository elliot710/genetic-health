"""Health risk insight generator."""
from ...db.models import HealthRisk
from .base import (
    GeneratorContext, generate_from_maps, assess_risk_level,
    get_health_recommendations, extract_gene_and_consequence,
    risk_level_to_score, zygosity_adjust, get_clingen_validity,
)

_CLINGEN_SKIP = frozenset({'Disputed', 'Refuted'})


async def generate_health_risks(ctx: GeneratorContext) -> int:
    def _is_clingen_disputed(rsid):
        ar = ctx.annotation_results.get(rsid)
        validity = get_clingen_validity(ar)
        return validity in _CLINGEN_SKIP

    def from_rsid(aid, rsid, genotype, info):
        if _is_clingen_disputed(rsid):
            return None
        annotation_result = ctx.annotation_results.get(rsid)
        path_score = None
        if annotation_result and annotation_result.annotation_data:
            path_score = annotation_result.annotation_data.get('pathogenicity_score')
        risk_level = assess_risk_level(
            genotype, info['risk_multiplier'],
            ref_allele=info.get('_ref_allele'),
            pathogenicity_score=path_score,
        )
        recommendations = info.get('recommendations')
        if not recommendations or recommendations == ['Consult with healthcare provider']:
            recommendations = get_health_recommendations(info['condition'], risk_level)
        _ps = info.get('_pathogenicity_score')
        _classification = _ps.get('classification') if isinstance(_ps, dict) else None
        return HealthRisk(
            analysis_id=aid, condition=info['condition'],
            risk_level=risk_level, risk_score=risk_level_to_score(risk_level),
            associated_variants=[rsid],
            recommendations=recommendations,
            gene=info.get('gene') or None,
            review_status=info.get('review_status') or None,
            pathogenicity_classification=_classification,
        )

    def from_gene(aid, rsid, gene, consequence, info):
        if _is_clingen_disputed(rsid):
            return None
        genotype = info.get('_genotype', '')
        ref_allele = info.get('_ref_allele')
        risk_level = zygosity_adjust(info['risk_level'], genotype, ref_allele=ref_allele)
        _ps = info.get('_pathogenicity_score')
        _classification = _ps.get('classification') if isinstance(_ps, dict) else None
        return HealthRisk(
            analysis_id=aid, condition=info['condition'],
            risk_level=risk_level, risk_score=risk_level_to_score(risk_level),
            associated_variants=[rsid], recommendations=info['recommendations'],
            gene=gene or info.get('gene') or None,
            review_status=info.get('review_status') or None,
            pathogenicity_classification=_classification,
        )

    rsid_map, gene_map = ctx.get_maps('health')
    return await generate_from_maps(
        ctx, rsid_map=rsid_map, gene_map=gene_map,
        dedup_field='condition',
        build_from_rsid=from_rsid, build_from_gene=from_gene,
        filter_benign=True,
        max_population_af=0.05,
    )
