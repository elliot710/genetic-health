"""
Admin user-management routes.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_session
from ...db.models import User, GeneticAnalysis
from .schemas import AdminUserResponse, AdminUserUpdate, require_admin

# No prefix here -- folded into admin_routes.router, which already carries
# "/api/admin"; baking it in twice double-prefixes (see admin_routes.py).
router = APIRouter(tags=["admin"])


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
        .outerjoin(
            GeneticAnalysis,
            (User.id == GeneticAnalysis.user_id) & (GeneticAnalysis.deleted_at.is_(None))
        )
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
        select(func.count(GeneticAnalysis.id)).where(
            GeneticAnalysis.user_id == user_id,
            GeneticAnalysis.deleted_at.is_(None),
        )
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
