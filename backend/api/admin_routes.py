"""
Admin API routes for user management and panel marker configuration.
"""
import csv
import io
import yaml
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from ..db.database import get_session
from ..db.models import User, PanelMarkerConfig, GeneticAnalysis, VariantMapping
from .auth_routes import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


# --- Pydantic schemas ---

class AdminUserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: Optional[str] = None
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
