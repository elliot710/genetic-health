"""Categorizer domain data and value types.

Constants, the mutable startup-loaded maps/sets, and the SourceEvidence/
CategorySuggestion dataclasses. The mutable globals here are populated in-place
at startup by categorizer.loaders.init_categorizer_data and shared by reference
across the package, so they must stay defined in exactly one module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


__all__ = [
    "GENE_CATEGORY_MAP",
    "_CONDITION_CATEGORY_KW",
    "_SEVERE_EXCLUSION_KW",
    "_LIFESTYLE_CATEGORIES",
    "_PATHOGENIC_SIGS",
    "_RISK_SIGS",
    "_DRUG_SIGS",
    "_BENIGN_SIGS",
    "_PRIMARY_FIELD",
    "_CATEGORY_FIELD_SUFFIX",
    "SourceEvidence",
    "CategorySuggestion",
]

# ── Gene → category map ─────────────────────────────────────────────
# Populated at startup from CategoryRule rows where rule_type='gene_list'.
# Keys are UPPER-CASE gene symbols; values are lists of category strings.
# Do NOT add entries here — add a migration that inserts a CategoryRule row.
GENE_CATEGORY_MAP: Dict[str, List[str]] = {}

# ── Condition keyword → category routing ───────────────────────────
# Populated from CategoryRule rows where rule_type='clinvar_condition_keyword'.
# Keys are category strings; values are lists of lowercase keyword strings.
_CONDITION_CATEGORY_KW: Dict[str, List[str]] = {}

# ── Severe-condition exclusion keywords for lifestyle panels ────────
# Populated from CategoryRule rows where rule_type='lifestyle_exclude_keyword'.
# When a condition label contains any of these keywords, lifestyle categories
# (sports, physical, nutrition, etc.) are skipped to avoid false positives.
_SEVERE_EXCLUSION_KW: Set[str] = set()

_LIFESTYLE_CATEGORIES = frozenset([
    "sports", "physical", "personality", "nutrition", "wellness",
    "methylation", "detox", "cognitive", "ancestry",
])

# ClinVar significances considered clinically meaningful (logic constants — stay in code)
_PATHOGENIC_SIGS = {"pathogenic", "likely pathogenic", "likely_pathogenic",
                    "pathogenic/likely_pathogenic", "pathogenic/likely pathogenic"}
_RISK_SIGS = {"risk_factor", "risk factor", "association", "protective"}
_DRUG_SIGS = {"drug_response", "drug response"}
_BENIGN_SIGS = {"benign", "likely benign", "likely_benign",
                "benign/likely_benign", "benign/likely benign"}

# ── Primary dedup field per category (structural config — stays in code) ──
_PRIMARY_FIELD = {
    "health": "condition", "carrier": "condition",
    "drug": "drug", "nutrition": "nutrient",
    "sports": "category", "wellness": "metric",
    "cognitive": "domain", "personality": "trait",
    "physical": "trait", "methylation": "gene",
    "detox": "gene", "rare": "condition", "uncommon": "condition",
}


# ── Category-aware label helpers ────────────────────────────────────

# Maps category → semantic suffix for non-primary fields when we only
# have a gene name (i.e. no ClinVar condition).  These produce labels
# like "CYP2D6 metabolism" instead of "CYP2D6 variant" as a nutrient.
_CATEGORY_FIELD_SUFFIX: Dict[str, Dict[str, str]] = {
    "nutrition":    {"nutrient": "{gene} metabolism",     "trait": "{gene}-related nutrition"},
    "sports":       {"category": "{gene}-related fitness",  "trait": "{gene} performance factor"},
    "wellness":     {"metric": "{gene} wellness factor",    "trait": "{gene}-related wellness"},
    "cognitive":    {"domain": "{gene}-related cognition",  "trait": "{gene} cognitive factor"},
    "personality":  {"trait": "{gene} behavioral factor",   "domain": "{gene}-related behavior"},
    "physical":     {"trait": "{gene}-related trait",       "domain": "{gene} physical factor"},
    "methylation":  {"nutrient": "{gene} methylation",      "trait": "{gene} methylation capacity"},
    "detox":        {"nutrient": "{gene} detoxification",   "trait": "{gene} detox capacity"},
    "drug":         {"drug": "{gene}-related drug response"},
    "health":       {},
    "carrier":      {},
    "rare":         {},
    "uncommon":     {},
}


@dataclass
class SourceEvidence:
    """Evidence collected from a single annotation source."""
    source_name: str
    gene: Optional[str] = None
    conditions: List[str] = field(default_factory=list)
    clinical_significances: List[str] = field(default_factory=list)
    consequence: Optional[str] = None
    pathogenicity_score: Optional[float] = None  # 0.0-1.0
    sift_score: Optional[float] = None
    polyphen_score: Optional[float] = None
    allele_frequency: Optional[float] = None
    review_status: Optional[str] = None
    impact: Optional[str] = None  # HIGH, MODERATE, LOW, MODIFIER
    gene_description: Optional[str] = None  # From ensembl_genes or similar


@dataclass
class CategorySuggestion:
    """A suggested category assignment with confidence and sources."""
    category: str
    confidence: float  # 0.0-1.0
    sources: List[str]
    condition: str
    gene: Optional[str]
    risk_multiplier: float
    clinical_significance: Optional[str]
    data: Dict[str, Any]  # Full mapping data dict
