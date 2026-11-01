"""Service layer for creating and managing privacy-safe in-app notifications."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from app.modules.notifications.schemas import (
    CursorNotificationListResponse,
    MarkNotificationsReadRequest,
    NotificationResponse,
)
from app.modules.posts.service import decode_cursor, encode_cursor

NOTIF_COLUMNS = (
    "id",
    "recipient_user_id",
    "notification_type",
    "reference_type",
    "reference_id",
    "title",
    "body_preview",
    "is_read",
    "created_at",
)


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(NOTIF_COLUMNS, row))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class NotificationService:
    """Creates and queries in-app alerts while respecting anonymous author boundaries."""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def create_notification(
        self,
        *,
        recipient_user_id: str,
        notification_type: str,
        reference_type: str,
        reference_id: str,
        title: str,
        body_preview: Optional[str] = None,
    ) -> str:
        notif_id = str(uuid.uuid4())
        preview = (body_preview or "")[:240] or None
        await self.session.execute(
            """
            INSERT INTO notifications (
                id, recipient_user_id, notification_type, reference_type,
                reference_id, title, body_preview, is_read, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                notif_id,
                recipient_user_id,
                notification_type,
                reference_type,
                reference_id,
                title[:160],
                preview,
                _now_iso(),
            ),
        )
        return notif_id

    async def list_notifications(
        self,
        *,
        user_id: str,
        unread_only: bool = False,
        cursor: Optional[str] = None,
        limit: int = 20,
    ) -> CursorNotificationListResponse:
        safe_limit = max(1, min(limit, 50))
        clauses = ["recipient_user_id = ?"]
        params: List[Any] = [user_id]

        if unread_only:
            clauses.append("is_read = 0")

        if cursor:
            c_time, c_id = decode_cursor(cursor)
            clauses.append("(created_at < ? OR (created_at = ? AND id < ?))")
            params.extend([c_time, c_time, c_id])

        where_sql = " AND ".join(clauses)
        rows = await self.session.execute(
            f"""
            SELECT {', '.join(NOTIF_COLUMNS)}
            FROM notifications
            WHERE {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            tuple(params + [safe_limit + 1]),
        )

        has_more = len(rows) > safe_limit
        sliced = rows[:safe_limit]

        items = [
            NotificationResponse(
                id=str(d["id"]),
                notification_type=str(d["notification_type"]),
                reference_type=str(d["reference_type"]),
                reference_id=str(d["reference_id"]),
                title=str(d["title"]),
                body_preview=d.get("body_preview"),
                is_read=bool(d["is_read"]),
                created_at=str(d["created_at"]),
            )
            for d in (_row_to_dict(r) for r in sliced)
        ]

        unread_rows = await self.session.execute(
            "SELECT COUNT(*) FROM notifications WHERE recipient_user_id = ? AND is_read = 0",
            (user_id,),
        )
        unread_count = int(unread_rows[0][0]) if unread_rows else 0

        next_cur: Optional[str] = None
        if has_more and items:
            last = items[-1]
            next_cur = encode_cursor(last.created_at, last.id)

        return CursorNotificationListResponse(
            items=items,
            unread_count=unread_count,
            next_cursor=next_cur,
            has_more=has_more,
        )

    async def mark_read(
        self,
        *,
        user_id: str,
        payload: MarkNotificationsReadRequest,
    ) -> int:
        if payload.mark_all:
            await self.session.execute(
                "UPDATE notifications SET is_read = 1 WHERE recipient_user_id = ? AND is_read = 0",
                (user_id,),
            )
            return 1

        if not payload.notification_ids:
            return 0

        updated = 0
        for nid in payload.notification_ids:
            await self.session.execute(
                "UPDATE notifications SET is_read = 1 WHERE id = ? AND recipient_user_id = ?",
                (nid, user_id),
            )
            updated += 1
        return updated
