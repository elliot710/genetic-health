"""
Variant profile and shared generator context dataclasses.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession

from ....db.models import AnalysisVariant


# ---------------------------------------------------------------------------
# Variant profile — pre-computed per-variant enrichment
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class VariantProfile:
    """Pre-computed per-variant data extracted ONCE and shared by all generators.

    This is the single source of truth for variant-level attributes during
    insight generation.  Generators should read from profiles rather than
    re-extracting from raw annotation JSON — ensuring consistent ref allele
    resolution, frequency handling, and zygosity classification everywhere.
    """
    rsid: str
    genotype: Optional[str]
    effective_ref: Optional[str]
    gene: Optional[str]
    consequence: Optional[str]
    impact: Optional[str]
    chromosome: Optional[str]
    # None = no frequency data available.  0.0 = monomorphic (not the same!).
    population_frequency: Optional[float]
    clinical_significance: Optional[str]   # First ClinVar sig, lowercased
    is_benign: bool
    is_hom_ref: bool
    is_het: bool
    is_no_call: bool
    composite_score: float
    pathogenicity_score: Optional[dict]
    annotation_result: Any   # AnnotationResult reference for generator-specific needs
    variant: Any             # VariantLite reference


# ---------------------------------------------------------------------------
# Shared context object passed to every generator
# ---------------------------------------------------------------------------

@dataclass
class GeneratorContext:
    """Immutable bag of data every insight generator needs."""
    analysis_id: int
    variants: List[AnalysisVariant]
    annotation_results: Dict[str, Any]  # rsid -> AnnotationResult
    session: AsyncSession
    rsid_gene_map: Dict[str, str]       # rsid -> gene symbol
    registry: Dict[str, Dict[str, Dict]]  # category -> {rsid: {}, gene: {}}
    variant_profiles: Dict[str, VariantProfile] = field(default_factory=dict)
    inferred_sex: Optional[str] = None  # 'male', 'female', 'unknown'

    def get_maps(self, category: str):
        """Return (rsid_map, gene_map) for a category from the loaded registry."""
        maps = self.registry.get(category, {'rsid': {}, 'gene': {}})
        return maps['rsid'], maps['gene']
