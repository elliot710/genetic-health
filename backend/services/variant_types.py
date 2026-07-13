"""
Lightweight variant/annotation dataclasses shared across the analysis pipeline.

Kept in a leaf module (no imports from other backend.services modules) so that
variant_loader, annotation_coordinator, insight_dispatcher, and analysis_service
can all depend on it without creating an import cycle.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AnnotationResult:
    """Result of variant annotation with reuse tracking."""
    rsid: str
    was_reused: bool
    annotation_data: Optional[Dict[str, Any]]
    source: str  # 'existing', 'api', 'failed'


@dataclass
class _MarkerLite:
    """Lightweight marker proxy — avoids SQLAlchemy ORM overhead for 600k+ variants."""
    id: int
    rsid: Optional[str]
    chromosome: Optional[str]
    position: Optional[int]
    ref_allele: Optional[str]
    alt_alleles: Optional[str]
    gene_symbol: Optional[str] = None  # Cached gene symbol (PERF-04)


@dataclass
class VariantLite:
    """Lightweight variant with the same public interface as AnalysisVariant.

    Using Core SQL rows + dataclasses instead of ORM objects avoids the
    60-90 second event-loop stall caused by SQLAlchemy materialising
    600k+ ORM instances after selectinload returns.
    """
    id: int
    analysis_id: int
    marker_id: int
    genotype: Optional[str]
    quality: Optional[str]
    filter_status: Optional[str]
    info: Optional[dict]
    marker: '_MarkerLite'

    # Proxy properties to match AnalysisVariant interface
    @property
    def rsid(self): return self.marker.rsid

    @property
    def chromosome(self): return self.marker.chromosome

    @property
    def position(self): return self.marker.position

    @property
    def ref_allele(self): return self.marker.ref_allele

    @property
    def alt_allele(self): return self.marker.alt_alleles
