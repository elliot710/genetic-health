"""Drug response insight generator."""
from ...db.models import DrugResponse
from .base import (
    GeneratorContext, extract_gene_and_consequence,
    assess_drug_response, get_drug_recommendations,
    get_user_genotype, is_homozygous_reference,
    _get_effective_ref_allele,
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

        # Extract genotype and ref allele early
        genotype = get_user_genotype(variant)
        annotation_result = ctx.annotation_results.get(variant_rsid)
        effective_ref = _get_effective_ref_allele(variant, annotation_result)

        # Skip homozygous reference — user has no alternate allele
        if effective_ref and is_homozygous_reference(genotype, effective_ref):
            continue

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

        gene, consequence, impact = extract_gene_and_consequence(
            annotation_result, ctx.rsid_gene_map
        )
        if gene and gene in drug_gene_map:
            info = drug_gene_map[gene]
            for drug_name, response, rec in info['drugs']:
                if drug_name in _PLACEHOLDER_DRUGS:
                    continue
                drug_key = f"{info['gene']}_{drug_name}"
                if drug_key not in seen_drugs:
                    seen_drugs.add(drug_key)
                    drug_responses.append(DrugResponse(
                        analysis_id=ctx.analysis_id, gene=info['gene'],
                        drug=drug_name, response_type=response,
                        recommendations=rec, variants_involved=[variant_rsid]
                    ))

    for r in drug_responses:
        ctx.session.add(r)
    return len(drug_responses)
