"""
Admin API routes for user management and panel marker configuration.
"""
import asyncio
import csv
import io
import logging
import yaml
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from ..db.database import get_session
from ..db.models import User, PanelMarkerConfig, GeneticAnalysis, VariantMapping, PendingDiscovery, SharedVariantAnnotation
from .auth_routes import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger(__name__)


# --- Pydantic schemas ---

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


class MarkerConfigResponse(BaseModel):
    id: int
    panel_id: str
    rsid: str
    gene: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: bool = True
    is_auto_discovered: bool = False
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MarkerConfigCreate(BaseModel):
    panel_id: str
    rsid: str
    gene: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None


class MarkerConfigUpdate(BaseModel):
    rsid: Optional[str] = None
    gene: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


class PanelSummary(BaseModel):
    panel_id: str
    marker_count: int
    active_count: int


# --- Dependencies ---

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


# --- User Management ---

@router.get("/users", response_model=List[AdminUserResponse])
async def list_users(
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """List all users with analysis counts."""
    result = await db.execute(
        select(
            User,
            func.count(GeneticAnalysis.id).label("analysis_count")
        )
        .outerjoin(GeneticAnalysis, User.id == GeneticAnalysis.user_id)
        .group_by(User.id)
        .order_by(User.created_at.desc())
    )
    rows = result.all()
    users = []
    for user, count in rows:
        users.append(AdminUserResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            is_active=user.is_active,
            is_verified=user.is_verified,
            is_admin=user.is_admin,
            created_at=user.created_at,
            analysis_count=count,
        ))
    return users


