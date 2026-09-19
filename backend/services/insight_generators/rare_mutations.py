"""Rare mutations insight generator."""
import asyncio
import logging
from ...db.models import RareMutation
from .base import (
    GeneratorContext, extract_gene_and_consequence, extract_frequency,
    get_user_genotype, _get_effective_ref_allele, is_homozygous_reference,
    is_no_call_genotype, is_indel_genotype, get_annotation_allele_parts,
    is_heterozygous, indel_d_is_ref, STRAND_COMPLEMENT,
)

logger = logging.getLogger(__name__)


def _clinvar_alleles(cv_local):
    """ClinVar's own (ref, alt) for this variant, or (None, None).

    The claim being adjudicated is a ClinVar claim, so it is resolved against
    ClinVar's alleles rather than get_annotation_allele_parts(), which prefers
    Ensembl's allele_string and returns every alt joined at a multi-allelic
    site — resolving D/I direction against an allele ClinVar never classified.
    """
    ref = (cv_local.get('ref_allele') or cv_local.get('reference_allele') or '').strip().upper()
    alt = (cv_local.get('alt_allele') or cv_local.get('alternate_allele') or '').strip().upper()
    return (ref or None), (alt or None)


def _carries_clinvar_indel(user_gt, ref_allele, alt_allele):
    """Whether a consumer-array D/I genotype carries ClinVar's pathogenic allele.

    Returns True/False when direction resolves, and None when it cannot — a
    multi-allelic site, an equal-length pair, or a missing allele leaves D/I
    unattributable to one specific alt. None means no clinical claim is
    supportable; the caller drops the finding rather than guessing.
    """
    if not ref_allele or not alt_allele:
        return None
    if ',' in alt_allele:
        # Multi-allelic: "II" cannot be attributed to ClinVar's specific alt.
        return None
    gt = (user_gt or '').strip().upper()
    if gt in ('DI', 'ID'):
        return True  # one copy of whichever allele is alt
    d_is_ref = indel_d_is_ref(ref_allele, alt_allele)
    if d_is_ref is None:
        return None
    if d_is_ref:
        return gt == 'II'  # insertion variant: I is the alternate allele
    return gt == 'DD'      # deletion variant: D is the alternate allele


