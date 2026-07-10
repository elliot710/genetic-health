from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.genetic_api_service import GeneticAPIService
from backend.db.database import get_session
from .auth_routes import get_current_user
from backend.core.config import settings
from backend.core.rate_limit import limiter
from backend.db.schemas import User
from backend.utils.annotation_text import (
    build_variant_description as _build_variant_description,
)
from backend.services.variant_detail_builder import (
    extract_ensembl, extract_clinvar, extract_clinvar_local,
    extract_pharmacogenomics, extract_snpedia, extract_publications,
    extract_alpha_missense, extract_gnomad, extract_gnomad_tx,
    extract_thousand_genomes, extract_gwas_clingen,
    backfill_clinical_significance, compute_pathogenicity_score,
)
from backend.services.annotation_loader import (
    load_or_fetch_annotation, attach_user_genotype,
    enrich_bigquery, attach_open_targets,
)
from backend.services.clinical_summary_builder import (
    build_clinical_summary, build_clinical_summary_from_cache,
)
from backend.api.annotation_static_data import SUPPORTED_APIS, ANNOTATION_EXAMPLES

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


class VariantAnnotationRequest(BaseModel):
    rsid: str
    gene: Optional[str] = None

class BatchAnnotationRequest(BaseModel):
    variants: List[Dict[str, Any]]

class LiteratureSearchRequest(BaseModel):
    rsid: str

class ClinicalSummaryRequest(BaseModel):
    rsid: str
    gene: Optional[str] = None

class AnnotationResponse(BaseModel):
    rsid: str
    gene: Optional[str]
    annotations: Dict[str, Any]
    error: Optional[str] = None

