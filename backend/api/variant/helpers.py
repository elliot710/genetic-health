"""Variant-route request/response models and pure helper functions (split out of variant_routes.py).
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


class VariantLookupRequest(BaseModel):
    variant_id: str = Field(..., description="Variant identifier (e.g., rs12202969)")
    include_literature: bool = Field(default=True, description="Include literature search")
    include_clinpgx: bool = Field(default=True, description="Include ClinPGx pharmacogenomic data")
    force_refresh: bool = Field(default=False, description="Force fetch from external sources even if cached")

class VariantLookupResponse(BaseModel):
    variant_id: str
    found: bool
    source: str
    search_timestamp: str
    description: Optional[str] = None
    basic_info: Dict[str, Any]
    clinical_significance: List[str]
    population_data: Dict[str, Any]
    pharmacogenomics: Dict[str, Any]
    literature: Dict[str, Any]
    alpha_missense: Optional[Dict[str, Any]] = None
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


async def _create_multi_source_mappings(
    session: AsyncSession,
    rsid: str,
    response_data: Dict[str, Any],
    min_confidence: float = 0.4,
) -> int:
    """Create VariantMappings from multi-source evidence collected during lookup.

    Upserts mappings: if the category+rsid already exists, it updates sources
    and confidence if the new evidence is stronger.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    annotations = response_data.get("annotations", {})
    gene = response_data.get("basic_info", {}).get("gene_symbol")
    suggestions = categorize_variant(rsid, annotations, gene_hint=gene)
    created = 0

    for s in suggestions:
        if s.confidence < min_confidence:
            continue
        stmt = pg_insert(VariantMapping).values(
            category=s.category,
            map_type="rsid",
            key=rsid,
            data=s.data,
            sources=s.sources,
            confidence=s.confidence,
            is_active=True,
            is_auto_discovered=True,
        ).on_conflict_do_update(
            index_elements=["category", "map_type", "key"],
            set_={
                "data": s.data,
                "sources": s.sources,
                "confidence": s.confidence,
                "is_active": True,
            },
        )
        result = await session.execute(stmt)
        if result.rowcount > 0:
            created += 1

    # Also create gene-level mappings
    if gene:
        from backend.services.multi_source_categorizer import GENE_CATEGORY_MAP
        if gene.upper() in GENE_CATEGORY_MAP:
            for cat in GENE_CATEGORY_MAP[gene.upper()]:
                data = {
                    "gene": gene,
                    "condition": f"{gene} variant",
                    "source": ", ".join(src for s in suggestions for src in s.sources) if suggestions else "lookup",
                }
                stmt = pg_insert(VariantMapping).values(
                    category=cat,
                    map_type="gene",
                    key=gene,
                    data=data,
                    sources=["lookup"],
                    confidence=0.5,
                    is_active=True,
                    is_auto_discovered=True,
                ).on_conflict_do_nothing(
                    index_elements=["category", "map_type", "key"],
                )
                await session.execute(stmt)

    return created


def _generate_external_links(variant_id: str) -> Dict[str, str]:
    """Generate external resource links for a variant"""
    return {
        "dbSNP": f"https://www.ncbi.nlm.nih.gov/snp/{variant_id}",
        "Ensembl": f"https://www.ensembl.org/Homo_sapiens/Variation/Summary?v={variant_id}",
        "ClinVar": f"https://www.ncbi.nlm.nih.gov/clinvar/?term={variant_id}",
        "ClinPGx": f"https://www.clinpgx.org/variant/{variant_id}",
        "SNPedia": f"https://www.snpedia.com/index.php/{variant_id}",
        "PubMed": f"https://pubmed.ncbi.nlm.nih.gov/?term={variant_id}"
    }


def _build_variant_lookup_description(
    variant_id: str,
    basic_info: Dict[str, Any],
    clinical_significance: List[str],
    clinvar_data: Dict[str, Any],
    pharmacogenomics: Dict[str, Any],
) -> str:
    """Build natural language description from variant lookup data."""
    parts = []
    consequence = basic_info.get("most_severe_consequence", "")
    variant_type_label = consequence if consequence else "variant"
    gene = basic_info.get("gene_symbol")

    # HGVS name and conditions from ClinVar entries
    hgvs_name = None
    all_conditions: list[str] = []
    clinvar_variation_type = None
    entries = clinvar_data.get("entries", []) if clinvar_data else []
    for entry in entries:
        title = entry.get("title", "")
        if title and not hgvs_name:
            hgvs_name = title
        vt = entry.get("variation_type", "")
        if vt and not clinvar_variation_type:
            clinvar_variation_type = vt
        for c in entry.get("conditions", []):
            if c and c.lower() not in ("not provided", "not specified"):
                all_conditions.append(c)
    all_conditions = list(dict.fromkeys(all_conditions))

    # Prefer ClinVar variation type over Ensembl consequence
    if clinvar_variation_type:
        variant_type_label = clinvar_variation_type

    # Opening sentence
    if gene and gene != "Unknown" and not gene.startswith("rs"):
        parts.append(f"{variant_id} is a {variant_type_label} in the {gene} gene")
    else:
        parts.append(f"{variant_id} is a {variant_type_label}")

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
    if clinical_significance:
        formatted = [s.replace("_", " ") for s in clinical_significance]
        parts.append(f"Clinical assessments classify it as {', '.join(formatted)}.")

    # Pharmacogenomic note
    if pharmacogenomics and pharmacogenomics.get("found"):
        parts.append("It has known pharmacogenomic associations that may affect drug response.")

    return " ".join(parts) if len(parts) > 1 else parts[0] if parts else ""


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
