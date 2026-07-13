"""Variant browse/search routes (examples, stats, search, categories) — split out of variant_routes.py.
"""

from fastapi import APIRouter, HTTPException, Depends, status, Query, Request
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func, literal_column
import re

from backend.services.genetic_api_service import GeneticAPIService
from backend.services.discovery_service import process_lookup_discoveries
from backend.services.multi_source_categorizer import categorize_variant
from backend.utils.alpha_missense import get_alpha_missense_service
from backend.services.clinvar_local import get_clinvar_local_service
from backend.services.gnomad_local import get_gnomad_service
from backend.services.ensembl_vep_local import get_ensembl_local_service
from backend.services.bq_public import BigQueryPublicService
from backend.services.gwas_catalog_local import get_gwas_catalog_service
from backend.services.clingen_local import get_clingen_service
from backend.services.open_targets_service import get_open_targets_service
from backend.db.database import get_session
from backend.db.models import (
    GeneticAnalysis, AnalysisVariant, GeneticMarker,
    SharedVariantAnnotation, VariantAnnotation, VariantLookupCache, SavedVariant,
    VariantMapping,
)
from backend.api.auth_routes import get_current_user
from backend.core.config import settings
from backend.core.rate_limit import limiter

from backend.api.variant.helpers import get_variant_category, VariantLookupResponse

router = APIRouter(prefix="/api/variants", tags=["variants"])


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
                "expected_data": ["Ensembl", "ClinPGx", "ClinVar"]
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
            "ClinPGx",
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


@router.get("/search")
@limiter.limit(lambda: f"{settings.rate_limit.lookup_per_minute}/minute")
async def search_user_variants(
    request: Request,
    q: str = Query(default="", description="Search by rsid (prefix or contains)"),
    chromosome: Optional[str] = Query(default=None, description="Filter by chromosome"),
    annotated: Optional[bool] = Query(default=None, description="Filter by annotation status"),
    category: Optional[str] = Query(default=None, description="Filter by functional category"),
    saved: Optional[bool] = Query(default=None, description="Filter to saved variants only"),
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
            SharedVariantAnnotation.alpha_missense_data,
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
    if saved is True:
        base_query = base_query.join(
            SavedVariant,
            (SavedVariant.rsid == GeneticMarker.rsid) & (SavedVariant.user_id == current_user.id)
        )
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

            clinvar_count = 0
            if r.clinvar_data and r.clinvar_data.get('found'):
                sources.append('clinvar')
                clinvar_count = r.clinvar_data.get('count', 0)
                for entry in r.clinvar_data.get('entries', []):
                    clinical_significance.extend(entry.get('clinical_significance', []))

            if r.pharmgkb_data and r.pharmgkb_data.get('found'):
                sources.append('clinpgx')

            if r.snpedia_data and r.snpedia_data.get('found'):
                sources.append('snpedia')

            if r.litvar_data and r.litvar_data.get('total_publications', 0) > 0:
                sources.append('litvar')

            # Extract AlphaMissense pathogenicity if available
            am_summary = None
            if r.alpha_missense_data and isinstance(r.alpha_missense_data, dict) and r.alpha_missense_data.get('found'):
                am_summary = {
                    "score": r.alpha_missense_data.get('am_pathogenicity'),
                    "classification": r.alpha_missense_data.get('am_class'),
                }

            annotation_summary = {
                "sources": sources,
                "gene": gene_name,
                "consequence": consequence,
                "clinical_significance": list(set(clinical_significance)) if clinical_significance else [],
                "clinvar_count": clinvar_count,
                "alpha_missense": am_summary,
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
    try:
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

        # Count ALL user variants
        total_result = await db.execute(
            select(sa_func.count(AnalysisVariant.id))
            .where(AnalysisVariant.analysis_id == analysis.id)
        )
        total_variants = total_result.scalar() or 0

        # Extract only the consequence string at the SQL level (avoids loading full JSON)
        consequence_col = literal_column(
            "ensembl_data -> 'data' -> 0 ->> 'most_severe_consequence'"
        ).label("consequence")

        rows = (await db.execute(
            select(consequence_col)
            .select_from(SharedVariantAnnotation)
            .join(GeneticMarker, SharedVariantAnnotation.marker_id == GeneticMarker.id)
            .join(AnalysisVariant, AnalysisVariant.marker_id == GeneticMarker.id)
            .where(
                AnalysisVariant.analysis_id == analysis.id,
                SharedVariantAnnotation.ensembl_data.isnot(None),
            )
        )).all()

        # Count annotated variants by category
        category_counts: dict[str, int] = {}
        annotated_count = 0
        for (consequence,) in rows:
            cat = get_variant_category(consequence)
            category_counts[cat] = category_counts.get(cat, 0) + 1
            annotated_count += 1

        # All unannotated variants go into "Unknown"
        unannotated = total_variants - annotated_count
        if unannotated > 0:
            category_counts['Unknown'] = category_counts.get('Unknown', 0) + unannotated

        categories = [
            {"name": name, "count": count}
            for name, count in sorted(category_counts.items(), key=lambda x: -x[1])
        ]

        return {"categories": categories, "total_variants": total_variants, "annotated_variants": annotated_count}
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error in get_variant_categories: {e}")
        raise HTTPException(status_code=500, detail="Failed to load variant categories")
