"""Uncommon mutations insight generator."""
import asyncio
import logging
from ...db.models import UncommonMutation
from .base import (
    GeneratorContext, extract_gene_and_consequence, extract_frequency,
    get_user_genotype, _get_effective_ref_allele, is_homozygous_reference,
    is_no_call_genotype, is_indel_genotype,
)

logger = logging.getLogger(__name__)

# Strand complement for allele verification (handles arrays reporting on minus strand)
_COMPLEMENT = str.maketrans('ACGT', 'TGCA')

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


def _get_alt_alleles(annotations: dict) -> list[str]:
    """Extract alternate (risk) alleles from annotation sources.

    For multi-allelic sites (Ensembl allele_string "REF/A,T") returns ALL
    alternate alleles so callers can check if the user carries ANY of them.
    """
    # Ensembl VEP first — may have multiple alts e.g. "G/A,T"
    ensembl = annotations.get('ensembl', {})
    data_list = ensembl.get('data', [])
    if data_list:
        allele_str = data_list[0].get('allele_string', '')
        if '/' in allele_str:
            parts = allele_str.split('/')
            if len(parts) >= 2:
                alts = [a.strip().upper() for a in parts[1].split(',')
                        if a.strip() and a.strip() not in ('N', '-', '.')]
                if alts:
                    return alts
    # ClinVar local — single alt
    cv = annotations.get('clinvar_local', {})
    if cv and cv.get('found'):
        alt = cv.get('alt_allele') or cv.get('alternate_allele')
        if alt and alt not in ('N', '-', '.', ''):
            return [alt.strip().upper()]
    # gnomAD — single alt
    gnomad = annotations.get('gnomad', {})
    if gnomad and gnomad.get('found'):
        alt = gnomad.get('alt')
        if alt and alt not in ('N', '-', '.', ''):
            return [alt.strip().upper()]
    return []


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

        # Skip no-call and indel-coded genotypes (II/DD/DI/ID)
        user_gt = get_user_genotype(variant)
        if is_no_call_genotype(user_gt) or is_indel_genotype(user_gt):
            continue

        # Use annotation-derived ref allele (more reliable than marker for consumer CSV).
        # Also perform a strand-flip-aware hom-ref check: some microarray chips report
        # alleles on the minus strand, so CC can mean GG on the plus strand (hom-ref
        # for a G/A variant). Complement the user's alleles and re-check if needed.
        effective_ref = _get_effective_ref_allele(variant, annotation_result)
        if effective_ref:
            gt = user_gt.upper()
            if is_homozygous_reference(gt, effective_ref):
                continue
            # Strand-flip fallback: if none of the alleles match the reference on the
            # forward strand, try the reverse complement — if that is all-ref, the user
            # is homozygous reference on the reported (minus) strand.
            if not any(a == effective_ref for a in gt):
                flipped = gt.translate(_COMPLEMENT)
                if is_homozygous_reference(flipped, effective_ref):
                    continue

        annotations = annotation_result.annotation_data.get('annotations', {})

        # Allele verification: confirm the user actually carries at least one
        # of the alternate alleles. Handles multi-allelic sites (e.g. G/A,T)
        # and applies strand-flip correction for minus-strand arrays.
        alt_alleles = _get_alt_alleles(annotations)
        if alt_alleles:
            gt = user_gt.upper()
            gt_set = set(gt)
            gt_flipped = set(gt.translate(_COMPLEMENT))
            snp_alts = [a for a in alt_alleles if len(a) == 1]
            if snp_alts:
                carries = any(a in gt_set or a in gt_flipped for a in snp_alts)
                if not carries:
                    continue  # User does not carry any alternate allele

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
