"""
API routes for genetic variant annotation using external services
Enhanced with NCBI E-utilities, LitVar, SNPedia, ClinVar, and Ensembl APIs
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.services.genetic_api_service import GeneticAPIService
from backend.db.database import get_session
from backend.db.models import SharedVariantAnnotation, VariantLookupCache, AnnotationSourceConfig
from backend.utils.alpha_missense import get_alpha_missense_service, AlphaMissenseService
from .auth_routes import get_current_user
from backend.db.schemas import User

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


def _build_variant_description(rsid: str, response: Dict[str, Any]) -> str:
    """Build a natural language description of a variant from annotation data."""
    parts = []

    # Determine variant type
    consequence = response.get("most_severe_consequence", "")
    variant_type_label = consequence if consequence else "variant"

    # Gene info
    gene = None
    transcripts = response.get("transcripts", [])
    if transcripts:
        gene = transcripts[0].get("gene_symbol")

    # HGVS name and conditions from ClinVar entries
    hgvs_name = None
    all_conditions: list[str] = []
    clinvar_variation_type = None
    clinvar_entries = response.get("clinvar", {}).get("entries", [])
    for entry in clinvar_entries:
        title = entry.get("title", "")
        if title and not hgvs_name:
            hgvs_name = title
        vt = entry.get("variation_type", "")
        if vt and not clinvar_variation_type:
            clinvar_variation_type = vt
        conditions = entry.get("conditions", [])
        all_conditions.extend(c for c in conditions if c and c.lower() != "not provided" and c.lower() != "not specified")

    all_conditions = list(dict.fromkeys(all_conditions))  # dedupe preserving order

    # Prefer ClinVar variation type (e.g. "single nucleotide variant") over Ensembl consequence
    if clinvar_variation_type:
        variant_type_label = clinvar_variation_type

    # Opening sentence
    if gene and gene != "Unknown" and not gene.startswith("rs"):
        parts.append(f"{rsid} is a {variant_type_label} in the {gene} gene")
    else:
        parts.append(f"{rsid} is a {variant_type_label}")

    # HGVS nomenclature
    if hgvs_name:
        parts[-1] += f", specifically identified as {hgvs_name}."
    else:
        parts[-1] += "."

    # Associated conditions
    if all_conditions:
        if len(all_conditions) == 1:
            parts.append(f"This variant is associated with {all_conditions[0]}.")
        else:
            joined = ", ".join(all_conditions[:-1]) + " and " + all_conditions[-1]
            parts.append(f"This variant is associated with {joined}.")

    # Clinical significance
    clin_sigs = response.get("clinical_significance", [])
    if clin_sigs:
        formatted = [s.replace("_", " ") for s in clin_sigs]
        parts.append(f"Clinical assessments classify it as {', '.join(formatted)}.")

    # Pharmacogenomic note
    if response.get("pharmacogenomics", {}).get("found"):
        parts.append("It has known pharmacogenomic associations that may affect drug response.")

    return " ".join(parts) if len(parts) > 1 else parts[0] if parts else ""


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
async def annotate_single_variant(
    request: VariantAnnotationRequest,
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
            result = await api_service.annotate_variant(request.rsid, request.gene)
            return AnnotationResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Annotation failed: {str(e)}")

@router.post("/batch", response_model=List[AnnotationResponse])
async def annotate_batch_variants(
    request: BatchAnnotationRequest,
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
            results = await api_service.batch_annotate_variants(request.variants)
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
async def get_clinical_summary(
    request: ClinicalSummaryRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Get a comprehensive clinical summary combining all data sources
    
    Provides a unified view of:
    - Clinical significance from ClinVar
    - Population frequencies from Ensembl
    - Drug response information
    - Literature evidence count
    - Clinical recommendations
    """
    try:
        async with GeneticAPIService() as api_service:
            result = await api_service.get_variant_clinical_summary(request.rsid, request.gene)
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clinical summary failed: {str(e)}")

