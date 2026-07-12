"""
Admin API routes for user management and panel marker configuration.
"""
import asyncio
import csv
import io
import logging
import time
import yaml
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, case, cast, literal_column, text, update
from sqlalchemy.types import Integer as SAInteger
from typing import List, Optional

from ..db.database import get_session
from ..db.models import User, GeneticAnalysis, VariantMapping, PendingDiscovery, SharedVariantAnnotation, AnnotationSourceConfig
from ..services.notification_service import get_notification_service

# Imported before `router` is constructed so the require_admin guard can be
# baked into the router itself (see dependencies= below) -- this makes
# backend.api.admin's aggregate a plain re-export of this router rather than
# a second APIRouter that .include_router()'s a copy: with two objects, the
# copy step captures whatever routes existed at that exact import moment,
# which is empty if something imports admin_routes.py directly before the
# admin package (circular import, order-dependent). One router, mutated in
# place by every decorator below, has no such moment to get wrong.
from .admin.schemas import (
    require_admin,
    SOURCE_TO_COLUMN,
    LATENCY_P95_THRESHOLD_SECONDS,
    VariantMappingResponse,
    VariantMappingCreate,
    VariantMappingUpdate,
    VariantMappingCategorySummary,
    PendingDiscoveryResponse,
    DiscoverySummary,
    DiscoveryReviewAction,
    AnnotationSourceResponse,
    AnnotationSourceUpdate,
    _source_cache_file_size,
    _is_source_stale,
    BackfillResponse,
    IncompleteAnnotationResponse,
    PaginatedIncompleteResponse,
    IncompleteAnnotationSummary,
    AdminJobResponse,
    AdminJobsSummary,
    AdminJobsLatency,
    CategoryRuleCreate,
    CategoryRuleUpdate,
    SentinelResetResponse,
)
from .admin.users import router as _users_router

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])
logger = logging.getLogger(__name__)

router.include_router(_users_router)


# --- Variant Mapping Registry ---


