"""
Admin annotation-source configuration + incomplete-annotation retrigger routes.
"""
import asyncio
import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, cast, update

from ...db.database import get_session
from ...db.models import User, SharedVariantAnnotation, AnnotationSourceConfig
from .schemas import (
    require_admin,
    SOURCE_TO_COLUMN,
    AnnotationSourceResponse,
    AnnotationSourceUpdate,
    _source_cache_file_size,
    _is_source_stale,
    BackfillResponse,
    IncompleteAnnotationResponse,
    PaginatedIncompleteResponse,
    IncompleteAnnotationSummary,
    SentinelResetResponse,
)

# No prefix here -- folded into admin_routes.router, which already carries
# "/api/admin"; baking it in twice double-prefixes (see admin_routes.py).
router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)


# --- Annotation Source Configuration ---

DEFAULT_SOURCES = [
    # Third-party HTTP APIs
    {"source_name": "ensembl", "display_name": "Ensembl VEP", "is_enabled": True, "source_type": "api", "description": "Variant Effect Predictor — gene consequences, transcript impact, regulatory annotations", "rate_limit": 15.0, "priority": 1},
    {"source_name": "clinvar", "display_name": "ClinVar API (supplementary)", "is_enabled": True, "source_type": "api", "description": "Supplementary NCBI ClinVar API cache. Analysis uses ClinVar Local (local PG table, 100% filled) for all classification — this API column is optional extra context only. Backfilling 609k variants takes ~17hrs at 10 req/s.", "rate_limit": 10.0, "priority": 2},
    {"source_name": "clinpgx", "display_name": "ClinPGx (supplementary)", "is_enabled": True, "source_type": "api", "description": "Supplementary ClinPGx/PharmGKB API cache for pharmacogenomics. Analysis uses this for drug response enrichment when populated. Backfilling 609k variants takes ~170hrs at 1 req/s.", "rate_limit": 1.0, "priority": 3},
    {"source_name": "snpedia", "display_name": "SNPedia (supplementary)", "is_enabled": True, "source_type": "api", "description": "Supplementary SNPedia wiki cache. Populated on-demand during analysis for relevant variants only — not useful to bulk-backfill. Backfilling 609k variants takes ~85hrs at 2 req/s.", "rate_limit": 2.0, "priority": 4},
    # Local files (tabix/TSV in data_sources/)
    {"source_name": "alpha_missense", "display_name": "AlphaMissense", "is_enabled": True, "source_type": "file", "description": "AI-based missense pathogenicity predictions — bgzip tabix files in data_sources/alpha_missense/", "rate_limit": None, "priority": 5},
    {"source_name": "ensembl_vep", "display_name": "Ensembl VEP (Local)", "is_enabled": True, "source_type": "file", "description": "Local Ensembl VEP variant annotations — per-chromosome VCFs in data_sources/ensembl/ (SQLite cache)", "rate_limit": None, "priority": 6},
    # Local files + PostgreSQL hybrid (ETL imports files → PG; raw files also in data_sources/)
    {"source_name": "gnomad", "display_name": "gnomAD", "is_enabled": True, "source_type": "hybrid", "description": "gnomAD allele frequencies — tabix TSV files in data_sources/gnomad/ (SQLite cache primary path) + PostgreSQL import (run ETL to populate)", "rate_limit": None, "priority": 7},
    {"source_name": "gnomad_tx", "display_name": "gnomAD tx-annotated", "is_enabled": True, "source_type": "file", "description": "gnomAD transcript annotation + GTEx tissue expression — data_sources/gnomad/all.possible.snvs.tx_annotated.GTEx.v7.021520.tsv.bgz", "rate_limit": None, "priority": 8},
    # PostgreSQL-backed (data originally from local files, now imported into PG)
    {"source_name": "clinvar_local", "display_name": "ClinVar Local", "is_enabled": True, "source_type": "hybrid", "description": "ClinVar — source files in data_sources/clinvar/ (VCF + TSV), ETL-imported into PostgreSQL for fast lookups", "rate_limit": None, "priority": 9},
    {"source_name": "thousand_genomes", "display_name": "1000 Genomes Phase 3", "is_enabled": True, "source_type": "hybrid", "description": "1000 Genomes Phase 3 — source VCF in data_sources/ensembl/homo_sapiens/variation/vcf_vep/1000GENOMES-phase_3.vcf.gz, ETL-imported into PostgreSQL", "rate_limit": None, "priority": 10},
    # Google BigQuery
    {"source_name": "chembl", "display_name": "ChEMBL (BigQuery)", "is_enabled": True, "source_type": "bigquery", "description": "Drug mechanisms, indications, and safety warnings for gene targets — ebi_chembl v33 public dataset", "rate_limit": None, "priority": 11},
    {"source_name": "fda_drug", "display_name": "FDA Drug Labels (BigQuery)", "is_enabled": True, "source_type": "bigquery", "description": "FDA drug labels with CYP enzyme interaction data and pharmacokinetics", "rate_limit": None, "priority": 12},
    {"source_name": "alphafold", "display_name": "AlphaFold (BigQuery)", "is_enabled": True, "source_type": "bigquery", "description": "DeepMind AlphaFold protein structure confidence scores (pLDDT)", "rate_limit": None, "priority": 13},
    # EBI / ClinGen curated databases
    {"source_name": "gwas_catalog", "display_name": "GWAS Catalog", "is_enabled": True, "source_type": "hybrid", "description": "EBI GWAS Catalog — rsID→trait associations with p-values and effect sizes. Download: data_sources/gwas_catalog/gwas_associations.tsv, ETL-imported into PostgreSQL", "rate_limit": None, "priority": 14},
    {"source_name": "clingen", "display_name": "ClinGen Gene Validity", "is_enabled": True, "source_type": "hybrid", "description": "ClinGen gene-disease validity classifications (Definitive/Strong/Moderate/Limited). Download: data_sources/clingen/clingen_gene_validity.tsv, ETL-imported into PostgreSQL", "rate_limit": None, "priority": 15},
    {"source_name": "open_targets", "display_name": "Open Targets Platform", "is_enabled": True, "source_type": "api", "description": "Open Targets Platform gene-disease scores aggregated from genetic, literature, and animal model evidence. Queried live via GraphQL API by gene symbol during annotation.", "rate_limit": 5.0, "priority": 16},
]

