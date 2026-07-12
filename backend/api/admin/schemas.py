"""
Shared Pydantic schemas and helpers for the admin API package.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel

from ...db.models import User
from ..auth_routes import get_current_user
from ...services.annotation_constants import SOURCE_TO_COLUMN


# --- Dependencies ---

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


# --- User Management schemas ---

class AdminUserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    is_verified: bool
    is_admin: bool
    created_at: datetime
    analysis_count: int = 0

    class Config:
        from_attributes = True


class AdminUserUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    is_verified: Optional[bool] = None


# --- Variant Mapping Registry schemas ---

class VariantMappingResponse(BaseModel):
    id: int
    category: str
    map_type: str
    key: str
    data: dict
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VariantMappingCreate(BaseModel):
    category: str
    map_type: str        # 'rsid' or 'gene'
    key: str             # e.g. 'rs7903146' or 'TP73'
    data: dict


class VariantMappingUpdate(BaseModel):
    key: Optional[str] = None
    data: Optional[dict] = None
    is_active: Optional[bool] = None


class VariantMappingCategorySummary(BaseModel):
    category: str
    rsid_count: int
    gene_count: int
    total: int


# --- Discoveries schemas ---

class PendingDiscoveryResponse(BaseModel):
    id: int
    discovery_type: str
    rsid: str
    gene: Optional[str] = None
    panel_id: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    map_type: Optional[str] = None
    mapping_category: Optional[str] = None
    mapping_data: Optional[dict] = None
    source_data: Optional[dict] = None
    status: str
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    discovered_by: Optional[int] = None
    lookup_count: int = 1
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DiscoverySummary(BaseModel):
    total_pending: int
    total_approved: int
    total_rejected: int
    variant_mapping_pending: int


class DiscoveryReviewAction(BaseModel):
    action: str  # 'approve' or 'reject'
    rejection_reason: Optional[str] = None
    # Optional overrides before approving
    description: Optional[str] = None
    category: Optional[str] = None
    mapping_data: Optional[dict] = None


# --- Annotation Sources schemas + helpers ---

class AnnotationSourceResponse(BaseModel):
    id: int
    source_name: str
    display_name: str
    is_enabled: bool
    description: Optional[str] = None
    # 'api' = third-party HTTP API, 'database' = PostgreSQL only,
    # 'file' = local tabix/TSV files only, 'hybrid' = files + PostgreSQL,
    # 'bigquery' = Google BigQuery
    source_type: str = 'api'
    rate_limit: Optional[float] = None
    priority: int = 0
    annotated_count: int = 0
    missing_count: int = 0
    # True coverage: rows where the source actually returned found=true. A stored
    # {"found": false} (confirmed absence) inflates annotated_count but must not
    # count as coverage — found_count is the honest signal, no_data_count the rest.
    found_count: int = 0
    no_data_count: int = 0
    # On-disk cache size (bytes) for file/hybrid sources; None if the source has no
    # known cache file or the file is absent. Stat only — contents never read.
    cache_file_bytes: Optional[int] = None
    # Heuristic flag so a stale/unbuilt cache (e.g. the empty gnomAD CADD build)
    # is visible on the admin surface.
    is_stale: bool = False

    class Config:
        from_attributes = True


class AnnotationSourceUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    priority: Optional[int] = None


# file/hybrid cache below this size is treated stale/unbuilt (e.g. empty
# gnomAD CADD build, ~180 KB) so it is flagged on the admin data-sources surface.
_STALE_CACHE_BYTES = 1_000_000


def _source_cache_file_size(source_name: str) -> Optional[int]:
    """On-disk size (bytes) of a source's cache file, or None when the source has
    no known cache file or the file is absent. Stats only — never reads contents."""
    if source_name == 'gnomad':
        try:
            from ...services.gnomad_local import _SQLITE_FILE
            return _SQLITE_FILE.stat().st_size
        except (OSError, ImportError):
            return None  # absent -> report as None, never error
    return None


def _is_source_stale(is_enabled: bool, found_count: int, annotated_count: int,
                     cache_file_bytes: Optional[int]) -> bool:
    """Flag a source whose coverage looks empty/unbuilt. Two signals: a tiny on-disk
    cache file, or an enabled source that has stored rows but zero real coverage
    (found=true), which is the empty-build case the honest found-rate exposes."""
    if cache_file_bytes is not None and cache_file_bytes < _STALE_CACHE_BYTES:
        return True
    if is_enabled and annotated_count > 0 and found_count == 0:
        return True
    return False


class BackfillResponse(BaseModel):
    detail: str
    source: str
    total_to_backfill: int
    completed: int
    failed: int
    confirmed_no_data: int


class VepEtlResponse(BaseModel):
    detail: str
    chromosomes_imported: list = []
    total_variants: int = 0
    skipped_chromosomes: list = []


class IncompleteAnnotationResponse(BaseModel):
    id: int
    rsid: str
    annotation_status: Optional[str] = None
    failed_sources: Optional[list] = None
    missing_sources: List[str] = []  # derived: enabled sources with status "missing"
    total_api_calls: int = 0
    # Source status: "found" = has data, "no_data" = confirmed absence, "missing" = never queried/error
    ensembl: str = "missing"
    clinvar: str = "missing"
    clinpgx: str = "missing"
    snpedia: str = "missing"
    litvar: str = "missing"
    alpha_missense: str = "missing"
    clinvar_local: str = "missing"
    gnomad: str = "missing"
    chembl: str = "missing"
    fda_drug: str = "missing"
    alphafold: str = "missing"
    first_annotated_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    usage_count: int = 0

    class Config:
        from_attributes = True


class PaginatedIncompleteResponse(BaseModel):
    items: List[IncompleteAnnotationResponse]
    total_count: int
    limit: int
    offset: int


class IncompleteAnnotationSummary(BaseModel):
    total_annotations: int
    complete: int
    partial: int
    failed: int
    enabled_sources: List[str] = []  # all enabled sources (for table columns)
    active_sources: List[str] = []   # high-coverage sources (used for counts)


# --- Jobs schemas ---

class AdminJobResponse(BaseModel):
    id: int
    user_id: int
    user_email: str
    username: str
    filename: str
    file_type: str
    analysis_status: str
    progress_percentage: int
    total_variants: int
    processed_variants: int
    current_step: Optional[str] = None
    upload_date: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdminJobsSummary(BaseModel):
    total: int
    pending: int
    processing: int
    completed: int
    failed: int


# Measurement-first threshold (U12): backend latency optimization is out of
# scope for the analysis pipeline until real p95 completion time exceeds this.
# Below it, the wait-UX/honest-progress work in this unit is sufficient.
LATENCY_P95_THRESHOLD_SECONDS = 5 * 60


class AdminJobsLatency(BaseModel):
    sample_size: int
    p50_seconds: Optional[float] = None
    p95_seconds: Optional[float] = None
    threshold_seconds: int = LATENCY_P95_THRESHOLD_SECONDS
    exceeds_threshold: bool = False


# --- Category Rules schemas ---

class CategoryRuleCreate(BaseModel):
    category: str
    rule_type: str
    rule_value: str
    priority: int = 50
    is_active: bool = True
    mapping_data_template: Optional[dict] = None


class CategoryRuleUpdate(BaseModel):
    rule_value: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    mapping_data_template: Optional[dict] = None


# --- ETL schemas ---

class SentinelResetResponse(BaseModel):
    detail: str
    source: str
    reset_count: int
