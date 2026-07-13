"""Multi-source variant categorizer package (split from the former
multi_source_categorizer.py module). Re-exports the full public + internal
surface so existing imports keep resolving.
"""

from .models import (
    GENE_CATEGORY_MAP,
    _CONDITION_CATEGORY_KW,
    _SEVERE_EXCLUSION_KW,
    _LIFESTYLE_CATEGORIES,
    _PATHOGENIC_SIGS,
    _RISK_SIGS,
    _DRUG_SIGS,
    _BENIGN_SIGS,
    _PRIMARY_FIELD,
    _CATEGORY_FIELD_SUFFIX,
    SourceEvidence,
    CategorySuggestion,
)
from .evidence import extract_evidence
from .scoring import (
    _conf_to_level,
    _category_aware_label,
    _category_extra_fields,
    _is_severe,
    _risk_from_evidence,
    _compute_confidence,
)
from .engine import categorize_variant
from .loaders import (
    init_categorizer_data,
    load_condition_hints,
    enrich_generic_mappings,
)

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
    "extract_evidence",
    "_conf_to_level",
    "_category_aware_label",
    "_category_extra_fields",
    "_is_severe",
    "_risk_from_evidence",
    "_compute_confidence",
    "categorize_variant",
    "init_categorizer_data",
    "load_condition_hints",
    "enrich_generic_mappings",
]
