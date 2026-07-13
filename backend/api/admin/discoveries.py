"""
Admin pending-discovery review routes.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_session
from ...db.models import User, VariantMapping, PendingDiscovery
from ...services.notification_service import get_notification_service
from .schemas import (
    require_admin,
    DiscoverySummary,
    PendingDiscoveryResponse,
    DiscoveryReviewAction,
)

# No prefix here -- folded into the admin package's aggregated router (see
# admin/__init__.py), which carries "/api/admin"; baking it in twice
# double-prefixes.
router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)


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