@router.put("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: int,
    update: AdminUserUpdate,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Update user flags (active, admin, verified)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if update.is_active is not None:
        user.is_active = update.is_active
    if update.is_admin is not None:
        user.is_admin = update.is_admin
    if update.is_verified is not None:
        user.is_verified = update.is_verified

    await db.commit()
    await db.refresh(user)

    # Get analysis count
    count_result = await db.execute(
        select(func.count(GeneticAnalysis.id)).where(GeneticAnalysis.user_id == user_id)
    )
    count = count_result.scalar() or 0

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_admin=user.is_admin,
        created_at=user.created_at,
        analysis_count=count,
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Delete a user. Cannot delete yourself."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user)
    await db.commit()
    return {"detail": "User deleted"}


# --- Panel Marker Configuration ---

@router.get("/panels", response_model=List[PanelSummary])
async def list_panels(
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """List all panels with marker counts."""
    result = await db.execute(
        select(
            PanelMarkerConfig.panel_id,
            func.count().label("marker_count"),
            func.count().filter(PanelMarkerConfig.is_active == True).label("active_count"),
        )
        .group_by(PanelMarkerConfig.panel_id)
        .order_by(PanelMarkerConfig.panel_id)
    )
    rows = result.all()
    return [PanelSummary(panel_id=r[0], marker_count=r[1], active_count=r[2]) for r in rows]


@router.get("/panels/{panel_id}/markers", response_model=List[MarkerConfigResponse])
async def get_panel_markers(
    panel_id: str,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Get all markers for a specific panel."""
    result = await db.execute(
        select(PanelMarkerConfig)
        .where(PanelMarkerConfig.panel_id == panel_id)
        .order_by(PanelMarkerConfig.category, PanelMarkerConfig.gene)
    )
    return result.scalars().all()


@router.post("/panels/{panel_id}/markers", response_model=MarkerConfigResponse, status_code=201)
async def add_panel_marker(
    panel_id: str,
    marker: MarkerConfigCreate,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Add a marker to a panel."""
    # Check for duplicate
    existing = await db.execute(
        select(PanelMarkerConfig).where(
            PanelMarkerConfig.panel_id == panel_id,
            PanelMarkerConfig.rsid == marker.rsid,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Marker already exists for this panel")

    config = PanelMarkerConfig(
        panel_id=panel_id,
        rsid=marker.rsid,
        gene=marker.gene,
        description=marker.description,
        category=marker.category,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


@router.put("/panels/markers/{config_id}", response_model=MarkerConfigResponse)
async def update_panel_marker(
    config_id: int,
    update: MarkerConfigUpdate,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Update a marker configuration."""
    result = await db.execute(select(PanelMarkerConfig).where(PanelMarkerConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Marker config not found")

    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(config, field, value)

    config.updated_at = func.now()
    await db.commit()
    await db.refresh(config)
    return config


@router.delete("/panels/markers/{config_id}")
async def delete_panel_marker(
    config_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Delete a marker from a panel."""
    result = await db.execute(select(PanelMarkerConfig).where(PanelMarkerConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Marker config not found")

    await db.delete(config)
    await db.commit()
    return {"detail": "Marker deleted"}


# --- Export / Import ---

@router.get("/panels/{panel_id}/markers/export")
async def export_panel_markers(
    panel_id: str,
    format: str = Query("csv", pattern="^(csv|yaml)$"),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Export markers for a panel as CSV or YAML."""
    result = await db.execute(
        select(PanelMarkerConfig)
        .where(PanelMarkerConfig.panel_id == panel_id)
        .order_by(PanelMarkerConfig.category, PanelMarkerConfig.gene)
    )
    markers = result.scalars().all()

    rows = [
        {
            "rsid": m.rsid,
            "gene": m.gene or "",
            "description": m.description or "",
            "category": m.category or "",
            "is_active": m.is_active,
        }
        for m in markers
    ]

    if format == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["rsid", "gene", "description", "category", "is_active"])
        writer.writeheader()
        writer.writerows(rows)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={panel_id}_markers.csv"},
        )
    else:
        content = yaml.dump({"panel_id": panel_id, "markers": rows}, default_flow_style=False, allow_unicode=True)
        return StreamingResponse(
            iter([content]),
            media_type="application/x-yaml",
            headers={"Content-Disposition": f"attachment; filename={panel_id}_markers.yaml"},
        )


@router.post("/panels/{panel_id}/markers/import")
async def import_panel_markers(
    panel_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Import markers for a panel from CSV or YAML. Skips duplicates."""
    content = (await file.read()).decode("utf-8")
    filename = file.filename or ""

    if filename.endswith(".yaml") or filename.endswith(".yml"):
        try:
            parsed = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")
        if isinstance(parsed, dict):
            rows = parsed.get("markers", [])
        elif isinstance(parsed, list):
            rows = parsed
        else:
            raise HTTPException(status_code=400, detail="YAML must contain a list or a dict with 'markers' key")
    elif filename.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
    else:
        raise HTTPException(status_code=400, detail="File must be .csv, .yaml, or .yml")

    # Validate rows have required 'rsid' field
    added = 0
    skipped = 0
    for row in rows:
        rsid = row.get("rsid", "").strip()
        if not rsid:
            skipped += 1
            continue

        existing = await db.execute(
            select(PanelMarkerConfig).where(
                PanelMarkerConfig.panel_id == panel_id,
                PanelMarkerConfig.rsid == rsid,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        is_active_raw = row.get("is_active", True)
        if isinstance(is_active_raw, str):
            is_active = is_active_raw.lower() not in ("false", "0", "no")
        else:
            is_active = bool(is_active_raw)

        config = PanelMarkerConfig(
            panel_id=panel_id,
            rsid=rsid,
            gene=row.get("gene", "").strip() or None,
            description=row.get("description", "").strip() or None,
            category=row.get("category", "").strip() or None,
            is_active=is_active,
        )
        db.add(config)
        added += 1

    await db.commit()
    return {"detail": f"Import complete: {added} added, {skipped} skipped"}


# --- Variant Mapping Registry ---

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
    panel_marker_pending: int
    variant_mapping_pending: int


class DiscoveryReviewAction(BaseModel):
    action: str  # 'approve' or 'reject'
    rejection_reason: Optional[str] = None
    # Optional overrides before approving
    description: Optional[str] = None
    category: Optional[str] = None
    mapping_data: Optional[dict] = None


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
        'panel_marker_pending': 0, 'variant_mapping_pending': 0,
    }
    for status_val, dtype, cnt in rows:
        if status_val == 'pending':
            summary['total_pending'] += cnt
            if dtype == 'panel_marker':
                summary['panel_marker_pending'] = cnt
            elif dtype == 'variant_mapping':
                summary['variant_mapping_pending'] = cnt
        elif status_val == 'approved':
            summary['total_approved'] += cnt
        elif status_val == 'rejected':
            summary['total_rejected'] += cnt

    return DiscoverySummary(**summary)


@router.get("/discoveries", response_model=List[PendingDiscoveryResponse])
async def list_discoveries(
    status_filter: Optional[str] = Query('pending', pattern="^(pending|approved|rejected|all)$"),
    discovery_type: Optional[str] = Query(None, pattern="^(panel_marker|variant_mapping)$"),
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
        raise HTTPException(status_code=409, detail=f"Discovery already {discovery.status}")

    if review.action == 'reject':
        discovery.status = 'rejected'
        discovery.reviewed_by = admin.id
        discovery.reviewed_at = func.now()
        discovery.rejection_reason = review.rejection_reason
        await db.commit()
        await db.refresh(discovery)
        return discovery

    # Approve: create the live entry
    if discovery.discovery_type == 'panel_marker':
        # Apply overrides if provided
        desc = review.description or discovery.description
        cat = review.category or discovery.category

        # Final duplicate check
        existing = await db.execute(
            select(PanelMarkerConfig.id).where(
                PanelMarkerConfig.panel_id == discovery.panel_id,
                PanelMarkerConfig.rsid == discovery.rsid,
            )
        )
        if existing.scalar_one_or_none() is not None:
            discovery.status = 'rejected'
            discovery.reviewed_by = admin.id
            discovery.reviewed_at = func.now()
            discovery.rejection_reason = 'Already exists in panel markers'
            await db.commit()
            await db.refresh(discovery)
            raise HTTPException(status_code=409, detail="Marker already exists in the target panel")

        marker = PanelMarkerConfig(
            panel_id=discovery.panel_id,
            rsid=discovery.rsid,
            gene=discovery.gene,
            description=desc,
            category=cat,
            is_active=True,
            is_auto_discovered=True,
        )
        db.add(marker)

    elif discovery.discovery_type == 'variant_mapping':
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
            raise HTTPException(status_code=409, detail="Mapping already exists")

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
        if discovery.discovery_type == 'panel_marker':
            existing = await db.execute(
                select(PanelMarkerConfig.id).where(
                    PanelMarkerConfig.panel_id == discovery.panel_id,
                    PanelMarkerConfig.rsid == discovery.rsid,
                )
            )
            if existing.scalar_one_or_none() is not None:
                discovery.status = 'rejected'
                discovery.reviewed_by = admin.id
                discovery.reviewed_at = func.now()
                discovery.rejection_reason = 'Duplicate - already exists'
                skipped += 1
                continue

            db.add(PanelMarkerConfig(
                panel_id=discovery.panel_id,
                rsid=discovery.rsid,
                gene=discovery.gene,
                description=discovery.description,
                category=discovery.category,
                is_active=True,
                is_auto_discovered=True,
            ))

        elif discovery.discovery_type == 'variant_mapping':
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


# --- Incomplete Annotations ---

class IncompleteAnnotationResponse(BaseModel):
    id: int
    rsid: str
    annotation_status: Optional[str] = None
    failed_sources: Optional[list] = None
    total_api_calls: int = 0
    # Source status: "found" = has data, "no_data" = confirmed absence, "missing" = never queried/error
    ensembl: str = "missing"
    clinvar: str = "missing"
    clinpgx: str = "missing"
    snpedia: str = "missing"
    litvar: str = "missing"
    first_annotated_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    usage_count: int = 0

    class Config:
        from_attributes = True


class IncompleteAnnotationSummary(BaseModel):
    total_annotations: int
    complete: int
    partial: int
    failed: int


@router.get("/annotations/incomplete/summary", response_model=IncompleteAnnotationSummary)
async def get_incomplete_summary(
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Get counts of incomplete annotations."""
    result = await db.execute(
        select(SharedVariantAnnotation.annotation_status, func.count().label("cnt"))
        .group_by(SharedVariantAnnotation.annotation_status)
    )
    rows = {r[0]: r[1] for r in result.all()}
    total = sum(rows.values())
    return IncompleteAnnotationSummary(
        total_annotations=total,
        complete=rows.get('completed', 0),
        partial=rows.get('partial', 0),
        failed=rows.get('failed', 0),
    )


@router.get("/annotations/incomplete", response_model=List[IncompleteAnnotationResponse])
async def list_incomplete_annotations(
    status_filter: Optional[str] = Query('partial', pattern="^(partial|failed|all)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """List annotations with incomplete data from external sources."""
    q = select(SharedVariantAnnotation)
    if status_filter == 'all':
        q = q.where(SharedVariantAnnotation.annotation_status.in_(['partial', 'failed']))
    else:
        q = q.where(SharedVariantAnnotation.annotation_status == status_filter)
    q = q.order_by(SharedVariantAnnotation.usage_count.desc()).limit(limit).offset(offset)

    result = await db.execute(q)
    annotations = result.scalars().all()

    def _source_status(data):
        if data is None:
            return "missing"
        if isinstance(data, dict):
            if data.get('found', False):
                return "found"
            return "no_data"  # confirmed absence
        return "missing"

    return [
        IncompleteAnnotationResponse(
            id=a.id,
            rsid=a.rsid,
            annotation_status=a.annotation_status,
            failed_sources=a.failed_sources,
            total_api_calls=a.total_api_calls or 0,
            ensembl=_source_status(a.ensembl_data),
            clinvar=_source_status(a.clinvar_data),
            clinpgx=_source_status(a.pharmgkb_data),
            snpedia=_source_status(a.snpedia_data),
            litvar=_source_status(a.litvar_data),
            first_annotated_at=a.first_annotated_at,
            last_updated_at=a.last_updated_at,
            usage_count=a.usage_count or 0,
        )
        for a in annotations
    ]


@router.post("/annotations/retrigger/{annotation_id}")
async def retrigger_annotation(
    annotation_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Re-trigger external API calls for failed sources of an incomplete annotation."""
    result = await db.execute(
        select(SharedVariantAnnotation).where(SharedVariantAnnotation.id == annotation_id)
    )
    annotation = result.scalar_one_or_none()
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    failed = annotation.failed_sources or []
    if not failed and annotation.annotation_status == 'completed':
        return {"detail": "Annotation is already complete", "updated_sources": []}

    # Determine which sources to retry (only null or not-yet-confirmed sources)
    sources_to_retry = []
    ALL_SOURCES = ['ensembl', 'clinvar', 'clinpgx', 'snpedia']
    # Map source name to DB column name (clinpgx data stored in pharmgkb_data column)
    SOURCE_TO_COLUMN = {'ensembl': 'ensembl', 'clinvar': 'clinvar', 'clinpgx': 'pharmgkb', 'snpedia': 'snpedia'}
    for src in ALL_SOURCES:
        col = SOURCE_TO_COLUMN.get(src, src)
        src_data = getattr(annotation, f'{col}_data', None)
        if src_data is None:
            sources_to_retry.append(src)
        elif isinstance(src_data, dict) and not src_data.get('found', True) and not src_data.get('confirmed_no_data', False):
            sources_to_retry.append(src)

    if not sources_to_retry:
        annotation.annotation_status = 'completed'
        annotation.failed_sources = None
        await db.commit()
        return {"detail": "All sources already have data or confirmed no data", "updated_sources": [], "confirmed_no_data": [], "still_failed": [], "new_status": "completed"}

    # Import and call the API service
    from ..services.genetic_api_service import OptimizedGeneticAPIService
    api_service = OptimizedGeneticAPIService()
    await api_service.initialize()

    updated = []
    still_failed = []
    confirmed_no_data = []

    try:
        for src in sources_to_retry:
            try:
                method = getattr(api_service, f'_get_{src}_annotation', None)
                if not method:
                    still_failed.append(src)
                    continue
                result_data = await method(annotation.rsid)
                col = SOURCE_TO_COLUMN.get(src, src)
                if result_data and isinstance(result_data, dict) and result_data.get('found', False):
                    setattr(annotation, f'{col}_data', result_data)
                    updated.append(src)
                else:
                    # API responded but no data — mark as confirmed absence
                    setattr(annotation, f'{col}_data', {'found': False, 'confirmed_no_data': True, 'source': src})
                    confirmed_no_data.append(src)
            except Exception as e:
                still_failed.append(src)
    finally:
        await api_service.close()

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

    from ..services.genetic_api_service import OptimizedGeneticAPIService
    api_service = OptimizedGeneticAPIService()
    await api_service.initialize()

    completed_count = 0
    still_incomplete = 0

    ALL_SOURCES = ['ensembl', 'clinvar', 'clinpgx', 'snpedia']
    SOURCE_TO_COLUMN = {'ensembl': 'ensembl', 'clinvar': 'clinvar', 'clinpgx': 'pharmgkb', 'snpedia': 'snpedia'}

    try:
        for idx, ann in enumerate(annotations):
            # Rate-limit between annotations to avoid overwhelming external APIs
            if idx > 0:
                await asyncio.sleep(0.5)

            sources_to_retry = []
            for src in ALL_SOURCES:
                col = SOURCE_TO_COLUMN.get(src, src)
                src_data = getattr(ann, f'{col}_data', None)
                if src_data is None:
                    sources_to_retry.append(src)
                elif isinstance(src_data, dict) and not src_data.get('found', True) and not src_data.get('confirmed_no_data', False):
                    sources_to_retry.append(src)

            if not sources_to_retry:
                ann.annotation_status = 'completed'
                ann.failed_sources = None
                completed_count += 1
                continue

            still_failed = []
            for src in sources_to_retry:
                try:
                    method = getattr(api_service, f'_get_{src}_annotation', None)
                    if not method:
                        still_failed.append(src)
                        continue
                    result_data = await method(ann.rsid)
                    col = SOURCE_TO_COLUMN.get(src, src)
                    if result_data and isinstance(result_data, dict) and result_data.get('found', False):
                        setattr(ann, f'{col}_data', result_data)
                    else:
                        # API responded but no data — confirmed absence, not a failure
                        setattr(ann, f'{col}_data', {'found': False, 'confirmed_no_data': True, 'source': src})
                except Exception:
                    still_failed.append(src)

            ann.failed_sources = still_failed if still_failed else None
            ann.annotation_status = 'completed' if not still_failed else 'partial'
            if not still_failed:
                completed_count += 1
            else:
                still_incomplete += 1
    finally:
        await api_service.close()

    await db.commit()
    return {
        "detail": f"Bulk retrigger complete: {completed_count} now complete, {still_incomplete} still incomplete",
        "completed": completed_count,
        "still_incomplete": still_incomplete,
        "total_processed": len(annotations),
    }


# --- Job Management ---

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
        ).group_by(GeneticAnalysis.analysis_status)
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
    if analysis.analysis_status not in ('pending', 'processing'):
        raise HTTPException(status_code=400, detail=f"Cannot cancel job with status '{analysis.analysis_status}'")

    await db.execute(
        update(GeneticAnalysis)
        .where(GeneticAnalysis.id == job_id)
        .values(analysis_status="failed", current_step="cancelled_by_admin")
    )
    await db.commit()
    return {"detail": f"Job {job_id} cancelled"}


@router.post("/jobs/{job_id}/restart")
async def restart_job(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Restart a failed or completed analysis job."""
    from sqlalchemy import update

    result = await db.execute(
        select(GeneticAnalysis).where(GeneticAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")
    if analysis.analysis_status == 'processing':
        raise HTTPException(status_code=400, detail="Job is already processing")

    await db.execute(
        update(GeneticAnalysis)
        .where(GeneticAnalysis.id == job_id)
        .values(
            analysis_status="processing",
            progress_percentage=0,
            processed_variants=0,
            current_step="initializing",
            estimated_completion=None,
        )
    )
    await db.commit()

    user_id = analysis.user_id

    async def run_analysis():
        try:
            from ..core.container import ServiceManager
            async with ServiceManager() as service_manager:
                analysis_service = service_manager.get_analysis_service(user_id)
                await analysis_service.process_analysis(job_id)
        except Exception as e:
            logger.error(f"Admin-restarted analysis {job_id} failed: {e}")

    asyncio.create_task(run_analysis())
    return {"detail": f"Job {job_id} restarted"}


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
    if analysis.analysis_status == 'processing':
        raise HTTPException(status_code=400, detail="Cannot delete a job that is currently processing. Cancel it first.")

    await db.delete(analysis)
    await db.commit()
    return {"detail": f"Job {job_id} deleted"}


@router.get("/jobs/{job_id}/logs")
async def get_job_logs(
    job_id: int,
    last_n: Optional[int] = Query(None, description="Return only the last N log entries"),
    admin: User = Depends(require_admin),
):
    """Get in-memory log entries for a specific analysis job."""
    from ..services.job_logs import JobLogCollector
    collector = JobLogCollector.get_instance()
    logs = collector.get_logs(job_id, last_n=last_n)
    return {"job_id": job_id, "count": len(logs), "logs": logs}
