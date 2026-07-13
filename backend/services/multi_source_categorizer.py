"""Re-export shim: multi_source_categorizer.py was split into the categorizer/
package. Kept so existing `from backend.services.multi_source_categorizer import X`
imports, `import ... as msc` module access, and test monkeypatches keep resolving.
"""

from backend.services.categorizer import (
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
    extract_evidence,
    _conf_to_level,
    _category_aware_label,
    _category_extra_fields,
    _is_severe,
    _risk_from_evidence,
    _compute_confidence,
    categorize_variant,
    init_categorizer_data,
    load_condition_hints,
    enrich_generic_mappings,
)  # noqa: F401
