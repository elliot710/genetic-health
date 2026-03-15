"""
Shared constants for annotation sources.

Single source of truth for source names, DB column mappings, and source
categories used across admin retrigger endpoints, annotation routes, and
the analysis pipeline.
"""
from typing import Dict, List, Set

# All annotation sources the system knows about
ALL_SOURCES: List[str] = [
    'ensembl', 'clinvar', 'clinpgx', 'snpedia',
    'alpha_missense', 'clinvar_local', 'gnomad', 'thousand_genomes',
    'ensembl_vep',
    'chembl', 'fda_drug', 'alphafold',
]

# Map source name → DB column prefix (e.g. clinpgx data stored in pharmgkb_data)
SOURCE_TO_COLUMN: Dict[str, str] = {
    'ensembl': 'ensembl',
    'clinvar': 'clinvar',
    'clinpgx': 'pharmgkb',
    'snpedia': 'snpedia',
    'alpha_missense': 'alpha_missense',
    'clinvar_local': 'clinvar_local',
    'gnomad': 'gnomad',
    'thousand_genomes': 'thousand_genomes',
    'ensembl_vep': 'ensembl',  # ensembl_vep local uses the same ensembl_data column
    'chembl': 'chembl',
    'fda_drug': 'fda_drug',
    'alphafold': 'alphafold',
}

# Sources that use external HTTP APIs (via OptimizedGeneticAPIService)
REMOTE_API_SOURCES: Set[str] = {'ensembl', 'clinvar', 'clinpgx', 'snpedia'}

# Sources backed by local data (files, local DB tables)
# 'ensembl' is hybrid — uses local VEP VCF when loaded, falls back to API
LOCAL_SOURCES: Set[str] = {'clinvar_local', 'gnomad', 'alpha_missense', 'ensembl', 'thousand_genomes', 'ensembl_vep'}

# Sources backed by BigQuery public datasets
BQ_SOURCES: Set[str] = {'chembl', 'fda_drug', 'alphafold'}


def source_status(data) -> str:
    """Return a human-readable status for an annotation source's data."""
    if data is None:
        return "missing"
    if isinstance(data, dict):
        if data.get('found', False):
            return "found"
        return "no_data"  # confirmed absence
    return "missing"


def get_missing_sources(annotation) -> list:
    """Return list of source names that are missing or unconfirmed for an annotation."""
    missing = []
    for src in ALL_SOURCES:
        col = SOURCE_TO_COLUMN.get(src, src)
        src_data = getattr(annotation, f'{col}_data', None)
        if src_data is None:
            missing.append(src)
        elif isinstance(src_data, dict) and not src_data.get('found', True) and not src_data.get('confirmed_no_data', False):
            missing.append(src)
    return missing
