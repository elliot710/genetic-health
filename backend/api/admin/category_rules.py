"""
Admin category-rule management + auto-categorization routes.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update

from ...db.database import get_session
from ...db.models import User
from .schemas import (
    require_admin,
    CategoryRuleCreate,
    CategoryRuleUpdate,
)

# No prefix here -- folded into the admin package's aggregated router (see
# admin/__init__.py), which carries "/api/admin"; baking it in twice
# double-prefixes.
router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)


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
    from ...db.models import CategoryRule
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
    from ...db.models import CategoryRule
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
    from ...db.models import CategoryRule
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
    from ...db.models import CategoryRule
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
    from ...services.auto_categorizer import seed_category_rules
    return await seed_category_rules(force=force)




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
    from ...db.models import WorkerJob
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

