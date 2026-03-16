"""Uncommon mutations insight generator."""
from ...db.models import UncommonMutation
from .base import (
    GeneratorContext, extract_gene_and_consequence, extract_frequency,
    get_user_genotype, get_ref_allele, is_homozygous_reference,
)


async def generate_uncommon_mutations(ctx: GeneratorContext) -> int:
    uncommon_mutations = []

    for variant in ctx.variants:
        variant_rsid = getattr(variant, 'rsid', None)
        if not variant_rsid:
            continue

        annotation_result = ctx.annotation_results.get(variant_rsid)
        if not annotation_result or not annotation_result.annotation_data:
            continue

        freq = extract_frequency(annotation_result)
        gene, consequence, impact = extract_gene_and_consequence(
            annotation_result, ctx.rsid_gene_map
        )

        # Skip homozygous-reference genotypes
        user_gt = get_user_genotype(variant)
        ref_allele = get_ref_allele(variant)
        if is_homozygous_reference(user_gt, ref_allele):
            continue

        if 0.001 <= freq <= 0.05 and gene:
            effect_size = 'moderate' if consequence in ('missense_variant', 'stop_gained', 'frameshift_variant') else 'small'
            research_status = 'well_established' if consequence == 'missense_variant' else 'emerging'
            consequence_label = (consequence or 'variant').replace("_", " ")

            uncommon_mutations.append(UncommonMutation(
                analysis_id=ctx.analysis_id,
                mutation_type='low_frequency_variant',
                gene=gene,
                mutation_name=f'{gene} {consequence_label}',
                clinical_significance='moderate' if effect_size == 'moderate' else 'low',
                trait_association=f'{gene} pathway variant',
                effect_size=effect_size,
                population_frequency=freq,
                research_status=research_status,
                lifestyle_implications=['Standard healthy lifestyle', 'No immediate action required'],
                monitoring_suggestions=['Routine health screening'],
                research_participation='optional',
                follow_up_timeline='annual',
                associated_variants=[variant_rsid]
            ))

    for m in uncommon_mutations:
        ctx.session.add(m)
    return len(uncommon_mutations)
