"""REST API endpoints for In-App Notifications (`/api/v1/notifications`)."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_notification_service, require_authenticated_context
from app.modules.notifications.schemas import (
    CursorNotificationListResponse,
    MarkNotificationsReadRequest,
)
from app.modules.notifications.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    response_model=CursorNotificationListResponse,
    summary="Retrieve cursor-paginated in-app notifications for the current user",
)
async def list_notifications(
    unread_only: bool = Query(False),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: NotificationService = Depends(get_notification_service),
) -> CursorNotificationListResponse:
    return await service.list_notifications(
        user_id=str(auth_ctx["user"]["id"]),
        unread_only=unread_only,
        cursor=cursor,
        limit=limit,
    )


@router.patch(
    "/read",
    summary="Mark specific or all notifications as read",
)
async def mark_notifications_read(
    payload: MarkNotificationsReadRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: NotificationService = Depends(get_notification_service),
) -> dict[str, int]:
    count = await service.mark_read(
        user_id=str(auth_ctx["user"]["id"]),
        payload=payload,
    )
    return {"updated_count": count}