@router.post("/variant", response_model=AnnotationResponse)
@limiter.limit(lambda: f"{settings.rate_limit.lookup_per_minute}/minute")
async def annotate_single_variant(
    request: Request,
    payload: VariantAnnotationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Annotate a single genetic variant using multiple public databases
    
    Now includes comprehensive data from:
    - NCBI ClinVar (clinical significance)
    - Ensembl (population frequencies, consequences)
    - SNPedia (community annotations via MediaWiki API)
    - LitVar/PubMed (scientific literature)
    - ClinPGx pharmacogenomic data
    
    Examples of supported variants:
    - rs5443 (GNB3 gene - sildenafil response)
    - rs11615 (ERCC1 gene - platinum compound response)
    - rs1045642 (ABCB1 gene - drug transport)
    """
    try:
        async with GeneticAPIService() as api_service:
            result = await api_service.annotate_variant(payload.rsid, payload.gene)
            return AnnotationResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Annotation failed: {str(e)}")

@router.post("/batch", response_model=List[AnnotationResponse])
@limiter.limit(lambda: f"{settings.rate_limit.lookup_per_minute}/minute")
async def annotate_batch_variants(
    request: Request,
    payload: BatchAnnotationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Annotate multiple genetic variants in batch with enhanced rate limiting
    
    Request format:
    {
        "variants": [
            {"rsid": "rs5443", "gene": "GNB3"},
            {"rsid": "rs11615", "gene": "ERCC1"},
            {"rsid": "rs1045642", "gene": "ABCB1"}
        ]
    }
    """
    try:
        async with GeneticAPIService() as api_service:
            results = await api_service.batch_annotate_variants(payload.variants)
            return [AnnotationResponse(**result) if isinstance(result, dict) else 
                   AnnotationResponse(rsid="unknown", gene=None, annotations={}, error=str(result))
                   for result in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch annotation failed: {str(e)}")

@router.post("/literature")
async def search_literature(
    request: LiteratureSearchRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Search for scientific literature related to a genetic variant
    
    Uses LitVar API with PubMed fallback to find publications mentioning the variant.
    Returns publication details including PMIDs, titles, authors, and abstracts.
    """
    try:
        async with GeneticAPIService() as api_service:
            result = await api_service.get_litvar_publications(request.rsid)
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Literature search failed: {str(e)}")

@router.post("/clinical-summary")
async def get_clinical_summary_route(
    request: ClinicalSummaryRequest,
    refresh: bool = False,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    try:
        return await build_clinical_summary(
            request.rsid, request.gene, refresh, db
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Clinical summary failed: {str(e)}"
        )


@router.get("/variant-details/{rsid}")
@limiter.limit(lambda: f"{settings.rate_limit.lookup_per_minute}/minute")
async def get_variant_details(
    request: Request,
    rsid: str,
    refresh: bool = False,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    try:
        annotation, cache_hit = await load_or_fetch_annotation(
            rsid, refresh, db, current_user
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Variant details lookup failed: {str(e)}"
        )
    if not annotation:
        return {"found": False, "rsid": rsid}

    response: Dict[str, Any] = {
        "found": True, "rsid": rsid, "cache_hit": cache_hit
    }
    await attach_user_genotype(rsid, current_user.id, db, response)
    _extract_all_sources(annotation, response)

    scoring_annotations, score = compute_pathogenicity_score(
        annotation, response
    )
    response["pathogenicity_score"] = score

    gene_symbol = _first_gene_symbol(response)
    await enrich_bigquery(annotation, response, gene_symbol, db)
    await attach_open_targets(
        annotation, response, scoring_annotations, gene_symbol, db
    )
    await _attach_gene_level_data(gene_symbol, db, response, scoring_annotations, score)
    return response


def _extract_all_sources(annotation, response: dict):
    extract_ensembl(annotation, response)
    extract_clinvar(annotation, response)
    extract_clinvar_local(annotation, response)
    extract_pharmacogenomics(annotation, response)
    extract_snpedia(annotation, response)
    extract_publications(annotation, response)
    extract_alpha_missense(annotation, response)
    extract_gnomad(annotation, response)
    extract_gnomad_tx(annotation, response)
    extract_thousand_genomes(annotation, response)
    extract_gwas_clingen(annotation, response)
    response["description"] = _build_variant_description(
        response.get("rsid", ""), response
    )
    backfill_clinical_significance(annotation, response)


def _first_gene_symbol(response: dict) -> Optional[str]:
    transcripts = response.get("transcripts", [])
    return transcripts[0].get("gene_symbol") if transcripts else None


async def _attach_gene_level_data(
    gene_symbol: Optional[str], db: AsyncSession,
    response: dict, scoring_annotations: dict, score: dict,
) -> None:
    if not gene_symbol:
        return
    from backend.services.gene_constraint_service import (
        get_gene_constraint, get_clinvar_gene_stats,
    )
    constraint = await get_gene_constraint(gene_symbol, db)
    if constraint:
        response["gene_constraint"] = constraint
        scoring_annotations["gene_constraint"] = constraint
    stats = await get_clinvar_gene_stats(gene_symbol, db)
    if stats:
        response["clinvar_gene_stats"] = stats
        scoring_annotations["clinvar_gene_stats"] = stats
    if constraint or stats:
        from backend.services.scoring_engine import get_scoring_engine
        response["pathogenicity_score"] = get_scoring_engine().score_variant(
            scoring_annotations
        )


@router.get("/drug-response/{gene}")
async def get_drug_response_info(
    gene: str,
    current_user: User = Depends(get_current_user)
):
    try:
        async with GeneticAPIService() as api_service:
            return await api_service.get_clinpgx_drug_info(gene)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drug response lookup failed: {str(e)}")


@router.get("/snpedia/{rsid}")
async def get_snpedia_annotation(
    rsid: str,
    current_user: User = Depends(get_current_user)
):
    try:
        async with GeneticAPIService() as api_service:
            return await api_service.get_snpedia_info(rsid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SNPedia lookup failed: {str(e)}")


@router.get("/ensembl/{rsid}")
async def get_ensembl_annotation(
    rsid: str,
    current_user: User = Depends(get_current_user)
):
    try:
        async with GeneticAPIService() as api_service:
            return await api_service.get_variant_info_from_ensembl(rsid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ensembl lookup failed: {str(e)}")


@router.get("/clinvar/{rsid}")
async def get_clinvar_annotation(
    rsid: str,
    current_user: User = Depends(get_current_user)
):
    try:
        async with GeneticAPIService() as api_service:
            return await api_service.get_variant_info_from_clinvar(rsid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ClinVar lookup failed: {str(e)}")


@router.get("/supported-apis")
async def get_supported_apis():
    return SUPPORTED_APIS


@router.get("/examples")
async def get_annotation_examples():
    return ANNOTATION_EXAMPLES
