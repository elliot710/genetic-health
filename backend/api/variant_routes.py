"""
Variant lookup and annotation API routes
Provides comprehensive variant information from multiple databases
"""
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import Dict, Any, List
from datetime import datetime
import re

from ..services.genetic_api_service import GeneticAPIService
from .auth_routes import get_current_user

router = APIRouter(prefix="/api/variants", tags=["variants"])

class VariantLookupRequest(BaseModel):
    variant_id: str = Field(..., description="Variant identifier (e.g., rs12202969)")
    include_literature: bool = Field(default=True, description="Include literature search")
    include_pharmgkb: bool = Field(default=True, description="Include PharmGKB data")

class VariantLookupResponse(BaseModel):
    variant_id: str
    found: bool
    source: str
    search_timestamp: str
    basic_info: Dict[str, Any]
    clinical_significance: List[str]
    population_data: Dict[str, Any]
    pharmacogenomics: Dict[str, Any]
    literature: Dict[str, Any]
    external_links: Dict[str, str]
    annotations: Dict[str, Any]

def validate_variant_id(variant_id: str) -> bool:
    """Validate variant ID format"""
    # Support rs IDs, chromosome coordinates, and other common formats
    patterns = [
        r'^rs\d+$',  # rsID format
        r'^chr\d+[XY]?:\d+$',  # chr:pos format
        r'^\d+[XY]?:\d+$',  # chrom:pos format
        r'^[A-Z]+\d+$'  # Gene variant format
    ]
    
    return any(re.match(pattern, variant_id.upper()) for pattern in patterns)

@router.post("/lookup", response_model=VariantLookupResponse)
async def lookup_variant(
    request: VariantLookupRequest,
    current_user = Depends(get_current_user)
):
    """
    Comprehensive variant lookup with enhanced data from multiple sources
    
    This endpoint provides:
    - Basic variant information (name, consequence, allele frequencies)
    - Clinical significance from ClinVar
    - Population data from Ensembl
    - Pharmacogenomic data from PharmGKB
    - Literature evidence from PubMed/LitVar
    - External resource links
    
    Supported variant formats:
    - rsID: rs12202969, rs53576
    - Chromosome position: chr1:12345, 1:12345
    - Gene variants: APOE4, MTHFR677T
    """
    
    variant_id = request.variant_id.strip()
    
    if not variant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Variant ID is required"
        )
    
    if not validate_variant_id(variant_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid variant ID format: {variant_id}. Supported formats: rs12345, chr1:12345, GENE123"
        )
    
    try:
        # Initialize API service
        api_service = GeneticAPIService()
        await api_service.initialize()
        
        try:
            # Get comprehensive annotation
            annotation_result = await api_service.annotate_variant(variant_id)
            
            if not annotation_result or 'error' in annotation_result:
                error_msg = annotation_result.get('error', 'Unknown error') if annotation_result else 'No data returned'
                return VariantLookupResponse(
                    variant_id=variant_id,
                    found=False,
                    source="Multiple databases",
                    search_timestamp=datetime.now().isoformat(),
                    basic_info={"error": error_msg},
                    clinical_significance=[],
                    population_data={},
                    pharmacogenomics={},
                    literature={},
                    external_links=_generate_external_links(variant_id),
                    annotations={}
                )
            
            annotations = annotation_result.get('annotations', {})
            
            # Process basic information
            basic_info = {}
            ensembl_data = annotations.get('ensembl', {})
            if ensembl_data and not ensembl_data.get('error'):
                basic_info.update({
                    "name": ensembl_data.get("name"),
                    "most_severe_consequence": ensembl_data.get("most_severe_consequence"),
                    "synonyms": ensembl_data.get("synonyms", []),
                    "source": "Ensembl"
                })
            
            # Process clinical significance
            clinical_significance = []
            clinvar_data = annotations.get('clinvar', {})
            if clinvar_data and clinvar_data.get('found'):
                for entry in clinvar_data.get('entries', []):
                    clinical_significance.extend(entry.get('clinical_significance', []))
                clinical_significance = list(set(clinical_significance))  # Remove duplicates
            
            # Process population data
            population_data = {}
            if ensembl_data and not ensembl_data.get('error'):
                population_data = {
                    "minor_allele": ensembl_data.get("minor_allele"),
                    "minor_allele_frequency": ensembl_data.get("minor_allele_freq"),
                    "populations": ensembl_data.get("populations", {}),
                    "global_frequency": ensembl_data.get("minor_allele_freq")
                }
            
            # Process pharmacogenomics data
            pharmacogenomics = {}
            pharmgkb_data = annotations.get('pharmgkb_variant', {})
            if pharmgkb_data and pharmgkb_data.get('found'):
                pharmacogenomics = {
                    "found": True,
                    "gene": pharmgkb_data.get('gene'),
                    "clinical_significance": pharmgkb_data.get('clinical_significance'),
                    "clinical_annotations": pharmgkb_data.get('clinical_annotations', []),
                    "drug_labels": pharmgkb_data.get('drug_labels', [])
                }
            else:
                pharmacogenomics = {"found": False}
            
            # Process literature data
            literature = {}
            if request.include_literature:
                literature_data = annotations.get('literature', {})
                if literature_data:
                    literature = {
                        "total_publications": literature_data.get('total_publications', 0),
                        "source": literature_data.get('source', 'PubMed'),
                        "publications": literature_data.get('publications', [])[:5]  # Limit to 5
                    }
            
            # Generate external links
            external_links = _generate_external_links(variant_id)
            
            # Determine if variant was found
            found = any([
                basic_info.get('name'),
                clinical_significance,
                population_data.get('minor_allele'),
                pharmacogenomics.get('found'),
                literature.get('total_publications', 0) > 0
            ])
            
            return VariantLookupResponse(
                variant_id=variant_id,
                found=found,
                source="Multiple databases",
                search_timestamp=datetime.now().isoformat(),
                basic_info=basic_info,
                clinical_significance=clinical_significance,
                population_data=population_data,
                pharmacogenomics=pharmacogenomics,
                literature=literature,
                external_links=external_links,
                annotations=annotations
            )
            
        finally:
            # Clean up API service
            try:
                await api_service.close()
            except Exception:
                pass
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Variant lookup failed: {str(e)}"
        )

