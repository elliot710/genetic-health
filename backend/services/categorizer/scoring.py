"""Scoring and labelling helpers (confidence, risk, severity, field labels).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from backend.services.categorizer.models import *  # noqa: F401,F403


def _conf_to_level(conf: float) -> str:
    """Convert a 0.0-1.0 confidence float to a string severity level."""
    if conf >= 0.7:
        return "high"
    if conf >= 0.4:
        return "moderate"
    return "low"


def _category_aware_label(gene: str, category: str, field_name: str) -> str:
    """Produce a semantically appropriate label for a non-primary field.

    Instead of using "{gene} variant" for every field (which produces
    nonsensical results like nutrient="MTHFR variant"), this picks a
    label that makes sense for the field's category context.
    """
    templates = _CATEGORY_FIELD_SUFFIX.get(category, {})
    template = templates.get(field_name)
    if template:
        return template.format(gene=gene)
    return f"{gene} variant"


def _category_extra_fields(category: str, data: Dict[str, Any], conf: float) -> Dict[str, Any]:
    """Return category-specific fields that insight generators expect.

    Each generator accesses specific keys from the mapping data dict.
    This function ensures enrichment-generated mappings contain those keys
    with sensible defaults derived from the available evidence.
    """
    level = _conf_to_level(conf)
    gene = data.get("gene", "")
    condition = data.get("condition", "Unknown variant")

    if category == "drug":
        drug_name = data.get("drug", condition)
        return {
            "drugs": [drug_name],  # rsid-map format: list of drug name strings
        }
    if category == "physical":
        return {
            "result": "Variant detected",
            "confidence": level,
            "description": f"Genetic variant in {gene} linked to {data.get('trait', 'physical trait')}",
        }
    if category == "nutrition":
        nutrient = data.get("nutrient", "nutrient metabolism")
        # Avoid echoing "XXX variant" in recommendations
        rec_subject = data.get("gene", nutrient) if nutrient.endswith("variant") else nutrient
        return {
            "sensitivity": level,
            "metabolism": "variable",
            "recommendations": f"Consult a nutritionist regarding {rec_subject} nutrient metabolism",
        }
    if category == "sports":
        return {
            "advantage": level,
            "recommendations": f"Genetic factor in {data.get('category', 'athletic performance')}",
            "advice": "Consider personalized training approaches based on genetic profile",
        }
    if category == "cognitive":
        return {
            "score": str(round(conf * 100)),
            "percentile": min(99, max(1, int(conf * 80 + 10))),
            "suggestions": f"Variant associated with {data.get('domain', 'cognitive function')}",
        }
    if category == "personality":
        return {
            "tendency": level,
            "confidence": level,
            "insights": f"Genetic association with {data.get('trait', 'behavioral trait')}",
        }
    if category == "wellness":
        return {
            "predisposition": level,
            "score": str(round(conf * 100)),
            "recommendations": f"Monitor and optimize {data.get('metric', 'health metric')}",
        }
    if category == "methylation":
        return {
            "capacity": level,
            "supplements": f"Consider supporting {gene or 'methylation'} pathway",
        }
    if category == "detox":
        return {
            "phase": "Phase I/II",
            "capacity": level,
            "sensitivity": level,
            "recommendations": f"Support {gene or 'detoxification'} function",
        }
    return {}


def _is_severe(condition: str) -> bool:
    """Return True if condition describes a severe medical condition."""
    lower = condition.lower()
    return any(kw in lower for kw in _SEVERE_EXCLUSION_KW)


def _risk_from_evidence(evidence_list: List[SourceEvidence]) -> float:
    """Compute risk_multiplier from multi-source evidence."""
    path_scores = [e.pathogenicity_score for e in evidence_list
                   if e.pathogenicity_score is not None]
    if not path_scores:
        return 1.1

    avg_path = sum(path_scores) / len(path_scores)
    # Scale: 0.0-0.3 → 1.0, 0.3-0.5 → 1.1, 0.5-0.7 → 1.2, 0.7-0.85 → 1.5, 0.85-1.0 → 2.0
    if avg_path >= 0.85:
        base = 2.0
    elif avg_path >= 0.7:
        base = 1.5
    elif avg_path >= 0.5:
        base = 1.2
    elif avg_path >= 0.3:
        base = 1.1
    else:
        base = 1.0

    # Bonus for multi-source confirmation (up to +0.5)
    n_confirming = len([s for s in path_scores if s >= 0.5])
    bonus = min(n_confirming * 0.15, 0.5)
    return round(min(base + bonus, 3.0), 2)


def _compute_confidence(evidence_list: List[SourceEvidence], category: str) -> float:
    """Compute confidence score (0.0-1.0) based on number & agreement of sources."""
    if not evidence_list:
        return 0.0

    source_count = len(evidence_list)
    # Base confidence from source count: 1 source=0.3, 2=0.5, 3=0.65, 4+=0.75
    base = min(0.15 + source_count * 0.15, 0.75)

    # Bonus from pathogenicity agreement
    path_scores = [e.pathogenicity_score for e in evidence_list
                   if e.pathogenicity_score is not None]
    if len(path_scores) >= 2:
        # All agree on direction?
        all_high = all(s >= 0.5 for s in path_scores)
        all_low = all(s < 0.3 for s in path_scores)
        if all_high or all_low:
            base += 0.15  # Strong agreement bonus

    # Bonus for gene-category match
    genes = [e.gene for e in evidence_list if e.gene]
    if genes:
        gene = genes[0].upper()
        if gene in GENE_CATEGORY_MAP and category in GENE_CATEGORY_MAP[gene]:
            base += 0.1

    return round(min(base, 1.0), 2)
