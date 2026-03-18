"""Uncommon mutations insight generator."""
import asyncio
import logging
from ...db.models import UncommonMutation
from .base import (
    GeneratorContext, extract_gene_and_consequence, extract_frequency,
    get_user_genotype, get_ref_allele, is_homozygous_reference,
    is_no_call_genotype,
)

logger = logging.getLogger(__name__)

# Only include variants with functional consequences — skip intergenic,
# intronic, upstream/downstream which are rarely clinically actionable.
_FUNCTIONAL_CONSEQUENCES = {
    'missense_variant', 'stop_gained', 'frameshift_variant',
    'splice_acceptor_variant', 'splice_donor_variant',
    'stop_lost', 'start_lost', 'inframe_insertion', 'inframe_deletion',
    'protein_altering_variant', 'splice_region_variant',
}

# Cap output to avoid drowning real insights in low-value uncommon variants
_MAX_UNCOMMON = 500


async def generate_uncommon_mutations(ctx: GeneratorContext) -> int:
    uncommon_mutations = []

    for _idx, variant in enumerate(ctx.variants):
        if _idx > 0 and _idx % 100 == 0:
            await asyncio.sleep(0)
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

        # Skip no-call and homozygous-reference genotypes
        user_gt = get_user_genotype(variant)
        if is_no_call_genotype(user_gt):
            continue
        ref_allele = get_ref_allele(variant)
        if is_homozygous_reference(user_gt, ref_allele):
            continue

        # Require functional consequence
        if consequence not in _FUNCTIONAL_CONSEQUENCES:
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

    # Sort by clinical relevance: moderate effect first, then by rarity
    uncommon_mutations.sort(
        key=lambda m: (0 if m.effect_size == 'moderate' else 1, m.population_frequency)
    )

    # Cap to avoid flooding the dashboard
    uncommon_mutations = uncommon_mutations[:_MAX_UNCOMMON]

    for m in uncommon_mutations:
        ctx.session.add(m)
    return len(uncommon_mutations)
