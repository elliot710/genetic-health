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
    'ensembl_vep', 'gnomad_tx',
    'chembl', 'fda_drug', 'alphafold',
    'gwas_catalog', 'clingen',
    'open_targets',
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
    # INTENTIONAL shared column contract for ensembl_data:
    #   - 'ensembl' (remote REST fallback, hybrid local/remote via
    #     OptimizedGeneticAPIService) and 'ensembl_vep' (local VCF) both
    #     produce VEP consequence annotations and write ensembl_data.
    #     Same logical annotation — do NOT split into separate columns.
    #   - Authoritative writer: 'ensembl_vep' (local). During analysis the
    #     pipeline is single-writer — annotation_coordinator writes
    #     ensembl_data only from the local ensembl_vep source.
    #   - The only place both sources can be in play together is the admin
    #     retrigger/backfill path (_retrigger_sources in admin/annotation_sources.py).
    #     That path MUST NOT let a retrigger of 'ensembl' blindly overwrite
    #     an already-populated (found=True) ensembl_data value — it skips
    #     the clobbering write instead (see the guard + log there). Do not
    #     remove that guard when touching this path.
    'ensembl_vep': 'ensembl',
    'gnomad_tx': 'gnomad_tx',
    'chembl': 'chembl',
    'fda_drug': 'fda_drug',
    'alphafold': 'alphafold',
    'gwas_catalog': 'gwas_catalog',
    'clingen': 'clingen',
    'open_targets': 'open_targets',
}

# Sources that use external HTTP APIs (via OptimizedGeneticAPIService / GeneticAPIService)
REMOTE_API_SOURCES: Set[str] = {'ensembl', 'clinvar', 'clinpgx', 'snpedia'}

# Sources backed by local data (files, local DB tables, or SQLite cache)
# 'ensembl' is hybrid — uses local VEP VCF when loaded, falls back to API
# 'alphafold' uses local SQLite built from EBI FTP tar when available
LOCAL_SOURCES: Set[str] = {'clinvar_local', 'gnomad', 'gnomad_tx', 'alpha_missense', 'ensembl', 'thousand_genomes', 'ensembl_vep', 'alphafold', 'gwas_catalog', 'clingen'}

# Sources backed by BigQuery public datasets (alphafold moved to LOCAL_SOURCES)
BQ_SOURCES: Set[str] = {'chembl', 'fda_drug', 'open_targets'}


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
