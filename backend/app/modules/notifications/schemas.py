"""Pydantic schemas for Phase 6 In-App Notifications."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    id: str
    notification_type: str
    reference_type: str
    reference_id: str
    title: str
    body_preview: Optional[str] = None
    is_read: bool
    created_at: str


class CursorNotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    unread_count: int
    next_cursor: Optional[str] = None
    has_more: bool


class MarkNotificationsReadRequest(BaseModel):
    notification_ids: List[str] = Field(default_factory=list)
    mark_all: bool = False