@router.get("/variant-mappings/categories", response_model=List[VariantMappingCategorySummary])
async def list_variant_mapping_categories(
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """List all categories with mapping counts."""
    result = await db.execute(
        select(
            VariantMapping.category,
            func.count().filter(VariantMapping.map_type == 'rsid').label("rsid_count"),
            func.count().filter(VariantMapping.map_type == 'gene').label("gene_count"),
            func.count().label("total"),
        )
        .where(VariantMapping.is_active == True)
        .group_by(VariantMapping.category)
        .order_by(VariantMapping.category)
    )
    rows = result.all()
    return [
        VariantMappingCategorySummary(category=r[0], rsid_count=r[1], gene_count=r[2], total=r[3])
        for r in rows
    ]


@router.get("/variant-mappings/{category}", response_model=List[VariantMappingResponse])
async def get_variant_mappings(
    category: str,
    map_type: Optional[str] = Query(None, pattern="^(rsid|gene)$"),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Get all mappings for a category, optionally filtered by map_type."""
    q = select(VariantMapping).where(VariantMapping.category == category)
    if map_type:
        q = q.where(VariantMapping.map_type == map_type)
    q = q.order_by(VariantMapping.map_type, VariantMapping.key)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/variant-mappings", response_model=VariantMappingResponse, status_code=201)
async def create_variant_mapping(
    mapping: VariantMappingCreate,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Create a new variant mapping."""
    if mapping.map_type not in ('rsid', 'gene'):
        raise HTTPException(status_code=400, detail="map_type must be 'rsid' or 'gene'")

    existing = await db.execute(
        select(VariantMapping).where(
            VariantMapping.category == mapping.category,
            VariantMapping.map_type == mapping.map_type,
            VariantMapping.key == mapping.key,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Mapping already exists for this category/type/key")

    obj = VariantMapping(
        category=mapping.category,
        map_type=mapping.map_type,
        key=mapping.key,
        data=mapping.data,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.put("/variant-mappings/{mapping_id}", response_model=VariantMappingResponse)
async def update_variant_mapping(
    mapping_id: int,
    update: VariantMappingUpdate,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Update an existing variant mapping."""
    result = await db.execute(select(VariantMapping).where(VariantMapping.id == mapping_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Mapping not found")

    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    obj.updated_at = func.now()
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/variant-mappings/{mapping_id}")
async def delete_variant_mapping(
    mapping_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Delete a variant mapping."""
    result = await db.execute(select(VariantMapping).where(VariantMapping.id == mapping_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Mapping not found")

    await db.delete(obj)
    await db.commit()
    return {"detail": "Mapping deleted"}


# --- Pending Discoveries ---


@router.get("/discoveries/summary", response_model=DiscoverySummary)
async def get_discovery_summary(
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Get summary counts of pending discoveries."""
    result = await db.execute(
        select(
            PendingDiscovery.status,
            PendingDiscovery.discovery_type,
            func.count().label("cnt"),
        )
        .group_by(PendingDiscovery.status, PendingDiscovery.discovery_type)
    )
    rows = result.all()

    summary = {
        'total_pending': 0, 'total_approved': 0, 'total_rejected': 0,
        'variant_mapping_pending': 0,
    }
    for status_val, dtype, cnt in rows:
        if status_val == 'pending':
            summary['total_pending'] += cnt
            if dtype == 'variant_mapping':
                summary['variant_mapping_pending'] = cnt
        elif status_val == 'approved':
            summary['total_approved'] += cnt
        elif status_val == 'rejected':
            summary['total_rejected'] += cnt

    return DiscoverySummary(**summary)


@router.get("/discoveries", response_model=List[PendingDiscoveryResponse])
async def list_discoveries(
    status_filter: Optional[str] = Query('pending', pattern="^(pending|approved|rejected|all)$"),
    discovery_type: Optional[str] = Query(None, pattern="^(variant_mapping)$"),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """List pending discoveries with optional filters."""
    q = select(PendingDiscovery)
    if status_filter and status_filter != 'all':
        q = q.where(PendingDiscovery.status == status_filter)
    if discovery_type:
        q = q.where(PendingDiscovery.discovery_type == discovery_type)
    q = q.order_by(PendingDiscovery.lookup_count.desc(), PendingDiscovery.created_at.desc())

    result = await db.execute(q)
    return result.scalars().all()


@router.post("/discoveries/{discovery_id}/review", response_model=PendingDiscoveryResponse)
async def review_discovery(
    discovery_id: int,
    review: DiscoveryReviewAction,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Approve or reject a pending discovery. Approving creates the live entry."""
    if review.action not in ('approve', 'reject'):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    result = await db.execute(
        select(PendingDiscovery).where(PendingDiscovery.id == discovery_id)
    )
    discovery = result.scalar_one_or_none()
    if not discovery:
        raise HTTPException(status_code=404, detail="Discovery not found")
    if discovery.status != 'pending':
        # Already reviewed — return as-is (idempotent)
        return discovery

    if review.action == 'reject':
        discovery.status = 'rejected'
        discovery.reviewed_by = admin.id
        discovery.reviewed_at = func.now()
        discovery.rejection_reason = review.rejection_reason
        await db.commit()
        await db.refresh(discovery)

        # Notify the submitter if known
        if discovery.discovered_by:
            try:
                svc = get_notification_service()
                await svc.create(
                    user_id=discovery.discovered_by,
                    type='discovery_rejected',
                    title='Variant Discovery Rejected',
                    message=f'Variant {discovery.rsid!r} was not approved for the panel. Reason: {review.rejection_reason or "No reason provided"}.',
                    data={'discovery_id': discovery_id, 'rsid': discovery.rsid},
                )
            except Exception as ne:
                logger.warning(f"Could not send discovery-rejected notification: {ne}")

        return discovery

    # Approve: create the live entry
    if discovery.discovery_type == 'variant_mapping':
        m_data = review.mapping_data or discovery.mapping_data
        m_cat = discovery.mapping_category

        # Final duplicate check
        existing = await db.execute(
            select(VariantMapping.id).where(
                VariantMapping.category == m_cat,
                VariantMapping.map_type == discovery.map_type,
                VariantMapping.key == discovery.rsid,
            )
        )
        if existing.scalar_one_or_none() is not None:
            discovery.status = 'rejected'
            discovery.reviewed_by = admin.id
            discovery.reviewed_at = func.now()
            discovery.rejection_reason = 'Already exists in variant mappings'
            await db.commit()
            await db.refresh(discovery)
            return discovery

        mapping = VariantMapping(
            category=m_cat,
            map_type=discovery.map_type,
            key=discovery.rsid,
            data=m_data,
            is_active=True,
            is_auto_discovered=True,
        )
        db.add(mapping)

    discovery.status = 'approved'
    discovery.reviewed_by = admin.id
    discovery.reviewed_at = func.now()
    await db.commit()
    await db.refresh(discovery)

    # Notify the submitter if known
    if discovery.discovered_by:
        try:
            svc = get_notification_service()
            await svc.create(
                user_id=discovery.discovered_by,
                type='discovery_approved',
                title='Variant Discovery Approved',
                message=f'Variant {discovery.rsid!r} has been approved and added to the variant panel.',
                data={'discovery_id': discovery_id, 'rsid': discovery.rsid},
            )
        except Exception as ne:
            logger.warning(f"Could not send discovery-approved notification: {ne}")

    return discovery


@router.post("/discoveries/bulk-review")
async def bulk_review_discoveries(
    discovery_ids: List[int],
    review: DiscoveryReviewAction,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Bulk approve or reject multiple discoveries."""
    if review.action not in ('approve', 'reject'):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    result = await db.execute(
        select(PendingDiscovery).where(
            PendingDiscovery.id.in_(discovery_ids),
            PendingDiscovery.status == 'pending',
        )
    )
    discoveries = result.scalars().all()

    approved = 0
    rejected = 0
    skipped = 0

    for discovery in discoveries:
        if review.action == 'reject':
            discovery.status = 'rejected'
            discovery.reviewed_by = admin.id
            discovery.reviewed_at = func.now()
            discovery.rejection_reason = review.rejection_reason
            rejected += 1
            continue

        # Approve with duplicate check
        if discovery.discovery_type == 'variant_mapping':
            existing = await db.execute(
                select(VariantMapping.id).where(
                    VariantMapping.category == discovery.mapping_category,
                    VariantMapping.map_type == discovery.map_type,
                    VariantMapping.key == discovery.rsid,
                )
            )
            if existing.scalar_one_or_none() is not None:
                discovery.status = 'rejected'
                discovery.reviewed_by = admin.id
                discovery.reviewed_at = func.now()
                discovery.rejection_reason = 'Duplicate - already exists'
                skipped += 1
                continue

            db.add(VariantMapping(
                category=discovery.mapping_category,
                map_type=discovery.map_type,
                key=discovery.rsid,
                data=discovery.mapping_data,
                is_active=True,
                is_auto_discovered=True,
            ))

        discovery.status = 'approved'
        discovery.reviewed_by = admin.id
        discovery.reviewed_at = func.now()
        approved += 1

    await db.commit()
    return {
        "detail": f"Bulk review complete: {approved} approved, {rejected} rejected, {skipped} skipped (duplicates)",
        "approved": approved,
        "rejected": rejected,
        "skipped": skipped,
    }


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
    from ..db.models import WorkerJob
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
    from ..db.models import WorkerJob
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
    from ..services.ensembl_vep_local import get_ensembl_vep_service
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
    from ..services.annotation_constants import source_status
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
    from ..services.annotation_constants import get_missing_sources, SOURCE_TO_COLUMN

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
    from ..services.annotation_constants import get_missing_sources

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
    from ..services.annotation_constants import SOURCE_TO_COLUMN, REMOTE_API_SOURCES, BQ_SOURCES

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
                from ..services.clinvar_local import get_clinvar_local_service
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
                from ..services.gnomad_local import get_gnomad_service
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
                from ..utils.alpha_missense import get_alpha_missense_service
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
        from ..services.genetic_api_service import OptimizedGeneticAPIService
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
                from ..services.bq_public import get_bq_public_service
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

@router.get("/jobs/summary", response_model=AdminJobsSummary)
async def get_jobs_summary(
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Get summary counts of all analysis jobs by status."""
    result = await db.execute(
        select(
            GeneticAnalysis.analysis_status,
            func.count(GeneticAnalysis.id)
        )
        .where(GeneticAnalysis.deleted_at.is_(None))
        .group_by(GeneticAnalysis.analysis_status)
    )
    counts = {row[0]: row[1] for row in result.all()}
    total = sum(counts.values())
    return AdminJobsSummary(
        total=total,
        pending=counts.get('pending', 0),
        processing=counts.get('processing', 0),
        completed=counts.get('completed', 0),
        failed=counts.get('failed', 0),
    )


def _percentile(sorted_data: List[float], pct: float) -> float:
    """Nearest-rank percentile over already-sorted data (pct in [0, 1])."""
    index = min(len(sorted_data) - 1, int(round(pct * (len(sorted_data) - 1))))
    return sorted_data[index]


@router.get("/jobs/latency", response_model=AdminJobsLatency)
async def get_jobs_latency(
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """p50/p95 analysis completion latency, derived from completed_at - upload_date.

    Measurement only — see LATENCY_P95_THRESHOLD_SECONDS above.
    """
    result = await db.execute(
        select(GeneticAnalysis.upload_date, GeneticAnalysis.completed_at)
        .where(
            GeneticAnalysis.analysis_status == 'completed',
            GeneticAnalysis.completed_at.isnot(None),
            GeneticAnalysis.upload_date.isnot(None),
        )
    )
    durations = sorted(
        (completed_at - upload_date).total_seconds()
        for upload_date, completed_at in result.all()
    )
    if not durations:
        return AdminJobsLatency(sample_size=0)

    p95 = _percentile(durations, 0.95)
    return AdminJobsLatency(
        sample_size=len(durations),
        p50_seconds=round(_percentile(durations, 0.50), 1),
        p95_seconds=round(p95, 1),
        exceeds_threshold=p95 > LATENCY_P95_THRESHOLD_SECONDS,
    )


@router.get("/jobs", response_model=List[AdminJobResponse])
async def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """List all analysis jobs with user info. Optionally filter by status."""
    query = (
        select(GeneticAnalysis, User.email, User.username)
        .join(User, GeneticAnalysis.user_id == User.id)
        .where(GeneticAnalysis.deleted_at.is_(None))
        .order_by(GeneticAnalysis.upload_date.desc())
    )
    if status_filter and status_filter in ('pending', 'processing', 'completed', 'failed'):
        query = query.where(GeneticAnalysis.analysis_status == status_filter)

    result = await db.execute(query)
    rows = result.all()
    return [
        AdminJobResponse(
            id=analysis.id,
            user_id=analysis.user_id,
            user_email=email,
            username=username,
            filename=analysis.filename,
            file_type=analysis.file_type,
            analysis_status=analysis.analysis_status or 'pending',
            progress_percentage=analysis.progress_percentage or 0,
            total_variants=analysis.total_variants or 0,
            processed_variants=analysis.processed_variants or 0,
            current_step=analysis.current_step,
            upload_date=analysis.upload_date,
            estimated_completion=analysis.estimated_completion,
        )
        for analysis, email, username in rows
    ]


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Cancel a running or pending analysis job."""
    from sqlalchemy import update
    result = await db.execute(
        select(GeneticAnalysis).where(GeneticAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")
    if analysis.analysis_status not in ('pending', 'processing', 'paused'):
        raise HTTPException(status_code=400, detail=f"Cannot cancel job with status '{analysis.analysis_status}'")

    await db.execute(
        update(GeneticAnalysis)
        .where(GeneticAnalysis.id == job_id)
        .values(analysis_status="failed", current_step="cancelled_by_admin")
    )
    await db.commit()
    return {"detail": f"Job {job_id} cancelled"}


@router.post("/jobs/{job_id}/pause")
async def pause_job(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Pause a running analysis job. The background task will stop at the next checkpoint."""
    from sqlalchemy import update
    result = await db.execute(
        select(GeneticAnalysis).where(GeneticAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")
    if analysis.analysis_status not in ('processing', 'pending'):
        raise HTTPException(status_code=400, detail=f"Cannot pause job with status '{analysis.analysis_status}'")

    await db.execute(
        update(GeneticAnalysis)
        .where(GeneticAnalysis.id == job_id)
        .values(analysis_status="paused")
    )
    await db.commit()
    return {"detail": f"Job {job_id} paused — will stop at next checkpoint"}


@router.post("/jobs/{job_id}/resume")
async def resume_job(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Resume a paused analysis job from where it left off."""
    from sqlalchemy import update
    result = await db.execute(
        select(GeneticAnalysis).where(GeneticAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")
    if analysis.analysis_status != 'paused':
        raise HTTPException(status_code=400, detail=f"Cannot resume job with status '{analysis.analysis_status}'")

    await db.execute(
        update(GeneticAnalysis)
        .where(GeneticAnalysis.id == job_id)
        .values(analysis_status="pending", current_step="queued (resume)", job_logs=None)
    )
    await db.commit()
    return {"detail": f"Job {job_id} queued for resume"}


@router.post("/jobs/{job_id}/restart")
async def restart_job(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Restart a failed or completed analysis job (full re-analysis)."""
    from sqlalchemy import update

    result = await db.execute(
        select(GeneticAnalysis).where(GeneticAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")
    if analysis.analysis_status in ('processing', 'pending', 'queued'):
        raise HTTPException(status_code=400, detail="Job is already processing or queued")

    await db.execute(
        update(GeneticAnalysis)
        .where(GeneticAnalysis.id == job_id)
        .values(
            analysis_status="pending",
            progress_percentage=0,
            processed_variants=0,
            current_step="queued (restart)",
            estimated_completion=None,
            job_logs=None,
        )
    )
    await db.commit()
    return {"detail": f"Job {job_id} queued for restart"}


@router.post("/jobs/{job_id}/regenerate-insights")
async def regenerate_insights_admin(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Queue insight regeneration for a job (worker picks it up)."""
    from sqlalchemy import update

    result = await db.execute(
        select(GeneticAnalysis).where(GeneticAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")
    if analysis.analysis_status in ('processing', 'pending', 'queued'):
        raise HTTPException(status_code=400, detail="Job is already processing or queued")

    await db.execute(
        update(GeneticAnalysis)
        .where(GeneticAnalysis.id == job_id)
        .values(
            analysis_status="pending",
            progress_percentage=90,
            current_step="regenerating_insights",
            job_logs=None,
        )
    )
    await db.commit()
    return {"detail": f"Insight regeneration queued for job {job_id}"}


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Delete an analysis job and all its associated data (cascade)."""
    result = await db.execute(
        select(GeneticAnalysis).where(GeneticAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")

    # Soft-delete so background tasks see the record is gone
    analysis.analysis_status = 'deleted'
    from sqlalchemy import func as sa_func
    analysis.deleted_at = sa_func.now()
    await db.commit()

    return {"detail": f"Job {job_id} deleted"}


@router.post("/purge-deleted")
async def purge_deleted_analyses(
    older_than_days: int = Query(0, ge=0, description="Hard-delete analyses soft-deleted more than N days ago (0 = all)"),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Queue hard-deletion of soft-deleted analyses as a background worker job."""
    filters = [GeneticAnalysis.deleted_at.isnot(None)]
    if older_than_days > 0:
        cutoff = func.now() - text(f"interval '{int(older_than_days)} days'")
        filters.append(GeneticAnalysis.deleted_at < cutoff)

    result = await db.execute(select(GeneticAnalysis.id).where(*filters))
    ids = [row[0] for row in result.all()]

    if not ids:
        if older_than_days > 0:
            total = await db.execute(
                select(func.count()).select_from(GeneticAnalysis).where(GeneticAnalysis.deleted_at.isnot(None))
            )
            pending = total.scalar() or 0
            if pending:
                return {
                    "detail": f"No analyses deleted more than {older_than_days} days ago. "
                              f"{pending} soft-deleted analyse(s) exist but are newer. Use 0 days to purge all.",
                    "purged": 0,
                }
        return {"detail": "No analyses to purge", "purged": 0}

    from ..db.models import WorkerJob
    job = WorkerJob(
        job_type="purge_deleted",
        status="pending",
        params={"analysis_ids": ids, "older_than_days": older_than_days},
        requested_by=admin.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"Purge job {job.id} queued by admin {admin.id}: {len(ids)} analyses")
    return {
        "job_id": job.id,
        "status": "pending",
        "detail": f"Queued purge of {len(ids)} analyses for background processing",
        "count": len(ids),
    }


@router.get("/jobs/{job_id}/logs")
async def get_job_logs(
    job_id: int,
    last_n: Optional[int] = Query(None, description="Return only the last N log entries"),
    admin: User = Depends(require_admin),
):
    """Get log entries for a specific analysis job.
    
    Returns in-memory logs if the job is still running, otherwise
    falls back to persisted logs from the database.
    """
    from ..services.job_logs import JobLogCollector
    collector = JobLogCollector.get_instance()
    logs = collector.get_logs(job_id, last_n=last_n)
    source = "memory"

    # Fall back to persisted DB logs when in-memory logs are empty
    if not logs:
        from ..db.database import async_session_factory
        async with async_session_factory() as session:
            result = await session.execute(
                select(GeneticAnalysis.job_logs).where(GeneticAnalysis.id == job_id)
            )
            row = result.scalar_one_or_none()
            if row:
                logs = row if isinstance(row, list) else []
                if last_n and logs:
                    logs = logs[-last_n:]
                source = "database"

    return {"job_id": job_id, "count": len(logs), "logs": logs, "source": source}


# ======================================================================
# ClinVar ETL endpoints
# ======================================================================

@router.get("/clinvar-etl/status")
async def clinvar_etl_status(admin: User = Depends(require_admin)):
    """Get current ClinVar import status (row counts + file availability)."""
    from ..services.clinvar_etl import ClinVarETL
    etl = ClinVarETL()
    return await etl.get_import_status()


@router.get("/clinvar-etl/progress")
async def clinvar_etl_progress(admin: User = Depends(require_admin)):
    """Return live progress of the running (or last) ClinVar ETL import."""
    from ..services.clinvar_etl import get_etl_progress
    return get_etl_progress()


@router.post("/clinvar-etl/import")
async def clinvar_etl_import(admin: User = Depends(require_admin)):
    """Kick off a ClinVar ETL import in the background and return immediately.
    Poll GET /clinvar-etl/progress for live status."""
    from ..services.clinvar_etl import ClinVarETL, get_etl_progress

    # Reject concurrent imports
    prog = get_etl_progress()
    if prog.get("running"):
        return {"status": "already_running", "step": prog.get("step"), "pct": prog.get("pct")}

    async def _run():
        etl = ClinVarETL()
        try:
            await etl.run_full_import()
            # Refresh the ClinVar local service cache count
            from ..services.clinvar_local import get_clinvar_local_service
            cv_svc = get_clinvar_local_service()
            await cv_svc.ensure_loaded()
        except Exception:
            pass  # errors are recorded in _etl_progress

    import asyncio as _asyncio
    _asyncio.create_task(_run())
    return {"status": "started"}


# ======================================================================
# GWAS Catalog ETL endpoints
# ======================================================================

@router.get("/gwas-catalog-etl/progress")
async def gwas_catalog_etl_progress(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_session)):
    from ..services.gwas_catalog_etl import get_etl_progress
    from sqlalchemy import text
    prog = get_etl_progress()
    if not prog.get("running"):
        result = await db.execute(text("SELECT COUNT(*) FROM gwas_catalog_associations"))
        prog = dict(prog)
        prog["rows"] = result.scalar() or 0
    return prog


@router.post("/gwas-catalog-etl/import")
async def gwas_catalog_etl_import(admin: User = Depends(require_admin)):
    from ..services.gwas_catalog_etl import run_gwas_etl, get_etl_progress
    prog = get_etl_progress()
    if prog.get("running"):
        return {"status": "already_running", "step": prog.get("step"), "pct": prog.get("pct")}

    async def _run():
        try:
            await run_gwas_etl()
            from ..services.gwas_catalog_local import get_gwas_catalog_service
            await get_gwas_catalog_service().ensure_loaded()
        except Exception:
            pass

    import asyncio as _asyncio
    _asyncio.create_task(_run())
    return {"status": "started"}


# ======================================================================
# ClinGen ETL endpoints
# ======================================================================

@router.get("/clingen-etl/progress")
async def clingen_etl_progress(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_session)):
    from ..services.clingen_etl import get_etl_progress
    from sqlalchemy import text
    prog = get_etl_progress()
    if not prog.get("running"):
        result = await db.execute(text("SELECT COUNT(*) FROM clingen_gene_validity"))
        prog = dict(prog)
        prog["rows"] = result.scalar() or 0
    return prog


@router.post("/clingen-etl/import")
async def clingen_etl_import(admin: User = Depends(require_admin)):
    from ..services.clingen_etl import run_clingen_etl, get_etl_progress
    prog = get_etl_progress()
    if prog.get("running"):
        return {"status": "already_running", "step": prog.get("step"), "pct": prog.get("pct")}

    async def _run():
        try:
            await run_clingen_etl()
            from ..services.clingen_local import get_clingen_service
            await get_clingen_service().ensure_loaded()
        except Exception:
            pass

    import asyncio as _asyncio
    _asyncio.create_task(_run())
    return {"status": "started"}


# ======================================================================
# Open Targets test endpoint
# ======================================================================

@router.get("/open-targets/test")
async def open_targets_test(admin: User = Depends(require_admin)):
    from ..services.open_targets_service import get_open_targets_service
    svc = get_open_targets_service()
    try:
        result = await svc.lookup_by_gene("BRCA1")
        return {
            "status": "ok",
            "reachable": True,
            "test_gene": "BRCA1",
            "found": result.get("found", False),
            "association_count": len(result.get("associations", [])),
            "top_disease": result.get("top_disease"),
            "max_score": result.get("max_score"),
        }
    except Exception as exc:
        return {"status": "error", "reachable": False, "error": str(exc)}


# ======================================================================
# Category Rules endpoints
# ======================================================================

@router.get("/category-rules")
async def list_category_rules(
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """List all category rules, optionally filtered by category."""
    from ..db.models import CategoryRule
    q = select(CategoryRule).order_by(CategoryRule.category, CategoryRule.priority)
    if category:
        q = q.where(CategoryRule.category == category)
    result = await db.execute(q)
    rules = result.scalars().all()
    return [
        {
            "id": r.id, "category": r.category, "rule_type": r.rule_type,
            "rule_value": r.rule_value, "priority": r.priority,
            "is_active": r.is_active, "mapping_data_template": r.mapping_data_template,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rules
    ]


@router.post("/category-rules")
async def create_category_rule(
    rule: CategoryRuleCreate,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Create a new category rule."""
    from ..db.models import CategoryRule
    new_rule = CategoryRule(
        category=rule.category,
        rule_type=rule.rule_type,
        rule_value=rule.rule_value,
        priority=rule.priority,
        is_active=rule.is_active,
        mapping_data_template=rule.mapping_data_template,
    )
    db.add(new_rule)
    await db.commit()
    await db.refresh(new_rule)
    return {"id": new_rule.id, "category": new_rule.category, "rule_type": new_rule.rule_type}


@router.put("/category-rules/{rule_id}")
async def update_category_rule(
    rule_id: int,
    update: CategoryRuleUpdate,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Update a category rule."""
    from ..db.models import CategoryRule
    result = await db.execute(select(CategoryRule).where(CategoryRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await db.commit()
    return {"detail": "Rule updated"}


@router.delete("/category-rules/{rule_id}")
async def delete_category_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Delete a category rule."""
    from ..db.models import CategoryRule
    result = await db.execute(select(CategoryRule).where(CategoryRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.commit()
    return {"detail": "Rule deleted"}


@router.post("/category-rules/seed")
async def seed_rules(
    force: bool = Query(False, description="Delete existing rules before seeding"),
    admin: User = Depends(require_admin),
):
    """Seed default category rules (idempotent unless force=true)."""
    from ..services.auto_categorizer import seed_category_rules
    return await seed_category_rules(force=force)


# ======================================================================
# gnomAD ETL endpoints
# ======================================================================

@router.get("/gnomad-etl/status")
async def gnomad_etl_status(admin: User = Depends(require_admin)):
    """Get current gnomAD import status (row counts + file availability)."""
    from ..services.gnomad_etl import GnomadETL
    etl = GnomadETL()
    return await etl.get_import_status()


@router.post("/gnomad-etl/import")
async def gnomad_etl_import(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch gnomAD ETL to the background worker and return immediately."""
    from ..db.models import WorkerJob
    job = WorkerJob(job_type="etl_gnomad", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"gnomAD ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"gnomAD ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


@router.post("/gnomad/build-cadd-cache")
async def gnomad_build_cadd_cache(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Queue a worker job to build the gnomAD CADD SQLite cache via sequential scan.

    After this completes, all analysis gnomAD lookups hit SQLite (sub-second)
    instead of doing 609K per-variant tabix seeks (~14 min).
    """
    from ..db.models import WorkerJob
    job = WorkerJob(job_type="gnomad_build_cadd_cache", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"gnomAD CADD cache build job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"gnomAD CADD cache build queued as worker job #{job.id}"}


@router.post("/gnomad/refresh-ancestry-afs")
async def gnomad_refresh_ancestry_afs(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
    fst_threshold: float = 0.70,
    index_first: bool = False,
):
    """Queue a worker job to refresh ancestry_aims_panel with gnomAD v2 AFs.

    Reads from local GRCh37 VCF files — no network calls needed.
    Replaces the data previously loaded via the gnomAD GraphQL API.

    index_first=true will create .tbi indexes for any unindexed VCF files first.
    """
    from ..db.models import WorkerJob
    job = WorkerJob(
        job_type="gnomad_refresh_ancestry_afs",
        status="pending",
        params={"fst_threshold": fst_threshold, "index_first": index_first},
        requested_by=admin.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"gnomAD ancestry AF refresh job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"gnomAD ancestry AF refresh queued as worker job #{job.id}"}


@router.get("/gnomad/v2-status")
async def gnomad_v2_status(admin: User = Depends(require_admin)):
    """Get gnomAD v2 VCF file availability and index status."""
    from ..services.gnomad_v2_local import get_gnomad_v2_service
    svc = get_gnomad_v2_service()
    if not svc.is_loaded:
        await svc.ensure_loaded()
    return {
        "file_count": svc.file_count,
        "indexed_count": svc.indexed_count,
        "pg_rows": svc._pg_count,
        "ready": svc.has_pg_data or svc.indexed_count > 0,
    }


# ======================================================================
# gnomAD v2 exome ETL endpoints
# ======================================================================

@router.get("/gnomad-v2-etl/status")
async def gnomad_v2_etl_status(admin: User = Depends(require_admin)):
    """Get current gnomAD v2 exome import status (row counts + file availability)."""
    from ..services.gnomad_v2_etl import GnomadV2ETL
    etl = GnomadV2ETL()
    return await etl.get_import_status()


@router.post("/gnomad-v2-etl/import")
async def gnomad_v2_etl_import(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch gnomAD v2 exome ETL to the background worker and return immediately."""
    from ..db.models import WorkerJob
    # Prevent duplicate pending/processing jobs
    existing = (await db.execute(
        select(WorkerJob).where(
            WorkerJob.job_type == "etl_gnomad_v2",
            WorkerJob.status.in_(["pending", "processing"]),
        )
    )).scalars().first()
    if existing:
        return {"job_id": existing.id, "status": existing.status,
                "detail": f"gnomAD v2 ETL already {existing.status} (job #{existing.id})"}
    job = WorkerJob(job_type="etl_gnomad_v2", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"gnomAD v2 ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"gnomAD v2 ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


# ======================================================================
# AlphaFold ETL endpoints
# ======================================================================

@router.get("/alphafold-etl/status")
async def alphafold_etl_status(admin: User = Depends(require_admin)):
    """Get AlphaFold local data status (SQLite DB protein count)."""
    from ..services.alphafold_local import get_alphafold_local_service
    svc = get_alphafold_local_service()
    if not svc.available:
        svc.ensure_loaded()
    return {
        "alphafold_proteins": svc.protein_count,
        "loaded": svc.available,
        "db_exists": svc._db_path.exists(),
        "db_path": str(svc._db_path),
    }


@router.post("/alphafold-etl/import")
async def alphafold_etl_import(
    force: bool = Query(False, description="Rebuild even if DB already exists"),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch AlphaFold ETL (download + build SQLite) to the background worker."""
    from ..db.models import WorkerJob
    # Prevent duplicate pending/processing jobs
    existing = (await db.execute(
        select(WorkerJob).where(
            WorkerJob.job_type == "etl_alphafold",
            WorkerJob.status.in_(["pending", "processing"]),
        )
    )).scalars().first()
    if existing:
        return {"job_id": existing.id, "status": existing.status,
                "detail": f"AlphaFold ETL already {existing.status} (job #{existing.id})"}
    job = WorkerJob(
        job_type="etl_alphafold",
        status="pending",
        params={"force": force},
        requested_by=admin.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"AlphaFold ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"AlphaFold ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


@router.get("/ensembl-etl/status")
async def ensembl_etl_status(admin: User = Depends(require_admin)):
    """Get current Ensembl gene model import status (row counts + file availability)."""
    import os
    from pathlib import Path
    from sqlalchemy import text as sa_text
    from ..db.database import async_session_factory
    async with async_session_factory() as session:
        total = (await session.execute(sa_text("SELECT COUNT(*) FROM ensembl_genes"))).scalar() or 0
        protein_coding = (await session.execute(
            sa_text("SELECT COUNT(*) FROM ensembl_genes WHERE biotype = 'protein_coding'")
        )).scalar() or 0
        chromosomes = (await session.execute(
            sa_text("SELECT COUNT(DISTINCT chromosome) FROM ensembl_genes")
        )).scalar() or 0
    data_dir = Path(os.environ.get(
        "ENSEMBL_DATA_DIR",
        os.path.join(os.path.dirname(__file__), "..", "..", "data_sources", "ensembl", "homo_sapiens"),
    ))
    fasta_base = data_dir / "fasta"
    cdna_path = fasta_base / "cdna" / "Homo_sapiens.GRCh38.cdna.all.fa.gz"
    ncrna_path = fasta_base / "ncrna" / "Homo_sapiens.GRCh38.ncrna.fa.gz"
    if not cdna_path.exists():
        cdna_path = data_dir / "cdna" / "Homo_sapiens.GRCh38.cdna.all.fa.gz"
    if not ncrna_path.exists():
        ncrna_path = data_dir / "ncrna" / "Homo_sapiens.GRCh38.ncrna.fa.gz"
    return {
        "ensembl_genes": total,
        "protein_coding_genes": protein_coding,
        "chromosomes": chromosomes,
        "cdna_file_exists": cdna_path.exists(),
        "ncrna_file_exists": ncrna_path.exists(),
    }


@router.post("/ensembl-etl/import")
async def ensembl_etl_import(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch Ensembl gene model ETL to the background worker and return immediately."""
    from ..db.models import WorkerJob
    job = WorkerJob(job_type="etl_ensembl", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"Ensembl ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"Ensembl ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


# ======================================================================
# 1000 Genomes Phase 3 ETL endpoints
# ======================================================================

@router.get("/1kg-etl/status")
async def thousand_genomes_etl_status(admin: User = Depends(require_admin)):
    """Get current 1000 Genomes import status (row count + file availability)."""
    from ..services.thousand_genomes_etl import ThousandGenomesETL
    etl = ThousandGenomesETL()
    return await etl.get_import_status()


@router.post("/1kg-etl/import")
async def thousand_genomes_etl_import(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Dispatch 1000 Genomes ETL to the background worker and return immediately."""
    from ..db.models import WorkerJob
    job = WorkerJob(job_type="etl_1kg", status="pending", params={}, requested_by=admin.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"1000 Genomes ETL job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": f"1000 Genomes ETL queued as worker job #{job.id} — monitor via Worker Jobs"}


# ======================================================================
# gnomAD BigQuery backfill endpoints
# ======================================================================

@router.get("/gnomad-bigquery/status")
async def gnomad_bigquery_status(admin: User = Depends(require_admin)):
    """Get BigQuery backfill status — enrichment progress, BQ availability."""
    from ..services.gnomad_bigquery import GnomadBackfillService
    svc = GnomadBackfillService()
    return await svc.get_backfill_status()


@router.post("/gnomad-bigquery/backfill")
async def gnomad_bigquery_backfill(
    batch_size: int = Query(200, ge=10, le=1000, description="Variants per BigQuery query"),
    max_variants: int = Query(10000, ge=100, le=1000000, description="Max variants to process"),
    chromosome: Optional[str] = Query(None, description="Only backfill this chromosome (1-22, X, Y)"),
    admin: User = Depends(require_admin),
):
    """Run BigQuery backfill — enrich local CADD variants with population AFs.
    This queries Google BigQuery and may incur costs. Uses 10 GB byte budget per query."""
    from ..services.gnomad_bigquery import GnomadBackfillService
    svc = GnomadBackfillService()
    return await svc.backfill(
        batch_size=batch_size,
        max_variants=max_variants,
        chromosome=chromosome,
    )


# ======================================================================
# Auto-categorization endpoint
# ======================================================================

@router.post("/auto-categorize")
async def run_auto_categorize(
    categories: Optional[str] = Query(None, description="Comma-separated category filter"),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Queue auto-categorization as a background worker job.

    Returns immediately with a job ID that can be polled via
    GET /api/admin/jobs/{job_id}.
    """
    from ..db.models import WorkerJob
    cat_list = [c.strip() for c in categories.split(",")] if categories else None
    job = WorkerJob(
        job_type="auto_categorize",
        status="pending",
        params={"categories": cat_list} if cat_list else None,
        requested_by=admin.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info(f"Auto-categorize job {job.id} queued by admin {admin.id}")
    return {"job_id": job.id, "status": "pending", "detail": "Queued for worker processing"}


# --- Worker Job status ---

@router.get("/worker-jobs/{job_id}")
async def get_worker_job_status(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Poll the status of a background worker job."""
    from ..db.models import WorkerJob
    result = await db.execute(
        select(WorkerJob).where(WorkerJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "params": job.params,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/worker-jobs")
async def list_worker_jobs(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """List recent worker jobs (auto_categorize, purge_deleted, etc.)."""
    from ..db.models import WorkerJob
    q = (
        select(WorkerJob, User.email, User.username)
        .outerjoin(User, WorkerJob.requested_by == User.id)
        .order_by(WorkerJob.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        q = q.where(WorkerJob.status == status_filter)
    result = await db.execute(q)
    rows = result.all()
    return [
        {
            "job_id": j.id,
            "job_type": j.job_type,
            "status": j.status,
            "params": j.params,
            "result": j.result,
            "error": j.error,
            "job_logs": j.job_logs,
            "requested_by_email": email,
            "requested_by_username": uname,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j, email, uname in rows
    ]


# --- Annotation sentinel reset ---

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
    from ..services.annotation_constants import SOURCE_TO_COLUMN, LOCAL_SOURCES

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


# ======================================================================
# Mapping enrichment endpoint
# ======================================================================

@router.post("/enrich-mappings")
async def enrich_variant_mappings(
    categories: Optional[str] = Query(None, description="Comma-separated category filter"),
    dry_run: bool = Query(False, description="Preview changes without writing"),
    revise_all: bool = Query(False, description="Re-evaluate ALL mappings, not just generic ones"),
    admin: User = Depends(require_admin),
):
    """Enrich existing variant_mappings with proper conditions from all
    available sources.

    Multi-source resolution:
    1. ClinVar variant-level conditions
    2. ClinVar gene-level conditions (clinvar_gene_conditions)
    3. Ensembl gene descriptions (ensembl_genes)

    By default only updates rows with generic '{gene} variant' names.
    With revise_all=True, re-evaluates every active mapping and upgrades
    conditions when a higher-priority source is available.
    Named conditions are never downgraded to generic ones.
    """
    from ..services.multi_source_categorizer import enrich_generic_mappings

    cat_list = [c.strip() for c in categories.split(",")] if categories else None
    stats = await enrich_generic_mappings(dry_run=dry_run, categories=cat_list, revise_all=revise_all)
    logger.info(
        f"Mapping enrichment {'(dry run)' if dry_run else ''}{' (revise all)' if revise_all else ''}: "
        f"{stats['total_updated']}/{stats['total_checked']} updated"
    )
    return stats
