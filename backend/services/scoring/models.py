"""Scoring value types and source weights (split out of scoring_engine.py)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple




# ---------------------------------------------------------------------------
# Source weights  — total should be ≈ 1.0 for normalization
# Higher weight = more trusted source for pathogenicity assessment
# ---------------------------------------------------------------------------
_SOURCE_WEIGHTS = {
    "clinvar":         0.30,   # Gold standard clinical curation
    "clinvar_local":   0.30,   # Same authority, local copy
    "cadd":            0.15,   # Computational deleteriousness
    "alpha_missense":  0.15,   # Deep learning missense prediction
    "gnomad_af":       0.10,   # Population frequency (rarity = more likely pathogenic)
    "sift":            0.05,   # Functional prediction
    "polyphen":        0.05,   # Functional prediction
    "conservation":    0.05,   # Evolutionary conservation
    "splice_ai":       0.05,   # Splice site impact
    "alphafold":       0.03,   # Structural confidence (low pLDDT = disordered)
    "litvar":          0.03,   # Literature evidence (well-studied variant)
    "gene_constraint":  0.05,  # Gene intolerance to LoF (pLI/LOEUF)
    "clinvar_gene_stats": 0.05, # Gene-level ClinVar pathogenic burden
    "chembl":          0.03,   # Druggability — known drug targets
    "fda_drug":        0.03,   # FDA drug interactions / CYP involvement
    "gnomad_tx":       0.05,   # LoF annotation + tissue expression
}


@dataclass
class SourceEvidence:
    """Evidence from a single annotation source."""
    source: str
    score: float           # 0.0 (benign) .. 1.0 (pathogenic)
    weight: float          # Source weight (from _SOURCE_WEIGHTS)
    label: str             # Human-readable interpretation
    raw_value: Any = None  # Original value for transparency


@dataclass
class ScoringResult:
    """Complete scoring result for a variant."""
    composite_score: float = 0.0
    confidence: str = "none"          # none, low, moderate, high
    evidence_count: int = 0
    classification: str = "uncertain" # benign, likely_benign, uncertain, likely_pathogenic, pathogenic
    sources: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    conflicts: List[str] = field(default_factory=list)
    total_weight: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "composite_score": round(self.composite_score, 4),
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "classification": self.classification,
            "sources": self.sources,
            "conflicts": self.conflicts,
            "total_weight": round(self.total_weight, 3),
        }