@router.get("/variant-details/{rsid}")
async def get_variant_details(
    rsid: str,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get structured annotation details for a variant from the database.
    Falls back to live API fetch when no cached annotation exists.
    Returns processed ensembl, clinvar, and publication data.
    """
    result = await db.execute(
        select(SharedVariantAnnotation).where(SharedVariantAnnotation.rsid == rsid)
    )
    annotation = result.scalar_one_or_none()

    if not annotation:
        # Fall back: fetch live data from external APIs and persist it
        try:
            from backend.db.models import GeneticMarker
            marker_result = await db.execute(
                select(GeneticMarker).where(GeneticMarker.rsid == rsid)
            )
            marker = marker_result.scalar_one_or_none()

            async with GeneticAPIService() as api_service:
                live = await api_service.annotate_variant(rsid)
            raw = live.get("annotations", {})

            # Persist as a new SharedVariantAnnotation so future lookups are instant
            new_ann = SharedVariantAnnotation(
                rsid=rsid,
                marker_id=marker.id if marker else None,
                ensembl_data=raw.get("ensembl"),
                clinvar_data=raw.get("clinvar"),
                pharmgkb_data=raw.get("clinpgx"),
                snpedia_data=raw.get("snpedia"),
                litvar_data=raw.get("litvar"),
            )
            db.add(new_ann)
            await db.commit()
            await db.refresh(new_ann)
            annotation = new_ann
        except Exception:
            return {"found": False, "rsid": rsid}

    response: Dict[str, Any] = {"found": True, "rsid": rsid}

    # Process Ensembl data
    ensembl = annotation.ensembl_data
    if ensembl and isinstance(ensembl, dict) and ensembl.get("found"):
        data = ensembl.get("data", [])
        entry = data[0] if isinstance(data, list) and data else data if isinstance(data, dict) else None
        if entry:
            # Get most severe consequence
            response["most_severe_consequence"] = (entry.get("most_severe_consequence") or "").replace("_", " ")
            response["allele_string"] = entry.get("allele_string")
            response["chromosome"] = entry.get("seq_region_name")
            response["position"] = entry.get("start")

            # Extract unique transcript consequences (deduplicated by gene+consequence)
            tc_list = entry.get("transcript_consequences", [])
            seen = set()
            transcripts = []
            for tc in tc_list:
                if tc.get("biotype") != "protein_coding":
                    continue
                key = (tc.get("gene_symbol"), tuple(tc.get("consequence_terms", [])))
                if key in seen:
                    continue
                seen.add(key)
                transcripts.append({
                    "gene_symbol": tc.get("gene_symbol"),
                    "gene_id": tc.get("gene_id"),
                    "transcript_id": tc.get("transcript_id"),
                    "consequence_terms": [t.replace("_", " ") for t in tc.get("consequence_terms", [])],
                    "impact": tc.get("impact"),
                    "amino_acids": tc.get("amino_acids"),
                    "codons": tc.get("codons"),
                    "sift_prediction": tc.get("sift_prediction"),
                    "sift_score": tc.get("sift_score"),
                    "polyphen_prediction": tc.get("polyphen_prediction"),
                    "polyphen_score": tc.get("polyphen_score"),
                    "protein_position": f"{tc.get('protein_start', '')}" if tc.get("protein_start") else None,
                })
                if len(transcripts) >= 6:
                    break
            response["transcripts"] = transcripts
            response["total_transcripts"] = len(tc_list)

            # Extract clinical significance and population frequencies from colocated_variants
            colocated = entry.get("colocated_variants", [])
            clin_sigs = []
            frequencies = {}
            clinvar_ids = []
            for cv in colocated:
                if cv.get("clin_sig"):
                    clin_sigs.extend(cv["clin_sig"])
                if cv.get("var_synonyms", {}).get("ClinVar"):
                    clinvar_ids.extend(cv["var_synonyms"]["ClinVar"])
                freqs = cv.get("frequencies", {})
                for allele, pops in freqs.items():
                    for pop, freq in pops.items():
                        if pop in ("gnomade", "gnomadg", "af") or pop.startswith("gnomade_") or pop.startswith("gnomadg_"):
                            clean_pop = pop.replace("gnomade_", "gnomAD exomes: ").replace("gnomadg_", "gnomAD genomes: ").replace("gnomade", "gnomAD exomes (global)").replace("gnomadg", "gnomAD genomes (global)").replace("af", "1000 Genomes (global)")
                            if clean_pop not in frequencies or freq > frequencies[clean_pop]["frequency"]:
                                frequencies[clean_pop] = {"allele": allele, "frequency": freq}
            response["clinical_significance"] = list(set(clin_sigs))
            response["clinvar_ids"] = list(set(clinvar_ids))
            response["population_frequencies"] = frequencies

    # Process ClinVar data
    clinvar = annotation.clinvar_data
    if clinvar and isinstance(clinvar, dict) and clinvar.get("found"):
        clinvar_entries = clinvar.get("entries", [])
        # Fall back to lookup cache if shared annotation has no entries
        if not clinvar_entries:
            try:
                cache_result = await db.execute(
                    select(VariantLookupCache).where(VariantLookupCache.variant_id == rsid)
                )
                cached = cache_result.scalar_one_or_none()
                if cached and cached.response_data:
                    cached_clinvar = cached.response_data.get("annotations", {}).get("clinvar", {})
                    clinvar_entries = cached_clinvar.get("entries", [])
            except Exception:
                pass
        response["clinvar"] = {
            "found": True,
            "count": clinvar.get("count", 0),
            "ids": clinvar.get("ids", []),
            "entries": clinvar_entries,
        }

    # Process ClinPGx data (stored in pharmgkb_data column for backward compat)
    clinpgx_raw = annotation.pharmgkb_data
    if clinpgx_raw and isinstance(clinpgx_raw, dict) and clinpgx_raw.get("found"):
        response["pharmacogenomics"] = {
            "found": True,
            "data": clinpgx_raw.get("data", {}),
        }

    # Process SNPedia data
    snpedia = annotation.snpedia_data
    if snpedia and isinstance(snpedia, dict) and snpedia.get("found"):
        wiki_data = snpedia.get("data", {})
        revisions = wiki_data.get("revisions", [])
        wiki_text = revisions[0].get("*", "") if revisions else ""
        # Extract a clean summary from wiki text
        summary = ""
        if wiki_text:
            lines = [
                l.strip() for l in wiki_text.split("\n")
                if l.strip()
                and not l.strip().startswith("{{")
                and not l.strip().startswith("}}")
                and not l.strip().startswith("[[Category")
                and not l.strip().startswith("|")
                and not l.strip().startswith("<")
            ]
            summary = " ".join(lines[:3])[:500]
        response["snpedia"] = {
            "found": True,
            "title": wiki_data.get("title", ""),
            "summary": summary,
        }

    # Process LitVar / publications data
    litvar = annotation.litvar_data
    if litvar and isinstance(litvar, dict) and litvar.get("found"):
        pubs = litvar.get("publications", [])
        response["publications"] = {
            "count": len(pubs),
            "items": [
                {
                    "pmid": p.get("pmid"),
                    "title": p.get("title"),
                    "journal": p.get("journal"),
                    "year": p.get("year"),
                }
                for p in pubs[:20]
            ],
        }

    # Process AlphaMissense data (AI prediction, NOT clinically validated)
    am_raw = annotation.alpha_missense_data
    if am_raw and isinstance(am_raw, dict) and am_raw.get("found"):
        formatted = AlphaMissenseService.format_result_for_display(am_raw)
        if formatted:
            response["alpha_missense"] = formatted

    # Process gnomAD data (population frequencies + gene constraints + CADD scores)
    gnomad_raw = annotation.gnomad_data
    if gnomad_raw and isinstance(gnomad_raw, dict) and gnomad_raw.get("found"):
        gnomad_resp: Dict[str, Any] = {
            "found": True,
            "source": gnomad_raw.get("source", "gnomad"),
            "variant_id": gnomad_raw.get("variant_id"),
            "variant_type": gnomad_raw.get("variant_type"),
            "af": gnomad_raw.get("af"),
            "ac": gnomad_raw.get("ac"),
            "an": gnomad_raw.get("an"),
            "nhomalt": gnomad_raw.get("nhomalt"),
            "filter_status": gnomad_raw.get("filter_status"),
            "gene": gnomad_raw.get("gene"),
            "consequence": gnomad_raw.get("consequence"),
            "impact": gnomad_raw.get("impact"),
            "hgvsc": gnomad_raw.get("hgvsc"),
            "hgvsp": gnomad_raw.get("hgvsp"),
        }
        pop_freqs = gnomad_raw.get("population_frequencies", {})
        if pop_freqs:
            gnomad_resp["population_frequencies"] = pop_freqs
        # CADD pathogenicity scores
        if gnomad_raw.get("cadd"):
            gnomad_resp["cadd"] = gnomad_raw["cadd"]
        # Functional predictions (SIFT, PolyPhen)
        if gnomad_raw.get("predictions"):
            gnomad_resp["predictions"] = gnomad_raw["predictions"]
        # Conservation scores (PhyloP)
        if gnomad_raw.get("conservation"):
            gnomad_resp["conservation"] = gnomad_raw["conservation"]
        # SpliceAI scores
        if gnomad_raw.get("splice_ai"):
            gnomad_resp["splice_ai"] = gnomad_raw["splice_ai"]
        response["gnomad"] = gnomad_resp

    # Generate natural language variant description from combined sources (after all processing)
    response["description"] = _build_variant_description(rsid, response)

    # Composite pathogenicity scoring (aggregates all evidence sources)
    from backend.services.scoring_engine import get_scoring_engine
    scoring_annotations = {}
    # Feed raw annotation data (not the processed response) into the scoring engine
    if annotation.ensembl_data:
        scoring_annotations["ensembl"] = annotation.ensembl_data
    if annotation.clinvar_data:
        scoring_annotations["clinvar"] = annotation.clinvar_data
    if annotation.clinvar_local_data:
        scoring_annotations["clinvar_local"] = annotation.clinvar_local_data
    if annotation.alpha_missense_data:
        scoring_annotations["alpha_missense"] = annotation.alpha_missense_data
    if annotation.gnomad_data:
        scoring_annotations["gnomad"] = annotation.gnomad_data
    response["pathogenicity_score"] = get_scoring_engine().score_variant(scoring_annotations)

    # ── BigQuery enrichment (ChEMBL, FDA Drug, AlphaFold) ─────────
    # Uses cached data from the annotation row when available;
    # falls back to live BigQuery queries, then persists results.
    gene_symbol = None
    transcripts = response.get("transcripts", [])
    if transcripts:
        gene_symbol = transcripts[0].get("gene_symbol")

    BQ_SOURCES = {"chembl", "fda_drug", "alphafold"}
    bq_columns = {"chembl": "chembl_data", "fda_drug": "fda_drug_data", "alphafold": "alphafold_data"}

    # Determine which BQ sources are enabled
    try:
        src_result = await db.execute(
            select(AnnotationSourceConfig.source_name, AnnotationSourceConfig.is_enabled)
            .where(AnnotationSourceConfig.source_name.in_(list(BQ_SOURCES)))
        )
        src_rows = src_result.all()
        enabled_bq = {name for name, enabled in src_rows if enabled} if src_rows else BQ_SOURCES
    except Exception:
        enabled_bq = BQ_SOURCES  # table not seeded yet — enable all

    # Check what's already cached
    needs_fetch: set = set()
    for src in enabled_bq:
        col_attr = bq_columns[src]
        cached = getattr(annotation, col_attr, None)
        if cached and isinstance(cached, dict):
            response[src] = cached
        else:
            needs_fetch.add(src)

    # Fetch missing data from BigQuery and cache it
    if needs_fetch and gene_symbol:
        try:
            from backend.services.bq_public import get_bq_public_service
            bq_svc = get_bq_public_service()
            enrichment = await bq_svc.enrich_variant(
                gene_symbol=gene_symbol,
                enabled_sources=needs_fetch,
            )
            dirty = False
            for src, data in enrichment.items():
                if src in bq_columns and data:
                    setattr(annotation, bq_columns[src], data)
                    response[src] = data
                    dirty = True
            if dirty:
                await db.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("BigQuery enrichment failed: %s", e)

    return response


@router.get("/drug-response/{gene}")
async def get_drug_response_info(
    gene: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get enhanced pharmacogenomic information for a specific gene
    
    Supported genes include:
    - CYP2D6, CYP2C19, CYP3A4 (drug metabolism)
    - SLCO1B1 (statin transport)
    - GNB3 (cardiovascular drug response)
    - ERCC1 (chemotherapy response)
    - ABCB1 (drug transport/efflux)
    """
    try:
        async with GeneticAPIService() as api_service:
            result = await api_service.get_clinpgx_drug_info(gene)
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drug response lookup failed: {str(e)}")

@router.get("/snpedia/{rsid}")
async def get_snpedia_annotation(
    rsid: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get variant annotation from SNPedia using MediaWiki API
    
    Returns community-curated information including magnitude,
    frequency, and clinical significance where available.
    """
    try:
        async with GeneticAPIService() as api_service:
            result = await api_service.get_snpedia_info(rsid)
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SNPedia lookup failed: {str(e)}")

@router.get("/ensembl/{rsid}")
async def get_ensembl_annotation(
    rsid: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed variant information from Ensembl REST API
    
    Returns comprehensive data including population frequencies,
    consequence predictions, and functional annotations.
    """
    try:
        async with GeneticAPIService() as api_service:
            result = await api_service.get_variant_info_from_ensembl(rsid)
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ensembl lookup failed: {str(e)}")

@router.get("/clinvar/{rsid}")
async def get_clinvar_annotation(
    rsid: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get clinical variant annotation from ClinVar using NCBI E-utilities
    
    Returns clinical significance, associated conditions,
    and submission details from ClinVar database.
    """
    try:
        async with GeneticAPIService() as api_service:
            result = await api_service.get_variant_info_from_clinvar(rsid)
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ClinVar lookup failed: {str(e)}")

@router.get("/supported-apis")
async def get_supported_apis():
    """
    List all supported external APIs and their enhanced capabilities
    """
    return {
        "apis": [
            {
                "name": "NCBI E-utilities",
                "url": "https://eutils.ncbi.nlm.nih.gov",
                "description": "Unified access to NCBI databases including ClinVar and PubMed",
                "data_types": ["clinical_significance", "literature_search", "variant_submissions"],
                "methods": ["ESearch", "EFetch"],
                "rate_limit": "3 requests per second",
                "free": True
            },
            {
                "name": "LitVar API",
                "url": "https://www.ncbi.nlm.nih.gov/research/litvar2-api",
                "description": "Literature variants - connecting genomic variants to publications",
                "data_types": ["variant_literature", "pmids", "variant_gene_disease_drug_relations"],
                "rate_limit": "10 requests per second",
                "free": True
            },
            {
                "name": "SNPedia MediaWiki API",
                "url": "https://bots.snpedia.com/api.php",
                "description": "Community-curated genetic variant annotations",
                "data_types": ["magnitude", "summary", "frequency", "genotype_interpretations"],
                "rate_limit": "No strict limit",
                "free": True
            },
            {
                "name": "Ensembl REST API",
                "url": "https://rest.ensembl.org",
                "description": "Comprehensive genomic annotations and variant consequences",
                "data_types": ["variant_info", "consequences", "population_frequencies", "vep_annotations"],
                "rate_limit": "15 requests per second",
                "free": True
            },
            {
                "name": "ClinVar (via NCBI E-utilities)",
                "url": "https://eutils.ncbi.nlm.nih.gov",
                "description": "Clinical variant interpretations and submissions",
                "data_types": ["clinical_significance", "pathogenicity", "variant_submissions", "conditions"],
                "rate_limit": "3 requests per second",
                "free": True
            },
            {
                "name": "ClinPGx API",
                "url": "https://api.clinpgx.org",
                "description": "Pharmacogenomic annotations and drug interactions (formerly PharmGKB)",
                "data_types": ["drug_response", "dosing_guidelines", "clinical_annotations", "phenotypes"],
                "rate_limit": "2 requests per second",
                "free": True
            }
        ],
        "new_features": [
            "NCBI E-utilities integration for comprehensive database access",
            "LitVar API for variant-literature connections",
            "SNPedia MediaWiki API for community annotations",
            "Enhanced ClinVar data with XML parsing",
            "Improved rate limiting and error handling",
            "Clinical summary aggregation across all sources"
        ],
        "usage_examples": [
            {
                "endpoint": "/api/annotations/variant",
                "example": {
                    "rsid": "rs5443",
                    "gene": "GNB3"
                },
                "response_data": "Ensembl + ClinVar + SNPedia + LitVar annotations"
            },
            {
                "endpoint": "/api/annotations/clinical-summary",
                "example": {
                    "rsid": "rs5443",
                    "gene": "GNB3"
                },
                "response_data": "Unified clinical interpretation with recommendations"
            },
            {
                "endpoint": "/api/annotations/literature",
                "example": {
                    "rsid": "rs5443"
                },
                "response_data": "PubMed publications mentioning the variant"
            }
        ]
    }

@router.get("/examples")
async def get_annotation_examples():
    """
    Get enhanced example variants with known clinical significance
    """
    return {
        "cardiovascular": [
            {
                "rsid": "rs5443",
                "gene": "GNB3",
                "variant": "c.825C>T",
                "drugs": ["sildenafil", "antihypertensives"],
                "clinical_significance": "drug response - efficacy variation",
                "frequency": "46.124%",
                "available_data": ["Ensembl", "ClinVar", "SNPedia", "Literature"]
            }
        ],
        "oncology": [
            {
                "rsid": "rs11615", 
                "gene": "ERCC1",
                "variant": "c.354T>C",
                "drugs": ["cisplatin", "carboplatin", "oxaliplatin"],
                "clinical_significance": "chemotherapy response - efficacy and toxicity",
                "frequency": "57.54%",
                "available_data": ["Ensembl", "ClinVar", "Literature"]
            }
        ],
        "metabolism": [
            {
                "rsid": "rs1045642",
                "gene": "ABCB1",
                "variant": "c.3435C>T",
                "drugs": ["digoxin", "fexofenadine", "dabigatran"],
                "clinical_significance": "drug transport - P-glycoprotein substrate clearance",
                "frequency": "40-60%",
                "available_data": ["Ensembl", "ClinVar", "ClinPGx"]
            }
        ],
        "high_impact": [
            {
                "rsid": "rs121909001",
                "gene": "CFTR",
                "variant": "c.1521_1523delCTT",
                "condition": "Cystic fibrosis",
                "clinical_significance": "pathogenic",
                "available_data": ["ClinVar", "Literature", "Ensembl"]
            }
        ]
    }