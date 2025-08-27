"""
Base interfaces and common functionality for specialized genetic analyzers.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AnalysisVariant


@dataclass
class AnalysisContext:
    """Context information for genetic analysis."""
    analysis_id: int
    analysis_variant: AnalysisVariant
    annotation: Dict[str, Any]
    session: AsyncSession


class SpecializedAnalyzer(ABC):
    """Abstract base class for all specialized genetic analyzers."""
    
    @abstractmethod
    async def can_analyze(self, context: AnalysisContext) -> bool:
        """Check if this analyzer can process the given variant."""
        pass
    
    @abstractmethod
    async def analyze(self, context: AnalysisContext) -> Optional[Any]:
        """Perform the specialized analysis and return the result."""
        pass
    
    @abstractmethod
    def get_analyzer_name(self) -> str:
        """Get the name of this analyzer."""
        pass


class BaseAnalyzer(SpecializedAnalyzer):
    """Base implementation with common functionality."""
    
    def __init__(self):
        self.gene_variants: Dict[str, List[str]] = {}
        self.clinical_significance_cache: Dict[str, str] = {}
    
    def extract_clinical_significance(self, annotation: Dict[str, Any]) -> str:
        """Extract clinical significance from annotation data."""
        rsid = annotation.get('rsid', 'unknown')
        
        if rsid in self.clinical_significance_cache:
            return self.clinical_significance_cache[rsid]
        
        annotations = annotation.get('annotations', {})
        
        # Check ClinVar first
        clinvar = annotations.get('clinvar', {})
        if clinvar.get('found') and clinvar.get('entries'):
            for entry in clinvar['entries']:
                if entry.get('clinical_significance'):
                    significance = entry['clinical_significance'][0]
                    self.clinical_significance_cache[rsid] = significance
                    return significance
        
        # Check Ensembl
        ensembl = annotations.get('ensembl', {})
        if ensembl.get('clinical_significance'):
            significance = ensembl['clinical_significance'][0]
            self.clinical_significance_cache[rsid] = significance
            return significance
        
        # Default
        self.clinical_significance_cache[rsid] = 'unknown'
        return 'unknown'
    
    def extract_gene_from_variant(self, analysis_variant: AnalysisVariant) -> Optional[str]:
        """Extract gene symbol from variant annotation if available."""
        if analysis_variant.info is not None:
            return analysis_variant.info.get('gene', '').upper()
        return None
    
    def is_variant_in_gene_list(self, analysis_variant: AnalysisVariant, gene_list: List[str]) -> bool:
        """Check if variant is in any of the specified genes."""
        gene = self.extract_gene_from_variant(analysis_variant)
        return gene is not None and gene.upper() in [g.upper() for g in gene_list]
    
    def is_rsid_in_variant_list(self, rsid: str, variant_list: List[str]) -> bool:
        """Check if rsid is in the specified variant list."""
        return rsid in variant_list


class AnalyzerRegistry:
    """Registry for managing specialized analyzers."""
    
    def __init__(self):
        self._analyzers: List[SpecializedAnalyzer] = []
    
    def register(self, analyzer: SpecializedAnalyzer):
        """Register a new analyzer."""
        self._analyzers.append(analyzer)
    
    def get_analyzers(self) -> List[SpecializedAnalyzer]:
        """Get all registered analyzers."""
        return self._analyzers.copy()
    
    async def analyze_all(self, context: AnalysisContext) -> Dict[str, Any]:
        """Run all applicable analyzers on the given context."""
        results = {}
        
        for analyzer in self._analyzers:
            try:
                if await analyzer.can_analyze(context):
                    result = await analyzer.analyze(context)
                    if result is not None:
                        analyzer_name = analyzer.get_analyzer_name()
                        results[analyzer_name] = result
            except Exception as e:
                # Log error but continue with other analyzers
                analyzer_name = analyzer.get_analyzer_name()
                results[f"{analyzer_name}_error"] = str(e)
        
        return results


# Global registry instance
analyzer_registry = AnalyzerRegistry()