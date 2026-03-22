"""Carrier status insight generator."""
import logging
from ...db.models import CarrierStatus
from .base import (
    GeneratorContext, get_user_genotype, get_ref_allele,
    is_homozygous_reference, is_heterozygous, is_no_call_genotype,
    is_indel_genotype, _parse_alleles, indel_d_is_ref,
    get_annotation_allele_parts,
)

logger = logging.getLogger(__name__)


def _classify_carrier_status(user_gt: str, ref_allele: str, alt_allele: str) -> str:
    """Determine carrier status from genotype + known ref/alt alleles.

    Returns 'affected' (homozygous alt), 'carrier' (heterozygous), or
    'unaffected' (homozygous ref / no alt match).
    """
    if is_no_call_genotype(user_gt):
        return 'unaffected'
    # Consumer array indel codes: D=shorter allele, I=longer allele.
    # Whether D maps to ref or alt depends on the variant type.
    if is_indel_genotype(user_gt):
        gt = user_gt.strip().upper()
        if gt in ('DI', 'ID'):
            return 'carrier'  # heterozygous regardless of mapping
        d_ref = indel_d_is_ref(ref_allele, alt_allele)
        if d_ref is True:
            # Insertion variant (ref shorter): D=ref, I=alt
            return 'unaffected' if gt == 'DD' else 'affected'  # II=affected
        elif d_ref is False:
            # Deletion variant (ref longer): I=ref, D=alt
            return 'affected' if gt == 'DD' else 'unaffected'  # II=unaffected
        else:
            # Can't determine allele mapping — be conservative
            return 'carrier'

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
    seen_gene_variants: set = set()  # (rsid, gene) pairs — one entry per gene per variant

    for variant in ctx.variants:
        variant_rsid = getattr(variant, 'rsid', None)
        if not variant_rsid:
            continue

        # Skip no-call and homozygous-reference genotypes — user doesn't carry
        # the alternate allele at this position.
        user_gt = get_user_genotype(variant)
        if is_no_call_genotype(user_gt):
            continue
        # BUG-09: prefer profile.effective_ref (annotation-resolved) over
        # get_ref_allele which reads raw marker.ref_allele and may be None/N
        profile = ctx.variant_profiles.get(variant_rsid)
        annotation_result = ctx.annotation_results.get(variant_rsid)
        if profile:
            ref_allele = profile.effective_ref
        else:
            ref_allele = get_ref_allele(variant)

        # Get full ref/alt alleles (including "-" for indels) for D/I interpretation
        ann_ref, ann_alt = get_annotation_allele_parts(annotation_result)
        if is_homozygous_reference(user_gt, ref_allele, alt_allele=ann_alt):
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
                # For indels, prefer annotation-derived alt over marker
                effective_alt = ann_alt or marker_alt
                actual_status = _classify_carrier_status(
                    user_gt or '', ann_ref or ref_allele or '', effective_alt
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

        # Determine carrier status using ref/alt alleles from annotations or ClinVar/marker
        cv_alt = cv_local.get('alt_allele') or cv_local.get('alternate_allele') or ''
        marker_alt = getattr(getattr(variant, 'marker', None), 'alt_alleles', '') or ''
        effective_alt = ann_alt or cv_alt or marker_alt
        status = _classify_carrier_status(
            user_gt or '', ann_ref or ref_allele or '', effective_alt
        )

        if status == 'unaffected':
            continue

        # Deduplicate at gene+variant level: one carrier entry per (rsid, gene) pair.
        # This prevents disease-subtype explosion where a single rsid maps to many
        # ClinVar disease names (e.g. APOE rs405509 → multiple Alzheimer subtypes).
        # _classify_carrier_status() already verified the user carries the alt allele.
        gene_name = (cv_local.get('genes') or [''])[0]
        gv_key = (variant_rsid, gene_name or variant_rsid)
        if gv_key in seen_gene_variants:
            continue
        seen_gene_variants.add(gv_key)

        # Take the first meaningful disease name for this gene+variant combination
        diseases = [
            gc.get('disease', '') for gc in gene_conditions
            if gc.get('disease') and
            gc.get('disease', '').lower() not in ('not provided', 'not specified')
        ]
        disease = diseases[0] if diseases else gene_name
        if not disease or disease in seen_conditions:
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
