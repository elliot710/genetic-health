"""
API routes for genetic variant annotation using external services
Enhanced with NCBI E-utilities, LitVar, SNPedia, ClinVar, and Ensembl APIs
"""
import re
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.services.genetic_api_service import GeneticAPIService
from backend.db.database import get_session
from backend.db.models import SharedVariantAnnotation, VariantLookupCache, AnnotationSourceConfig, DashboardCache, GeneticAnalysis, AnalysisVariant, GeneticMarker
from backend.utils.alpha_missense import get_alpha_missense_service, AlphaMissenseService
from .auth_routes import get_current_user
from backend.db.schemas import User

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


def _clean_snpedia_text(wiki_text: str) -> str:
    """Extract a human-readable summary from raw SNPedia MediaWiki markup.

    Strategy:
    1. Try to pull the |Summary= field from {{Rsnum...}} template.
    2. Strip all {{ ... }} template blocks (Rsnum, ClinVar, population diversity, etc.).
    3. Convert wiki links [[target|label]] → label, [[target]] → target.
    4. Convert external links [url label] → label.
    5. Strip remaining markup artifacts and collapse whitespace.
    """
    if not wiki_text:
        return ""

    # 1. Try to extract |Summary= from {{Rsnum...}} template
    rsnum_summary = ""
    m = re.search(r'\|Summary\s*=\s*([^\n|]+)', wiki_text)
    if m:
        rsnum_summary = m.group(1).strip()

    # 2. Strip all template blocks {{ ... }} including nested/multiline
    # Process from innermost outward to handle nesting
    cleaned = wiki_text
    for _ in range(10):  # max depth
        prev = cleaned
        cleaned = re.sub(r'\{\{[^{}]*\}\}', ' ', cleaned)
        if cleaned == prev:
            break
    # Strip any remaining unclosed template starts
    cleaned = re.sub(r'\{\{[^}]*$', '', cleaned, flags=re.MULTILINE)

    # 3. Convert wiki links: [[target|label]] → label, [[target]] → target
    cleaned = re.sub(r'\[\[([^|\]]+)\|([^\]]+)\]\]', r'\2', cleaned)
    cleaned = re.sub(r'\[\[([^\]]+)\]\]', r'\1', cleaned)

    # 4. Convert external links: [url label] → label, [url] → (drop)
    cleaned = re.sub(r'\[https?://[^\]\s]+\s+([^\]]+)\]', r'\1', cleaned)
    cleaned = re.sub(r'\[https?://[^\]\s]+\]', '', cleaned)

    # 5. Strip Category links, HTML tags, residual markup
    cleaned = re.sub(r'\[\[Category:[^\]]*\]\]', '', cleaned)
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    cleaned = re.sub(r"'{2,}", '', cleaned)  # bold/italic wiki markup

    # 6. Collapse whitespace, trim
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # If we got a good cleaned body, use it; otherwise fall back to |Summary=
    if len(cleaned) > 20:
        return cleaned[:800]
    if rsnum_summary:
        return rsnum_summary
    return cleaned[:800]


def _is_noise_condition(s: str) -> bool:
    """Return True for placeholder condition strings that carry no clinical meaning."""
    lower = s.lower().strip()
    return lower in ("not provided", "not specified", "see cases", "")


def _split_condition_string(raw: str) -> list[str]:
    """Split a raw ClinVar condition string on pipe and semicolon delimiters."""
    parts: list[str] = []
    for chunk in raw.split("|"):
        for sub in chunk.split(";"):
            cleaned = sub.strip()
            if cleaned and not _is_noise_condition(cleaned):
                parts.append(cleaned)
    return parts