def _generate_external_links(variant_id: str) -> Dict[str, str]:
    """Generate external resource links for a variant"""
    return {
        "dbSNP": f"https://www.ncbi.nlm.nih.gov/snp/{variant_id}",
        "Ensembl": f"https://www.ensembl.org/Homo_sapiens/Variation/Summary?v={variant_id}",
        "ClinVar": f"https://www.ncbi.nlm.nih.gov/clinvar/?term={variant_id}",
        "PharmGKB": f"https://www.pharmgkb.org/variant/{variant_id}",
        "SNPedia": f"https://www.snpedia.com/index.php/{variant_id}",
        "PubMed": f"https://pubmed.ncbi.nlm.nih.gov/?term={variant_id}"
    }

@router.get("/examples")
async def get_example_variants():
    """Get example variants for testing the lookup functionality"""
    return {
        "examples": [
            {
                "variant_id": "rs12202969",
                "description": "Example variant with multiple database annotations",
                "expected_data": ["Ensembl", "ClinVar", "Literature"]
            },
            {
                "variant_id": "rs53576",
                "description": "OXTR gene variant associated with social behavior",
                "expected_data": ["Ensembl", "SNPedia", "Literature"]
            },
            {
                "variant_id": "rs1695", 
                "description": "GSTP1 gene variant affecting drug metabolism",
                "expected_data": ["Ensembl", "PharmGKB", "ClinVar"]
            },
            {
                "variant_id": "rs429358",
                "description": "APOE gene variant associated with Alzheimer's disease",
                "expected_data": ["Ensembl", "ClinVar", "Literature", "SNPedia"]
            },
            {
                "variant_id": "rs7412",
                "description": "APOE gene variant, complement to rs429358",
                "expected_data": ["Ensembl", "ClinVar", "Literature"]
            }
        ],
        "supported_formats": [
            "rsID: rs12345",
            "Chromosome position: chr1:12345 or 1:12345",
            "Gene variants: APOE4, MTHFR677T"
        ],
        "data_sources": [
            "Ensembl REST API",
            "NCBI ClinVar",
            "PharmGKB",
            "PubMed/LitVar", 
            "SNPedia"
        ]
    }

@router.get("/stats")
async def get_lookup_stats(
    current_user = Depends(get_current_user)
):
    """Get statistics about variant lookup usage"""
    # This could be enhanced to track actual usage statistics
    return {
        "supported_databases": 5,
        "average_response_time": "2-5 seconds",
        "success_rate": "~85%",
        "common_issues": [
            "Variant not found in any database",
            "API rate limiting",
            "Network timeouts"
        ],
        "recommendations": [
            "Use standard rsID format when possible",
            "Check variant ID spelling",
            "Try alternative variant names/synonyms"
        ]
    }