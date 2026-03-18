"""Drug response insight generator."""
from ...db.models import DrugResponse
from .base import (
    GeneratorContext, extract_gene_and_consequence,
    assess_drug_response, get_drug_recommendations,
    get_user_genotype, is_homozygous_reference,
    is_no_call_genotype, _get_effective_ref_allele,
)


async def generate_drug_responses(ctx: GeneratorContext) -> int:
    """Drug responses need custom logic (multiple drugs per match)."""
    drug_rsid_map, drug_gene_map = ctx.get_maps('drug')
    drug_responses = []
    seen_drugs: set = set()

    # Placeholder drug names from auto-categorizer templates — skip these
    _PLACEHOLDER_DRUGS = {'Associated medication', 'associated medication'}

    for variant in ctx.variants:
        variant_rsid = getattr(variant, 'rsid', None)
        if not variant_rsid:
            continue

        # Use pre-computed profile when available
        profile = ctx.variant_profiles.get(variant_rsid)
        if profile:
            genotype = profile.genotype
            if profile.is_no_call or profile.is_hom_ref:
                continue
            effective_ref = profile.effective_ref
            annotation_result = profile.annotation_result
            gene = profile.gene
            consequence = profile.consequence
            impact = profile.impact
        else:
            genotype = get_user_genotype(variant)
            if is_no_call_genotype(genotype):
                continue
            annotation_result = ctx.annotation_results.get(variant_rsid)
            effective_ref = _get_effective_ref_allele(variant, annotation_result)
            if effective_ref and is_homozygous_reference(genotype, effective_ref):
                continue
            gene, consequence, impact = extract_gene_and_consequence(
                annotation_result, ctx.rsid_gene_map
            )

        if variant_rsid in drug_rsid_map:
            info = drug_rsid_map[variant_rsid]
            for drug in info['drugs']:
                if drug in _PLACEHOLDER_DRUGS:
                    continue
                drug_key = f"{info['gene']}_{drug}"
                if drug_key not in seen_drugs:
                    seen_drugs.add(drug_key)
                    response_type = assess_drug_response(
                        genotype or '', info['gene'], ref_allele=effective_ref,
                    )
                    drug_responses.append(DrugResponse(
                        analysis_id=ctx.analysis_id, gene=info['gene'],
                        drug=drug, response_type=response_type,
                        recommendations=get_drug_recommendations(drug, response_type),
                        variants_involved=[variant_rsid]
                    ))

        if gene and gene in drug_gene_map:
            info = drug_gene_map[gene]
            for drug_name, _template_response, rec in info['drugs']:
                if drug_name in _PLACEHOLDER_DRUGS:
                    continue
                drug_key = f"{info['gene']}_{drug_name}"
                if drug_key not in seen_drugs:
                    seen_drugs.add(drug_key)
                    # Apply zygosity-aware response instead of using template
                    response_type = assess_drug_response(
                        genotype or '', info['gene'], ref_allele=effective_ref,
                    )
                    drug_responses.append(DrugResponse(
                        analysis_id=ctx.analysis_id, gene=info['gene'],
                        drug=drug_name, response_type=response_type,
                        recommendations=get_drug_recommendations(drug_name, response_type),
                        variants_involved=[variant_rsid]
                    ))

    for r in drug_responses:
        ctx.session.add(r)
    return len(drug_responses)
