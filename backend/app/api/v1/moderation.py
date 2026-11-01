"""FastAPI endpoints for Phase 9 Reporting, Moderator Queue, Actions, Appeals, Blocking & Audit."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import get_moderation_service, require_authenticated_context
from app.modules.moderation.schemas import (
    AppealListResponse,
    AppealResponse,
    BlockedAccountsListResponse,
    BlockMuteStatusResponse,
    CreateAppealRequest,
    CreateModerationActionRequest,
    CreateReportRequest,
    CursorAuditEventListResponse,
    CursorModerationQueueResponse,
    DecideAppealRequest,
    ModerationActionResponse,
    MyModerationActionsListResponse,
    MyReportListResponse,
    ReportResponse,
    SetBlockMuteRequest,
)
from app.modules.moderation.service import ModerationService

router = APIRouter(tags=["moderation"])


@router.post(
    "/reports",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_report_endpoint(
    payload: CreateReportRequest,
    request: Request,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: ModerationService = Depends(get_moderation_service),
) -> ReportResponse:
    """Submit a structured content or profile report with automatic velocity escalation."""
    corr_id = getattr(request.state, "correlation_id", "req_report")
    return await service.submit_report(
        reporter_user=auth_ctx["user"],
        payload=payload,
        correlation_id=corr_id,
    )


@router.get("/reports/mine", response_model=MyReportListResponse)
async def list_my_reports_endpoint(
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: ModerationService = Depends(get_moderation_service),
) -> MyReportListResponse:
    """Return the authenticated user's own submitted reports."""
    return await service.list_my_reports(user_id=str(auth_ctx["user"]["id"]))


@router.get("/moderation/queue", response_model=CursorModerationQueueResponse)
async def get_moderation_queue_endpoint(
    status: Optional[str] = Query(None),
    reason_code: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    content_language: Optional[str] = Query(None),
    community_slug: Optional[str] = Query(None),
    high_severity_only: bool = Query(False),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: ModerationService = Depends(get_moderation_service),
) -> CursorModerationQueueResponse:
    """Return the privacy-blind moderator triage queue scoped to the moderator's permissions."""
    return await service.list_moderation_queue(
        actor_user=auth_ctx["user"],
        status=status,
        reason_code=reason_code,
        target_type=target_type,
        content_language=content_language,
        community_slug=community_slug,
        high_severity_only=high_severity_only,
        cursor=cursor,
        limit=limit,
    )


@router.post(
    "/moderation/actions",
    response_model=ModerationActionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def execute_moderation_action_endpoint(
    payload: CreateModerationActionRequest,
    request: Request,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: ModerationService = Depends(get_moderation_service),
) -> ModerationActionResponse:
    """Execute an authorized, reason-backed moderation decision."""
    corr_id = getattr(request.state, "correlation_id", "req_mod_action")
    return await service.execute_moderation_action(
        actor_user=auth_ctx["user"],
        payload=payload,
        correlation_id=corr_id,
    )


@router.get("/moderation/my-actions", response_model=MyModerationActionsListResponse)
async def list_my_moderation_actions_endpoint(
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: ModerationService = Depends(get_moderation_service),
) -> MyModerationActionsListResponse:
    """List moderation actions affecting the authenticated user's content or account."""
    return await service.list_my_moderation_actions(user_id=str(auth_ctx["user"]["id"]))


@router.post(
    "/moderation/appeals",
    response_model=AppealResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_moderation_appeal_endpoint(
    payload: CreateAppealRequest,
    request: Request,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: ModerationService = Depends(get_moderation_service),
) -> AppealResponse:
    """Submit a user appeal against an eligible moderation decision."""
    corr_id = getattr(request.state, "correlation_id", "req_appeal")
    return await service.submit_appeal(
        appellant_user=auth_ctx["user"],
        payload=payload,
        correlation_id=corr_id,
    )


@router.get("/moderation/appeals", response_model=AppealListResponse)
async def list_moderation_appeals_endpoint(
    status: Optional[str] = Query(None),
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: ModerationService = Depends(get_moderation_service),
) -> AppealListResponse:
    """List appeals (all appeals for global moderators/admins; own appeals for regular members)."""
    return await service.list_appeals(viewer_user=auth_ctx["user"], status=status)


@router.post("/moderation/appeals/{appeal_id}/decision", response_model=AppealResponse)
async def decide_moderation_appeal_endpoint(
    appeal_id: str,
    payload: DecideAppealRequest,
    request: Request,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: ModerationService = Depends(get_moderation_service),
) -> AppealResponse:
    """Review and decide a pending moderation appeal (enforces separation of duties)."""
    corr_id = getattr(request.state, "correlation_id", "req_appeal_decide")
    return await service.decide_appeal(
        appeal_id=appeal_id,
        reviewer_user=auth_ctx["user"],
        payload=payload,
        correlation_id=corr_id,
    )


@router.put("/users/{handle}/block", response_model=BlockMuteStatusResponse)
async def set_user_block_or_mute_endpoint(
    handle: str,
    payload: SetBlockMuteRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: ModerationService = Depends(get_moderation_service),
) -> BlockMuteStatusResponse:
    """Block, unblock, mute, or unmute another account by public handle."""
    return await service.set_user_block_or_mute(
        blocker_user_id=str(auth_ctx["user"]["id"]),
        target_handle=handle,
        payload=payload,
    )


@router.get("/me/blocks", response_model=BlockedAccountsListResponse)
async def list_my_blocked_and_muted_accounts_endpoint(
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: ModerationService = Depends(get_moderation_service),
) -> BlockedAccountsListResponse:
    """List accounts blocked or muted by the authenticated user."""
    return await service.list_blocked_and_muted_accounts(
        user_id=str(auth_ctx["user"]["id"])
    )


@router.get("/moderation/audit", response_model=CursorAuditEventListResponse)
async def list_moderation_audit_events_endpoint(
    event_category: Optional[str] = Query(None),
    action_name: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    actor_user_id: Optional[str] = Query(None),
    reason_code: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=50),
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: ModerationService = Depends(get_moderation_service),
) -> CursorAuditEventListResponse:
    """Read-only administrative audit log endpoint (restricted to platform admins)."""
    return await service.list_audit_events(
        actor_user=auth_ctx["user"],
        event_category=event_category,
        action_name=action_name,
        target_type=target_type,
        actor_id_filter=actor_user_id,
        reason_code=reason_code,
        since=since,
        until=until,
        cursor=cursor,
        limit=limit,
    )