async def generate_rare_mutations(ctx: GeneratorContext) -> int:
    rare_mutations = []

    for _idx, variant in enumerate(ctx.variants):
        if _idx > 0 and _idx % 100 == 0:
            await asyncio.sleep(0)
        variant_rsid = getattr(variant, 'rsid', None)
        if not variant_rsid:
            continue

        # Use pre-computed profile when available
        profile = ctx.variant_profiles.get(variant_rsid)

        annotation_result = (profile.annotation_result if profile
                             else ctx.annotation_results.get(variant_rsid))
        if not annotation_result or not annotation_result.annotation_data:
            continue

        # Must have local ClinVar data to qualify. The legacy clinvar_api source
        # carries no ref/alt, so a claim sourced from it can never have its
        # allele carriage verified — and an unverifiable clinical claim is
        # exactly what this generator must not make.
        cv_local = annotation_result.annotation_data.get('annotations', {}).get('clinvar_local', {})
        if not (cv_local and cv_local.get('found')):
            continue

        # Genotype and zygosity from profile (consistent ref allele)
        if profile:
            user_gt = profile.genotype
            if profile.is_no_call or profile.is_hom_ref:
                continue
            effective_ref = profile.effective_ref
            freq = profile.population_frequency  # None = unknown, float = known
        else:
            user_gt = get_user_genotype(variant)
            if is_no_call_genotype(user_gt):
                continue
            effective_ref = _get_effective_ref_allele(variant, annotation_result)
            _, _ann_alt = get_annotation_allele_parts(annotation_result) if annotation_result else (None, None)
            if effective_ref:
                gt = user_gt.upper()
                if is_homozygous_reference(gt, effective_ref, alt_allele=_ann_alt):
                    continue
                # Strand-flip: if none of the alleles match ref on forward strand,
                # try reverse complement — hom-ref on minus strand means no variant.
                if not any(a == effective_ref for a in gt):
                    flipped = gt.translate(STRAND_COMPLEMENT)
                    if is_homozygous_reference(flipped, effective_ref):
                        continue
            raw_freq = extract_frequency(annotation_result)
            # Also try gnomAD direct AF if ensembl frequency missing
            if raw_freq == 0.0:
                gnomad = annotation_result.annotation_data.get('annotations', {}).get('gnomad', {})
                if gnomad and gnomad.get('found'):
                    raw_freq = gnomad.get('af', 0.0) or 0.0
            freq = raw_freq if raw_freq > 0 else None

        # Must be truly rare (< 1% population frequency)
        # When frequency is unknown (None), we allow it through
        # but will mark it as unknown in the output
        if freq is not None and freq > 0.01:
            continue

        # Allele verification: confirm the user's genotype contains the ClinVar-
        # recorded pathogenic allele. Consumer CSV data can have ref=alt entries
        # that survive the hom-ref check when the reference allele is unresolved.
        # Apply strand-flip fallback for arrays reporting on the minus strand.
        #
        # Indel genotypes are verified too. They used to be exempt, which is how
        # the 2026-09-16 incident happened: II/DD on chrX skipped this check
        # entirely and the X-linked branch below then promoted "not het" into
        # "hemizygous affected", reporting Rett syndrome and Duchenne muscular
        # dystrophy for an unaffected adult.
        if user_gt:
            _cv_ref, _cv_alt = _clinvar_alleles(cv_local)
            if is_indel_genotype(user_gt):
                if _carries_clinvar_indel(user_gt, _cv_ref, _cv_alt) is not True:
                    continue
            elif _cv_alt and len(_cv_alt) == 1:
                gt = user_gt.upper()
                carries = _cv_alt in set(gt)
                if not carries:
                    carries = _cv_alt in set(gt.translate(STRAND_COMPLEMENT))
                if not carries:
                    continue  # User doesn't carry this ClinVar-reported pathogenic allele

        # Extract gene and consequence (prefer profile's pre-computed values)
        if profile and profile.gene:
            gene, consequence, impact = profile.gene, profile.consequence, profile.impact
        else:
            gene, consequence, impact = extract_gene_and_consequence(
                annotation_result, ctx.rsid_gene_map
            )

        # Extract clinical significance from ClinVar local
        clinical_significance = 'uncertain'
        disease_association = ''
        gene_conditions = []
        inheritance_pattern = 'unknown'
        penetrance = 'unknown'
        review_statuses: list[str] = []

        if cv_local and cv_local.get('found'):
            clin_sigs = cv_local.get('clinical_significances', [])
            if clin_sigs:
                raw_sig = clin_sigs[0].lower().replace('_', ' ')
                # Check all significances for mixed pathogenic+benign conflicts
                all_sigs_lower = ' '.join(s.lower().replace('_', ' ') for s in clin_sigs)
                has_pathogenic = 'pathogenic' in all_sigs_lower
                has_benign = 'benign' in all_sigs_lower

                if 'conflicting' in raw_sig or (has_pathogenic and has_benign):
                    clinical_significance = 'conflicting'
                    penetrance = 'unknown'
                elif has_pathogenic and not has_benign:
                    clinical_significance = 'pathogenic' if 'likely' not in raw_sig else 'likely_pathogenic'
                    penetrance = 'moderate'
                elif has_benign and not has_pathogenic:
                    clinical_significance = 'benign' if 'likely' not in raw_sig else 'likely_benign'
                elif 'risk' in raw_sig:
                    clinical_significance = 'risk_factor'

            # ClinVar local stores conditions as a flat list of strings under
            # 'conditions' (not 'gene_conditions' which is a different legacy format).
            raw_conditions = cv_local.get('conditions', [])
            # Fallback: legacy dict-list format [{"disease": "..."}]
            if not raw_conditions:
                raw_conditions = [gc.get('disease', '') for gc in cv_local.get('gene_conditions', [])
                                  if gc.get('disease')]
            if raw_conditions:
                _skip = {'not provided', 'not specified', 'see cases', 'not applicable', 'none', ''}
                # Each condition string may itself be semicolon-separated (multiple conditions in one entry)
                flat_conditions: list[str] = []
                for raw_c in raw_conditions:
                    for part in raw_c.split(';'):
                        p = part.strip()
                        if p and p.lower() not in _skip:
                            flat_conditions.append(p)
                if flat_conditions:
                    disease_association = '; '.join(flat_conditions[:3])

                # Infer inheritance pattern from condition names
                for d in flat_conditions:
                    dl = d.lower()
                    if 'dominant' in dl:
                        inheritance_pattern = 'autosomal_dominant'
                        break
                    elif 'recessive' in dl:
                        inheritance_pattern = 'autosomal_recessive'
                        break
                    elif 'x-linked' in dl:
                        inheritance_pattern = 'x_linked'
                        break

            review_statuses = cv_local.get('review_statuses', [])

            if not gene:
                genes = cv_local.get('genes', [])
                if genes:
                    gene = genes[0]

        # Skip benign/likely_benign — not clinically relevant as rare findings
        if clinical_significance in ('benign', 'likely_benign'):
            continue

        # For ambiguous classifications, require known population frequency to
        # avoid flooding results with variants of entirely unknown rarity.
        # Pathogenic/likely_pathogenic are retained even without frequency data.
        if freq is None and clinical_significance not in ('pathogenic', 'likely_pathogenic'):
            continue

        if not gene:
            continue

        # Indel genotypes bypass allele verification. Without population frequency
        # confirming rarity, require at least multi-submitter ClinVar evidence to
        # avoid false positives from ambiguous D/I calls at multi-allelic positions.
        if freq is None and is_indel_genotype(user_gt):
            has_strong_evidence = any(
                'multiple submitters' in s.lower() or 'expert panel' in s.lower()
                or 'practice guideline' in s.lower()
                for s in review_statuses
            )
            if not has_strong_evidence:
                continue

        # X-linked carrier filter: het females are carriers, not affected.
        # Use the variant's chromosome as ground truth — condition names like
        # "Rett syndrome" or "Fabry disease" don't contain "x-linked".
        variant_chrom = getattr(variant, 'chromosome', None)
        effective_x_linked = (inheritance_pattern == 'x_linked') or (variant_chrom == 'X')
        if effective_x_linked:
            if profile:
                is_het = profile.is_het
            else:
                is_het = is_heterozygous(user_gt)

            if ctx.inferred_sex == 'female' and is_het:
                # Het female on X-linked condition = carrier, not affected
                continue
            elif ctx.inferred_sex == 'male' and is_het:
                # Het call on X for a male is a genotyping artifact (males are hemizygous on X)
                continue
            # Homozygous female on X — she IS affected, do not filter
            # Hemizygous (hom-reported) male on X — he IS affected, do not filter

        # Use scoring engine composite score for informational purposes only.
        # BUG-05 fix: Do NOT upgrade conflicting/uncertain classifications based
        # on composite_score — the score can be inflated by double-counted ClinVar
        # data and computational predictions that don't constitute clinical evidence.
        # ClinVar's clinical classification is authoritative.

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
            population_frequency=freq if freq is not None else None,
            clinical_actions=clinical_actions,
            specialist_referral=clinical_significance in ('pathogenic', 'likely_pathogenic'),
            genetic_counseling_urgent=clinical_significance == 'pathogenic',
            monitoring_recommendations=['Regular medical follow-up'],
            family_screening_recommended=clinical_significance in ('pathogenic', 'likely_pathogenic'),
            associated_variants=[variant_rsid]
        ))

    # Sort by clinical priority, then by frequency (unknown last)
    sig_priority = {
        'pathogenic': 0, 'likely_pathogenic': 1, 'risk_factor': 2,
        'conflicting': 3, 'uncertain': 4
    }
    rare_mutations.sort(key=lambda m: (
        sig_priority.get(m.clinical_significance, 5),
        m.population_frequency if m.population_frequency is not None else 1.0,
    ))

    for m in rare_mutations:
        ctx.session.add(m)
    return len(rare_mutations)
