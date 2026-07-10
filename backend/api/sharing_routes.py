"""
Dashboard sharing routes.

Allows users to share their dashboard with other users by email.
The recipient can then view the owner's insights via a read-only endpoint.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models import User, DashboardShare, DashboardCache
from .auth_routes import get_current_user
from ..services.dashboard_service import build_dashboard_for_user
from ..services.notification_service import get_notification_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sharing", tags=["sharing"])


# ── request / response models ────────────────────────────────────────────────

class ShareRequest(BaseModel):
    email: EmailStr


class ShareEntry(BaseModel):
    id: int
    email: str
    full_name: str | None = None
    avatar_url: str | None = None
    shared_since: str | None = None


# ── helpers ──────────────────────────────────────────────────────────────────

def _user_entry(user: User, share: DashboardShare) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
        "shared_since": share.created_at.isoformat() if share.created_at else None,
    }


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/share", status_code=200)
async def share_with_user(
    body: ShareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Share the current user's dashboard with another user by email."""
    if body.email.lower() == current_user.email.lower():
        raise HTTPException(status_code=400, detail="You cannot share with yourself")

    # Find recipient
    result = await db.execute(select(User).where(User.email == body.email))
    recipient = result.scalar_one_or_none()
    if not recipient:
        raise HTTPException(status_code=404, detail="No user found with that email address")

    # Check if already shared
    existing = await db.execute(
        select(DashboardShare).where(
            DashboardShare.owner_id == current_user.id,
            DashboardShare.recipient_id == recipient.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="You have already shared your dashboard with this user")

    share = DashboardShare(owner_id=current_user.id, recipient_id=recipient.id)
    db.add(share)
    await db.commit()

    # Notify recipient
    try:
        svc = get_notification_service()
        owner_name = current_user.full_name or current_user.username
        await svc.create(
            user_id=recipient.id,
            type="dashboard_shared",
            title="Dashboard Shared With You",
            message=f"{owner_name} has shared their genetic dashboard with you.",
            data={"owner_id": current_user.id, "owner_name": owner_name},
        )
    except Exception as e:
        logger.warning(f"Could not send dashboard_shared notification: {e}")

    owner_name = current_user.full_name or current_user.username
    return {"detail": f"Dashboard shared with {recipient.email}", "recipient_name": recipient.full_name or recipient.email}


@router.delete("/share/{recipient_id}", status_code=200)
async def unshare_with_user(
    recipient_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Revoke a dashboard share."""
    result = await db.execute(
        select(DashboardShare).where(
            DashboardShare.owner_id == current_user.id,
            DashboardShare.recipient_id == recipient_id,
        )
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")
    await db.delete(share)
    await db.commit()
    return {"detail": "Share revoked"}


@router.get("/my-shares")
async def get_my_shares(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List the users I have shared my dashboard with."""
    result = await db.execute(
        select(DashboardShare, User)
        .join(User, User.id == DashboardShare.recipient_id)
        .where(DashboardShare.owner_id == current_user.id)
        .order_by(DashboardShare.created_at.desc())
    )
    rows = result.all()
    return [_user_entry(user, share) for share, user in rows]


@router.get("/shared-with-me")
async def get_shared_with_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List the users who have shared their dashboard with me."""
    result = await db.execute(
        select(DashboardShare, User)
        .join(User, User.id == DashboardShare.owner_id)
        .where(DashboardShare.recipient_id == current_user.id)
        .order_by(DashboardShare.created_at.desc())
    )
    rows = result.all()
    return [_user_entry(user, share) for share, user in rows]


@router.get("/dashboard/{owner_id}")
async def get_shared_dashboard(
    owner_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Return the owner's dashboard data — only if the owner has shared with the current user.
    Serves from the owner's DashboardCache; returns a not-ready placeholder if no cache exists.
    """
    # Validate share exists
    result = await db.execute(
        select(DashboardShare).where(
            DashboardShare.owner_id == owner_id,
            DashboardShare.recipient_id == current_user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="This dashboard has not been shared with you")

    # Serve from cache
    cache_result = await db.execute(
        select(DashboardCache).where(DashboardCache.user_id == owner_id)
    )
    cached = cache_result.scalar_one_or_none()
    if cached and cached.dashboard_json:
        return cached.dashboard_json

    # No cache — build on demand from owner's completed analyses
    dashboard_data = await build_dashboard_for_user(db, owner_id)
    if dashboard_data:
        return dashboard_data

    return {
        "summary": {
            "total_variants": 0,
            "analysis_id": None,
            "status": "no_data",
        },
        "health_risks": [],
        "ancestry_results": [],
        "sports_performance": [],
        "nutrition_traits": [],
        "metabolic": {},
        "carrier_status": [],
        "drug_responses": [],
        "rare_mutations": [],
        "methylation_profiles": [],
        "detoxification_profiles": [],
        "physical_traits": [],
        "intelligence": [],
        "personality_traits": [],
        "wellness_traits": [],
        "uncommon_mutations": [],
    }
