"""Transactional service layer for Phase 9 Trust, Safety, Reporting, Moderation,
Velocity Auto-Hold, Privacy-Blind Queue, Appeals, User Blocking/Muting & Audit Trail.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.errors import AppError
from app.core.rate_limit import rate_limiter
from app.core.unicode import normalize_unicode_nfc
import base64
from app.modules.comments.serializers import serialize_public_comment
from app.modules.identity.schemas import PublicAuthorDisplay, validate_bcp47_tag
from app.modules.moderation.schemas import (
    AppealListResponse,
    AppealResponse,
    AuditEventResponse,
    BlockedAccountItem,
    BlockedAccountsListResponse,
    BlockMuteStatusResponse,
    CreateAppealRequest,
    CreateModerationActionRequest,
    CreateReportRequest,
    CursorAuditEventListResponse,
    CursorModerationQueueResponse,
    DecideAppealRequest,
    HIGH_SEVERITY_REASONS,
    ModerationActionResponse,
    ModerationQueueItemResponse,
    ModeratorTargetPreview,
    MyModerationActionsListResponse,
    MyReportListResponse,
    ReportResponse,
    SetBlockMuteRequest,
    VALID_ACTION_REASONS,
    VALID_BLOCK_MODES,
    VALID_MODERATION_ACTIONS,
    VALID_MODERATION_TARGETS,
    VALID_REPORT_STATUSES,
    compute_report_priority,
    validate_report_reason,
    validate_report_target_type,
)
from app.modules.notifications.service import NotificationService
from app.modules.posts.serializers import _serialize_post_author
POST_COLUMNS = (
    "id",
    "author_user_id",
    "community_slug",
    "post_type",
    "identity_mode",
    "professional_snapshot",
    "anonymous_alias",
    "title",
    "body",
    "meme_asset_id",
    "content_language",
    "moderation_status",
    "upvote_count",
    "downvote_count",
    "score",
    "reaction_counts",
    "comment_count",
    "hot_rank_score",
    "created_at",
    "updated_at",
    "deleted_at",
)

COMMENT_COLUMNS = (
    "id",
    "post_id",
    "author_user_id",
    "parent_comment_id",
    "path",
    "depth",
    "identity_mode",
    "professional_snapshot",
    "is_anonymous_op",
    "anonymous_thread_label",
    "body",
    "content_language",
    "moderation_status",
    "upvote_count",
    "downvote_count",
    "score",
    "reaction_counts",
    "created_at",
    "updated_at",
    "deleted_at",
)

PROFILE_COLUMNS = (
    "id",
    "user_id",
    "handle",
    "handle_normalized",
    "display_name",
    "bio",
    "avatar_storage_key",
    "show_karma",
    "created_at",
    "updated_at",
)

PROF_COLUMNS = (
    "id",
    "user_id",
    "role_title",
    "industry",
    "experience_band",
    "region_label",
    "is_enabled",
    "created_at",
    "updated_at",
)


def encode_cursor(created_at: str, item_id: str) -> str:
    payload = json.dumps({"c": created_at, "i": item_id})
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> Tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        data = json.loads(raw)
        return str(data["c"]), str(data["i"])
    except Exception:
        raise AppError(
            code="INVALID_CURSOR",
            message="Invalid pagination cursor.",
            status_code=422,
        )

REPORT_COLUMNS = (
    "id",
    "reporter_user_id",
    "target_type",
    "target_id",
    "community_slug",
    "content_language",
    "reason_code",
    "details",
    "priority_score",
    "status",
    "resolved_by_action_id",
    "created_at",
    "updated_at",
)

ACTION_COLUMNS = (
    "id",
    "moderator_user_id",
    "actor_type",
    "target_type",
    "target_id",
    "affected_user_id",
    "community_slug",
    "action_type",
    "reason_code",
    "internal_note",
    "public_explanation",
    "previous_state",
    "new_state",
    "is_appealable",
    "created_at",
)

APPEAL_COLUMNS = (
    "id",
    "moderation_action_id",
    "appellant_user_id",
    "appeal_statement",
    "status",
    "reviewed_by_user_id",
    "decision_reason_code",
    "review_decision_note",
    "created_at",
    "resolved_at",
)

AUDIT_COLUMNS = (
    "id",
    "actor_user_id",
    "actor_role",
    "event_category",
    "action_name",
    "target_type",
    "target_id",
    "reason_code",
    "redacted_metadata",
    "correlation_id",
    "created_at",
)

VELOCITY_WINDOW_MINUTES = 30
VELOCITY_DISTINCT_REPORTER_THRESHOLD = 3

_PII_REDACT_PATTERNS = (
    re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{3,4}\)?[\s\-]?\d{3}[\s\-]?\d{4})\b"),
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_utc().isoformat()


def _row_to_dict(columns: tuple[str, ...], row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(columns, row))


def redact_pii_in_text(text: str) -> str:
    cleaned = text
    for pat in _PII_REDACT_PATTERNS:
        cleaned = pat.sub("[REDACTED BY MODERATOR]", cleaned)
    return cleaned


async def check_user_can_contribute(session: Any, user_dict: dict[str, Any]) -> None:
    """Verify the authenticated user is not currently suspended or in an active cooldown."""
    user_id = str(user_dict["id"])
    rows = await session.execute(
        "SELECT account_status, cooldown_until FROM users WHERE id = ?",
        (user_id,),
    )
    if not rows:
        return
    status, cooldown_until = str(rows[0][0]), rows[0][1]
    if status == "suspended":
        raise AppError(
            code="ACCOUNT_RESTRICTED",
            message="Your account is currently suspended from posting or commenting. Visit /moderation/appeals to review or appeal this decision.",
            status_code=403,
        )
    if status == "cooldown" and cooldown_until:
        now_str = _now_iso()
        if str(cooldown_until) > now_str:
            raise AppError(
                code="ACCOUNT_RESTRICTED",
                message=f"Your account is on a temporary posting cooldown until {cooldown_until}.",
                status_code=403,
            )
        else:
            # Cooldown expired naturally; restore to active
            await session.execute(
                "UPDATE users SET account_status = 'active', cooldown_until = NULL WHERE id = ? AND account_status = 'cooldown'",
                (user_id,),
            )


async def is_interaction_blocked(
    session: Any, user_a_id: Optional[str], user_b_id: Optional[str]
) -> bool:
    """Return True if either user has an active 'block' against the other."""
    if not user_a_id or not user_b_id or str(user_a_id) == str(user_b_id):
        return False
    rows = await session.execute(
        """
        SELECT 1 FROM user_blocks
        WHERE block_mode = 'block'
          AND (
              (blocker_user_id = ? AND blocked_user_id = ?)
              OR (blocker_user_id = ? AND blocked_user_id = ?)
          )
        LIMIT 1
        """,
        (str(user_a_id), str(user_b_id), str(user_b_id), str(user_a_id)),
    )
    return bool(rows)


async def should_suppress_notification(
    session: Any, recipient_user_id: Optional[str], actor_user_id: Optional[str]
) -> bool:
    """Return True if `recipient_user_id` has blocked or muted `actor_user_id` (or vice versa for block)."""
    if not recipient_user_id or not actor_user_id or str(recipient_user_id) == str(actor_user_id):
        return False
    rows = await session.execute(
        """
        SELECT 1 FROM user_blocks
        WHERE (blocker_user_id = ? AND blocked_user_id = ?)
           OR (blocker_user_id = ? AND blocked_user_id = ? AND block_mode = 'block')
        LIMIT 1
        """,
        (
            str(recipient_user_id),
            str(actor_user_id),
            str(actor_user_id),
            str(recipient_user_id),
        ),
    )
    return bool(rows)


class ModerationService:
    """Coordinates reporting, velocity holds, privacy-blind queues, actions, appeals, blocks & audit logs."""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def _record_audit_event(
        self,
        *,
        actor_user_id: Optional[str],
        actor_role: str,
        event_category: str,
        action_name: str,
        target_type: str,
        target_id: Optional[str],
        reason_code: str,
        metadata: Optional[Dict[str, Any]] = None,
        correlation_id: str = "req_internal",
    ) -> str:
        """Append an immutable audit record to `audit_events` with strict privacy redaction."""
        safe_meta: Dict[str, Any] = {}
        if metadata:
            for k, v in metadata.items():
                if k in {
                    "author_user_id",
                    "reporter_user_id",
                    "affected_user_id",
                    "email",
                    "password_hash",
                    "token_hash",
                    "csrf_secret",
                }:
                    continue
                safe_meta[k] = v

        audit_id = str(uuid.uuid4())
        await self.session.execute(
            """
            INSERT INTO audit_events (
                id, actor_user_id, actor_role, event_category, action_name,
                target_type, target_id, reason_code, redacted_metadata,
                correlation_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                actor_user_id,
                actor_role,
                event_category,
                action_name,
                target_type,
                target_id,
                reason_code,
                json.dumps(safe_meta, ensure_ascii=False),
                correlation_id,
                _now_iso(),
            ),
        )
        return audit_id

    async def _resolve_report_target(
        self, target_type: str, target_id: str
    ) -> Tuple[Optional[str], Optional[str], str, str]:
        """Validate target exists & is eligible; return `(owner_user_id, community_slug, content_language, current_status)`."""
        if target_type == "post":
            rows = await self.session.execute(
                "SELECT author_user_id, community_slug, content_language, moderation_status, deleted_at FROM posts WHERE id = ?",
                (target_id,),
            )
            if not rows:
                raise AppError(
                    code="TARGET_NOT_FOUND",
                    message="The reported post does not exist.",
                    status_code=404,
                )
            author_id, comm_slug, lang, mod_status, deleted_at = rows[0]
            if deleted_at is not None or str(mod_status) == "removed":
                raise AppError(
                    code="TARGET_NO_LONGER_ELIGIBLE",
                    message="This post has already been removed or deleted.",
                    status_code=410,
                )
            return (
                str(author_id) if author_id else None,
                str(comm_slug) if comm_slug else None,
                str(lang or "en"),
                str(mod_status),
            )

        if target_type == "comment":
            rows = await self.session.execute(
                """
                SELECT c.author_user_id, p.community_slug, c.content_language, c.moderation_status, c.deleted_at
                FROM comments c
                JOIN posts p ON p.id = c.post_id
                WHERE c.id = ?
                """,
                (target_id,),
            )
            if not rows:
                raise AppError(
                    code="TARGET_NOT_FOUND",
                    message="The reported comment does not exist.",
                    status_code=404,
                )
            author_id, comm_slug, lang, mod_status, deleted_at = rows[0]
            if deleted_at is not None or str(mod_status) == "removed":
                raise AppError(
                    code="TARGET_NO_LONGER_ELIGIBLE",
                    message="This comment has already been removed or deleted.",
                    status_code=410,
                )
            return (
                str(author_id) if author_id else None,
                str(comm_slug) if comm_slug else None,
                str(lang or "en"),
                str(mod_status),
            )

        if target_type == "profile":
            rows = await self.session.execute(
                """
                SELECT pp.user_id, u.account_status
                FROM public_profiles pp
                JOIN users u ON u.id = pp.user_id
                WHERE pp.id = ? OR pp.handle_normalized = ? OR pp.user_id = ?
                """,
                (target_id, target_id.strip().lower(), target_id),
            )
            if not rows:
                raise AppError(
                    code="TARGET_NOT_FOUND",
                    message="The reported public profile does not exist.",
                    status_code=404,
                )
            uid, acc_status = str(rows[0][0]), str(rows[0][1])
            if acc_status in {"suspended", "deleted"}:
                raise AppError(
                    code="TARGET_NO_LONGER_ELIGIBLE",
                    message="This profile is no longer active.",
                    status_code=410,
                )
            return uid, None, "en", acc_status

        if target_type == "meme_asset":
            rows = await self.session.execute(
                "SELECT owner_user_id, caption_language, safety_status FROM meme_assets WHERE id = ?",
                (target_id,),
            )
            if not rows:
                raise AppError(
                    code="TARGET_NOT_FOUND",
                    message="The reported meme asset does not exist.",
                    status_code=404,
                )
            owner_id, lang, safety_status = rows[0]
            if str(safety_status) == "rejected":
                raise AppError(
                    code="TARGET_NO_LONGER_ELIGIBLE",
                    message="This meme asset has already been removed.",
                    status_code=410,
                )
            return (
                str(owner_id) if owner_id else None,
                None,
                str(lang or "en"),
                str(safety_status),
            )

        raise AppError(
            code="INVALID_REPORT_TARGET",
            message="Unsupported report target type.",
            status_code=422,
        )

    async def submit_report(
        self,
        *,
        reporter_user: dict[str, Any],
        payload: CreateReportRequest,
        correlation_id: str = "req_report",
    ) -> ReportResponse:
        """Validate and persist a report, triggering a temporary protective hold if velocity threshold is met."""
        reporter_id = str(reporter_user["id"])
        rate_limiter.check_and_record(
            bucket="report_submit",
            key=reporter_id,
            limit=15,
            window_seconds=3600,
        )

        target_type = validate_report_target_type(payload.target_type)
        reason_code = validate_report_reason(payload.reason_code)
        target_id = payload.target_id.strip()

        details_norm: Optional[str] = None
        if payload.details is not None and payload.details.strip():
            details_norm = normalize_unicode_nfc(payload.details).strip()
            if len(details_norm) > 1000:
                raise AppError(
                    code="VALIDATION_ERROR",
                    message="Report details must not exceed 1,000 characters.",
                    status_code=422,
                )

        owner_user_id, comm_slug, content_lang, current_status = (
            await self._resolve_report_target(target_type, target_id)
        )

        # Check duplicate report from same reporter on same target
        existing = await self.session.execute(
            "SELECT id FROM reports WHERE reporter_user_id = ? AND target_type = ? AND target_id = ?",
            (reporter_id, target_type, target_id),
        )
        if existing:
            raise AppError(
                code="DUPLICATE_REPORT",
                message="You have already submitted a report for this item. Duplicate submissions from the same account do not increase report priority.",
                status_code=409,
            )

        priority = compute_report_priority(reason_code)
        report_id = str(uuid.uuid4())
        now_dt = _now_utc()
        now_str = now_dt.isoformat()

        await self.session.execute(
            """
            INSERT INTO reports (
                id, reporter_user_id, target_type, target_id, community_slug,
                content_language, reason_code, details, priority_score,
                status, resolved_by_action_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', NULL, ?, ?)
            """,
            (
                report_id,
                reporter_id,
                target_type,
                target_id,
                comm_slug,
                content_lang,
                reason_code,
                details_norm,
                priority,
                now_str,
                now_str,
            ),
        )

        # High-Severity Velocity Safeguard (Section 6)
        # >= 3 distinct reporters for `doxxing_pii` or `threat` within rolling 30 minutes -> `awaiting_review`
        hold_triggered = False
        if (
            reason_code in HIGH_SEVERITY_REASONS
            and target_type in {"post", "comment"}
            and current_status == "published"
        ):
            cutoff_str = (now_dt - timedelta(minutes=VELOCITY_WINDOW_MINUTES)).isoformat()
            vel_rows = await self.session.execute(
                """
                SELECT COUNT(DISTINCT reporter_user_id)
                FROM reports
                WHERE target_type = ?
                  AND target_id = ?
                  AND reason_code IN ('doxxing_pii', 'threat')
                  AND created_at >= ?
                """,
                (target_type, target_id, cutoff_str),
            )
            distinct_reporters = int(vel_rows[0][0]) if vel_rows else 0

            if distinct_reporters >= VELOCITY_DISTINCT_REPORTER_THRESHOLD:
                table = "posts" if target_type == "post" else "comments"
                # Re-check current moderation_status inside transaction to prevent duplicate auto-hold actions
                curr_rows = await self.session.execute(
                    f"SELECT moderation_status FROM {table} WHERE id = ?",
                    (target_id,),
                )
                if curr_rows and str(curr_rows[0][0]) == "published":
                    await self.session.execute(
                        f"""
                        UPDATE {table}
                        SET moderation_status = 'awaiting_review', updated_at = ?
                        WHERE id = ? AND moderation_status = 'published'
                        """,
                        (now_str, target_id),
                    )
                    await self.session.execute(
                        """
                        UPDATE reports
                        SET status = 'in_review', updated_at = ?
                        WHERE target_type = ? AND target_id = ? AND status = 'open'
                        """,
                        (now_str, target_type, target_id),
                    )

                    action_id = str(uuid.uuid4())
                    pub_explanation = (
                        "This item was placed under a temporary protective hold after multiple high-severity safety reports (doxxing/threat) and is awaiting human moderator review. A protective hold is not a finding of misconduct."
                    )
                    await self.session.execute(
                        """
                        INSERT INTO moderation_actions (
                            id, moderator_user_id, actor_type, target_type, target_id,
                            affected_user_id, community_slug, action_type, reason_code,
                            internal_note, public_explanation, previous_state, new_state,
                            is_appealable, created_at
                        ) VALUES (?, NULL, 'system_auto_hold', ?, ?, ?, ?, 'place_under_review', 'auto_velocity_hold', ?, ?, 'published', 'awaiting_review', 1, ?)
                        """,
                        (
                            action_id,
                            target_type,
                            target_id,
                            owner_user_id,
                            comm_slug,
                            f"Automatic velocity protective hold triggered by {distinct_reporters} distinct high-severity reports within {VELOCITY_WINDOW_MINUTES} minutes.",
                            pub_explanation,
                            now_str,
                        ),
                    )
                    await self._record_audit_event(
                        actor_user_id=None,
                        actor_role="system_auto_hold",
                        event_category="auto_protective_hold",
                        action_name="place_under_review",
                        target_type=target_type,
                        target_id=target_id,
                        reason_code="auto_velocity_hold",
                        metadata={
                            "distinct_reporters": distinct_reporters,
                            "window_minutes": VELOCITY_WINDOW_MINUTES,
                            "community_slug": comm_slug,
                        },
                        correlation_id=correlation_id,
                    )
                    if owner_user_id:
                        notif_svc = NotificationService(self.session)
                        await notif_svc.create_notification(
                            recipient_user_id=owner_user_id,
                            notification_type="moderation_notice",
                            reference_type="moderation_action",
                            reference_id=action_id,
                            title="Temporary Protective Hold Pending Moderator Review",
                            body_preview=pub_explanation,
                        )
                    hold_triggered = True

        return ReportResponse(
            id=report_id,
            target_type=target_type,
            target_id=target_id,
            reason_code=reason_code,
            details=details_norm,
            priority_score=priority,
            status="in_review" if hold_triggered else "open",
            protective_hold_triggered=hold_triggered,
            created_at=now_str,
            updated_at=now_str,
        )

    async def list_my_reports(self, *, user_id: str) -> MyReportListResponse:
        rows = await self.session.execute(
            f"""
            SELECT {', '.join(REPORT_COLUMNS)}
            FROM reports
            WHERE reporter_user_id = ?
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (user_id,),
        )
        items: List[ReportResponse] = []
        for r in rows:
            d = _row_to_dict(REPORT_COLUMNS, r)
            items.append(
                ReportResponse(
                    id=str(d["id"]),
                    target_type=str(d["target_type"]),
                    target_id=str(d["target_id"]),
                    reason_code=str(d["reason_code"]),
                    details=d.get("details"),
                    priority_score=int(d["priority_score"]),
                    status=str(d["status"]),
                    protective_hold_triggered=str(d["status"]) == "in_review",
                    created_at=str(d["created_at"]),
                    updated_at=str(d["updated_at"]),
                )
            )
        return MyReportListResponse(items=items)

    async def _get_moderator_scope(
        self, actor_user: dict[str, Any]
    ) -> Tuple[bool, Set[str]]:
        """Return `(is_global_or_admin, set_of_moderated_community_slugs)` or raise 403."""
        user_id = str(actor_user["id"])
        role = str(actor_user.get("role", "member"))
        if role in {"global_moderator", "admin"}:
            return True, set()

        rows = await self.session.execute(
            """
            SELECT c.slug
            FROM community_memberships cm
            JOIN communities c ON c.id = cm.community_id
            WHERE cm.user_id = ? AND cm.role = 'moderator' AND cm.status = 'active'
            """,
            (user_id,),
        )
        slugs = {str(r[0]) for r in rows}
        if not slugs:
            raise AppError(
                code="FORBIDDEN_ROLE",
                message="Moderator or administrator permissions are required to access this resource.",
                status_code=403,
            )
        return False, slugs

    async def _build_privacy_blind_target_preview(
        self, target_type: str, target_id: str
    ) -> ModeratorTargetPreview:
        """Build a privacy-blind content preview that NEVER exposes anonymous `author_user_id` or `@handle`."""
        if target_type == "post":
            rows = await self.session.execute(
                f"SELECT {', '.join(POST_COLUMNS)} FROM posts WHERE id = ?",
                (target_id,),
            )
            if not rows:
                return ModeratorTargetPreview(
                    target_type="post",
                    target_id=target_id,
                    content_language="en",
                    moderation_status="removed",
                    is_protective_hold=False,
                    body_excerpt="[Post no longer available]",
                )
            p_dict = _row_to_dict(POST_COLUMNS, rows[0])
            mode = str(p_dict["identity_mode"])
            profile_row = None
            prof_row = None
            if mode != "anonymous" and p_dict.get("author_user_id"):
                pr = await self.session.execute(
                    f"SELECT {', '.join(PROFILE_COLUMNS)} FROM public_profiles WHERE user_id = ?",
                    (str(p_dict["author_user_id"]),),
                )
                profile_row = _row_to_dict(PROFILE_COLUMNS, pr[0]) if pr else None
                pfr = await self.session.execute(
                    f"SELECT {', '.join(PROF_COLUMNS)} FROM professional_profiles WHERE user_id = ?",
                    (str(p_dict["author_user_id"]),),
                )
                prof_row = _row_to_dict(PROF_COLUMNS, pfr[0]) if pfr else None

            pub_author = _serialize_post_author(
                post_row=p_dict, profile_row=profile_row, prof_row=prof_row
            )
            mod_status = str(p_dict["moderation_status"])
            return ModeratorTargetPreview(
                target_type="post",
                target_id=target_id,
                community_slug=str(p_dict.get("community_slug") or ""),
                content_language=str(p_dict.get("content_language") or "en"),
                moderation_status=mod_status,
                is_protective_hold=(mod_status == "awaiting_review"),
                title=str(p_dict.get("title") or ""),
                body_excerpt=str(p_dict.get("body") or "")[:500],
                public_author=pub_author,
            )

        if target_type == "comment":
            rows = await self.session.execute(
                f"""
                SELECT {', '.join('c.' + col for col in COMMENT_COLUMNS)}, p.community_slug
                FROM comments c
                JOIN posts p ON p.id = c.post_id
                WHERE c.id = ?
                """,
                (target_id,),
            )
            if not rows:
                return ModeratorTargetPreview(
                    target_type="comment",
                    target_id=target_id,
                    content_language="en",
                    moderation_status="removed",
                    is_protective_hold=False,
                    body_excerpt="[Comment no longer available]",
                )
            c_dict = _row_to_dict(COMMENT_COLUMNS, rows[0][:-1])
            comm_slug = str(rows[0][-1])
            mode = str(c_dict["identity_mode"])
            profile_row = None
            prof_row = None
            if mode != "anonymous" and c_dict.get("author_user_id"):
                pr = await self.session.execute(
                    f"SELECT {', '.join(PROFILE_COLUMNS)} FROM public_profiles WHERE user_id = ?",
                    (str(c_dict["author_user_id"]),),
                )
                profile_row = _row_to_dict(PROFILE_COLUMNS, pr[0]) if pr else None

            ser_comment = serialize_public_comment(
                comment_row=c_dict,
                profile_row=profile_row,
                prof_row=prof_row,
                viewer_user_id=None,
            )
            mod_status = str(c_dict["moderation_status"])
            return ModeratorTargetPreview(
                target_type="comment",
                target_id=target_id,
                community_slug=comm_slug,
                content_language=str(c_dict.get("content_language") or "en"),
                moderation_status=mod_status,
                is_protective_hold=(mod_status == "awaiting_review"),
                title=None,
                body_excerpt=str(c_dict.get("body") or "")[:500],
                public_author=ser_comment.author,
            )

        if target_type == "profile":
            rows = await self.session.execute(
                """
                SELECT pp.handle, pp.display_name, pp.bio, u.account_status
                FROM public_profiles pp
                JOIN users u ON u.id = pp.user_id
                WHERE pp.id = ? OR pp.handle_normalized = ? OR pp.user_id = ?
                """,
                (target_id, target_id.strip().lower(), target_id),
            )
            if not rows:
                return ModeratorTargetPreview(
                    target_type="profile",
                    target_id=target_id,
                    content_language="en",
                    moderation_status="removed",
                    is_protective_hold=False,
                    body_excerpt="[Profile not found]",
                )
            handle, disp, bio, acc_status = rows[0]
            return ModeratorTargetPreview(
                target_type="profile",
                target_id=target_id,
                content_language="en",
                moderation_status=str(acc_status),
                is_protective_hold=False,
                title=f"@{handle}",
                body_excerpt=str(bio or disp or ""),
                public_author=PublicAuthorDisplay(
                    identity_mode="pseudonymous",
                    display_name=str(disp or f"@{handle}"),
                    handle=str(handle),
                    avatar_url=None,
                    professional_badge=None,
                    is_anonymous_op=False,
                ),
            )

        # meme_asset
        rows = await self.session.execute(
            "SELECT alt_text, caption_language, safety_status FROM meme_assets WHERE id = ?",
            (target_id,),
        )
        if not rows:
            return ModeratorTargetPreview(
                target_type="meme_asset",
                target_id=target_id,
                content_language="en",
                moderation_status="removed",
                is_protective_hold=False,
                body_excerpt="[Meme asset not found]",
            )
        alt_txt, cap_lang, safety_st = rows[0]
        return ModeratorTargetPreview(
            target_type="meme_asset",
            target_id=target_id,
            content_language=str(cap_lang or "en"),
            moderation_status=str(safety_st),
            is_protective_hold=False,
            title="Meme Asset",
            body_excerpt=str(alt_txt or ""),
            public_author=None,
        )

    async def list_moderation_queue(
        self,
        *,
        actor_user: dict[str, Any],
        status: Optional[str] = None,
        reason_code: Optional[str] = None,
        target_type: Optional[str] = None,
        content_language: Optional[str] = None,
        community_slug: Optional[str] = None,
        high_severity_only: bool = False,
        cursor: Optional[str] = None,
        limit: int = 20,
    ) -> CursorModerationQueueResponse:
        is_global, mod_slugs = await self._get_moderator_scope(actor_user)

        clauses: List[str] = []
        params: List[Any] = []

        if status:
            st = status.strip().lower()
            if st not in VALID_REPORT_STATUSES:
                raise AppError(
                    code="INVALID_REPORT_STATUS",
                    message=f"Status filter must be one of: {', '.join(VALID_REPORT_STATUSES)}.",
                    status_code=422,
                )
            clauses.append("r.status = ?")
            params.append(st)
        else:
            clauses.append("r.status IN ('open', 'in_review', 'escalated_language_specialist')")

        if reason_code:
            clauses.append("r.reason_code = ?")
            params.append(validate_report_reason(reason_code))

        if target_type:
            clauses.append("r.target_type = ?")
            params.append(validate_report_target_type(target_type))

        if content_language:
            clauses.append("r.content_language = ?")
            params.append(validate_bcp47_tag(content_language))

        if high_severity_only:
            clauses.append("r.priority_score >= 10")

        if not is_global:
            if community_slug:
                cleaned_slug = community_slug.strip().lower()
                if cleaned_slug not in mod_slugs:
                    raise AppError(
                        code="FORBIDDEN_MODERATION_SCOPE",
                        message=f"You are not a moderator of c/{cleaned_slug}.",
                        status_code=403,
                    )
                clauses.append("r.community_slug = ?")
                params.append(cleaned_slug)
            else:
                placeholders = ", ".join("?" for _ in mod_slugs)
                clauses.append(f"r.community_slug IN ({placeholders})")
                params.extend(sorted(mod_slugs))
        elif community_slug:
            clauses.append("r.community_slug = ?")
            params.append(community_slug.strip().lower())

        if cursor:
            c_time, c_id = decode_cursor(cursor)
            clauses.append("(r.created_at > ? OR (r.created_at = ? AND r.id > ?))")
            params.extend([c_time, c_time, c_id])

        safe_limit = max(1, min(limit, 50))
        where_sql = " AND ".join(clauses) if clauses else "1=1"
        col_list = ", ".join(f"r.{c}" for c in REPORT_COLUMNS)

        rows = await self.session.execute(
            f"""
            SELECT {col_list}
            FROM reports r
            WHERE {where_sql}
            ORDER BY r.priority_score DESC, r.created_at ASC, r.id ASC
            LIMIT ?
            """,
            tuple(params + [safe_limit + 1]),
        )

        has_more = len(rows) > safe_limit
        sliced = rows[:safe_limit]

        items: List[ModerationQueueItemResponse] = []
        for r in sliced:
            r_dict = _row_to_dict(REPORT_COLUMNS, r)
            t_type = str(r_dict["target_type"])
            t_id = str(r_dict["target_id"])

            cnt_rows = await self.session.execute(
                "SELECT COUNT(DISTINCT reporter_user_id) FROM reports WHERE target_type = ? AND target_id = ?",
                (t_type, t_id),
            )
            distinct_cnt = int(cnt_rows[0][0]) if cnt_rows else 1
            preview = await self._build_privacy_blind_target_preview(t_type, t_id)

            items.append(
                ModerationQueueItemResponse(
                    report_id=str(r_dict["id"]),
                    target_type=t_type,
                    target_id=t_id,
                    community_slug=r_dict.get("community_slug"),
                    content_language=str(r_dict.get("content_language") or "en"),
                    reason_code=str(r_dict["reason_code"]),
                    details=r_dict.get("details"),
                    priority_score=int(r_dict["priority_score"]),
                    status=str(r_dict["status"]),
                    distinct_reporter_count=distinct_cnt,
                    target_preview=preview,
                    created_at=str(r_dict["created_at"]),
                )
            )

        next_cur: Optional[str] = None
        if has_more and items:
            last = items[-1]
            next_cur = encode_cursor(last.created_at, last.report_id)

        return CursorModerationQueueResponse(
            items=items,
            next_cursor=next_cur,
            has_more=has_more,
        )

    async def execute_moderation_action(
        self,
        *,
        actor_user: dict[str, Any],
        payload: CreateModerationActionRequest,
        correlation_id: str = "req_mod_action",
    ) -> ModerationActionResponse:
        """Authorize, validate target state transitions, apply moderation action, notify, and audit."""
        actor_id = str(actor_user["id"])
        actor_role = str(actor_user.get("role", "member"))
        is_global, mod_slugs = await self._get_moderator_scope(actor_user)

        rate_limiter.check_and_record(
            bucket="moderation_action",
            key=actor_id,
            limit=60,
            window_seconds=60,
        )

        target_type = payload.target_type.strip().lower()
        if target_type not in VALID_MODERATION_TARGETS:
            raise AppError(
                code="INVALID_MODERATION_TARGET",
                message=f"target_type must be one of: {', '.join(VALID_MODERATION_TARGETS)}.",
                status_code=422,
            )

        action_type = payload.action_type.strip().lower()
        if action_type not in VALID_MODERATION_ACTIONS:
            raise AppError(
                code="INVALID_MODERATION_ACTION",
                message=f"action_type must be one of: {', '.join(VALID_MODERATION_ACTIONS)}.",
                status_code=422,
            )

        reason_code = payload.reason_code.strip().lower()
        if reason_code not in VALID_ACTION_REASONS:
            raise AppError(
                code="INVALID_MODERATION_REASON",
                message=f"reason_code must be one of: {', '.join(VALID_ACTION_REASONS)}.",
                status_code=422,
            )

        internal_note = normalize_unicode_nfc(payload.internal_note).strip()
        public_explanation = normalize_unicode_nfc(payload.public_explanation).strip()
        if len(internal_note) < 3 or len(public_explanation) < 3:
            raise AppError(
                code="VALIDATION_ERROR",
                message="Both internal_note and public_explanation are required.",
                status_code=422,
            )

        # Validate target-specific action compatibility
        user_only_actions = {"user_cooldown", "user_suspend", "restore_user"}
        content_only_actions = {
            "dismiss_reports",
            "redact_pii",
            "restrict_visibility",
            "place_under_review",
            "remove_content",
            "restore_content",
            "escalate_language_specialist",
        }
        if target_type == "user" and action_type not in user_only_actions:
            raise AppError(
                code="INVALID_MODERATION_TRANSITION",
                message=f"Action '{action_type}' cannot be applied to a user account target.",
                status_code=422,
            )
        if target_type != "user" and action_type in user_only_actions:
            raise AppError(
                code="INVALID_MODERATION_TRANSITION",
                message=f"Account action '{action_type}' can only be applied when target_type is 'user'.",
                status_code=422,
            )

        # Community moderators cannot perform platform-wide user account actions
        if not is_global and (target_type == "user" or action_type in user_only_actions):
            raise AppError(
                code="FORBIDDEN_MODERATION_SCOPE",
                message="Community moderators cannot apply platform-wide account cooldowns or suspensions.",
                status_code=403,
            )

        target_id = payload.target_id.strip()
        now_dt = _now_utc()
        now_str = now_dt.isoformat()
        affected_user_id: Optional[str] = None
        comm_slug: Optional[str] = None
        prev_state: Optional[str] = None
        new_state: Optional[str] = None
        is_appealable = 1

        if target_type in {"post", "comment"}:
            if target_type == "post":
                rows = await self.session.execute(
                    "SELECT author_user_id, community_slug, moderation_status, deleted_at, title, body FROM posts WHERE id = ?",
                    (target_id,),
                )
            else:
                rows = await self.session.execute(
                    """
                    SELECT c.author_user_id, p.community_slug, c.moderation_status, c.deleted_at, NULL, c.body
                    FROM comments c
                    JOIN posts p ON p.id = c.post_id
                    WHERE c.id = ?
                    """,
                    (target_id,),
                )
            if not rows:
                raise AppError(
                    code="TARGET_NOT_FOUND",
                    message=f"Target {target_type} was not found.",
                    status_code=404,
                )
            author_id, c_slug, mod_status, deleted_at, t_title, t_body = rows[0]
            if deleted_at is not None:
                raise AppError(
                    code="INVALID_MODERATION_TRANSITION",
                    message=f"Cannot moderate a {target_type} that was already deleted by its author.",
                    status_code=422,
                )
            affected_user_id = str(author_id) if author_id else None
            comm_slug = str(c_slug) if c_slug else None
            prev_state = str(mod_status)

            if not is_global and comm_slug not in mod_slugs:
                raise AppError(
                    code="FORBIDDEN_MODERATION_SCOPE",
                    message=f"You are not authorized to moderate content in c/{comm_slug}.",
                    status_code=403,
                )

            table = "posts" if target_type == "post" else "comments"
            if action_type == "dismiss_reports":
                new_state = "published" if prev_state == "awaiting_review" else prev_state
                is_appealable = 0
                await self.session.execute(
                    f"UPDATE {table} SET moderation_status = ?, updated_at = ? WHERE id = ?",
                    (new_state, now_str, target_id),
                )
            elif action_type == "escalate_language_specialist":
                new_state = prev_state
                is_appealable = 0
                await self.session.execute(
                    """
                    UPDATE reports
                    SET status = 'escalated_language_specialist', updated_at = ?
                    WHERE target_type = ? AND target_id = ? AND status IN ('open', 'in_review')
                    """,
                    (now_str, target_type, target_id),
                )
            elif action_type == "place_under_review":
                new_state = "awaiting_review"
                await self.session.execute(
                    f"UPDATE {table} SET moderation_status = 'awaiting_review', updated_at = ? WHERE id = ?",
                    (now_str, target_id),
                )
            elif action_type == "redact_pii":
                new_state = "published"
                if target_type == "post":
                    redacted_title = redact_pii_in_text(str(t_title or ""))
                    redacted_body = redact_pii_in_text(str(t_body or ""))
                    await self.session.execute(
                        "UPDATE posts SET title = ?, body = ?, moderation_status = 'published', updated_at = ? WHERE id = ?",
                        (redacted_title, redacted_body, now_str, target_id),
                    )
                else:
                    redacted_body = redact_pii_in_text(str(t_body or ""))
                    await self.session.execute(
                        "UPDATE comments SET body = ?, moderation_status = 'published', updated_at = ? WHERE id = ?",
                        (redacted_body, now_str, target_id),
                    )
            elif action_type == "restrict_visibility":
                new_state = "restricted"
                await self.session.execute(
                    f"UPDATE {table} SET moderation_status = 'restricted', updated_at = ? WHERE id = ?",
                    (now_str, target_id),
                )
            elif action_type == "remove_content":
                new_state = "removed"
                await self.session.execute(
                    f"UPDATE {table} SET moderation_status = 'removed', updated_at = ? WHERE id = ?",
                    (now_str, target_id),
                )
            elif action_type == "restore_content":
                if prev_state == "published":
                    raise AppError(
                        code="INVALID_MODERATION_TRANSITION",
                        message="Content is already published.",
                        status_code=422,
                    )
                new_state = "published"
                is_appealable = 0
                await self.session.execute(
                    f"UPDATE {table} SET moderation_status = 'published', updated_at = ? WHERE id = ?",
                    (now_str, target_id),
                )

        elif target_type == "meme_asset":
            if not is_global:
                raise AppError(
                    code="FORBIDDEN_MODERATION_SCOPE",
                    message="Global moderator or admin permissions are required to moderate standalone meme assets.",
                    status_code=403,
                )
            rows = await self.session.execute(
                "SELECT owner_user_id, safety_status FROM meme_assets WHERE id = ?",
                (target_id,),
            )
            if not rows:
                raise AppError(
                    code="TARGET_NOT_FOUND",
                    message="Target meme asset was not found.",
                    status_code=404,
                )
            owner_id, safety_st = rows[0]
            affected_user_id = str(owner_id) if owner_id else None
            prev_state = str(safety_st)
            if action_type == "remove_content":
                new_state = "rejected"
                await self.session.execute(
                    "UPDATE meme_assets SET safety_status = 'rejected' WHERE id = ?",
                    (target_id,),
                )
            elif action_type == "restore_content":
                new_state = "approved"
                is_appealable = 0
                await self.session.execute(
                    "UPDATE meme_assets SET safety_status = 'approved' WHERE id = ?",
                    (target_id,),
                )
            elif action_type == "dismiss_reports":
                new_state = prev_state
                is_appealable = 0
            else:
                raise AppError(
                    code="INVALID_MODERATION_TRANSITION",
                    message=f"Action '{action_type}' is not supported for meme_asset.",
                    status_code=422,
                )

        elif target_type == "user":
            # Look up by user_id or @handle
            u_rows = await self.session.execute(
                """
                SELECT u.id, u.account_status
                FROM users u
                LEFT JOIN public_profiles pp ON pp.user_id = u.id
                WHERE u.id = ? OR pp.handle_normalized = ?
                """,
                (target_id, target_id.strip().lower()),
            )
            if not u_rows:
                raise AppError(
                    code="TARGET_NOT_FOUND",
                    message="Target user account was not found.",
                    status_code=404,
                )
            resolved_uid, acc_status = str(u_rows[0][0]), str(u_rows[0][1])
            if acc_status == "deleted":
                raise AppError(
                    code="INVALID_MODERATION_TRANSITION",
                    message="Cannot apply moderation actions to a deleted account.",
                    status_code=422,
                )
            target_id = resolved_uid
            affected_user_id = resolved_uid
            prev_state = acc_status

            if action_type == "user_cooldown":
                new_state = "cooldown"
                until_str = (now_dt + timedelta(hours=payload.cooldown_hours)).isoformat()
                await self.session.execute(
                    "UPDATE users SET account_status = 'cooldown', cooldown_until = ?, updated_at = ? WHERE id = ?",
                    (until_str, now_str, resolved_uid),
                )
            elif action_type == "user_suspend":
                new_state = "suspended"
                await self.session.execute(
                    "UPDATE users SET account_status = 'suspended', cooldown_until = NULL, updated_at = ? WHERE id = ?",
                    (now_str, resolved_uid),
                )
                # Revoke active sessions on suspension
                await self.session.execute(
                    "UPDATE user_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                    (now_str, resolved_uid),
                )
            elif action_type == "restore_user":
                new_state = "active"
                is_appealable = 0
                await self.session.execute(
                    "UPDATE users SET account_status = 'active', cooldown_until = NULL, updated_at = ? WHERE id = ?",
                    (now_str, resolved_uid),
                )

        action_id = str(uuid.uuid4())
        actor_label = "admin" if actor_role == "admin" else "moderator"
        await self.session.execute(
            """
            INSERT INTO moderation_actions (
                id, moderator_user_id, actor_type, target_type, target_id,
                affected_user_id, community_slug, action_type, reason_code,
                internal_note, public_explanation, previous_state, new_state,
                is_appealable, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action_id,
                actor_id,
                actor_label,
                target_type,
                target_id,
                affected_user_id,
                comm_slug,
                action_type,
                reason_code,
                internal_note,
                public_explanation,
                prev_state,
                new_state,
                is_appealable,
                now_str,
            ),
        )

        # Update associated open/in_review reports
        if action_type == "dismiss_reports":
            await self.session.execute(
                """
                UPDATE reports
                SET status = 'resolved_dismissed', resolved_by_action_id = ?, updated_at = ?
                WHERE target_type = ? AND target_id = ? AND status IN ('open', 'in_review', 'escalated_language_specialist')
                """,
                (action_id, now_str, target_type, target_id),
            )
        elif action_type not in {"escalate_language_specialist", "place_under_review"}:
            await self.session.execute(
                """
                UPDATE reports
                SET status = 'resolved_actioned', resolved_by_action_id = ?, updated_at = ?
                WHERE target_type = ? AND target_id = ? AND status IN ('open', 'in_review', 'escalated_language_specialist')
                """,
                (action_id, now_str, target_type, target_id),
            )

        await self._record_audit_event(
            actor_user_id=actor_id,
            actor_role=actor_role,
            event_category="moderation",
            action_name=action_type,
            target_type=target_type,
            target_id=target_id,
            reason_code=reason_code,
            metadata={
                "moderation_action_id": action_id,
                "community_slug": comm_slug,
                "previous_state": prev_state,
                "new_state": new_state,
            },
            correlation_id=correlation_id,
        )

        # Notify affected user when a restrictive or corrective action is taken
        if affected_user_id and action_type in {
            "redact_pii",
            "restrict_visibility",
            "place_under_review",
            "remove_content",
            "user_cooldown",
            "user_suspend",
        }:
            notif_svc = NotificationService(self.session)
            appeal_suffix = " You may submit an appeal at /moderation/appeals." if is_appealable else ""
            await notif_svc.create_notification(
                recipient_user_id=affected_user_id,
                notification_type="moderation_notice",
                reference_type="moderation_action",
                reference_id=action_id,
                title=f"Moderation Notice: {action_type.replace('_', ' ').title()} ({reason_code})",
                body_preview=f"{public_explanation}{appeal_suffix}"[:250],
            )

        return ModerationActionResponse(
            id=action_id,
            actor_type=actor_label,
            target_type=target_type,
            target_id=target_id,
            community_slug=comm_slug,
            action_type=action_type,
            reason_code=reason_code,
            public_explanation=public_explanation,
            previous_state=prev_state,
            new_state=new_state,
            is_appealable=bool(is_appealable),
            appeal_status=None,
            created_at=now_str,
        )

    async def list_my_moderation_actions(
        self, *, user_id: str
    ) -> MyModerationActionsListResponse:
        rows = await self.session.execute(
            f"""
            SELECT {', '.join('ma.' + c for c in ACTION_COLUMNS)}, ap.status
            FROM moderation_actions ma
            LEFT JOIN moderation_appeals ap ON ap.moderation_action_id = ma.id
            WHERE ma.affected_user_id = ?
            ORDER BY ma.created_at DESC
            LIMIT 50
            """,
            (user_id,),
        )
        items: List[ModerationActionResponse] = []
        for r in rows:
            d = _row_to_dict(ACTION_COLUMNS, r[:-1])
            ap_status = str(r[-1]) if r[-1] is not None else None
            items.append(
                ModerationActionResponse(
                    id=str(d["id"]),
                    actor_type=str(d["actor_type"]),
                    target_type=str(d["target_type"]),
                    target_id=str(d["target_id"]),
                    community_slug=d.get("community_slug"),
                    action_type=str(d["action_type"]),
                    reason_code=str(d["reason_code"]),
                    public_explanation=str(d["public_explanation"]),
                    previous_state=d.get("previous_state"),
                    new_state=d.get("new_state"),
                    is_appealable=bool(d["is_appealable"]),
                    appeal_status=ap_status,
                    created_at=str(d["created_at"]),
                )
            )
        return MyModerationActionsListResponse(items=items)

    async def submit_appeal(
        self,
        *,
        appellant_user: dict[str, Any],
        payload: CreateAppealRequest,
        correlation_id: str = "req_appeal",
    ) -> AppealResponse:
        appellant_id = str(appellant_user["id"])
        rate_limiter.check_and_record(
            bucket="appeal_submit",
            key=appellant_id,
            limit=5,
            window_seconds=86400,
        )

        act_id = payload.moderation_action_id.strip()
        rows = await self.session.execute(
            f"SELECT {', '.join(ACTION_COLUMNS)} FROM moderation_actions WHERE id = ?",
            (act_id,),
        )
        if not rows:
            raise AppError(
                code="MODERATION_ACTION_NOT_FOUND",
                message="The referenced moderation action was not found.",
                status_code=404,
            )
        act_dict = _row_to_dict(ACTION_COLUMNS, rows[0])

        if str(act_dict.get("affected_user_id") or "") != appellant_id:
            raise AppError(
                code="FORBIDDEN_NOT_AFFECTED_USER",
                message="You can only submit an appeal for a moderation action applied to your own content or account.",
                status_code=403,
            )

        if not bool(act_dict.get("is_appealable")):
            raise AppError(
                code="ACTION_NOT_APPEALABLE",
                message="This moderation record is not eligible for appeal.",
                status_code=422,
            )

        existing = await self.session.execute(
            "SELECT id FROM moderation_appeals WHERE moderation_action_id = ?",
            (act_id,),
        )
        if existing:
            raise AppError(
                code="APPEAL_ALREADY_EXISTS",
                message="An appeal has already been submitted for this moderation action.",
                status_code=409,
            )

        statement = normalize_unicode_nfc(payload.appeal_statement).strip()
        if len(statement) < 10 or len(statement) > 2000:
            raise AppError(
                code="VALIDATION_ERROR",
                message="Appeal statement must be between 10 and 2,000 characters.",
                status_code=422,
            )

        appeal_id = str(uuid.uuid4())
        now_str = _now_iso()
        await self.session.execute(
            """
            INSERT INTO moderation_appeals (
                id, moderation_action_id, appellant_user_id, appeal_statement,
                status, reviewed_by_user_id, decision_reason_code,
                review_decision_note, created_at, resolved_at
            ) VALUES (?, ?, ?, ?, 'pending', NULL, NULL, NULL, ?, NULL)
            """,
            (appeal_id, act_id, appellant_id, statement, now_str),
        )

        await self._record_audit_event(
            actor_user_id=appellant_id,
            actor_role=str(appellant_user.get("role", "member")),
            event_category="appeal_review",
            action_name="appeal_submitted",
            target_type=str(act_dict["target_type"]),
            target_id=str(act_dict["target_id"]),
            reason_code=str(act_dict["reason_code"]),
            metadata={"appeal_id": appeal_id, "moderation_action_id": act_id},
            correlation_id=correlation_id,
        )

        return AppealResponse(
            id=appeal_id,
            moderation_action_id=act_id,
            target_type=str(act_dict["target_type"]),
            target_id=str(act_dict["target_id"]),
            original_action_type=str(act_dict["action_type"]),
            original_reason_code=str(act_dict["reason_code"]),
            public_explanation=str(act_dict["public_explanation"]),
            appeal_statement=statement,
            status="pending",
            can_viewer_decide=False,
            created_at=now_str,
            resolved_at=None,
        )

    async def list_appeals(
        self,
        *,
        viewer_user: dict[str, Any],
        status: Optional[str] = None,
    ) -> AppealListResponse:
        viewer_id = str(viewer_user["id"])
        role = str(viewer_user.get("role", "member"))
        is_global_reviewer = role in {"global_moderator", "admin"}

        clauses: List[str] = []
        params: List[Any] = []
        if not is_global_reviewer:
            clauses.append("ap.appellant_user_id = ?")
            params.append(viewer_id)
        if status:
            st = status.strip().lower()
            if st not in {"pending", "accepted", "rejected"}:
                raise AppError(
                    code="VALIDATION_ERROR",
                    message="Appeal status filter must be pending, accepted, or rejected.",
                    status_code=422,
                )
            clauses.append("ap.status = ?")
            params.append(st)

        where_sql = " AND ".join(clauses) if clauses else "1=1"
        rows = await self.session.execute(
            f"""
            SELECT
                ap.id, ap.moderation_action_id, ap.appellant_user_id,
                ap.appeal_statement, ap.status, ap.reviewed_by_user_id,
                ap.decision_reason_code, ap.review_decision_note,
                ap.created_at, ap.resolved_at,
                ma.target_type, ma.target_id, ma.action_type,
                ma.reason_code, ma.public_explanation, ma.moderator_user_id
            FROM moderation_appeals ap
            JOIN moderation_actions ma ON ma.id = ap.moderation_action_id
            WHERE {where_sql}
            ORDER BY ap.created_at ASC
            LIMIT 50
            """,
            tuple(params),
        )

        items: List[AppealResponse] = []
        for r in rows:
            (
                ap_id,
                ma_id,
                _,
                ap_stmt,
                ap_status,
                _,
                dec_reason,
                dec_note,
                created_at,
                resolved_at,
                t_type,
                t_id,
                orig_action,
                orig_reason,
                pub_exp,
                orig_mod_id,
            ) = r
            can_decide = bool(
                is_global_reviewer
                and str(ap_status) == "pending"
                and (orig_mod_id is None or str(orig_mod_id) != viewer_id)
            )
            items.append(
                AppealResponse(
                    id=str(ap_id),
                    moderation_action_id=str(ma_id),
                    target_type=str(t_type),
                    target_id=str(t_id),
                    original_action_type=str(orig_action),
                    original_reason_code=str(orig_reason),
                    public_explanation=str(pub_exp),
                    appeal_statement=str(ap_stmt),
                    status=str(ap_status),
                    decision_reason_code=dec_reason,
                    review_decision_note=dec_note,
                    can_viewer_decide=can_decide,
                    created_at=str(created_at),
                    resolved_at=resolved_at,
                )
            )
        return AppealListResponse(items=items)

    async def decide_appeal(
        self,
        *,
        appeal_id: str,
        reviewer_user: dict[str, Any],
        payload: DecideAppealRequest,
        correlation_id: str = "req_appeal_decide",
    ) -> AppealResponse:
        """Review and decide a pending appeal, strictly enforcing separation of duties."""
        reviewer_id = str(reviewer_user["id"])
        reviewer_role = str(reviewer_user.get("role", "member"))
        if reviewer_role not in {"global_moderator", "admin"}:
            raise AppError(
                code="FORBIDDEN_ROLE",
                message="Only global moderators and administrators may review moderation appeals.",
                status_code=403,
            )

        decision = payload.decision.strip().lower()
        if decision not in {"accepted", "rejected"}:
            raise AppError(
                code="VALIDATION_ERROR",
                message="Appeal decision must be 'accepted' or 'rejected'.",
                status_code=422,
            )

        reason_code = payload.decision_reason_code.strip().lower()
        if reason_code not in VALID_ACTION_REASONS:
            raise AppError(
                code="INVALID_MODERATION_REASON",
                message=f"decision_reason_code must be one of: {', '.join(VALID_ACTION_REASONS)}.",
                status_code=422,
            )

        note = normalize_unicode_nfc(payload.review_decision_note).strip()
        if len(note) < 5:
            raise AppError(
                code="VALIDATION_ERROR",
                message="A review decision explanation of at least 5 characters is required.",
                status_code=422,
            )

        rows = await self.session.execute(
            """
            SELECT
                ap.id, ap.moderation_action_id, ap.appellant_user_id,
                ap.appeal_statement, ap.status, ap.created_at,
                ma.moderator_user_id, ma.target_type, ma.target_id,
                ma.action_type, ma.reason_code, ma.public_explanation
            FROM moderation_appeals ap
            JOIN moderation_actions ma ON ma.id = ap.moderation_action_id
            WHERE ap.id = ?
            """,
            (appeal_id,),
        )
        if not rows:
            raise AppError(
                code="APPEAL_NOT_FOUND",
                message="The requested moderation appeal was not found.",
                status_code=404,
            )

        (
            _,
            ma_id,
            appellant_id,
            ap_stmt,
            ap_status,
            ap_created_at,
            orig_mod_id,
            t_type,
            t_id,
            orig_action,
            orig_reason,
            pub_exp,
        ) = rows[0]

        if str(ap_status) != "pending":
            raise AppError(
                code="APPEAL_ALREADY_RESOLVED",
                message=f"This appeal has already been resolved ({ap_status}).",
                status_code=409,
            )

        # Separation of duties enforcement (Section 4.3 & 9)
        if orig_mod_id is not None and str(orig_mod_id) == reviewer_id:
            raise AppError(
                code="SEPARATION_OF_DUTIES_VIOLATION",
                message="A moderator cannot approve or reject an appeal against their own original moderation decision.",
                status_code=403,
            )

        now_str = _now_iso()
        await self.session.execute(
            """
            UPDATE moderation_appeals
            SET status = ?,
                reviewed_by_user_id = ?,
                decision_reason_code = ?,
                review_decision_note = ?,
                resolved_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (decision, reviewer_id, reason_code, note, now_str, appeal_id),
        )

        # Apply corrective action when accepted, respecting any independent active restrictions
        if decision == "accepted":
            t_type_str = str(t_type)
            t_id_str = str(t_id)

            if t_type_str in {"post", "comment"}:
                table = "posts" if t_type_str == "post" else "comments"
                # Check if there is another unappealed/rejected restrictive moderation action after ma_id
                other_restrictive = await self.session.execute(
                    """
                    SELECT 1
                    FROM moderation_actions ma2
                    LEFT JOIN moderation_appeals ap2 ON ap2.moderation_action_id = ma2.id
                    WHERE ma2.target_type = ?
                      AND ma2.target_id = ?
                      AND ma2.id != ?
                      AND ma2.action_type IN ('restrict_visibility', 'remove_content', 'place_under_review')
                      AND (ap2.status IS NULL OR ap2.status != 'accepted')
                      AND ma2.created_at > (SELECT created_at FROM moderation_actions WHERE id = ?)
                    LIMIT 1
                    """,
                    (t_type_str, t_id_str, str(ma_id), str(ma_id)),
                )
                if not other_restrictive:
                    await self.session.execute(
                        f"UPDATE {table} SET moderation_status = 'published', updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                        (now_str, t_id_str),
                    )
            elif t_type_str == "meme_asset":
                await self.session.execute(
                    "UPDATE meme_assets SET safety_status = 'approved' WHERE id = ?",
                    (t_id_str,),
                )
            elif t_type_str == "user":
                # Only restore account to 'active' if no other active unoverturned cooldown/suspension exists
                other_user_penalties = await self.session.execute(
                    """
                    SELECT 1
                    FROM moderation_actions ma2
                    LEFT JOIN moderation_appeals ap2 ON ap2.moderation_action_id = ma2.id
                    WHERE ma2.target_type = 'user'
                      AND ma2.target_id = ?
                      AND ma2.id != ?
                      AND ma2.action_type IN ('user_cooldown', 'user_suspend')
                      AND (ap2.status IS NULL OR ap2.status != 'accepted')
                    LIMIT 1
                    """,
                    (t_id_str, str(ma_id)),
                )
                if not other_user_penalties:
                    await self.session.execute(
                        "UPDATE users SET account_status = 'active', cooldown_until = NULL, updated_at = ? WHERE id = ? AND account_status != 'deleted'",
                        (now_str, t_id_str),
                    )

        await self._record_audit_event(
            actor_user_id=reviewer_id,
            actor_role=reviewer_role,
            event_category="appeal_review",
            action_name=f"appeal_{decision}",
            target_type=str(t_type),
            target_id=str(t_id),
            reason_code=reason_code,
            metadata={
                "appeal_id": appeal_id,
                "moderation_action_id": str(ma_id),
                "decision": decision,
            },
            correlation_id=correlation_id,
        )

        notif_svc = NotificationService(self.session)
        await notif_svc.create_notification(
            recipient_user_id=str(appellant_id),
            notification_type="appeal_update",
            reference_type="moderation_appeal",
            reference_id=appeal_id,
            title=f"Your Moderation Appeal Was {decision.title()}",
            body_preview=note[:240],
        )

        return AppealResponse(
            id=appeal_id,
            moderation_action_id=str(ma_id),
            target_type=str(t_type),
            target_id=str(t_id),
            original_action_type=str(orig_action),
            original_reason_code=str(orig_reason),
            public_explanation=str(pub_exp),
            appeal_statement=str(ap_stmt),
            status=decision,
            decision_reason_code=reason_code,
            review_decision_note=note,
            can_viewer_decide=False,
            created_at=str(ap_created_at),
            resolved_at=now_str,
        )

    async def set_user_block_or_mute(
        self,
        *,
        blocker_user_id: str,
        target_handle: str,
        payload: SetBlockMuteRequest,
    ) -> BlockMuteStatusResponse:
        norm_handle = target_handle.strip().lower().lstrip("@")
        rows = await self.session.execute(
            """
            SELECT pp.user_id, pp.handle, u.account_status
            FROM public_profiles pp
            JOIN users u ON u.id = pp.user_id
            WHERE pp.handle_normalized = ?
            """,
            (norm_handle,),
        )
        if not rows:
            raise AppError(
                code="USER_NOT_FOUND",
                message="The specified user handle was not found.",
                status_code=404,
            )
        target_uid, canonical_handle, acc_status = str(rows[0][0]), str(rows[0][1]), str(rows[0][2])
        if acc_status == "deleted":
            raise AppError(
                code="USER_NOT_FOUND",
                message="The specified account is no longer active.",
                status_code=404,
            )
        if target_uid == blocker_user_id:
            raise AppError(
                code="CANNOT_BLOCK_SELF",
                message="You cannot block or mute your own account.",
                status_code=422,
            )

        mode = payload.mode.strip().lower()
        if mode not in VALID_BLOCK_MODES:
            raise AppError(
                code="VALIDATION_ERROR",
                message="Mode must be 'block' or 'mute'.",
                status_code=422,
            )

        if not payload.active:
            await self.session.execute(
                "DELETE FROM user_blocks WHERE blocker_user_id = ? AND blocked_user_id = ?",
                (blocker_user_id, target_uid),
            )
            return BlockMuteStatusResponse(
                handle=canonical_handle,
                active=False,
                mode=None,
            )

        now_str = _now_iso()
        existing = await self.session.execute(
            "SELECT block_mode FROM user_blocks WHERE blocker_user_id = ? AND blocked_user_id = ?",
            (blocker_user_id, target_uid),
        )
        if existing:
            await self.session.execute(
                "UPDATE user_blocks SET block_mode = ?, created_at = ? WHERE blocker_user_id = ? AND blocked_user_id = ?",
                (mode, now_str, blocker_user_id, target_uid),
            )
        else:
            await self.session.execute(
                "INSERT INTO user_blocks (blocker_user_id, blocked_user_id, block_mode, created_at) VALUES (?, ?, ?, ?)",
                (blocker_user_id, target_uid, mode, now_str),
            )

        return BlockMuteStatusResponse(
            handle=canonical_handle,
            active=True,
            mode=mode,
        )

    async def list_blocked_and_muted_accounts(
        self, *, user_id: str
    ) -> BlockedAccountsListResponse:
        rows = await self.session.execute(
            """
            SELECT pp.handle, pp.display_name, ub.block_mode, ub.created_at
            FROM user_blocks ub
            JOIN public_profiles pp ON pp.user_id = ub.blocked_user_id
            WHERE ub.blocker_user_id = ?
            ORDER BY ub.created_at DESC
            """,
            (user_id,),
        )
        items = [
            BlockedAccountItem(
                handle=str(r[0]),
                display_name=str(r[1] or f"@{r[0]}"),
                mode=str(r[2]),
                created_at=str(r[3]),
            )
            for r in rows
        ]
        return BlockedAccountsListResponse(items=items)

    async def list_audit_events(
        self,
        *,
        actor_user: dict[str, Any],
        event_category: Optional[str] = None,
        action_name: Optional[str] = None,
        target_type: Optional[str] = None,
        actor_id_filter: Optional[str] = None,
        reason_code: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 30,
    ) -> CursorAuditEventListResponse:
        """Read-only administrative audit log. Strictly restricted to `role == 'admin'`."""
        if str(actor_user.get("role", "member")) != "admin":
            raise AppError(
                code="FORBIDDEN_ROLE",
                message="Only platform administrators are permitted to inspect the immutable audit trail.",
                status_code=403,
            )

        clauses: List[str] = []
        params: List[Any] = []
        if event_category:
            clauses.append("event_category = ?")
            params.append(event_category.strip().lower())
        if action_name:
            clauses.append("action_name = ?")
            params.append(action_name.strip().lower())
        if target_type:
            clauses.append("target_type = ?")
            params.append(target_type.strip().lower())
        if actor_id_filter:
            clauses.append("actor_user_id = ?")
            params.append(actor_id_filter.strip())
        if reason_code:
            clauses.append("reason_code = ?")
            params.append(reason_code.strip().lower())
        if since:
            clauses.append("created_at >= ?")
            params.append(since.strip())
        if until:
            clauses.append("created_at <= ?")
            params.append(until.strip())
        if cursor:
            c_time, c_id = decode_cursor(cursor)
            clauses.append("(created_at < ? OR (created_at = ? AND id < ?))")
            params.extend([c_time, c_time, c_id])

        safe_limit = max(1, min(limit, 50))
        where_sql = " AND ".join(clauses) if clauses else "1=1"
        col_list = ", ".join(AUDIT_COLUMNS)

        rows = await self.session.execute(
            f"""
            SELECT {col_list}
            FROM audit_events
            WHERE {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            tuple(params + [safe_limit + 1]),
        )

        has_more = len(rows) > safe_limit
        sliced = rows[:safe_limit]

        items: List[AuditEventResponse] = []
        for r in sliced:
            d = _row_to_dict(AUDIT_COLUMNS, r)
            try:
                meta = json.loads(str(d.get("redacted_metadata") or "{}"))
            except Exception:
                meta = {}
            items.append(
                AuditEventResponse(
                    id=str(d["id"]),
                    actor_user_id=d.get("actor_user_id"),
                    actor_role=str(d["actor_role"]),
                    event_category=str(d["event_category"]),
                    action_name=str(d["action_name"]),
                    target_type=str(d["target_type"]),
                    target_id=d.get("target_id"),
                    reason_code=str(d["reason_code"]),
                    redacted_metadata=meta,
                    correlation_id=str(d["correlation_id"]),
                    created_at=str(d["created_at"]),
                )
            )

        next_cur: Optional[str] = None
        if has_more and items:
            last = items[-1]
            next_cur = encode_cursor(last.created_at, last.id)

        return CursorAuditEventListResponse(
            items=items,
            next_cursor=next_cur,
            has_more=has_more,
        )
