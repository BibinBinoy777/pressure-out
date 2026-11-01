"""Pydantic schemas and validators for Phase 9 Trust, Safety, Reporting & Moderation."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.core.unicode import normalize_unicode_nfc
from app.modules.identity.schemas import PublicAuthorDisplay

VALID_REPORT_TARGETS: tuple[str, ...] = (
    "post",
    "comment",
    "profile",
    "meme_asset",
)

VALID_REPORT_REASONS: tuple[str, ...] = (
    "doxxing_pii",
    "harassment",
    "threat",
    "impersonation",
    "spam",
    "hate_speech",
    "confidential_ip",
    "misleading_allegation",
    "other",
)

HIGH_SEVERITY_REASONS: frozenset[str] = frozenset({"doxxing_pii", "threat"})

MEDIUM_SEVERITY_REASONS: frozenset[str] = frozenset(
    {"harassment", "hate_speech", "confidential_ip", "impersonation"}
)

VALID_REPORT_STATUSES: tuple[str, ...] = (
    "open",
    "in_review",
    "escalated_language_specialist",
    "resolved_actioned",
    "resolved_dismissed",
)

VALID_MODERATION_TARGETS: tuple[str, ...] = (
    "post",
    "comment",
    "user",
    "meme_asset",
)

VALID_MODERATION_ACTIONS: tuple[str, ...] = (
    "dismiss_reports",
    "redact_pii",
    "restrict_visibility",
    "place_under_review",
    "remove_content",
    "restore_content",
    "escalate_language_specialist",
    "user_cooldown",
    "user_suspend",
    "restore_user",
)

VALID_ACTION_REASONS: tuple[str, ...] = (
    "doxxing_pii",
    "harassment",
    "threat",
    "impersonation",
    "spam",
    "hate_speech",
    "confidential_ip",
    "misleading_allegation",
    "other",
    "no_violation_found",
    "appeal_overturned",
    "auto_velocity_hold",
    "language_specialist_needed",
)

VALID_BLOCK_MODES: tuple[str, ...] = ("block", "mute")


def validate_report_target_type(target_type: str) -> str:
    cleaned = (target_type or "").strip().lower()
    if cleaned not in VALID_REPORT_TARGETS:
        raise AppError(
            code="INVALID_REPORT_TARGET",
            message=f"Target type must be one of: {', '.join(VALID_REPORT_TARGETS)}.",
            status_code=422,
        )
    return cleaned


def validate_report_reason(reason_code: str) -> str:
    cleaned = (reason_code or "").strip().lower()
    if cleaned not in VALID_REPORT_REASONS:
        raise AppError(
            code="INVALID_REPORT_REASON",
            message=f"Report reason must be one of: {', '.join(VALID_REPORT_REASONS)}.",
            status_code=422,
        )
    return cleaned


def compute_report_priority(reason_code: str) -> int:
    if reason_code in HIGH_SEVERITY_REASONS:
        return 10
    if reason_code in MEDIUM_SEVERITY_REASONS:
        return 5
    return 2


class CreateReportRequest(BaseModel):
    target_type: str = Field(..., description="post | comment | profile | meme_asset")
    target_id: str = Field(..., min_length=2, max_length=64)
    reason_code: str = Field(..., description="One of the 9 supported Phase 1 reason codes")
    details: Optional[str] = Field(None, max_length=1000)


class ReportResponse(BaseModel):
    """Privacy-safe representation of a user's submitted report.

    Never exposes other reporters or internal moderator notes.
    """

    id: str
    target_type: str
    target_id: str
    reason_code: str
    details: Optional[str] = None
    priority_score: int
    status: str
    protective_hold_triggered: bool = False
    created_at: str
    updated_at: str


class MyReportListResponse(BaseModel):
    items: List[ReportResponse]


class ModeratorTargetPreview(BaseModel):
    """Privacy-blind content context for moderators.

    NEVER contains `author_user_id`, `reporter_user_id`, `email`, `ip_subnet_hash`,
    or private handle when `identity_mode == 'anonymous'`.
    """

    target_type: str
    target_id: str
    community_slug: Optional[str] = None
    content_language: str
    moderation_status: str
    is_protective_hold: bool
    title: Optional[str] = None
    body_excerpt: str
    public_author: Optional[PublicAuthorDisplay] = None


class ModerationQueueItemResponse(BaseModel):
    report_id: str
    target_type: str
    target_id: str
    community_slug: Optional[str] = None
    content_language: str
    reason_code: str
    details: Optional[str] = None
    priority_score: int
    status: str
    distinct_reporter_count: int
    allegation_notice: str = (
        "Reports represent allegations requiring human assessment, not automatic proof of misconduct."
    )
    target_preview: ModeratorTargetPreview
    created_at: str


class CursorModerationQueueResponse(BaseModel):
    items: List[ModerationQueueItemResponse]
    next_cursor: Optional[str] = None
    has_more: bool


class CreateModerationActionRequest(BaseModel):
    target_type: str = Field(..., description="post | comment | user | meme_asset")
    target_id: str = Field(..., min_length=2, max_length=64)
    action_type: str = Field(
        ...,
        description="dismiss_reports | redact_pii | restrict_visibility | place_under_review | remove_content | restore_content | escalate_language_specialist | user_cooldown | user_suspend | restore_user",
    )
    reason_code: str = Field(..., description="Required policy reason code")
    internal_note: str = Field(..., min_length=3, max_length=1000)
    public_explanation: str = Field(..., min_length=3, max_length=500)
    cooldown_hours: int = Field(24, ge=1, le=720)


class ModerationActionResponse(BaseModel):
    """Privacy-safe moderation decision record.

    Omits `affected_user_id` and `moderator_user_id` in public/user-facing views.
    """

    id: str
    actor_type: str
    target_type: str
    target_id: str
    community_slug: Optional[str] = None
    action_type: str
    reason_code: str
    public_explanation: str
    previous_state: Optional[str] = None
    new_state: Optional[str] = None
    is_appealable: bool
    appeal_status: Optional[str] = None
    created_at: str


class MyModerationActionsListResponse(BaseModel):
    items: List[ModerationActionResponse]


class CreateAppealRequest(BaseModel):
    moderation_action_id: str = Field(..., min_length=2, max_length=64)
    appeal_statement: str = Field(..., min_length=10, max_length=2000)


class DecideAppealRequest(BaseModel):
    decision: str = Field(..., description="accepted | rejected")
    decision_reason_code: str = Field(..., min_length=3, max_length=32)
    review_decision_note: str = Field(..., min_length=5, max_length=1000)


class AppealResponse(BaseModel):
    id: str
    moderation_action_id: str
    target_type: str
    target_id: str
    original_action_type: str
    original_reason_code: str
    public_explanation: str
    appeal_statement: str
    status: str
    decision_reason_code: Optional[str] = None
    review_decision_note: Optional[str] = None
    can_viewer_decide: bool = False
    created_at: str
    resolved_at: Optional[str] = None


class AppealListResponse(BaseModel):
    items: List[AppealResponse]


class SetBlockMuteRequest(BaseModel):
    active: bool = True
    mode: str = Field("block", description="block | mute")


class BlockMuteStatusResponse(BaseModel):
    handle: str
    active: bool
    mode: Optional[str] = None


class BlockedAccountItem(BaseModel):
    handle: str
    display_name: str
    mode: str
    created_at: str


class BlockedAccountsListResponse(BaseModel):
    items: List[BlockedAccountItem]


class AuditEventResponse(BaseModel):
    """Read-only administrative audit record.

    Never exposes anonymous post author IDs, plaintext emails, or session secrets.
    """

    id: str
    actor_user_id: Optional[str] = None
    actor_role: str
    event_category: str
    action_name: str
    target_type: str
    target_id: Optional[str] = None
    reason_code: str
    redacted_metadata: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: str
    created_at: str


class CursorAuditEventListResponse(BaseModel):
    items: List[AuditEventResponse]
    next_cursor: Optional[str] = None
    has_more: bool
