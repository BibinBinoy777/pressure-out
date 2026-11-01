"""Pydantic schemas for Phase 6 Threaded Comments & Sticky Anonymous OP Replies."""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.core.unicode import normalize_unicode_nfc
from app.modules.identity.schemas import PublicAuthorDisplay


def validate_and_normalize_comment_body(body: str) -> str:
    norm = normalize_unicode_nfc(body).strip()
    if len(norm) < 1 or len(norm) > 5000:
        raise AppError(
            code="VALIDATION_ERROR",
            message="Comment body must be between 1 and 5,000 characters.",
            status_code=422,
        )
    return norm


class CreateCommentRequest(BaseModel):
    parent_comment_id: Optional[str] = Field(
        None, description="Optional parent comment ID for threaded replies (max depth 10)"
    )
    body: str = Field(..., min_length=1, max_length=5000)
    identity_mode: Optional[str] = Field(
        None,
        description="Per-comment identity mode. Defaults to 'anonymous' (Anonymous OP) if replying to own anonymous post!",
    )
    confirm_op_identity_reveal: bool = Field(
        False,
        description="Must be True if the author of an anonymous post explicitly wishes to reply under their handle.",
    )
    content_language: str = Field("en")
    acknowledge_pii_warning: bool = False


class UpdateCommentRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)
    acknowledge_pii_warning: bool = False


class CommentStatsResponse(BaseModel):
    score: int
    upvote_count: int
    downvote_count: int
    reaction_counts: Dict[str, int]


class CommentViewerContext(BaseModel):
    is_author: bool
    can_edit: bool
    can_delete: bool
    viewer_vote: int = 0
    viewer_reactions: List[str] = Field(default_factory=list)


class PublicCommentResponse(BaseModel):
    """Privacy-safe public comment representation.

    NEVER includes `author_user_id`. When `identity_mode == 'anonymous'`,
    `author` displays either `'Anonymous OP'` or a thread-scoped label
    (`'Anonymous • 4F2A'`) with zero link to `@handle` or `user_id`.
    """

    id: str
    post_id: str
    parent_comment_id: Optional[str] = None
    path: str
    depth: int
    identity_mode: str
    author: PublicAuthorDisplay
    body: str
    content_language: str
    is_deleted: bool = False
    stats: CommentStatsResponse
    viewer_context: CommentViewerContext
    pii_warnings: List[Dict[str, str]] = Field(default_factory=list)
    created_at: str
    updated_at: str


class CursorCommentListResponse(BaseModel):
    items: List[PublicCommentResponse]
    next_cursor: Optional[str] = None
    has_more: bool
