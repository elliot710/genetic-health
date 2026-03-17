"""Carrier status insight generator."""
import logging
from ...db.models import CarrierStatus
from .base import (
    GeneratorContext, get_user_genotype, get_ref_allele,
    is_homozygous_reference, is_heterozygous, _parse_alleles,
)

logger = logging.getLogger(__name__)


def _classify_carrier_status(user_gt: str, ref_allele: str, alt_allele: str) -> str:
    """Determine carrier status from genotype + known ref/alt alleles.

    Returns 'affected' (homozygous alt), 'carrier' (heterozygous), or
    'unaffected' (homozygous ref / no alt match).
    """
    alleles = _parse_alleles(user_gt)
    if not alleles:
        return 'unaffected'

    ref = (ref_allele or '').strip().upper()
    alt = (alt_allele or '').strip().upper()

    if ref and alt and ref != alt:
        # We know both the reference and alternate alleles — exact classification
        alt_count = sum(1 for a in alleles if a == alt)
        if alt_count == 0:
            return 'unaffected'
        elif alt_count == len(alleles):
            return 'affected'
        else:
            return 'carrier'

    # Fallback: we only have ref_allele (common for consumer CSV where ref==alt)
    if ref:
        ref_count = sum(1 for a in alleles if a == ref)
        if ref_count == len(alleles):
            return 'unaffected'  # All reference
        elif ref_count == 0:
            # All non-reference — but we don't know if the non-ref allele
            # is the pathogenic one. Be conservative: report as carrier, not affected.
            return 'carrier'
        else:
            return 'carrier'  # Mix of ref + non-ref

    # No ref_allele at all — heterozygous is the safest assumption for non-ref
    if is_heterozygous(user_gt):
        return 'carrier'

    return 'unaffected'


async def generate_carrier_status(ctx: GeneratorContext) -> int:
    carrier_rsid_map, _ = ctx.get_maps('carrier')
    carrier_results = []
    seen_conditions: set = set()

    for variant in ctx.variants:
        variant_rsid = getattr(variant, 'rsid', None)
        if not variant_rsid:
            continue

        # Skip homozygous-reference genotypes — user doesn't carry
        # the alternate allele at this position.
        user_gt = get_user_genotype(variant)
        ref_allele = get_ref_allele(variant)
        if is_homozygous_reference(user_gt, ref_allele):
            continue

        # Registry-based matching
        if variant_rsid in carrier_rsid_map:
            info = carrier_rsid_map[variant_rsid]
            cond = info['condition']
            if cond not in seen_conditions:
                seen_conditions.add(cond)
                # Determine actual carrier status from genotype instead of
                # blindly using the registry template (which always says 'carrier').
                marker = getattr(variant, 'marker', None)
                marker_alt = getattr(marker, 'alt_alleles', '') or ''
                actual_status = _classify_carrier_status(
                    user_gt or '', ref_allele or '', marker_alt
                )
                if actual_status == 'unaffected':
                    seen_conditions.discard(cond)
                    continue
                carrier_results.append(CarrierStatus(
                    analysis_id=ctx.analysis_id,
                    condition=cond,
                    carrier_status=actual_status,
                    inheritance_pattern=info.get('inheritance', 'autosomal_recessive'),
                    associated_variants=[variant_rsid],
                    genetic_counseling_recommended=info.get('counseling', False)
                ))

        # ClinVar-local annotation-based discovery
        annotation_result = ctx.annotation_results.get(variant_rsid)
        if not annotation_result or not annotation_result.annotation_data:
            continue

        cv_local = annotation_result.annotation_data.get('annotations', {}).get('clinvar_local', {})
        if not cv_local or not cv_local.get('found'):
            continue

        clin_sigs = cv_local.get('clinical_significances', [])
        sig_lower = ' '.join(s.lower() for s in clin_sigs)

        # Only carrier-relevant: pathogenic/likely pathogenic variants
        if not any(kw in sig_lower for kw in ('pathogenic', 'risk_factor', 'risk factor')):
            continue

        gene_conditions = cv_local.get('gene_conditions', [])
        if not gene_conditions:
            continue

        # Determine carrier status using ref/alt alleles from ClinVar or marker
        cv_alt = cv_local.get('alt_allele') or cv_local.get('alternate_allele') or ''
        marker_alt = getattr(getattr(variant, 'marker', None), 'alt_alleles', '') or ''
        alt_allele = cv_alt or marker_alt
        status = _classify_carrier_status(user_gt or '', ref_allele or '', alt_allele)

        if status == 'unaffected':
            continue

        for gc in gene_conditions:
            disease = gc.get('disease', '')
            if not disease or disease in seen_conditions or disease.lower() == 'not provided':
                continue
            seen_conditions.add(disease)

            inheritance = 'autosomal_recessive'
            if 'dominant' in disease.lower():
                inheritance = 'autosomal_dominant'
            elif 'x-linked' in disease.lower():
                inheritance = 'x_linked'

            needs_counseling = 'pathogenic' in sig_lower and not ('benign' in sig_lower)
            carrier_results.append(CarrierStatus(
                analysis_id=ctx.analysis_id,
                condition=disease,
                carrier_status=status,
                inheritance_pattern=inheritance,
                associated_variants=[variant_rsid],
                genetic_counseling_recommended=needs_counseling
            ))

    # Prioritize counseling-recommended conditions
    carrier_results.sort(key=lambda c: (0 if c.genetic_counseling_recommended else 1, c.condition))

    for c in carrier_results:
        ctx.session.add(c)
    return len(carrier_results)
