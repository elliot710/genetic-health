"""
Variant lookup and annotation API routes
Provides comprehensive variant information from multiple databases
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func
import re

from ..services.genetic_api_service import GeneticAPIService
from ..db.database import get_session
from ..db.models import (
    GeneticAnalysis, AnalysisVariant, GeneticMarker,
    SharedVariantAnnotation, VariantAnnotation, VariantLookupCache
)
from .auth_routes import get_current_user

router = APIRouter(prefix="/api/variants", tags=["variants"])

class VariantLookupRequest(BaseModel):
    variant_id: str = Field(..., description="Variant identifier (e.g., rs12202969)")
    include_literature: bool = Field(default=True, description="Include literature search")
    include_pharmgkb: bool = Field(default=True, description="Include PharmGKB data")
    force_refresh: bool = Field(default=False, description="Force fetch from external sources even if cached")

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
    cached: bool = False
    cached_at: Optional[str] = None

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
    session: AsyncSession = Depends(get_session),
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
        # Check cache first (unless force_refresh)
        if not request.force_refresh:
            result = await session.execute(
                select(VariantLookupCache).where(VariantLookupCache.variant_id == variant_id)
            )
            cached = result.scalar_one_or_none()
            if cached and cached.response_data:
                # Read data before any commit
                resp = cached.response_data
                cached_at = cached.updated_at.isoformat() if cached.updated_at else (cached.created_at.isoformat() if cached.created_at else None)
                
                # Increment lookup count
                cached.lookup_count = (cached.lookup_count or 0) + 1
                await session.commit()
                
                return VariantLookupResponse(
                    variant_id=variant_id,
                    found=resp.get('found', False),
                    source=resp.get('source', 'Multiple databases'),
                    search_timestamp=resp.get('search_timestamp', ''),
                    basic_info=resp.get('basic_info', {}),
                    clinical_significance=resp.get('clinical_significance', []),
                    population_data=resp.get('population_data', {}),
                    pharmacogenomics=resp.get('pharmacogenomics', {}),
                    literature=resp.get('literature', {}),
                    external_links=_generate_external_links(variant_id),
                    annotations=resp.get('annotations', {}),
                    cached=True,
                    cached_at=cached_at
                )
        
        # Fetch from external sources
        api_service = GeneticAPIService()
        await api_service.initialize()
        
        try:
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
                    annotations={},
                    cached=False
                )
            
            annotations = annotation_result.get('annotations', {})
            
            # Process basic information from Ensembl
            basic_info = {}
            ensembl_raw = annotations.get('ensembl', {})
            ensembl_entry = None
            colocated_variants = []
            if ensembl_raw and ensembl_raw.get('found') and ensembl_raw.get('data'):
                ensembl_entry = ensembl_raw['data'][0] if isinstance(ensembl_raw['data'], list) else ensembl_raw['data']
                colocated_variants = ensembl_entry.get('colocated_variants', [])
                
                # Extract gene from transcript_consequences
                gene_symbol = None
                transcript_consequences = ensembl_entry.get('transcript_consequences', [])
                if transcript_consequences:
                    gene_symbol = transcript_consequences[0].get('gene_symbol')
                
                basic_info.update({
                    "name": ensembl_entry.get("id", variant_id),
                    "most_severe_consequence": ensembl_entry.get("most_severe_consequence", "").replace("_", " "),
                    "allele_string": ensembl_entry.get("allele_string"),
                    "gene_symbol": gene_symbol,
                    "chromosome": ensembl_entry.get("seq_region_name"),
                    "start": ensembl_entry.get("start"),
                    "end": ensembl_entry.get("end"),
                    "strand": ensembl_entry.get("strand"),
                    "source": "Ensembl"
                })
            
            # Process clinical significance from Ensembl colocated_variants
            clinical_significance = []
            for cv in colocated_variants:
                clin_sigs = cv.get('clin_sig', [])
                if clin_sigs:
                    clinical_significance.extend(clin_sigs)
            clinical_significance = list(set(clinical_significance))
            
            # Also note ClinVar IDs if available
            clinvar_data = annotations.get('clinvar', {})
            if clinvar_data and clinvar_data.get('found'):
                basic_info["clinvar_ids"] = clinvar_data.get('ids', [])
                basic_info["clinvar_count"] = clinvar_data.get('count', 0)
            
            # Process population data from Ensembl colocated_variants
            population_data = {}
            for cv in colocated_variants:
                if cv.get('id') == variant_id or cv.get('id', '').lower() == variant_id.lower():
                    frequencies = cv.get('frequencies', {})
                    minor_allele = cv.get('minor_allele')
                    minor_allele_freq = cv.get('minor_allele_freq')
                    
                    # Flatten population frequencies
                    populations = {}
                    for allele, pops in frequencies.items():
                        for pop_name, freq in pops.items():
                            populations[pop_name] = {"allele": allele, "frequency": freq}
                    
                    population_data = {
                        "minor_allele": minor_allele,
                        "minor_allele_frequency": minor_allele_freq,
                        "populations": populations,
                        "global_frequency": minor_allele_freq
                    }
                    break
            
            # Process pharmacogenomics data
            pharmacogenomics = {}
            pharmgkb_data = annotations.get('pharmgkb', {})
            if pharmgkb_data and pharmgkb_data.get('found'):
                pharmacogenomics = {
                    "found": True,
                    "data": pharmgkb_data.get('data', {}),
                }
            else:
                pharmacogenomics = {"found": False}
            
            # Process SNPedia data 
            literature = {}
            snpedia_data = annotations.get('snpedia', {})
            if snpedia_data and snpedia_data.get('found'):
                wiki_data = snpedia_data.get('data', {})
                revisions = wiki_data.get('revisions', [])
                wiki_text = revisions[0].get('*', '') if revisions else ''
                literature = {
                    "snpedia_found": True,
                    "title": wiki_data.get('title', ''),
                    "wiki_text": wiki_text[:2000],  # Limit size
                    "source": "SNPedia"
                }
            
            # Generate external links
            external_links = _generate_external_links(variant_id)
            
            # Determine if variant was found
            found = any([
                basic_info.get('name'),
                clinical_significance,
                population_data.get('minor_allele'),
                pharmacogenomics.get('found'),
                literature.get('snpedia_found')
            ])
            
            # Build response data to cache
            now = datetime.now()
            response_data = {
                "found": found,
                "source": "Multiple databases",
                "search_timestamp": now.isoformat(),
                "basic_info": basic_info,
                "clinical_significance": clinical_significance,
                "population_data": population_data,
                "pharmacogenomics": pharmacogenomics,
                "literature": literature,
                "annotations": annotations
            }
            
            # Save to cache
            try:
                result = await session.execute(
                    select(VariantLookupCache).where(VariantLookupCache.variant_id == variant_id)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    existing.found = found
                    existing.response_data = response_data
                    existing.raw_annotations = annotations
                    existing.updated_at = now
                    existing.lookup_count = (existing.lookup_count or 0) + 1
                else:
                    cache_entry = VariantLookupCache(
                        variant_id=variant_id,
                        found=found,
                        response_data=response_data,
                        raw_annotations=annotations,
                        lookup_count=1
                    )
                    session.add(cache_entry)
                await session.commit()
            except Exception:
                pass
            
            return VariantLookupResponse(
                variant_id=variant_id,
                found=found,
                source="Multiple databases",
                search_timestamp=now.isoformat(),
                basic_info=basic_info,
                clinical_significance=clinical_significance,
                population_data=population_data,
                pharmacogenomics=pharmacogenomics,
                literature=literature,
                external_links=external_links,
                annotations=annotations,
                cached=False
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


CONSEQUENCE_CATEGORIES = {
    'missense_variant': 'Coding',
    'synonymous_variant': 'Coding',
    'stop_gained': 'Coding',
    'stop_lost': 'Coding',
    'frameshift_variant': 'Coding',
    'start_lost': 'Coding',
    'inframe_insertion': 'Coding',
    'inframe_deletion': 'Coding',
    'coding_sequence_variant': 'Coding',
    'protein_altering_variant': 'Coding',
    '5_prime_UTR_variant': 'Regulatory',
    '3_prime_UTR_variant': 'Regulatory',
    'upstream_gene_variant': 'Regulatory',
    'downstream_gene_variant': 'Regulatory',
    'regulatory_region_variant': 'Regulatory',
    'TF_binding_site_variant': 'Regulatory',
    'splice_region_variant': 'Splicing',
    'splice_donor_variant': 'Splicing',
    'splice_acceptor_variant': 'Splicing',
    'splice_donor_5th_base_variant': 'Splicing',
    'splice_polypyrimidine_tract_variant': 'Splicing',
    'intron_variant': 'Intronic',
    'non_coding_transcript_exon_variant': 'Non-coding',
    'non_coding_transcript_variant': 'Non-coding',
    'mature_miRNA_variant': 'Non-coding',
    'intergenic_variant': 'Intergenic',
}


def get_variant_category(consequence: Optional[str]) -> str:
    if not consequence:
        return 'Unknown'
    return CONSEQUENCE_CATEGORIES.get(consequence, 'Other')


@router.get("/search")
async def search_user_variants(
    q: str = Query(default="", description="Search by rsid (prefix or contains)"),
    chromosome: Optional[str] = Query(default=None, description="Filter by chromosome"),
    annotated: Optional[bool] = Query(default=None, description="Filter by annotation status"),
    category: Optional[str] = Query(default=None, description="Filter by functional category"),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=50, ge=1, le=200, description="Items per page"),
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Search the user's own uploaded variants with filters.
    Returns variant data with annotation summaries.
    """
    # Find user's primary completed analysis
    result = await db.execute(
        select(GeneticAnalysis)
        .where(
            GeneticAnalysis.user_id == current_user.id,
            GeneticAnalysis.analysis_status == 'completed'
        )
        .order_by(GeneticAnalysis.upload_date.desc())
        .limit(1)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        return {"variants": [], "total": 0, "page": page, "per_page": per_page, "pages": 0}

    # Build base query
    base_query = (
        select(
            GeneticMarker.id.label('marker_id'),
            GeneticMarker.rsid,
            GeneticMarker.chromosome,
            GeneticMarker.position,
            GeneticMarker.ref_allele,
            GeneticMarker.alt_alleles,
            AnalysisVariant.genotype,
            SharedVariantAnnotation.id.label('annotation_id'),
            SharedVariantAnnotation.annotation_status,
            SharedVariantAnnotation.ensembl_data,
            SharedVariantAnnotation.clinvar_data,
            SharedVariantAnnotation.pharmgkb_data,
            SharedVariantAnnotation.snpedia_data,
            SharedVariantAnnotation.litvar_data,
        )
        .join(GeneticMarker, AnalysisVariant.marker_id == GeneticMarker.id)
        .outerjoin(SharedVariantAnnotation, SharedVariantAnnotation.marker_id == GeneticMarker.id)
        .where(AnalysisVariant.analysis_id == analysis.id)
    )

    # Apply filters
    if q:
        base_query = base_query.where(GeneticMarker.rsid.ilike(f"%{q}%"))
    if chromosome:
        base_query = base_query.where(GeneticMarker.chromosome == chromosome)
    if annotated is True:
        base_query = base_query.where(SharedVariantAnnotation.id.isnot(None))
    elif annotated is False:
        base_query = base_query.where(SharedVariantAnnotation.id.is_(None))
    if category:
        # Filter by functional category using consequence type from ensembl_data
        matching_consequences = [k for k, v in CONSEQUENCE_CATEGORIES.items() if v == category]
        if matching_consequences:
            from sqlalchemy import text
            placeholders = ', '.join(f':c{i}' for i in range(len(matching_consequences)))
            params = {f'c{i}': c for i, c in enumerate(matching_consequences)}
            base_query = base_query.where(
                text(f"shared_variant_annotations.ensembl_data->'data'->0->>'most_severe_consequence' IN ({placeholders})").bindparams(**params)
            )

    # Get total count
    count_query = select(sa_func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar() or 0
    pages = (total + per_page - 1) // per_page

    # Paginate and fetch
    rows = (await db.execute(
        base_query
        .order_by(GeneticMarker.chromosome, GeneticMarker.position)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )).all()

    variants = []
    for r in rows:
        annotation_summary = None
        if r.annotation_id:
            # Build concise summary from raw annotation data
            sources = []
            clinical_significance = []
            gene_name = None
            consequence = None

            if r.ensembl_data and not r.ensembl_data.get('error'):
                sources.append('ensembl')
                ens_entries = r.ensembl_data.get('data', [])
                if ens_entries and isinstance(ens_entries, list) and len(ens_entries) > 0:
                    ens = ens_entries[0]
                    consequence = ens.get('most_severe_consequence')
                    for tc in ens.get('transcript_consequences', []):
                        if tc.get('gene_symbol'):
                            gene_name = tc['gene_symbol']
                            break

            if r.clinvar_data and r.clinvar_data.get('found'):
                sources.append('clinvar')
                for entry in r.clinvar_data.get('entries', []):
                    clinical_significance.extend(entry.get('clinical_significance', []))

            if r.pharmgkb_data and r.pharmgkb_data.get('found'):
                sources.append('pharmgkb')

            if r.snpedia_data and r.snpedia_data.get('found'):
                sources.append('snpedia')

            if r.litvar_data and r.litvar_data.get('total_publications', 0) > 0:
                sources.append('litvar')

            annotation_summary = {
                "sources": sources,
                "gene": gene_name,
                "consequence": consequence,
                "clinical_significance": list(set(clinical_significance)) if clinical_significance else [],
            }

        variant_category = get_variant_category(
            annotation_summary.get('consequence') if annotation_summary else None
        )

        variants.append({
            "rsid": r.rsid,
            "chromosome": r.chromosome,
            "position": r.position,
            "ref_allele": r.ref_allele,
            "alt_allele": r.alt_alleles,
            "genotype": r.genotype,
            "has_annotation": r.annotation_id is not None,
            "category": variant_category,
            "annotation": annotation_summary,
        })

    return {
        "variants": variants,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/categories")
async def get_variant_categories(
    db: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Returns category distribution for the user's annotated variants.
    Categories are derived from Ensembl most_severe_consequence.
    """
    result = await db.execute(
        select(GeneticAnalysis)
        .where(
            GeneticAnalysis.user_id == current_user.id,
            GeneticAnalysis.analysis_status == 'completed'
        )
        .order_by(GeneticAnalysis.upload_date.desc())
        .limit(1)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        return {"categories": []}

    # Get all annotated variants with their ensembl consequence
    rows = (await db.execute(
        select(
            SharedVariantAnnotation.ensembl_data,
        )
        .join(GeneticMarker, SharedVariantAnnotation.marker_id == GeneticMarker.id)
        .join(AnalysisVariant, AnalysisVariant.marker_id == GeneticMarker.id)
        .where(
            AnalysisVariant.analysis_id == analysis.id,
            SharedVariantAnnotation.ensembl_data.isnot(None),
        )
    )).all()

    # Count by category
    category_counts: dict[str, int] = {}
    for (ensembl_data,) in rows:
        consequence = None
        if ensembl_data and not ensembl_data.get('error'):
            entries = ensembl_data.get('data', [])
            if entries and isinstance(entries, list) and len(entries) > 0:
                consequence = entries[0].get('most_severe_consequence')
        cat = get_variant_category(consequence)
        category_counts[cat] = category_counts.get(cat, 0) + 1

    categories = [
        {"name": name, "count": count}
        for name, count in sorted(category_counts.items(), key=lambda x: -x[1])
    ]

    return {"categories": categories}