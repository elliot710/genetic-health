"""Rare mutations insight generator."""
import logging
from ...db.models import RareMutation
from .base import (
    GeneratorContext, extract_gene_and_consequence, extract_frequency,
    get_user_genotype, is_homozygous_reference,
)

logger = logging.getLogger(__name__)


async def generate_rare_mutations(ctx: GeneratorContext) -> int:
    rare_mutations = []

    for variant in ctx.variants:
        variant_rsid = getattr(variant, 'rsid', None)
        if not variant_rsid:
            continue

        annotation_result = ctx.annotation_results.get(variant_rsid)
        if not annotation_result or not annotation_result.annotation_data:
            continue

        # Must have ClinVar data to qualify
        cv_local = annotation_result.annotation_data.get('annotations', {}).get('clinvar_local', {})
        clinvar_api = annotation_result.annotation_data.get('annotations', {}).get('clinvar', {})
        if not ((cv_local and cv_local.get('found')) or (clinvar_api and clinvar_api.get('found'))):
            continue

        # Skip homozygous-reference genotypes — if both alleles are
        # identical at a rare ClinVar position, the user almost certainly
        # carries the reference allele, not the pathogenic alternate.
        user_gt = get_user_genotype(variant)
        if is_homozygous_reference(user_gt):
            continue

        # Extract frequency — must be truly rare (< 1%)
        freq = extract_frequency(annotation_result)
        # Also try gnomAD direct AF if ensembl frequency missing
        if freq == 0.0:
            gnomad = annotation_result.annotation_data.get('annotations', {}).get('gnomad', {})
            if gnomad and gnomad.get('found'):
                freq = gnomad.get('af', 0.0) or 0.0
        if freq > 0.01:
            continue

        # Extract gene and consequence
        gene, consequence, impact = extract_gene_and_consequence(
            annotation_result, ctx.rsid_gene_map
        )

        # Extract clinical significance from ClinVar local
        clinical_significance = 'uncertain'
        disease_association = ''
        gene_conditions = []
        inheritance_pattern = 'unknown'
        penetrance = 'unknown'

        if cv_local and cv_local.get('found'):
            clin_sigs = cv_local.get('clinical_significances', [])
            if clin_sigs:
                raw_sig = clin_sigs[0].lower().replace('_', ' ')
                if 'conflicting' in raw_sig:
                    clinical_significance = 'conflicting'
                    penetrance = 'unknown'
                elif 'pathogenic' in raw_sig and 'benign' not in raw_sig:
                    clinical_significance = 'pathogenic' if 'likely' not in raw_sig else 'likely_pathogenic'
                    penetrance = 'moderate'
                elif 'benign' in raw_sig and 'pathogenic' not in raw_sig:
                    clinical_significance = 'benign' if 'likely' not in raw_sig else 'likely_benign'
                elif 'risk' in raw_sig:
                    clinical_significance = 'risk_factor'

            gene_conditions = cv_local.get('gene_conditions', [])
            if gene_conditions:
                diseases = [gc.get('disease', '') for gc in gene_conditions
                            if gc.get('disease') and gc.get('disease', '').lower() != 'not provided']
                disease_association = '; '.join(diseases[:3]) if diseases else ''

                # Infer inheritance from disease name
                for gc in gene_conditions:
                    d = gc.get('disease', '').lower()
                    if 'dominant' in d:
                        inheritance_pattern = 'autosomal_dominant'
                        break
                    elif 'recessive' in d:
                        inheritance_pattern = 'autosomal_recessive'
                        break
                    elif 'x-linked' in d:
                        inheritance_pattern = 'x_linked'
                        break

            if not gene:
                genes = cv_local.get('genes', [])
                if genes:
                    gene = genes[0]

        # Skip benign/likely_benign — not clinically relevant as rare findings
        if clinical_significance in ('benign', 'likely_benign'):
            continue

        if not gene:
            continue

        consequence_label = (consequence or 'variant').replace('_', ' ')
        mutation_name = f'{gene} {consequence_label}'

        # Determine mutation type from clinical significance
        if clinical_significance in ('pathogenic', 'likely_pathogenic'):
            mutation_type = 'clinically_significant'
        elif clinical_significance == 'conflicting':
            mutation_type = 'conflicting_evidence'
        elif clinical_significance == 'risk_factor':
            mutation_type = 'risk_factor'
        else:
            mutation_type = 'potentially_significant'

        # Build clinical actions based on significance
        clinical_actions = []
        if clinical_significance in ('pathogenic', 'likely_pathogenic'):
            clinical_actions = ['Genetic counseling recommended', 'Discuss with specialist']
        elif clinical_significance == 'conflicting':
            clinical_actions = ['Further testing may clarify significance']
        else:
            clinical_actions = ['Monitor in future research updates']

        rare_mutations.append(RareMutation(
            analysis_id=ctx.analysis_id,
            mutation_type=mutation_type,
            gene=gene,
            mutation_name=mutation_name,
            clinical_significance=clinical_significance,
            disease_association=disease_association or 'No known disease association',
            penetrance=penetrance,
            inheritance_pattern=inheritance_pattern,
            population_frequency=freq if freq > 0 else 0.001,
            clinical_actions=clinical_actions,
            specialist_referral=clinical_significance in ('pathogenic', 'likely_pathogenic'),
            genetic_counseling_urgent=clinical_significance == 'pathogenic',
            monitoring_recommendations=['Regular medical follow-up'],
            family_screening_recommended=clinical_significance in ('pathogenic', 'likely_pathogenic'),
            associated_variants=[variant_rsid]
        ))

    # Sort by clinical priority
    sig_priority = {
        'pathogenic': 0, 'likely_pathogenic': 1, 'risk_factor': 2,
        'conflicting': 3, 'uncertain': 4
    }
    rare_mutations.sort(key=lambda m: (sig_priority.get(m.clinical_significance, 5), m.population_frequency))

    for m in rare_mutations:
        ctx.session.add(m)
    return len(rare_mutations)
