"""
Generic map-driven insight generator used by most category generators.
"""
import asyncio
import logging
import re
from typing import Callable, Dict, Optional

from ....core.config import settings
from ....db.annotation_schemas import validate_associated_variants

from .alleles import (
    STRAND_COMPLEMENT, get_user_genotype, is_no_call_genotype,
    _get_effective_ref_allele, get_annotation_allele_parts,
    is_homozygous_reference, is_indel_genotype, indel_d_is_ref, _parse_alleles,
)
from .clinical import is_clinvar_benign, _get_all_clinvar_significances, should_skip_sex_linked
from .context import GeneratorContext
from .frequency import extract_frequency, extract_gene_and_consequence

logger = logging.getLogger(__name__)

_BENIGN_CLASSIFICATIONS = frozenset(('benign', 'likely_benign'))

# Hard population-frequency ceiling for the ClinVar-pathogenic AF-gate bypass.
# A ClinVar "pathogenic" label may override the per-category soft ceiling
# (max_population_af) only for genuinely uncommon alleles. A pathogenic
# rare-disease allele is by definition rare (Mendelian disease alleles are
# <1%); an allele carried by >10% of the population is the common/major allele,
# so a pathogenic classification on it is contradictory and must not surface as
# a personal risk finding. This is the minor-allele safeguard (R3): a risk
# allele must be uncommon, enforced by frequency rather than fragile ref/alt
# orientation.
_PATHOGENIC_AF_HARD_CAP = 0.10


def _should_exclude_benign(max_population_af, path_score) -> bool:
    """Benign-exclusion is a CLINICAL gate only. A benign-classified variant is
    not a health/carrier finding — but lifestyle panels (sports, methylation,
    nutrition, …; max_population_af=0.20) report traits that are benign by
    nature (ACTN3, MTHFR, …). Applying the filter there wrongly zeroes them, so
    gate on the clinical AF threshold (<=0.05) that already separates the two."""
    return bool(
        settings.analysis.exclude_benign_from_panels
        and max_population_af is not None and max_population_af <= 0.05
        and isinstance(path_score, dict)
        and path_score.get('classification') in _BENIGN_CLASSIFICATIONS
    )


