"""
WebSocket connection manager and notification service.

Manages per-user WebSocket connections and provides helpers to
create DB-persisted notifications + push them to connected clients.

Notification types:
  analysis_queued       — analysis queued for processing
  analysis_completed    — analysis finished successfully
  analysis_failed       — analysis encountered a fatal error
  analysis_progress     — periodic progress update (not persisted to DB)
  upload_complete       — file uploaded and variants stored
  upload_failed         — file processing failed
  variant_saved         — user bookmarked a variant
  discovery_approved    — admin approved a pending discovery
  discovery_rejected    — admin rejected a pending discovery
  data_deleted          — user's analysis data was deleted
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import WebSocket
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import async_session_factory
from ..db.models import Notification

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Singleton service that tracks WebSocket connections and sends notifications.
    """

    def __init__(self) -> None:
        # user_id → set of active WebSocket connections
        self._connections: dict[int, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    # ─────────────────────────────────────── connection management ──

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(websocket)
        logger.info(f"[notifications] user {user_id} connected ({len(self._connections[user_id])} sockets)")

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            bucket = self._connections.get(user_id, set())
            bucket.discard(websocket)
            if not bucket:
                self._connections.pop(user_id, None)
        logger.debug(f"[notifications] user {user_id} disconnected")

    # ─────────────────────────────────────── push helpers ───────────

    async def _push_to_user(self, user_id: int, payload: dict) -> None:
        """Send a JSON payload to every active WebSocket for a user (best-effort)."""
        sockets = list(self._connections.get(user_id, set()))
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        # clean up stale connections
        if dead:
            async with self._lock:
                bucket = self._connections.get(user_id, set())
                for d in dead:
                    bucket.discard(d)
                if not bucket:
                    self._connections.pop(user_id, None)

    # ─────────────────────────────────────── public API ─────────────

    async def create(
        self,
        user_id: int,
        type: str,
        title: str,
        message: str,
        data: Optional[dict[str, Any]] = None,
    ) -> Notification:
        """Persist a notification to the DB and push it to connected clients."""
        async with async_session_factory() as session:
            notif = Notification(
                user_id=user_id,
                type=type,
                title=title,
                message=message,
                data=data or {},
                read=False,
            )
            session.add(notif)
            await session.commit()
            await session.refresh(notif)

        payload = {
            "event": "notification",
            "notification": _serialize(notif),
        }
        await self._push_to_user(user_id, payload)
        return notif

    async def push_progress(
        self,
        user_id: int,
        analysis_id: int,
        progress: int,
        step: str,
    ) -> None:
        """Push a live progress update (not persisted to DB)."""
        payload = {
            "event": "analysis_progress",
            "analysis_id": analysis_id,
            "progress": progress,
            "step": step,
        }
        await self._push_to_user(user_id, payload)

    # ─────────────────────────────────────── REST helpers ───────────

    async def get_for_user(
        self,
        db: AsyncSession,
        user_id: int,
        limit: int = 50,
        unread_only: bool = False,
    ) -> list[dict]:
        stmt = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        if unread_only:
            stmt = stmt.where(Notification.read.is_(False))
        result = await db.execute(stmt)
        return [_serialize(n) for n in result.scalars().all()]

    async def mark_read(self, db: AsyncSession, notification_id: int, user_id: int) -> bool:
        result = await db.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
            .values(read=True)
            .returning(Notification.id)
        )
        await db.commit()
        return result.scalar_one_or_none() is not None

    async def mark_all_read(self, db: AsyncSession, user_id: int) -> int:
        result = await db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read.is_(False))
            .values(read=True)
            .returning(Notification.id)
        )
        await db.commit()
        return len(result.all())

    async def delete(self, db: AsyncSession, notification_id: int, user_id: int) -> bool:
        notif = await db.get(Notification, notification_id)
        if not notif or notif.user_id != user_id:
            return False
        await db.delete(notif)
        await db.commit()
        return True

    async def unread_count(self, db: AsyncSession, user_id: int) -> int:
        from sqlalchemy import func
        result = await db.execute(
            select(func.count()).where(
                Notification.user_id == user_id,
                Notification.read.is_(False),
            )
        )
        return result.scalar_one() or 0


# ────────────────────────────────────────────── helpers ─────────────


def _serialize(notif: Notification) -> dict:
    return {
        "id": notif.id,
        "type": notif.type,
        "title": notif.title,
        "message": notif.message,
        "data": notif.data or {},
        "read": notif.read,
        "created_at": (
            notif.created_at.isoformat()
            if notif.created_at
            else datetime.now(timezone.utc).isoformat()
        ),
    }


# ────────────────────────────────────────────── singleton ───────────

_instance: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    global _instance
    if _instance is None:
        _instance = NotificationService()
    return _instance
