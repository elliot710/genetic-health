"""
Notification routes — WebSocket real-time channel + REST history/management.

WebSocket: ws[s]://host/ws/notifications?token=<JWT>
REST:
  GET    /api/notifications          — list (limit, unread_only)
  GET    /api/notifications/unread-count
  POST   /api/notifications/{id}/read
  POST   /api/notifications/read-all
  DELETE /api/notifications/{id}
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models import User
from ..services.notification_service import get_notification_service
from .auth_routes import get_current_user, verify_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notifications"])

# ──────────────────────────────────────────── WebSocket ─────────────


@router.websocket("/ws/notifications")
async def notifications_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    Real-time notification channel.  Authenticate via:
      • ?token=<JWT>  query param (preferred for WS)
      • ws sends first message {"type": "auth", "token": "..."} (fallback)
    """
    svc = get_notification_service()
    user_id: Optional[int] = None

    # ── Authenticate via query param ──────────────────────────────
    if token:
        username = verify_token(token)
        if username:
            # Resolve user_id from DB
            from ..db.database import async_session_factory
            from ..db.models import User as UserModel
            from sqlalchemy import select
            async with async_session_factory() as db:
                result = await db.execute(
                    select(UserModel.id).where(UserModel.username == username)
                )
                user_id = result.scalar_one_or_none()

    if not user_id:
        # Accept then immediately close with 4001 (unauthorized)
        await websocket.accept()
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await svc.connect(user_id, websocket)

    # Send unread count on connect as a welcome frame
    from ..db.database import async_session_factory
    async with async_session_factory() as db:
        unread = await svc.unread_count(db, user_id)
        recent = await svc.get_for_user(db, user_id, limit=20)

    await websocket.send_json({
        "event": "connected",
        "unread_count": unread,
        "recent": recent,
    })

    try:
        # Keep connection alive — just consume any pings from client
        while True:
            text = await websocket.receive_text()
            # Optionally handle ping/pong or client-sent "mark-read" messages
            if text == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await svc.disconnect(user_id, websocket)


# ──────────────────────────────────────────── REST ──────────────────

notification_router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@notification_router.get("")
async def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = get_notification_service()
    return await svc.get_for_user(db, current_user.id, limit=limit, unread_only=unread_only)


@notification_router.get("/unread-count")
async def unread_count(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = get_notification_service()
    count = await svc.unread_count(db, current_user.id)
    return {"count": count}


@notification_router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = get_notification_service()
    ok = await svc.mark_read(db, notification_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return {"ok": True}


@notification_router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = get_notification_service()
    updated = await svc.mark_all_read(db, current_user.id)
    return {"updated": updated}


@notification_router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = get_notification_service()
    ok = await svc.delete(db, notification_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return {"ok": True}