async def generate_from_maps(
    ctx: GeneratorContext,
    *,
    rsid_map: Dict,
    gene_map: Dict,
    dedup_field: str,
    build_from_rsid: Callable,
    build_from_gene: Callable,
    filter_benign: bool = False,
    skip_benign_filter: bool = False,
    max_population_af: Optional[float] = None,
) -> int:
    """
    Generic loop shared by most category generators.

    Args:
        rsid_map / gene_map: lookup dicts from variant_registry.
        dedup_field: key inside the info dict used to avoid duplicates.
        build_from_rsid(analysis_id, rsid, genotype, info) -> model | None
        build_from_gene(analysis_id, rsid, gene, consequence, info) -> model | None
        filter_benign: deprecated — kept for backward compat.
        skip_benign_filter: deprecated — use max_population_af instead.
        max_population_af: population allele frequency ceiling. Variants
            above this threshold are skipped unless ClinVar explicitly
            classifies them as pathogenic.  Clinical panels use 0.05,
            lifestyle panels use 0.20.  None disables the gate.
    """
    items = []
    seen: set = set()

    for _idx, variant in enumerate(ctx.variants):
        if _idx > 0 and _idx % 200 == 0:
            await asyncio.sleep(0)
        rsid = getattr(variant, 'rsid', None)
        if not rsid:
            continue

        # Extract genotype, ref allele, and annotation data early
        # (used by both rsid and gene matching).
        genotype = get_user_genotype(variant)
        if is_no_call_genotype(genotype):
            continue
        annotation_result = ctx.annotation_results.get(rsid)
        effective_ref = _get_effective_ref_allele(variant, annotation_result)

        # Get alt allele for proper indel D/I code interpretation
        _, _alt_allele = get_annotation_allele_parts(annotation_result)

        # Skip homozygous reference — user doesn't carry any risk allele
        # at this position. Other variants in the same gene can still match.
        if effective_ref and is_homozygous_reference(genotype, effective_ref, alt_allele=_alt_allele):
            continue

        # Population frequency gate — skip common variants that are too
        # frequent to be clinically meaningful.  Variants with strong
        # ClinVar pathogenic evidence bypass this gate.
        if max_population_af is not None:
            _prof = ctx.variant_profiles.get(rsid)
            _var_freq = _prof.population_frequency if _prof else extract_frequency(annotation_result)
            if _var_freq is not None and _var_freq > max_population_af:
                _has_clinvar_path = False
                if annotation_result and annotation_result.annotation_data:
                    _cv_sigs = _get_all_clinvar_significances(
                        annotation_result.annotation_data.get('annotations', {})
                    )
                    _has_clinvar_path = any(
                        'pathogenic' in s.lower() for s in _cv_sigs
                    )
                # ClinVar-pathogenic bypasses the soft ceiling only up to the
                # hard rarity cap; a common allele is suppressed regardless of
                # its ClinVar label (see _PATHOGENIC_AF_HARD_CAP).
                if not _has_clinvar_path or _var_freq > _PATHOGENIC_AF_HARD_CAP:
                    continue

        # rsid-based matching
        if rsid in rsid_map:
            # Defence-in-depth: skip variants where ALL annotation sources
            # agree the variant is benign. This catches both auto-categorized
            # mappings that slipped through (e.g. "Conflicting" matched as
            # "Pathogenic") and manually-seeded mappings for variants that
            # ClinVar has since reclassified as benign.
            if is_clinvar_benign(annotation_result):
                continue

            info = rsid_map[rsid]

            # Sex-linked condition filtering
            _chromosome = getattr(variant, 'chromosome', None)
            _condition_name = info.get('condition', info.get('trait', info.get('drug', '')))
            if should_skip_sex_linked(rsid, _condition_name, info.get('gene'), _chromosome, ctx.inferred_sex):
                continue

            # Allele verification — confirm the user's genotype actually carries
            # the alternate (risk) allele from annotation data.  Both SNPs and
            # consumer-array indel codes (D/I) are now verified.
            if genotype and not is_indel_genotype(genotype):
                _, ann_alt = get_annotation_allele_parts(annotation_result)
                # FIX-02: skip when annotation data lacks allele information.
                # We cannot verify the user carries the risk allele vs reference,
                # so omit rather than risk a false positive.
                # (A prior info.get('risk_allele') fallback was removed — no
                # variant_mappings row has ever populated risk_allele, so it was
                # dead code; populating a real allele column is deferred — see U5.)
                if ann_alt is None:
                    logger.debug(
                        "rsid %s: no allele data for SNP verification — skipping", rsid
                    )
                    continue
                # ann_alt may be a comma-separated list for multi-allelic sites
                # (e.g. "A,T" for REF/A,T). Extract all single-base alts and
                # check whether the user carries ANY of them.
                gt_upper = genotype.upper()
                alleles = set(gt_upper.replace('/', '').replace('|', ''))
                alleles_flipped = {a.translate(STRAND_COMPLEMENT) for a in alleles}
                ann_alts = [a.strip() for a in ann_alt.split(',') if a.strip()]
                snp_alts = [a for a in ann_alts if len(a) == 1]
                if snp_alts:
                    carries = any(a in alleles or a in alleles_flipped for a in snp_alts)
                    if not carries:
                        continue
                # If no single-base alt was extracted, fall through without allele
                # filtering (multi-base alt or structural variant — handled elsewhere).
            elif genotype and is_indel_genotype(genotype):
                # FIX-01: Verify consumer D/I indel codes against annotation allele
                # lengths.  D = shorter allele, I = longer allele.  indel_d_is_ref()
                # returns True when D maps to the reference (insertion variant), False
                # when D maps to the alternate (deletion variant), None when unknown.
                _ind_ref, _ind_alt = get_annotation_allele_parts(annotation_result)
                _d_is_ref = indel_d_is_ref(_ind_ref, _ind_alt)
                if _d_is_ref is not None:
                    # The risk (alternate) allele code
                    _risk_code = 'I' if _d_is_ref else 'D'
                    _user_codes = _parse_alleles(genotype) or []
                    if _risk_code not in _user_codes:
                        continue  # User carries only the reference indel allele
                elif genotype.strip().upper() in ('II', 'DD'):
                    # BUG-15: No allele data to determine insertion/deletion direction.
                    # For homozygous indel codes, we cannot confirm whether the user
                    # carries the risk (alternate) allele or the reference allele —
                    # either code can be hom-ref or hom-alt depending on the variant.
                    # Skip to avoid false positives (e.g. rs61749708 "II" = hom-ref).
                    # Heterozygous DI/ID is preserved since one allele is the insertion
                    # and one is the deletion, so the user plausibly carries the risk one.
                    logger.debug(
                        "rsid %s: homozygous indel %s with no allele-direction data — "
                        "skipping to prevent false positive (BUG-15)",
                        rsid, genotype,
                    )
                    continue
            key = info[dedup_field]
            if key not in seen:
                seen.add(key)
                # BUG-13: pass path_score so non-health generators can call
                # boost_if_pathogenic() before zygosity_adjust().
                _prof = ctx.variant_profiles.get(rsid)
                _path_score = (
                    _prof.pathogenicity_score if _prof
                    else (
                        annotation_result.annotation_data.get('pathogenicity_score')
                        if annotation_result and annotation_result.annotation_data else None
                    )
                )
                info_with_ref = {**info, '_ref_allele': effective_ref, '_pathogenicity_score': _path_score}
                # Skip "Unknown variant" entries unless the composite pathogenicity
                # score or ClinVar confirms meaningful evidence. Auto-categorization
                # produces these when no condition name could be resolved (BUG-06).
                _condition = info.get('condition', '')
                if _condition.lower() in ('unknown variant', 'unknown') and not (
                    isinstance(_path_score, dict) and _path_score.get('composite_score', 0) >= 0.60
                ):
                    logger.debug("rsid %s: skipping 'Unknown variant' mapping with no pathogenicity evidence", rsid)
                    continue
                # Skip generic "Gene Name variant" conditions that have no ClinVar
                # clinical significance. These are auto-generated fallback names
                # (e.g. "UBR4 variant") created when no real disease association
                # exists — usually caused by AlphaMissense coordinate mismatches
                # with MODIFIER/intergenic VEP consequences. Require either:
                #   a) non-empty clinical_significance from ClinVar, OR
                #   b) strong composite pathogenicity score (≥ 0.75)
                _is_generic_variant_condition = (
                    bool(re.search(r'\bvariant\s*$', _condition, re.IGNORECASE))
                    and _condition.lower() not in ('unknown variant',)
                    and not info.get('clinical_significance', '').strip()
                )
                if _is_generic_variant_condition and not (
                    isinstance(_path_score, dict) and _path_score.get('composite_score', 0) >= 0.75
                    and _path_score.get('evidence_count', 0) >= 2
                ):
                    logger.debug(
                        "rsid %s: skipping generic '%s' — no ClinVar significance and insufficient multi-source evidence",
                        rsid, _condition,
                    )
                    continue
                # Filter benign/likely_benign variants — applies to all panels.
                # Lifestyle panels with max_population_af already filter common
                # variants above, so this catches remaining benign-classified ones.
                if _should_exclude_benign(max_population_af, _path_score):
                    continue
                # RC-7: When no scoring data exists and no ClinVar evidence,
                # skip for clinical panels (health/carrier/drug) to prevent
                # unscored variants from appearing as health risks.
                if (not skip_benign_filter
                        and max_population_af is not None and max_population_af <= 0.05
                        and not isinstance(_path_score, dict)):
                    if not info.get('clinical_significance', '').strip():
                        continue
                item = build_from_rsid(ctx.analysis_id, rsid, genotype or '', info_with_ref)
                if item:
                    items.append(item)

        # Gene-based matching from annotations — require a non-benign
        # consequence to avoid generating insights for synonymous or
        # intergenic variants that happen to sit in a known gene.
        gene, consequence, impact = extract_gene_and_consequence(
            annotation_result, ctx.rsid_gene_map
        )
        if gene and gene in gene_map:
            # P1-8: Skip gene matches where all annotation sources agree benign
            if is_clinvar_benign(annotation_result):
                continue

            # Filter: only moderate/high impact consequences qualify.
            # When consequence data is unavailable (gene came from ClinVar
            # rsid→gene map only), check ClinVar significance as a proxy
            # — a known pathogenic variant in a mapped gene should not be
            # silently dropped just because VEP data is missing.
            if impact and impact.lower() in ('high', 'moderate'):
                pass  # Qualifies
            elif consequence and consequence in (
                'missense_variant', 'stop_gained', 'frameshift_variant',
                'splice_acceptor_variant', 'splice_donor_variant',
                'stop_lost', 'start_lost', 'inframe_insertion',
                'inframe_deletion', 'protein_altering_variant',
            ):
                pass  # Qualifies by consequence type
            elif consequence is None and impact is None:
                # No VEP data — check ClinVar significance as fallback.
                # RC-6: Require rsid-specific ClinVar evidence, not just
                # gene-level. A pathogenic variant at position X doesn't
                # imply pathogenicity for an intron variant at position Y.
                _cv_qualifies = False
                if annotation_result and annotation_result.annotation_data:
                    cv_local = annotation_result.annotation_data.get('annotations', {}).get('clinvar_local', {})
                    if cv_local and cv_local.get('found'):
                        sigs = cv_local.get('clinical_significances', [])
                        sig_str = ' '.join(s.lower() for s in sigs)
                        has_path_sig = any(kw in sig_str for kw in ('pathogenic', 'drug_response'))
                        # Require the ClinVar record to match this specific rsid
                        cv_rsid = cv_local.get('rsid') or cv_local.get('rs_id') or ''
                        is_rsid_specific = str(cv_rsid) == str(rsid) or str(cv_rsid) == rsid.lstrip('rs')
                        if has_path_sig and is_rsid_specific:
                            _cv_qualifies = True
                if not _cv_qualifies:
                    continue
            else:
                continue  # Skip benign/low-impact variants

            info = gene_map[gene]
            key = info[dedup_field]
            if key not in seen:
                seen.add(key)
                # Pass genotype, ref allele, and pathogenicity score (BUG-13)
                _prof = ctx.variant_profiles.get(rsid)
                _path_score = (
                    _prof.pathogenicity_score if _prof
                    else (
                        annotation_result.annotation_data.get('pathogenicity_score')
                        if annotation_result and annotation_result.annotation_data else None
                    )
                )
                info_with_gt = {**info, '_ref_allele': effective_ref, '_genotype': genotype or '', '_pathogenicity_score': _path_score}
                if _should_exclude_benign(max_population_af, _path_score):
                    continue
                item = build_from_gene(ctx.analysis_id, rsid, gene, consequence, info_with_gt)
                if item:
                    items.append(item)

    for item in items:
        validate_associated_variants(type(item).__name__, getattr(item, 'associated_variants', None))
        ctx.session.add(item)
    return len(items)
