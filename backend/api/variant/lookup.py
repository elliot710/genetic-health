"""Variant lookup route (POST /api/variants/lookup) — split out of variant_routes.py.
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

from backend.api.variant.helpers import (
    VariantLookupRequest,
    VariantLookupResponse,
    validate_variant_id,
    _create_multi_source_mappings,
    _generate_external_links,
    _build_variant_lookup_description,
)

router = APIRouter(prefix="/api/variants", tags=["variants"])


@router.post("/lookup", response_model=VariantLookupResponse)
@limiter.limit(lambda: f"{settings.rate_limit.lookup_per_minute}/minute")
async def lookup_variant(
    request: Request,
    payload: VariantLookupRequest,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """
    Comprehensive variant lookup with enhanced data from multiple sources
    
    This endpoint provides:
    - Basic variant information (name, consequence, allele frequencies)
    - Clinical significance from ClinVar
    - Population data from Ensembl
    - Pharmacogenomic data from ClinPGx
    - Literature evidence from PubMed/LitVar
    - External resource links
    
    Supported variant formats:
    - rsID: rs12202969, rs53576
    - Chromosome position: chr1:12345, 1:12345
    - Gene variants: APOE4, MTHFR677T
    """
    
    variant_id = payload.variant_id.strip()
    
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
        if not payload.force_refresh:
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

                # Create multi-source mappings from cached data
                if resp.get("found"):
                    try:
                        await _create_multi_source_mappings(session, variant_id, resp)
                        await session.commit()
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning("Multi-source mapping failed (cached) for %s: %s", variant_id, e)
                        await session.rollback()
                
                return VariantLookupResponse(
                    variant_id=variant_id,
                    found=resp.get('found', False),
                    source=resp.get('source', 'Multiple databases'),
                    search_timestamp=resp.get('search_timestamp', ''),
                    description=resp.get('description') or _build_variant_lookup_description(
                        variant_id,
                        resp.get('basic_info', {}),
                        resp.get('clinical_significance', []),
                        resp.get('annotations', {}).get('clinvar', {}),
                        resp.get('pharmacogenomics', {}),
                    ),
                    basic_info=resp.get('basic_info', {}),
                    clinical_significance=resp.get('clinical_significance', []),
                    population_data=resp.get('population_data', {}),
                    pharmacogenomics=resp.get('pharmacogenomics', {}),
                    literature=resp.get('literature', {}),
                    alpha_missense=resp.get('alpha_missense'),
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
            clinpgx_data = annotations.get('clinpgx', {})
            if clinpgx_data and clinpgx_data.get('found'):
                pharmacogenomics = {
                    "found": True,
                    "data": clinpgx_data.get('data', {}),
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
            
            # AlphaMissense local lookup (AI prediction, NOT clinically validated)
            alpha_missense = {}
            if ensembl_entry:
                chrom = ensembl_entry.get('seq_region_name')
                pos = ensembl_entry.get('start')
                allele_str = ensembl_entry.get('allele_string', '')
                allele_parts = allele_str.split('/') if allele_str else []
                if chrom and pos and len(allele_parts) == 2:
                    ref_a, alt_a = allele_parts[0], allele_parts[1]
                    if len(ref_a) == 1 and len(alt_a) == 1:
                        am_svc = get_alpha_missense_service()
                        formatted = am_svc.lookup_comprehensive(str(chrom), int(pos), ref_a, alt_a)
                        if formatted:
                            alpha_missense = formatted

            # ── Local data source enrichment ─────────────────────────
            import logging as _log
            _logger = _log.getLogger(__name__)

            # ClinVar local DB
            try:
                clinvar_local_svc = get_clinvar_local_service()
                await clinvar_local_svc.ensure_loaded()
                clinvar_local_result = await clinvar_local_svc.lookup(variant_id)
                if clinvar_local_result:
                    annotations['clinvar_local'] = clinvar_local_result
                    # Supplement gene if not found from Ensembl remote
                    if not basic_info.get('gene_symbol') and clinvar_local_result.get('genes'):
                        basic_info['gene_symbol'] = clinvar_local_result['genes'][0]
                    # Supplement clinical significance
                    local_clinsig = clinvar_local_result.get('clinical_significance')
                    if local_clinsig and local_clinsig not in clinical_significance:
                        clinical_significance.append(local_clinsig)
            except Exception as e:
                _logger.debug("ClinVar local lookup failed for %s: %s", variant_id, e)

            # gnomAD local DB (local only — no BQ fallback for speed)
            try:
                gnomad_svc = get_gnomad_service()
                await gnomad_svc.ensure_loaded()
                gnomad_result = await gnomad_svc.lookup(variant_id, local_only=True)
                if gnomad_result and gnomad_result.get('found'):
                    annotations['gnomad_local'] = gnomad_result
            except Exception as e:
                _logger.debug("gnomAD local lookup failed for %s: %s", variant_id, e)

            # Ensembl local gene info (position-based)
            gene_symbol = basic_info.get('gene_symbol')
            try:
                ensembl_local_svc = get_ensembl_local_service()
                chrom = basic_info.get('chromosome') or (ensembl_entry.get('seq_region_name') if ensembl_entry else None)
                pos_val = basic_info.get('start') or (ensembl_entry.get('start') if ensembl_entry else None)
                if chrom and pos_val:
                    ensembl_local_result = await ensembl_local_svc.lookup_gene_by_position(str(chrom), int(pos_val))
                    if ensembl_local_result and ensembl_local_result.get('found'):
                        annotations['ensembl_local'] = ensembl_local_result
                        if not gene_symbol:
                            gene_symbol = ensembl_local_result.get('gene_symbol')
                            basic_info['gene_symbol'] = gene_symbol
                # Also fetch full gene info if we have a symbol
                if gene_symbol:
                    gene_info = await ensembl_local_svc.lookup_gene(gene_symbol)
                    if gene_info and gene_info.get('found'):
                        annotations.setdefault('ensembl_local', {}).update(gene_info)
            except Exception as e:
                _logger.debug("Ensembl local lookup failed for %s: %s", variant_id, e)

            # gnomAD gene constraint (if gene known)
            if gene_symbol:
                try:
                    gnomad_svc = get_gnomad_service()
                    constraint = await gnomad_svc.get_gene_constraint(gene_symbol)
                    if constraint:
                        annotations['gnomad_constraint'] = constraint
                except Exception as e:
                    _logger.debug("gnomAD constraint failed for %s: %s", gene_symbol, e)

            # BigQuery enrichment: ChEMBL drugs, AlphaFold, FDA (if gene known)
            if gene_symbol:
                try:
                    bq_svc = BigQueryPublicService()
                    bq_data = await bq_svc.enrich_variant(
                        gene_symbol, {"chembl", "alphafold", "fda_drug"}
                    )
                    for source_name, source_data in bq_data.items():
                        if source_data and source_data.get('found', False):
                            annotations[f'bq_{source_name}'] = source_data
                except Exception as e:
                    _logger.debug("BQ enrichment failed for %s: %s", gene_symbol, e)

            # GWAS Catalog local lookup
            try:
                gwas_svc = get_gwas_catalog_service()
                await gwas_svc.ensure_loaded()
                gwas_batch = await gwas_svc.lookup_batch([variant_id])
                gwas_result = gwas_batch.get(variant_id)
                if gwas_result and gwas_result.get('found'):
                    annotations['gwas_catalog'] = gwas_result
            except Exception as e:
                _logger.debug("GWAS Catalog lookup failed for %s: %s", variant_id, e)

            # ClinGen gene validity (requires gene symbol)
            if gene_symbol:
                try:
                    clingen_svc = get_clingen_service()
                    await clingen_svc.ensure_loaded()
                    clingen_result = await clingen_svc.lookup_by_gene(gene_symbol)
                    if clingen_result and clingen_result.get('found'):
                        annotations['clingen'] = clingen_result
                except Exception as e:
                    _logger.debug("ClinGen lookup failed for %s: %s", gene_symbol, e)

            # Open Targets gene-disease associations (requires gene symbol)
            if gene_symbol:
                try:
                    ot_svc = get_open_targets_service()
                    ot_result = await ot_svc.lookup_by_gene(gene_symbol)
                    if ot_result and ot_result.get('found'):
                        annotations['open_targets'] = ot_result
                except Exception as e:
                    _logger.debug("Open Targets lookup failed for %s: %s", gene_symbol, e)

            # Transcript consequences from Ensembl VEP
            if ensembl_entry:
                tcs = ensembl_entry.get('transcript_consequences', [])
                if tcs:
                    annotations['transcript_consequences'] = tcs[:25]

            # Determine if variant was found
            found = any([
                basic_info.get('name'),
                clinical_significance,
                population_data.get('minor_allele'),
                pharmacogenomics.get('found'),
                literature.get('snpedia_found'),
                annotations.get('clinvar_local'),
                annotations.get('gnomad_local', {}).get('found'),
                annotations.get('ensembl_local', {}).get('found'),
            ])
            
            # Build response data to cache
            now = datetime.now()

            # Generate natural language description
            description = _build_variant_lookup_description(
                variant_id, basic_info, clinical_significance, clinvar_data, pharmacogenomics
            )

            response_data = {
                "found": found,
                "source": "Multiple databases",
                "search_timestamp": now.isoformat(),
                "description": description,
                "basic_info": basic_info,
                "clinical_significance": clinical_significance,
                "population_data": population_data,
                "pharmacogenomics": pharmacogenomics,
                "literature": literature,
                "alpha_missense": alpha_missense,
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
            
            # Auto-discover panel markers and variant mappings for admin review
            if found:
                try:
                    user_id = current_user.id if current_user else None
                    await process_lookup_discoveries(session, variant_id, response_data, user_id)
                    await session.commit()
                except Exception:
                    await session.rollback()

                # Multi-source direct mapping creation
                try:
                    await _create_multi_source_mappings(session, variant_id, response_data)
                    await session.commit()
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("Multi-source mapping failed for %s: %s", variant_id, e)
                    await session.rollback()
            
            return VariantLookupResponse(
                variant_id=variant_id,
                found=found,
                source="Multiple databases",
                search_timestamp=now.isoformat(),
                description=description,
                basic_info=basic_info,
                clinical_significance=clinical_significance,
                population_data=population_data,
                pharmacogenomics=pharmacogenomics,
                literature=literature,
                alpha_missense=alpha_missense if alpha_missense else None,
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