async def _ensure_source_configs(db: AsyncSession) -> List[AnnotationSourceConfig]:
    """Ensure all default sources exist in annotation_source_configs. Returns all configs."""
    result = await db.execute(
        select(AnnotationSourceConfig).order_by(AnnotationSourceConfig.priority)
    )
    existing = list(result.scalars().all())
    existing_names = {s.source_name for s in existing}

    for default in DEFAULT_SOURCES:
        if default["source_name"] not in existing_names:
            db.add(AnnotationSourceConfig(**default))

    if len(existing_names) < len(DEFAULT_SOURCES):
        await db.commit()
        result = await db.execute(
            select(AnnotationSourceConfig).order_by(AnnotationSourceConfig.priority)
        )
        existing = list(result.scalars().all())

    return existing


@router.get("/annotation-sources", response_model=List[AnnotationSourceResponse])
async def get_annotation_sources(
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Get all annotation source configurations with health stats.

    Coverage is reported honestly: found_count counts only rows the source
    actually resolved (found=true), so a stored {"found": false} no longer
    inflates the coverage figure. A per-source on-disk cache size and a stale
    flag make an empty/unbuilt cache (e.g. gnomAD CADD) visible.
    """
    sources = await _ensure_source_configs(db)

    total_result = await db.execute(select(func.count(SharedVariantAnnotation.id)))
    total_annotations = total_result.scalar() or 0

    responses = []
    for src in sources:
        col_name = SOURCE_TO_COLUMN.get(src.source_name, src.source_name)
        col = getattr(SharedVariantAnnotation, f'{col_name}_data', None)
        annotated = 0
        found = 0
        if col is not None:
            count_result = await db.execute(
                select(func.count(SharedVariantAnnotation.id)).where(col.isnot(None))
            )
            annotated = count_result.scalar() or 0
            try:
                found_result = await db.execute(
                    select(func.count(SharedVariantAnnotation.id)).where(
                        col['found'].as_boolean().is_(True)
                    )
                )
                found = found_result.scalar() or 0
            except Exception as e:
                logger.warning(
                    "found-rate query failed for source=%s; falling back to "
                    "non-null count: %s", src.source_name, e,
                )
                found = annotated

        cache_bytes = _source_cache_file_size(src.source_name)
        responses.append(AnnotationSourceResponse(
            id=src.id,
            source_name=src.source_name,
            display_name=src.display_name,
            is_enabled=src.is_enabled,
            description=src.description,
            source_type=src.source_type or 'api',
            rate_limit=src.rate_limit,
            priority=src.priority,
            annotated_count=annotated,
            missing_count=total_annotations - annotated,
            found_count=found,
            no_data_count=max(annotated - found, 0),
            cache_file_bytes=cache_bytes,
            is_stale=_is_source_stale(src.is_enabled, found, annotated, cache_bytes),
        ))

    return responses


@router.put("/annotation-sources/{source_name}", response_model=AnnotationSourceResponse)
async def update_annotation_source(
    source_name: str,
    update: AnnotationSourceUpdate,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Enable/disable an annotation source or change its priority."""
    result = await db.execute(
        select(AnnotationSourceConfig).where(AnnotationSourceConfig.source_name == source_name)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail=f"Source '{source_name}' not found")

    if update.is_enabled is not None:
        config.is_enabled = update.is_enabled
        # Invalidate the enabled-sources cache so the next summary poll recomputes coverage
        global _enabled_sources_cache
        _enabled_sources_cache = None
    if update.priority is not None:
        config.priority = update.priority

    await db.commit()
    await db.refresh(config)

    # Get counts for the response
    col_name = SOURCE_TO_COLUMN.get(config.source_name, config.source_name)
    col = getattr(SharedVariantAnnotation, f'{col_name}_data', None)
    annotated = 0
    if col is not None:
        count_result = await db.execute(
            select(func.count(SharedVariantAnnotation.id)).where(col.isnot(None))
        )
        annotated = count_result.scalar() or 0

    total_result = await db.execute(select(func.count(SharedVariantAnnotation.id)))
    total_annotations = total_result.scalar() or 0

    return AnnotationSourceResponse(
        id=config.id,
        source_name=config.source_name,
        display_name=config.display_name,
        is_enabled=config.is_enabled,
        description=config.description,
        source_type=config.source_type or 'api',
        rate_limit=config.rate_limit,
        priority=config.priority,
        annotated_count=annotated,
        missing_count=total_annotations - annotated,
    )


def _extract_am_coords(ensembl_data) -> Optional[tuple]:
    if not (ensembl_data and isinstance(ensembl_data, dict)
            and ensembl_data.get('found') and ensembl_data.get('data')):
        return None
    e_data = ensembl_data['data']
    e_entry = e_data[0] if isinstance(e_data, list) else e_data
    chrom = e_entry.get('seq_region_name')
    pos = e_entry.get('start')
    parts = (e_entry.get('allele_string', '') or '').split('/')
    if chrom and pos and len(parts) == 2 and len(parts[0]) == 1 and len(parts[1]) == 1:
        return (str(chrom), int(pos), parts[0], parts[1])
    return None


@router.post("/annotation-sources/{source_name}/backfill", response_model=BackfillResponse)
async def backfill_source(
    source_name: str,
    limit: int = Query(100, ge=1, description="Max variants to backfill in one request"),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Enqueue a backfill WorkerJob for a specific annotation source.
    The worker process will execute the backfill asynchronously."""
    from ...db.models import WorkerJob
    if source_name not in SOURCE_TO_COLUMN:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source_name}")

    col_name = SOURCE_TO_COLUMN[source_name]
    col = getattr(SharedVariantAnnotation, f'{col_name}_data')

    # Quick count to check if there's anything to do
    count_result = await db.execute(
        select(func.count()).select_from(SharedVariantAnnotation).where(col.is_(None))
    )
    missing = count_result.scalar() or 0

    if missing == 0:
        return BackfillResponse(
            detail=f"No variants need backfilling from {source_name}",
            source=source_name, total_to_backfill=0,
            completed=0, failed=0, confirmed_no_data=0,
        )

    job = WorkerJob(
        job_type="backfill_source",
        status="pending",
        params={"source_name": source_name, "limit": limit},
        requested_by=admin.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return BackfillResponse(
        detail=f"Backfill job #{job.id} queued for {source_name} ({min(limit, missing):,} variants). Check Jobs tab for progress.",
        source=source_name,
        total_to_backfill=min(limit, missing),
        completed=0,
        failed=0,
        confirmed_no_data=0,
    )


# --- Ensembl VEP ETL ---

@router.post("/ensembl-vep-etl/import")
async def trigger_vep_etl(
    chromosomes: Optional[str] = Query(None, description="Comma-separated chromosome list, e.g. '1,2,X'. Omit for all available."),
    force_reload: bool = Query(False, description="Re-import already loaded chromosomes"),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch Ensembl VEP ETL to the background worker and return immediately."""
    from ...db.models import WorkerJob
    chrom_list = [c.strip() for c in chromosomes.split(',')] if chromosomes else None
    job = WorkerJob(
        job_type="etl_vep",
        status="pending",
        params={"chromosomes": chrom_list, "force_reload": force_reload},
        requested_by=admin.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"VEP ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"VEP ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


@router.get("/ensembl-vep-etl/status")
async def vep_etl_status(
    admin: User = Depends(require_admin),
):
    """Check Ensembl VEP local data status."""
    from ...services.ensembl_vep_local import get_ensembl_vep_service
    vep_svc = get_ensembl_vep_service()
    loaded = await vep_svc.ensure_loaded()
    count = vep_svc.variant_count

    # Check available VCF files
    import os
    data_dir = os.environ.get('ENSEMBL_DATA_DIR', '')
    vcf_dir = os.path.join(data_dir, 'variation', 'vcf_vep') if data_dir else ''
    available_files = []
    if vcf_dir and os.path.isdir(vcf_dir):
        import glob
        available_files = sorted([
            os.path.basename(f) for f in glob.glob(os.path.join(vcf_dir, 'homo_sapiens_incl_consequences-chr*.vcf.gz'))
        ])

    return {
        "loaded": loaded,
        "variant_count": count,
        "data_dir": data_dir,
        "vcf_dir": vcf_dir,
        "available_vcf_files": available_files,
    }


# --- Incomplete Annotations ---

def _has_failed_sources():
    """Safe SQL expression: true when failed_sources is a non-empty JSON array.

    Avoids ``json_array_length`` crash on JSON null / scalar values.
    """
    return (
        SharedVariantAnnotation.failed_sources.isnot(None)
        & (func.json_typeof(SharedVariantAnnotation.failed_sources) == 'array')
        & (
            case(
                (func.json_typeof(SharedVariantAnnotation.failed_sources) == 'array',
                 func.json_array_length(SharedVariantAnnotation.failed_sources)),
                else_=0,
            ) > 0
        )
    )


def _no_failed_sources():
    """Safe SQL expression: true when failed_sources is NULL, not an array, or empty."""
    return (
        SharedVariantAnnotation.failed_sources.is_(None)
        | (func.json_typeof(SharedVariantAnnotation.failed_sources) != 'array')
        | (
            case(
                (func.json_typeof(SharedVariantAnnotation.failed_sources) == 'array',
                 func.json_array_length(SharedVariantAnnotation.failed_sources)),
                else_=0,
            ) == 0
        )
    )


async def _get_all_enabled_source_names(db: AsyncSession) -> List[str]:
    """Return all enabled source names (for display in table columns)."""
    result = await db.execute(
        select(AnnotationSourceConfig.source_name)
        .where(AnnotationSourceConfig.is_enabled.is_(True))
        .order_by(AnnotationSourceConfig.priority)
    )
    names = [r[0] for r in result.all()]
    return names if names else list(SOURCE_TO_COLUMN.keys())


# Module-level cache for _get_enabled_source_names — the 12-column COUNT query
# is expensive (full table scan) and its result changes only when a source is
# enabled/disabled or a large batch of new annotations is processed.
_enabled_sources_cache: Optional[List[str]] = None
_enabled_sources_cache_ts: float = 0.0
_ENABLED_SOURCES_TTL = 60.0  # seconds


async def _get_enabled_source_names(db: AsyncSession) -> List[str]:
    """Return enabled source names that have been systematically applied.

    A source is considered 'active' only when it covers more than 50% of all
    annotations.  This avoids counting sources that were never called during
    bulk processing (e.g. remote APIs, niche local sources) as contributing
    to 'incompleteness'.

    Result is cached for 60 seconds so that the expensive full-table COUNT
    aggregation is not repeated on every admin poll.
    """
    global _enabled_sources_cache, _enabled_sources_cache_ts
    now = time.monotonic()
    if _enabled_sources_cache is not None and now - _enabled_sources_cache_ts < _ENABLED_SOURCES_TTL:
        return _enabled_sources_cache
    result = await db.execute(
        select(AnnotationSourceConfig.source_name)
        .where(AnnotationSourceConfig.is_enabled.is_(True))
    )
    enabled = [r[0] for r in result.all()]
    if not enabled:
        enabled = list(SOURCE_TO_COLUMN.keys())

    # Single-pass: get total count + per-source non-NULL count
    count_exprs = [func.count().label('total')]
    src_cols: List[tuple] = []  # (source_name, column_object)
    for src in enabled:
        col_prefix = SOURCE_TO_COLUMN.get(src)
        if col_prefix is None:
            continue
        col = getattr(SharedVariantAnnotation, f'{col_prefix}_data', None)
        if col is None:
            continue
        src_cols.append((src, col))
        count_exprs.append(func.count(col).label(f'{src}_cnt'))

    if not src_cols:
        return []

    row = (await db.execute(select(*count_exprs).select_from(SharedVariantAnnotation))).one()
    total = row[0] or 1  # avoid division by zero

    active: List[str] = []
    for idx, (src, _col) in enumerate(src_cols, start=1):
        non_null = row[idx]
        if non_null / total > 0.5:
            active.append(src)

    _enabled_sources_cache = active
    _enabled_sources_cache_ts = now
    return active


def _build_incomplete_condition(enabled_sources: List[str]):
    """Build SQLAlchemy OR condition: at least one enabled source column IS NULL.

    Returns ``None`` when there are no enabled sources to check.
    """
    from sqlalchemy import or_

    conditions = []
    for src in enabled_sources:
        col_prefix = SOURCE_TO_COLUMN.get(src)
        if col_prefix is None:
            continue
        col = getattr(SharedVariantAnnotation, f'{col_prefix}_data', None)
        if col is not None:
            conditions.append(col.is_(None))
    return or_(*conditions) if conditions else None


@router.get("/annotations/incomplete/summary", response_model=IncompleteAnnotationSummary)
async def get_incomplete_summary(
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Get counts of incomplete annotations.

    A variant is 'incomplete' if at least one *enabled* source column is NULL
    (never queried).  Columns with ``{found: false}`` are considered complete
    (confirmed absence of data in the source).
    """
    from sqlalchemy import or_, and_

    all_enabled = await _get_all_enabled_source_names(db)
    active = await _get_enabled_source_names(db)
    incomplete_cond = _build_incomplete_condition(active)

    total_result = await db.execute(
        select(func.count()).select_from(SharedVariantAnnotation)
    )
    total = total_result.scalar() or 0

    if incomplete_cond is None:
        # No active sources → nothing can be incomplete
        return IncompleteAnnotationSummary(
            total_annotations=total, complete=total, partial=0, failed=0,
            enabled_sources=all_enabled, active_sources=active,
        )

    incomplete_result = await db.execute(
        select(func.count()).select_from(SharedVariantAnnotation).where(incomplete_cond)
    )
    incomplete = incomplete_result.scalar() or 0

    failed_result = await db.execute(
        select(func.count()).select_from(SharedVariantAnnotation)
        .where(_has_failed_sources())
    )
    failed = failed_result.scalar() or 0

    return IncompleteAnnotationSummary(
        total_annotations=total,
        complete=total - incomplete,
        partial=incomplete - failed,
        failed=failed,
        enabled_sources=all_enabled,
        active_sources=active,
    )


@router.get("/annotations/incomplete", response_model=PaginatedIncompleteResponse)
async def list_incomplete_annotations(
    status_filter: Optional[str] = Query('partial', pattern="^(partial|failed|all)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """List annotations with truly missing data from enabled sources.

    Only returns variants where at least one enabled source column is NULL.
    Variants where all enabled sources returned ``found`` or ``no_data`` are
    considered complete and excluded.
    """
    from ...services.annotation_constants import source_status
    from sqlalchemy import and_

    enabled = await _get_enabled_source_names(db)
    all_enabled = await _get_all_enabled_source_names(db)
    incomplete_cond = _build_incomplete_condition(enabled)

    if incomplete_cond is None:
        return PaginatedIncompleteResponse(items=[], total_count=0, limit=limit, offset=offset)

    base_q = select(SharedVariantAnnotation).where(incomplete_cond)

    if status_filter == 'failed':
        base_q = base_q.where(_has_failed_sources())
    elif status_filter == 'partial':
        # Exclude rows that have recorded failures — show only "never queried" gaps
        base_q = base_q.where(_no_failed_sources())
    # 'all' — no extra filter

    # Total count for pagination
    count_q = select(func.count()).select_from(base_q.subquery())
    total_count = (await db.execute(count_q)).scalar() or 0

    q = base_q.order_by(SharedVariantAnnotation.usage_count.desc()).limit(limit).offset(offset)

    result = await db.execute(q)
    annotations = result.scalars().all()

    items = []
    for a in annotations:
        src_statuses = {
            'ensembl': source_status(a.ensembl_data),
            'clinvar': source_status(a.clinvar_data),
            'clinpgx': source_status(a.pharmgkb_data),
            'snpedia': source_status(a.snpedia_data),
            'litvar': source_status(a.litvar_data),
            'alpha_missense': source_status(a.alpha_missense_data),
            'clinvar_local': source_status(a.clinvar_local_data),
            'gnomad': source_status(a.gnomad_data),
            'chembl': source_status(a.chembl_data),
            'fda_drug': source_status(a.fda_drug_data),
            'alphafold': source_status(a.alphafold_data),
        }
        # Derive missing_sources: enabled sources that are "missing" (never queried)
        missing = [s for s in all_enabled if src_statuses.get(s) == 'missing']
        items.append(IncompleteAnnotationResponse(
            id=a.id,
            rsid=a.rsid,
            annotation_status=a.annotation_status,
            failed_sources=a.failed_sources if isinstance(a.failed_sources, list) else [],
            missing_sources=missing,
            total_api_calls=a.total_api_calls or 0,
            first_annotated_at=a.first_annotated_at,
            last_updated_at=a.last_updated_at,
            usage_count=a.usage_count or 0,
            **src_statuses,
        ))

    return PaginatedIncompleteResponse(
        items=items, total_count=total_count, limit=limit, offset=offset,
    )


@router.post("/annotations/retrigger/{annotation_id}")
async def retrigger_annotation(
    annotation_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Re-trigger external API calls for failed sources of an incomplete annotation."""
    from ...services.annotation_constants import get_missing_sources, SOURCE_TO_COLUMN

    result = await db.execute(
        select(SharedVariantAnnotation).where(SharedVariantAnnotation.id == annotation_id)
    )
    annotation = result.scalar_one_or_none()
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    if not annotation.failed_sources and annotation.annotation_status == 'completed':
        return {"detail": "Annotation is already complete", "updated_sources": []}

    sources_to_retry = get_missing_sources(annotation)
    if not sources_to_retry:
        annotation.annotation_status = 'completed'
        annotation.failed_sources = None
        await db.commit()
        return {"detail": "All sources already have data or confirmed no data", "updated_sources": [], "confirmed_no_data": [], "still_failed": [], "new_status": "completed"}

    updated, confirmed_no_data, still_failed = await _retrigger_sources(annotation, sources_to_retry)

    annotation.failed_sources = still_failed if still_failed else None
    annotation.annotation_status = 'completed' if not still_failed else 'partial'
    annotation.total_api_calls = (annotation.total_api_calls or 0) + len(updated) + len(confirmed_no_data)
    await db.commit()

    return {
        "detail": f"Retrigger complete for {annotation.rsid}",
        "updated_sources": updated,
        "confirmed_no_data": confirmed_no_data,
        "still_failed": still_failed,
        "new_status": annotation.annotation_status,
    }


@router.post("/annotations/retrigger-bulk")
async def retrigger_bulk_annotations(
    annotation_ids: List[int] = [],
    retrigger_all: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Bulk re-trigger incomplete annotations. Either specific IDs or all partials."""
    from ...services.annotation_constants import get_missing_sources

    if retrigger_all:
        result = await db.execute(
            select(SharedVariantAnnotation)
            .where(SharedVariantAnnotation.annotation_status.in_(['partial', 'failed']))
            .order_by(SharedVariantAnnotation.usage_count.desc())
            .limit(limit)
        )
        annotations = result.scalars().all()
    elif annotation_ids:
        result = await db.execute(
            select(SharedVariantAnnotation).where(SharedVariantAnnotation.id.in_(annotation_ids))
        )
        annotations = result.scalars().all()
    else:
        return {"detail": "Provide annotation_ids or set retrigger_all=true", "completed": 0, "still_incomplete": 0}

    completed_count = 0
    still_incomplete = 0

    for idx, ann in enumerate(annotations):
        # Rate-limit between annotations to avoid overwhelming external APIs
        if idx > 0:
            await asyncio.sleep(0.5)

        sources_to_retry = get_missing_sources(ann)

        if not sources_to_retry:
            ann.annotation_status = 'completed'
            ann.failed_sources = None
            completed_count += 1
            continue

        _updated, _confirmed, still_failed = await _retrigger_sources(ann, sources_to_retry)

        ann.failed_sources = still_failed if still_failed else None
        ann.annotation_status = 'completed' if not still_failed else 'partial'
        if not still_failed:
            completed_count += 1
        else:
            still_incomplete += 1

    await db.commit()
    return {
        "detail": f"Bulk retrigger complete: {completed_count} now complete, {still_incomplete} still incomplete",
        "completed": completed_count,
        "still_incomplete": still_incomplete,
        "total_processed": len(annotations),
    }


async def _retrigger_sources(
    annotation,
    sources_to_retry: list,
) -> tuple[list, list, list]:
    """Retry missing annotation sources for a single SharedVariantAnnotation.

    Returns (updated, confirmed_no_data, still_failed) lists of source names.
    Handles remote APIs, local lookups, and BigQuery sources.
    """
    from ...services.annotation_constants import SOURCE_TO_COLUMN, REMOTE_API_SOURCES, BQ_SOURCES

    updated: list = []
    confirmed_no_data: list = []
    still_failed: list = []

    # Partition sources by type
    remote_sources = [s for s in sources_to_retry if s in REMOTE_API_SOURCES]
    bq_sources = [s for s in sources_to_retry if s in BQ_SOURCES]
    local_sources = [s for s in sources_to_retry if s not in REMOTE_API_SOURCES and s not in BQ_SOURCES]

    # --- Local sources (no external service needed) ---
    for src in local_sources:
        try:
            if src == 'clinvar_local':
                from ...services.clinvar_local import get_clinvar_local_service
                cv_svc = get_clinvar_local_service()
                if cv_svc.is_loaded:
                    result_data = await cv_svc.lookup(annotation.rsid)
                    if result_data and result_data.get('found'):
                        annotation.clinvar_local_data = result_data
                        updated.append(src)
                    else:
                        annotation.clinvar_local_data = {'found': False, 'confirmed_no_data': True, 'source': 'clinvar_local'}
                        confirmed_no_data.append(src)
                else:
                    still_failed.append(src)
            elif src == 'gnomad':
                from ...services.gnomad_local import get_gnomad_service
                gnomad_svc = get_gnomad_service()
                if gnomad_svc.is_loaded:
                    result_data = await gnomad_svc.lookup(annotation.rsid)
                    if result_data and result_data.get('found'):
                        annotation.gnomad_data = result_data
                        updated.append(src)
                    else:
                        annotation.gnomad_data = {'found': False, 'confirmed_no_data': True, 'source': 'gnomad'}
                        confirmed_no_data.append(src)
                else:
                    still_failed.append(src)
            elif src == 'alpha_missense':
                from ...utils.alpha_missense import get_alpha_missense_service
                coords = _extract_am_coords(annotation.ensembl_data)
                if coords:
                    am_svc = get_alpha_missense_service()
                    result_data = am_svc.lookup_comprehensive(*coords)
                    if result_data:
                        annotation.alpha_missense_data = result_data
                        updated.append(src)
                    else:
                        annotation.alpha_missense_data = {'found': False, 'confirmed_no_data': True, 'source': 'alpha_missense'}
                        confirmed_no_data.append(src)
                else:
                    annotation.alpha_missense_data = {'found': False, 'confirmed_no_data': True, 'source': 'alpha_missense', 'reason': 'not_missense'}
                    confirmed_no_data.append(src)
        except Exception:
            still_failed.append(src)

    # --- Remote API sources ---
    if remote_sources:
        from ...services.genetic_api_service import OptimizedGeneticAPIService
        api_service = OptimizedGeneticAPIService()
        await api_service.initialize()
        try:
            for src in remote_sources:
                try:
                    col = SOURCE_TO_COLUMN.get(src, src)
                    # Guard: 'ensembl' shares ensembl_data with the authoritative
                    # local 'ensembl_vep' writer. Never let this lower-priority
                    # remote fetch clobber a value that's already populated —
                    # skip instead of overwriting (see annotation_constants.py).
                    if src == 'ensembl':
                        existing = getattr(annotation, f'{col}_data', None)
                        if isinstance(existing, dict) and existing.get('found'):
                            logger.info(
                                "Retrigger: skipping remote 'ensembl' fetch for rsid=%s — "
                                "shared ensembl_data column is already populated "
                                "(ensembl_vep is the authoritative writer); refusing to clobber",
                                annotation.rsid,
                            )
                            continue

                    method = getattr(api_service, f'_get_{src}_annotation', None)
                    if not method:
                        still_failed.append(src)
                        continue
                    result_data = await method(annotation.rsid)
                    if result_data and isinstance(result_data, dict) and result_data.get('found', False):
                        setattr(annotation, f'{col}_data', result_data)
                        updated.append(src)
                    else:
                        setattr(annotation, f'{col}_data', {'found': False, 'confirmed_no_data': True, 'source': src})
                        confirmed_no_data.append(src)
                except Exception:
                    still_failed.append(src)
        finally:
            await api_service.close()

    # --- BigQuery sources (need a gene symbol from Ensembl data) ---
    if bq_sources:
        gene_symbol = _extract_gene_symbol(annotation)
        if gene_symbol:
            try:
                from ...services.bq_public import get_bq_public_service
                bq_svc = get_bq_public_service()
                bq_result = await bq_svc.enrich_variant(gene_symbol, set(bq_sources))
                for src in bq_sources:
                    col = SOURCE_TO_COLUMN.get(src, src)
                    src_data = bq_result.get(src)
                    if src_data and isinstance(src_data, dict) and src_data.get('found', False):
                        setattr(annotation, f'{col}_data', src_data)
                        updated.append(src)
                    else:
                        setattr(annotation, f'{col}_data', {'found': False, 'confirmed_no_data': True, 'source': src})
                        confirmed_no_data.append(src)
            except Exception:
                still_failed.extend(bq_sources)
        else:
            # No gene symbol available — can't query BQ
            for src in bq_sources:
                still_failed.append(src)

    return updated, confirmed_no_data, still_failed


def _extract_gene_symbol(annotation) -> Optional[str]:
    """Extract gene symbol from an annotation's Ensembl or ClinVar local data."""
    # Try Ensembl first
    ensembl_ann = annotation.ensembl_data
    if ensembl_ann and isinstance(ensembl_ann, dict) and ensembl_ann.get('found') and ensembl_ann.get('data'):
        e_data = ensembl_ann['data']
        e_entry = e_data[0] if isinstance(e_data, list) else e_data
        tcs = e_entry.get('transcript_consequences', [])
        if tcs:
            gene = tcs[0].get('gene_symbol')
            if gene:
                return gene
    # Fallback to ClinVar local
    cv = annotation.clinvar_local_data
    if cv and isinstance(cv, dict) and cv.get('found'):
        return cv.get('gene_symbol') or cv.get('gene')
    return None


# --- Job Management ---


@router.post("/annotation-sources/{source_name}/reset-sentinels", response_model=SentinelResetResponse)
async def reset_source_sentinels(
    source_name: str,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Reset 'found: false' sentinels for a local source back to NULL.

    Use this after importing new data into a local source table (e.g. after
    1000G ETL, gnomAD import, ClinVar update) so the next analysis backfill
    will re-query the source with the updated data.

    Only resets entries where found=false — entries with found=true (real data)
    are left untouched.
    """
    from ...services.annotation_constants import SOURCE_TO_COLUMN, LOCAL_SOURCES

    if source_name not in SOURCE_TO_COLUMN:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source_name}")
    if source_name not in LOCAL_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Sentinel reset is only for local sources. {source_name} is a remote API source.",
        )

    col_name = SOURCE_TO_COLUMN[source_name]
    col = getattr(SharedVariantAnnotation, f'{col_name}_data')

    # Reset found:false entries to NULL so backfill will re-check them
    from sqlalchemy import cast, String, or_
    result = await db.execute(
        update(SharedVariantAnnotation)
        .where(
            col.isnot(None),
            or_(
                cast(col, String).like('%"found": false%'),
                cast(col, String).like('%"found":false%'),
            ),
        )
        .values(**{f'{col_name}_data': None})
    )
    await db.commit()

    reset_count = result.rowcount
    logger.info(f"Admin reset {reset_count} '{source_name}' sentinels to NULL")

    return SentinelResetResponse(
        detail=f"Reset {reset_count} stale '{source_name}' sentinels to NULL. Next analysis backfill will re-query this source.",
        source=source_name,
        reset_count=reset_count,
    )

