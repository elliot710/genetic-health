"""Real-time categorization: orchestrates evidence + scoring into a CategorySuggestion.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from backend.services.categorizer.models import *  # noqa: F401,F403
from backend.services.categorizer.evidence import extract_evidence
from backend.services.categorizer.scoring import (
    _category_aware_label,
    _category_extra_fields,
    _is_severe,
    _risk_from_evidence,
    _compute_confidence,
)


def categorize_variant(
    rsid: str,
    annotations: Dict[str, Any],
    gene_hint: Optional[str] = None,
    condition_hints: Optional[Dict[str, Any]] = None,
) -> List[CategorySuggestion]:
    """Analyze annotation data and return category suggestions.

    Args:
        rsid: Variant rsid.
        annotations: Merged annotation dict from all sources.
        gene_hint: Optional gene symbol from rsid→gene map.
        condition_hints: Optional pre-loaded enrichment data with keys:
            - gene_conditions: Dict[str, List[str]] — gene → disease names
              from clinvar_gene_conditions table
            - gene_descriptions: Dict[str, str] — gene → Ensembl description

    Returns a list of CategorySuggestion objects sorted by confidence,
    one per applicable category.
    """
    evidence_list = extract_evidence(annotations)
    if not evidence_list:
        return []

    # Collect gene from any source
    gene = gene_hint
    for ev in evidence_list:
        if ev.gene and not gene:
            gene = ev.gene
            break

    # Collect all conditions
    all_conditions: List[str] = []
    for ev in evidence_list:
        all_conditions.extend(ev.conditions)
    # Deduplicate preserving order
    seen: Set[str] = set()
    conditions: List[str] = []
    for c in all_conditions:
        cl = c.lower().strip()
        if cl and cl not in seen:
            seen.add(cl)
            conditions.append(c)

    # Collect all clinical significances
    all_sigs: List[str] = []
    for ev in evidence_list:
        all_sigs.extend(ev.clinical_significances)
    sig_set = set(s.lower() for s in all_sigs)

    # Get consequence from Ensembl VEP
    consequence = None
    impact = None
    for ev in evidence_list:
        if ev.consequence:
            consequence = ev.consequence
            impact = ev.impact
            break

    # Source names
    source_names = [ev.source_name for ev in evidence_list]

    suggestions: List[CategorySuggestion] = []

    # ── Determine applicable categories ─────────────────────────────

    applicable_categories: Set[str] = set()

    # 1. Gene-based assignment (highest specificity)
    if gene and gene.upper() in GENE_CATEGORY_MAP:
        applicable_categories.update(GENE_CATEGORY_MAP[gene.upper()])

    # 2. ClinVar significance-based
    has_pathogenic = bool(sig_set & _PATHOGENIC_SIGS)
    has_drug_response = bool(sig_set & _DRUG_SIGS)
    has_benign = bool(sig_set & _BENIGN_SIGS) and not has_pathogenic
    has_risk = bool(sig_set & _RISK_SIGS)

    if has_pathogenic or has_risk:
        applicable_categories.add("health")
    if has_drug_response:
        applicable_categories.add("drug")

    # 3. Condition keyword-based
    for cat, keywords in _CONDITION_CATEGORY_KW.items():
        for cond in conditions:
            cond_lower = cond.lower()
            if any(kw in cond_lower for kw in keywords):
                applicable_categories.add(cat)
                break

    # 4. Rare / uncommon based on allele frequency.
    # Require MODERATE or HIGH VEP impact to exclude MODIFIER intron/intergenic noise.
    # Also require at least one piece of clinical evidence (ClinVar sig OR MODERATE impact)
    # so we don't populate these panels with generic frequency-only entries.
    afs = [ev.allele_frequency for ev in evidence_list if ev.allele_frequency is not None]
    min_af = min(afs) if afs else None
    _MODIFIER_IMPACTS = frozenset(('modifier', 'low'))
    _MODIFIER_CONSEQUENCES = frozenset((
        'intron_variant', 'intergenic_variant', 'upstream_gene_variant',
        'downstream_gene_variant', 'synonymous_variant', '3_prime_utr_variant',
        '5_prime_utr_variant', 'non_coding_transcript_exon_variant',
        'regulatory_region_variant', 'TF_binding_site_variant',
    ))
    _af_impact_ok = (
        impact and impact.upper() not in ('MODIFIER', 'LOW')
        and (not consequence or consequence not in _MODIFIER_CONSEQUENCES)
    )
    # Clinical evidence = ClinVar has any significance OR VEP says MODERATE/HIGH
    _af_has_evidence = bool(sig_set) or (impact and impact.upper() in ('HIGH', 'MODERATE'))
    if min_af is not None and _af_impact_ok and _af_has_evidence:
        if min_af < 0.001:
            applicable_categories.add("rare")
        elif min_af < 0.05:
            applicable_categories.add("uncommon")

    # 5. High-impact variants go to health if not already assigned
    if impact == "HIGH" and "health" not in applicable_categories:
        applicable_categories.add("health")

    # If nothing matched, and we have pathogenicity evidence, default to health.
    # GUARD: only apply for coding variants with MODERATE or HIGH VEP impact AND
    # at least one non-AlphaMissense source. AlphaMissense alone is insufficient
    # because it sometimes assigns high scores to positions that Ensembl VEP
    # classifies as intergenic/MODIFIER (genome build or annotation version
    # mismatch), producing false-positive health flags with no disease name.
    _NON_CODING_IMPACTS = frozenset(('modifier', 'low'))
    _REQUIRES_CLINVAR_SIGS = frozenset(('intergenic_variant', 'upstream_gene_variant',
                                        'downstream_gene_variant', 'non_coding_transcript_exon_variant',
                                        'intron_variant', 'synonymous_variant',
                                        '3_prime_utr_variant', '5_prime_utr_variant'))
    if not applicable_categories:
        path_scores = [ev.pathogenicity_score for ev in evidence_list
                       if ev.pathogenicity_score is not None]
        _impact_ok = impact and impact.lower() not in _NON_CODING_IMPACTS
        _consequence_ok = not consequence or consequence not in _REQUIRES_CLINVAR_SIGS
        _has_clinvar = bool(sig_set)  # any ClinVar significance data
        # Require ClinVar evidence OR HIGH (not just MODERATE) VEP impact.
        # Previously _multi_source (any non-AM source) was accepted — this was too
        # weak because gnomAD is always present, so AM + gnomAD would falsely
        # trigger health categorisation with no disease name.
        _clinvar_or_high_impact = _has_clinvar or impact == "HIGH"
        if path_scores and max(path_scores) >= 0.5 and _impact_ok and _consequence_ok and _clinvar_or_high_impact:
            applicable_categories.add("health")

    # If still nothing, skip
    if not applicable_categories:
        return []

    # Only benign? Skip health but still allow carrier/drug/lifestyle
    if has_benign and not has_pathogenic:
        applicable_categories.discard("health")
        applicable_categories.discard("rare")

    # ── Build suggestions per category ──────────────────────────────
    # Condition label resolution — multi-source fallback chain:
    #   1. ClinVar variant-level conditions (from annotation evidence)
    #   2. clinvar_gene_conditions table (gene↔disease associations)
    #   3. Ensembl gene description (functional description)
    #   4. Fallback: "{gene} variant"
    condition_label = None
    if conditions:
        condition_label = conditions[0]
    if not condition_label and gene and condition_hints:
        # Try gene→condition from clinvar_gene_conditions
        gene_conds = (condition_hints.get("gene_conditions") or {}).get(gene)
        if gene_conds:
            # Pick the shortest non-severe condition for lifestyle; first for health
            condition_label = gene_conds[0]
        # Try Ensembl gene description
        if not condition_label:
            gene_desc = (condition_hints.get("gene_descriptions") or {}).get(gene)
            if gene_desc:
                # Clean up Ensembl description: Title Case, remove "[Source:...]"
                clean_desc = gene_desc.split("[")[0].strip()
                if clean_desc:
                    condition_label = f"{clean_desc.title()} variant"
    if not condition_label:
        condition_label = f"{gene} variant" if gene else "Unknown variant"
    clinical_sig_str = ", ".join(sorted(sig_set)) if sig_set else None

    for category in applicable_categories:
        # Severity filter for lifestyle panels
        if category in _LIFESTYLE_CATEGORIES and _is_severe(condition_label):
            continue

        risk_mult = _risk_from_evidence(evidence_list)
        conf = _compute_confidence(evidence_list, category)

        # Build the data dict for this category
        data: Dict[str, Any] = {
            "condition": condition_label,
            "gene": gene or "",
            "clinical_significance": clinical_sig_str or "",
            "risk_multiplier": risk_mult,
            "source": ", ".join(source_names),
        }

        # Populate category-specific fields
        primary = _PRIMARY_FIELD.get(category, "condition")
        data.setdefault(primary, condition_label)
        for f in ("condition", "trait", "domain", "metric", "nutrient", "category", "drug"):
            if f != primary:
                fallback = _category_aware_label(gene, category, f) if gene else condition_label
                data.setdefault(f, fallback)

        # Add pathogenicity details
        path_scores = [e.pathogenicity_score for e in evidence_list
                       if e.pathogenicity_score is not None]
        if path_scores:
            data["avg_pathogenicity"] = round(sum(path_scores) / len(path_scores), 3)
        if consequence:
            data["consequence"] = consequence
        if impact:
            data["impact"] = impact

        # Add category-specific fields that insight generators require
        extras = _category_extra_fields(category, data, conf)
        for k, v in extras.items():
            data.setdefault(k, v)

        suggestions.append(CategorySuggestion(
            category=category,
            confidence=conf,
            sources=source_names,
            condition=condition_label,
            gene=gene,
            risk_multiplier=risk_mult,
            clinical_significance=clinical_sig_str,
            data=data,
        ))

    # Sort by confidence descending
    suggestions.sort(key=lambda s: s.confidence, reverse=True)
    return suggestions