def _is_hgvs_name(title: str) -> bool:
    """Heuristic: real HGVS names contain ':c.' / ':p.' / ':g.' or 'NM_' / 'NC_' prefixes."""
    return bool(title) and (":c." in title or ":p." in title or ":g." in title
                            or title.startswith("NM_") or title.startswith("NC_")
                            or title.startswith("NR_"))


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
        # Only accept titles that look like real HGVS nomenclature
        if title and not hgvs_name and _is_hgvs_name(title):
            hgvs_name = title
        vt = entry.get("variation_type", "")
        if vt and not clinvar_variation_type:
            clinvar_variation_type = vt
        conditions = entry.get("conditions", [])
        for cond_str in conditions:
            all_conditions.extend(_split_condition_string(cond_str))

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
    refresh: bool = False,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get a comprehensive clinical summary combining all data sources.
    Serves from SharedVariantAnnotation cache when available.
    Pass ?refresh=true to force a fresh fetch from external APIs.
    """
    rsid = request.rsid
    gene = request.gene

    # ── Build empty summary skeleton ──
    summary: Dict[str, Any] = {
        'rsid': rsid,
        'gene': gene,
        'clinical_significance': 'unknown',
        'population_frequency': None,
        'drug_responses': [],
        'literature_count': 0,
        'sources': [],
    }

    # ── Step 1: Check DB cache unless refresh requested ──
    if not refresh:
        result = await db.execute(
            select(SharedVariantAnnotation).where(SharedVariantAnnotation.rsid == rsid)
        )
        cached = result.scalar_one_or_none()

        if cached and (cached.ensembl_data or cached.clinvar_data or cached.pharmgkb_data or cached.snpedia_data):
            return _build_clinical_summary_from_cache(cached, rsid, gene)

    # ── Step 2: Cache miss or refresh — fetch live, persist, and build summary ──
    try:
        async with GeneticAPIService() as api_service:
            raw_ann = await api_service.annotate_variant(rsid)
        raw = raw_ann.get("annotations", {}) if raw_ann else {}

        # Persist raw annotations so future calls are served from cache
        if raw:
            try:
                from backend.db.models import GeneticMarker
                existing = await db.execute(
                    select(SharedVariantAnnotation).where(SharedVariantAnnotation.rsid == rsid)
                )
                existing_ann = existing.scalar_one_or_none()
                if existing_ann:
                    existing_ann.ensembl_data = raw.get("ensembl") or existing_ann.ensembl_data
                    existing_ann.clinvar_data = raw.get("clinvar") or existing_ann.clinvar_data
                    existing_ann.pharmgkb_data = raw.get("clinpgx") or existing_ann.pharmgkb_data
                    existing_ann.snpedia_data = raw.get("snpedia") or existing_ann.snpedia_data
                    existing_ann.litvar_data = raw.get("litvar") or existing_ann.litvar_data
                    await db.commit()
                else:
                    marker_result = await db.execute(
                        select(GeneticMarker).where(GeneticMarker.rsid == rsid)
                    )
                    marker = marker_result.scalar_one_or_none()
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
            except Exception:
                pass  # Cache persistence is best-effort

        # Build summary from the raw annotations
        clinvar = raw.get('clinvar', {})
        if isinstance(clinvar, dict) and clinvar.get('found'):
            summary['sources'].append('clinvar')
            summary['clinical_significance'] = 'Reported in ClinVar'
            summary['clinvar_ids'] = clinvar.get('ids', [])

        ensembl = raw.get('ensembl', {})
        if isinstance(ensembl, dict) and ensembl.get('found'):
            summary['sources'].append('ensembl')
            data = ensembl.get('data', [])
            if isinstance(data, list) and data:
                vep = data[0]
                freqs = vep.get('colocated_variants', [{}])
                if freqs:
                    freq_data = freqs[0].get('frequencies', {})
                    if freq_data:
                        summary['population_frequency'] = freq_data
                consequences = vep.get('most_severe_consequence', '')
                if consequences:
                    summary['consequence'] = consequences.replace('_', ' ')

        clinpgx = raw.get('clinpgx', {})
        if isinstance(clinpgx, dict) and clinpgx.get('found'):
            summary['sources'].append('clinpgx')

        snpedia = raw.get('snpedia', {})
        if isinstance(snpedia, dict) and snpedia.get('found'):
            summary['sources'].append('snpedia')

        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clinical summary failed: {str(e)}")


def _build_clinical_summary_from_cache(
    cached: SharedVariantAnnotation, rsid: str, gene: Optional[str]
) -> Dict[str, Any]:
    """Build a clinical summary dict from cached SharedVariantAnnotation data."""
    summary: Dict[str, Any] = {
        'rsid': rsid,
        'gene': gene,
        'clinical_significance': 'unknown',
        'population_frequency': None,
        'drug_responses': [],
        'literature_count': 0,
        'sources': [],
    }

    # ClinVar
    clinvar = cached.clinvar_data
    if isinstance(clinvar, dict) and clinvar.get('found'):
        summary['sources'].append('clinvar')
        summary['clinical_significance'] = 'Reported in ClinVar'
        summary['clinvar_ids'] = clinvar.get('ids', [])

    # Ensembl
    ensembl = cached.ensembl_data
    if isinstance(ensembl, dict) and ensembl.get('found'):
        summary['sources'].append('ensembl')
        data = ensembl.get('data', [])
        if isinstance(data, list) and data:
            vep = data[0]
            freqs = vep.get('colocated_variants', [{}])
            if freqs:
                freq_data = freqs[0].get('frequencies', {})
                if freq_data:
                    summary['population_frequency'] = freq_data
            consequences = vep.get('most_severe_consequence', '')
            if consequences:
                summary['consequence'] = consequences.replace('_', ' ')

    # ClinPGx
    clinpgx = cached.pharmgkb_data
    if isinstance(clinpgx, dict) and clinpgx.get('found'):
        summary['sources'].append('clinpgx')

    # SNPedia
    snpedia = cached.snpedia_data
    if isinstance(snpedia, dict) and snpedia.get('found'):
        summary['sources'].append('snpedia')

    # AlphaMissense from cache
    am = cached.alpha_missense_data
    if isinstance(am, dict) and am.get('found'):
        summary['alpha_missense'] = {
            'am_pathogenicity': am.get('am_pathogenicity'),
            'am_class': am.get('am_class'),
        }

    return summary

@router.get("/variant-details/{rsid}")
async def get_variant_details(
    rsid: str,
    refresh: bool = False,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get structured annotation details for a variant from the database.
    Falls back to live API fetch when no cached annotation exists.
    Pass ?refresh=true to force a fresh fetch from external APIs.
    """
    annotation = None
    cache_hit = False

    if not refresh:
        result = await db.execute(
            select(SharedVariantAnnotation).where(SharedVariantAnnotation.rsid == rsid)
        )
        annotation = result.scalar_one_or_none()
        if annotation:
            cache_hit = True

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

            if refresh:
                # Update existing annotation in-place
                existing = await db.execute(
                    select(SharedVariantAnnotation).where(SharedVariantAnnotation.rsid == rsid)
                )
                existing_ann = existing.scalar_one_or_none()
                if existing_ann:
                    existing_ann.ensembl_data = raw.get("ensembl")
                    existing_ann.clinvar_data = raw.get("clinvar")
                    existing_ann.pharmgkb_data = raw.get("clinpgx")
                    existing_ann.snpedia_data = raw.get("snpedia")
                    existing_ann.litvar_data = raw.get("litvar")
                    # Invalidate dashboard cache so pathogenicity scores recompute
                    await db.execute(
                        DashboardCache.__table__.delete().where(
                            DashboardCache.user_id == current_user.id
                        )
                    )
                    await db.commit()
                    await db.refresh(existing_ann)
                    annotation = existing_ann
                else:
                    refresh = False  # No existing row, insert below

            if not annotation:
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

    response: Dict[str, Any] = {"found": True, "rsid": rsid, "cache_hit": cache_hit}

    # Look up the current user's genotype for this variant from their latest analysis
    try:
        geno_result = await db.execute(
            select(AnalysisVariant.genotype)
            .join(GeneticMarker, GeneticMarker.id == AnalysisVariant.marker_id)
            .join(GeneticAnalysis, GeneticAnalysis.id == AnalysisVariant.analysis_id)
            .where(
                GeneticMarker.rsid == rsid,
                GeneticAnalysis.user_id == current_user.id,
                GeneticAnalysis.deleted_at.is_(None),
            )
            .order_by(GeneticAnalysis.id.desc())
            .limit(1)
        )
        user_genotype = geno_result.scalar_one_or_none()
        if user_genotype:
            response["user_genotype"] = user_genotype
    except Exception:
        pass

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
        # Clean conditions: split pipe/semicolon delimiters, filter noise, deduplicate
        for entry in clinvar_entries:
            raw_conds = entry.get("conditions", [])
            cleaned: list[str] = []
            for c in raw_conds:
                cleaned.extend(_split_condition_string(c))
            entry["conditions"] = list(dict.fromkeys(cleaned))

        response["clinvar"] = {
            "found": True,
            "count": clinvar.get("count", 0),
            "ids": clinvar.get("ids", []),
            "entries": clinvar_entries,
        }

    # Process ClinVar local data (curated from local ClinVar DB — richer than API)
    cv_local = annotation.clinvar_local_data
    if cv_local and isinstance(cv_local, dict) and cv_local.get("found"):
        cv_local_resp: Dict[str, Any] = {
            "found": True,
            "genes": cv_local.get("genes", []),
            "clinical_significances": cv_local.get("clinical_significances", []),
            "gene_conditions": cv_local.get("gene_conditions", []),
            "review_statuses": cv_local.get("review_statuses", []),
            "has_conflicting_interpretations": cv_local.get("has_conflicting_interpretations", False),
        }
        vcf = cv_local.get("vcf_data", {})
        if vcf:
            cv_local_resp["molecular_consequences"] = vcf.get("molecular_consequences", [])
            cv_local_resp["conflicting_classifications"] = vcf.get("conflicting_classifications", [])
            cv_local_resp["allele_frequencies"] = vcf.get("allele_frequencies", {})
        gene_stats = cv_local.get("gene_stats", [])
        if gene_stats:
            cv_local_resp["gene_stats"] = gene_stats
        response["clinvar_local"] = cv_local_resp

        # Backfill clinvar entries from local data if API entries are empty
        if "clinvar" not in response or not response.get("clinvar", {}).get("entries"):
            entries = cv_local.get("entries", [])
            if entries:
                # Clean conditions in local entries too
                for entry in entries:
                    raw_conds = entry.get("conditions", [])
                    cleaned_local: list[str] = []
                    for c in raw_conds:
                        cleaned_local.extend(_split_condition_string(c))
                    entry["conditions"] = list(dict.fromkeys(cleaned_local))
                response["clinvar"] = {
                    "found": True,
                    "count": cv_local.get("count", len(entries)),
                    "ids": cv_local.get("ids", []),
                    "entries": entries,
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
        summary = _clean_snpedia_text(wiki_text)
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

    # Process gnomAD tx_annotated data (gene/consequence/LoF/GTEx tissue expression)
    gtx_raw = annotation.gnomad_tx_data
    if gtx_raw and isinstance(gtx_raw, dict) and gtx_raw.get("found"):
        gtx_resp: Dict[str, Any] = {
            "found": True,
            "source": "gnomad_tx",
            "gene": gtx_raw.get("gene"),
            "consequence": gtx_raw.get("consequence"),
            "lof": gtx_raw.get("lof"),
            "mean_expression": gtx_raw.get("mean_expression"),
            "transcript_count": gtx_raw.get("transcript_count", 0),
        }
        transcripts = gtx_raw.get("transcripts", [])
        if transcripts:
            # Include top tissues from the primary transcript
            primary = transcripts[0]
            if primary.get("top_tissues"):
                gtx_resp["top_tissues"] = primary["top_tissues"]
            gtx_resp["transcripts"] = transcripts
        response["gnomad_tx"] = gtx_resp

    # Process 1000 Genomes Phase 3 data (super-population allele frequencies)
    tkg_raw = annotation.thousand_genomes_data
    if tkg_raw and isinstance(tkg_raw, dict) and tkg_raw.get("found"):
        tkg_resp: Dict[str, Any] = {
            "found": True,
            "source": tkg_raw.get("source", "1000genomes_local"),
            "variant_type": tkg_raw.get("variant_type"),
            "minor_allele": tkg_raw.get("minor_allele"),
            "maf": tkg_raw.get("maf"),
            "mac": tkg_raw.get("mac"),
            "ancestral_allele": tkg_raw.get("ancestral_allele"),
        }
        pop_freqs = tkg_raw.get("population_frequencies", {})
        if pop_freqs:
            tkg_resp["population_frequencies"] = pop_freqs
        response["thousand_genomes"] = tkg_resp

    # Generate natural language variant description from combined sources (after all processing)
    response["description"] = _build_variant_description(rsid, response)

    # Backfill clinical_significance from ClinVar entries when Ensembl colocated_variants
    # didn't return clin_sig (e.g. stale cached Ensembl data without colocated annotations).
    if not response.get("clinical_significance"):
        cv = response.get("clinvar", {})
        sigs: list[str] = []
        for entry in cv.get("entries", []):
            for sig in entry.get("clinical_significance", []):
                if sig and sig not in sigs:
                    sigs.append(sig)
        # Also check clinvar_local clinical_significances
        if not sigs:
            cv_local = annotation.clinvar_local_data
            if cv_local and isinstance(cv_local, dict):
                for sig in cv_local.get("clinical_significances", []):
                    if sig and sig not in sigs:
                        sigs.append(sig)
        if sigs:
            response["clinical_significance"] = sigs

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
    if annotation.thousand_genomes_data:
        scoring_annotations["thousand_genomes"] = annotation.thousand_genomes_data
    if annotation.gwas_catalog_data:
        scoring_annotations["gwas_catalog"] = annotation.gwas_catalog_data
    if annotation.clingen_data:
        scoring_annotations["clingen"] = annotation.clingen_data
    if annotation.open_targets_data:
        scoring_annotations["open_targets"] = annotation.open_targets_data
    response["pathogenicity_score"] = get_scoring_engine().score_variant(scoring_annotations)

    # ── Expose GWAS Catalog, ClinGen, Open Targets data in response ─────
    gwas_raw = annotation.gwas_catalog_data
    if gwas_raw and isinstance(gwas_raw, dict) and gwas_raw.get("found"):
        response["gwas_catalog"] = {
            "found": True,
            "source": "gwas_catalog",
            "associations": gwas_raw.get("associations", [])[:10],
            "top_trait": gwas_raw.get("top_trait"),
            "top_p_value": gwas_raw.get("top_p_value"),
            "genome_wide_significant": gwas_raw.get("genome_wide_significant", False),
        }

    clingen_raw = annotation.clingen_data
    if clingen_raw and isinstance(clingen_raw, dict) and clingen_raw.get("found"):
        response["clingen"] = {
            "found": True,
            "source": "clingen",
            "gene_symbol": clingen_raw.get("gene_symbol"),
            "strongest_classification": clingen_raw.get("strongest_classification"),
            "is_definitive": clingen_raw.get("is_definitive", False),
            "is_disputed": clingen_raw.get("is_disputed", False),
            "disease_count": clingen_raw.get("disease_count", 0),
            "curations": clingen_raw.get("curations", [])[:8],
        }

    # ── BigQuery enrichment (ChEMBL, FDA Drug, AlphaFold) + Open Targets API ──
    # Uses cached data from the annotation row when available;
    # falls back to live queries, then persists results.
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

    # ── Open Targets Platform (gene-disease associations) ────────────────
    if gene_symbol and not (annotation.open_targets_data and isinstance(annotation.open_targets_data, dict) and annotation.open_targets_data.get("found")):
        try:
            from backend.services.open_targets_service import get_open_targets_service
            ot_svc = get_open_targets_service()
            ot_data = await ot_svc.lookup_by_gene(gene_symbol)
            annotation.open_targets_data = ot_data
            await db.commit()
        except Exception as ot_exc:
            import logging
            logging.getLogger(__name__).debug("Open Targets lookup failed: %s", ot_exc)
            ot_data = {}
    else:
        ot_data = annotation.open_targets_data or {}

    if ot_data and isinstance(ot_data, dict) and ot_data.get("found"):
        response["open_targets"] = {
            "found": True,
            "source": "open_targets",
            "gene_symbol": ot_data.get("gene_symbol"),
            "ensembl_id": ot_data.get("ensembl_id"),
            "associations": ot_data.get("associations", [])[:10],
            "top_disease": ot_data.get("top_disease"),
            "max_score": ot_data.get("max_score"),
            "has_strong_genetic_evidence": ot_data.get("has_strong_genetic_evidence", False),
        }
        # Feed into scoring if not already there
        if "open_targets" not in scoring_annotations:
            scoring_annotations["open_targets"] = ot_data
            response["pathogenicity_score"] = get_scoring_engine().score_variant(scoring_annotations)

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