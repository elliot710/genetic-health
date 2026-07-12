"""
Admin variant-mapping registry routes.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_session
from ...db.models import User, VariantMapping
from .schemas import (
    require_admin,
    VariantMappingResponse,
    VariantMappingCreate,
    VariantMappingUpdate,
    VariantMappingCategorySummary,
)

# No prefix here -- folded into admin_routes.router, which already carries
# "/api/admin"; baking it in twice double-prefixes (see admin_routes.py).
router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)


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
    from ...services.multi_source_categorizer import enrich_generic_mappings

    cat_list = [c.strip() for c in categories.split(",")] if categories else None
    stats = await enrich_generic_mappings(dry_run=dry_run, categories=cat_list, revise_all=revise_all)
    logger.info(
        f"Mapping enrichment {'(dry run)' if dry_run else ''}{' (revise all)' if revise_all else ''}: "
        f"{stats['total_updated']}/{stats['total_checked']} updated"
    )
    return stats
