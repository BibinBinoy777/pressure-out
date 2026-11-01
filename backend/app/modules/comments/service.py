"""Transactional service for Phase 6 Threaded Comments, Sticky Anonymous OP Replies, and Notifications."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.core.errors import AppError
from app.modules.comments.schemas import (
    CreateCommentRequest,
    CursorCommentListResponse,
    PublicCommentResponse,
    UpdateCommentRequest,
    validate_and_normalize_comment_body,
)
from app.modules.comments.serializers import serialize_public_comment
from app.modules.communities.service import CommunityService
from app.modules.moderation.guards import check_user_can_contribute, is_interaction_blocked, should_suppress_notification
from app.modules.identity.schemas import validate_bcp47_tag, validate_identity_mode
from app.modules.notifications.service import NotificationService
from app.modules.posts.pii_guard import enforce_prepublish_pii_guardrail
from app.modules.feed.service import refresh_post_hot_rank
from app.modules.posts.service import PROFILE_COLUMNS, PROF_COLUMNS, decode_cursor, encode_cursor

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

MAX_COMMENT_DEPTH = 10


def _row_to_dict(columns: tuple[str, ...], row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(columns, row))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_thread_scoped_anonymous_label(post_id: str, user_id: str, pepper: str) -> str:
    """Compute a deterministic per-thread label (`Anonymous • 4F2A`) that cannot be correlated across posts."""
    digest = hmac.new(
        pepper.encode("utf-8"),
        f"thread_anon:{post_id}:{user_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:4].upper()
    return f"Anonymous • {digest}"


class CommentService:
    """Manages nested comments (`ltree`/path), Sticky Anonymous OP protection, and reply notifications."""

    def __init__(self, session: Any, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def _fetch_profile(self, user_id: Optional[str]) -> Optional[dict[str, Any]]:
        if not user_id:
            return None
        rows = await self.session.execute(
            f"SELECT {', '.join(PROFILE_COLUMNS)} FROM public_profiles WHERE user_id = ?",
            (user_id,),
        )
        return _row_to_dict(PROFILE_COLUMNS, rows[0]) if rows else None

    async def _fetch_prof_profile(self, user_id: Optional[str]) -> Optional[dict[str, Any]]:
        if not user_id:
            return None
        rows = await self.session.execute(
            f"SELECT {', '.join(PROF_COLUMNS)} FROM professional_profiles WHERE user_id = ?",
            (user_id,),
        )
        return _row_to_dict(PROF_COLUMNS, rows[0]) if rows else None

    async def _build_comment_response(
        self,
        comment_row: dict[str, Any],
        *,
        viewer_user_id: Optional[str] = None,
        pii_warnings: Optional[List[Dict[str, str]]] = None,
    ) -> PublicCommentResponse:
        author_id = comment_row.get("author_user_id")
        if str(comment_row["identity_mode"]) == "anonymous" or comment_row.get("deleted_at") is not None:
            profile_row = None
            prof_row = None
        else:
            profile_row = await self._fetch_profile(str(author_id) if author_id else None)
            prof_row = await self._fetch_prof_profile(str(author_id) if author_id else None)

        viewer_vote = 0
        viewer_reactions: List[str] = []
        if viewer_user_id:
            v_rows = await self.session.execute(
                "SELECT value FROM votes WHERE user_id = ? AND target_type = 'comment' AND target_id = ?",
                (viewer_user_id, str(comment_row["id"])),
            )
            if v_rows:
                viewer_vote = int(v_rows[0][0])
            r_rows = await self.session.execute(
                "SELECT reaction_kind FROM reactions WHERE user_id = ? AND target_type = 'comment' AND target_id = ?",
                (viewer_user_id, str(comment_row["id"])),
            )
            viewer_reactions = [str(r[0]) for r in r_rows]

        return serialize_public_comment(
            comment_row=comment_row,
            profile_row=profile_row,
            prof_row=prof_row,
            viewer_user_id=viewer_user_id,
            viewer_vote=viewer_vote,
            viewer_reactions=viewer_reactions,
            pii_warnings=pii_warnings,
        )

    async def create_comment(
        self,
        *,
        post_id: str,
        author_user: dict[str, Any],
        payload: CreateCommentRequest,
    ) -> PublicCommentResponse:
        await check_user_can_contribute(self.session, author_user)
        user_id = str(author_user["id"])

        # 1. Verify target post exists and is published
        post_rows = await self.session.execute(
            """
            SELECT id, author_user_id, community_slug, identity_mode, title, moderation_status, deleted_at
            FROM posts WHERE id = ?
            """,
            (post_id,),
        )
        if not post_rows:
            raise AppError(
                code="POST_NOT_FOUND",
                message="The target post was not found.",
                status_code=404,
            )
        _, post_author_id, comm_slug, post_identity_mode, post_title, post_mod_status, post_deleted_at = post_rows[0]
        if post_deleted_at is not None or str(post_mod_status) in {"removed", "restricted", "awaiting_review"}:
            raise AppError(
                code="POST_REMOVED",
                message="Cannot comment on a deleted or removed post.",
                status_code=410,
            )

        if await is_interaction_blocked(self.session, user_id, str(post_author_id) if post_author_id else None):
            raise AppError(
                code="INTERACTION_BLOCKED",
                message="You cannot interact with this content due to an active account block.",
                status_code=403,
            )
        # 2. Enforce community membership/ban permissions
        comm_service = CommunityService(self.session)
        await comm_service.verify_can_post_and_get_community(
            slug=str(comm_slug), author_user=author_user
        )

        # 3. Enforce Sticky Anonymous OP Guardrail (AC-IMP-06)!
        is_post_author = bool(post_author_id and str(post_author_id) == user_id)
        post_is_anonymous = str(post_identity_mode) == "anonymous"

        if is_post_author and post_is_anonymous:
            if payload.identity_mode is None:
                effective_mode = "anonymous"
            else:
                requested_mode = validate_identity_mode(payload.identity_mode)
                if requested_mode != "anonymous" and not payload.confirm_op_identity_reveal:
                    raise AppError(
                        code="OP_ANONYMITY_MISMATCH",
                        message="You published this post anonymously. Replying under your handle may reveal you as the original poster. Set confirm_op_identity_reveal=true to override.",
                        status_code=409,
                    )
                effective_mode = requested_mode
        else:
            raw_mode = payload.identity_mode or str(author_user.get("default_identity_mode", "pseudonymous"))
            effective_mode = validate_identity_mode(raw_mode)

        # 4. Professional profile snapshot if mode == 'professional'
        prof_snapshot_json: Optional[str] = None
        if effective_mode == "professional":
            prof_row = await self._fetch_prof_profile(user_id)
            if not prof_row or not bool(prof_row.get("is_enabled")):
                raise AppError(
                    code="PROFESSIONAL_PROFILE_REQUIRED",
                    message="To comment in Professional identity mode, enable your Professional Profile in Settings first.",
                    status_code=422,
                )
            prof_snapshot_json = json.dumps(
                {
                    "role_title": prof_row["role_title"],
                    "industry": prof_row["industry"],
                    "experience_band": prof_row["experience_band"],
                    "region_label": prof_row.get("region_label"),
                },
                ensure_ascii=False,
            )

        # 5. Validate parent comment & compute materialized ltree path
        parent_author_id: Optional[str] = None
        comment_id = str(uuid.uuid4())
        short_segment = comment_id.replace("-", "")[:12]

        if payload.parent_comment_id:
            parent_rows = await self.session.execute(
                "SELECT id, post_id, author_user_id, path, depth, deleted_at FROM comments WHERE id = ?",
                (payload.parent_comment_id,),
            )
            if not parent_rows:
                raise AppError(
                    code="PARENT_COMMENT_NOT_FOUND",
                    message="Parent comment was not found.",
                    status_code=404,
                )
            _, p_post_id, p_author_id, p_path, p_depth, _ = parent_rows[0]
            if str(p_post_id) != post_id:
                raise AppError(
                    code="INVALID_PARENT_COMMENT",
                    message="Parent comment belongs to a different post.",
                    status_code=422,
                )
            depth = int(p_depth) + 1
            if depth > MAX_COMMENT_DEPTH:
                raise AppError(
                    code="MAX_COMMENT_DEPTH_EXCEEDED",
                    message=f"Maximum comment nesting depth ({MAX_COMMENT_DEPTH}) reached.",
                    status_code=422,
                )
            path_str = f"{p_path}.{short_segment}"
            parent_author_id = str(p_author_id) if p_author_id else None
            if await is_interaction_blocked(self.session, user_id, parent_author_id):
                raise AppError(
                    code="INTERACTION_BLOCKED",
                    message="You cannot reply to this comment due to an active account block.",
                    status_code=403,
                )
        else:
            depth = 0
            path_str = short_segment

        # 6. Validate body, language & run PII guardrail
        body = validate_and_normalize_comment_body(payload.body)
        content_language = validate_bcp47_tag(payload.content_language)
        pii_warnings = enforce_prepublish_pii_guardrail(
            title="",
            body=body,
            acknowledge_pii_warning=payload.acknowledge_pii_warning,
        )

        is_anon_op = bool(is_post_author and effective_mode == "anonymous")
        anon_label: Optional[str] = None
        if effective_mode == "anonymous":
            anon_label = (
                "Anonymous OP"
                if is_anon_op
                else compute_thread_scoped_anonymous_label(
                    post_id, user_id, self.settings.email_hmac_pepper
                )
            )

        now_str = _now_iso()
        await self.session.execute(
            """
            INSERT INTO comments (
                id, post_id, author_user_id, parent_comment_id, path, depth,
                identity_mode, professional_snapshot, is_anonymous_op,
                anonymous_thread_label, body, content_language, moderation_status,
                upvote_count, downvote_count, score, reaction_counts,
                created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', 0, 0, 0, '{}', ?, ?, NULL)
            """,
            (
                comment_id,
                post_id,
                user_id,
                payload.parent_comment_id,
                path_str,
                depth,
                effective_mode,
                prof_snapshot_json,
                1 if is_anon_op else 0,
                anon_label,
                body,
                content_language,
                now_str,
                now_str,
            ),
        )

        # Increment post.comment_count & recalculate hot_rank_score
        await self.session.execute(
            "UPDATE posts SET comment_count = comment_count + 1, updated_at = ? WHERE id = ?",
            (now_str, post_id),
        )
        await refresh_post_hot_rank(self.session, post_id)

        # 7. Dispatch privacy-safe in-app notification to post author or parent comment author
        notif_service = NotificationService(self.session)
        actor_profile = await self._fetch_profile(user_id)
        public_actor_label = (
            "Anonymous Member"
            if effective_mode == "anonymous"
            else f"@{actor_profile['handle']}" if actor_profile else "A member"
        )

        if payload.parent_comment_id and parent_author_id and parent_author_id != user_id and not await should_suppress_notification(self.session, parent_author_id, user_id):
            await notif_service.create_notification(
                recipient_user_id=parent_author_id,
                notification_type="comment_reply",
                reference_type="comment",
                reference_id=comment_id,
                title=f"{public_actor_label} replied to your comment",
                body_preview=body,
            )
        elif post_author_id and str(post_author_id) != user_id and not await should_suppress_notification(self.session, str(post_author_id), user_id):
            await notif_service.create_notification(
                recipient_user_id=str(post_author_id),
                notification_type="post_reply",
                reference_type="post",
                reference_id=post_id,
                title=f"{public_actor_label} commented on '{str(post_title)[:60]}'",
                body_preview=body,
            )

        c_rows = await self.session.execute(
            f"SELECT {', '.join(COMMENT_COLUMNS)} FROM comments WHERE id = ?",
            (comment_id,),
        )
        c_dict = _row_to_dict(COMMENT_COLUMNS, c_rows[0])
        return await self._build_comment_response(
            c_dict, viewer_user_id=user_id, pii_warnings=pii_warnings
        )

    async def list_comments(
        self,
        *,
        post_id: str,
        parent_comment_id: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 30,
        viewer_user_id: Optional[str] = None,
    ) -> CursorCommentListResponse:
        # Verify post exists
        p_rows = await self.session.execute("SELECT id FROM posts WHERE id = ?", (post_id,))
        if not p_rows:
            raise AppError(
                code="POST_NOT_FOUND",
                message="The target post was not found.",
                status_code=404,
            )

        safe_limit = max(1, min(limit, 50))
        clauses = ["c.post_id = ?", "c.moderation_status = 'published'"]
        params: List[Any] = [post_id]

        if parent_comment_id:
            parent_rows = await self.session.execute(
                "SELECT path FROM comments WHERE id = ? AND post_id = ?",
                (parent_comment_id, post_id),
            )
            if not parent_rows:
                raise AppError(
                    code="PARENT_COMMENT_NOT_FOUND",
                    message="Parent comment was not found.",
                    status_code=404,
                )
            parent_path = str(parent_rows[0][0])
            clauses.append("c.path LIKE ?")
            params.append(f"{parent_path}.%")

        if viewer_user_id:
            clauses.append(
                """
                (
                    c.author_user_id IS NULL
                    OR NOT EXISTS (
                        SELECT 1 FROM user_blocks ub
                        WHERE (ub.blocker_user_id = ? AND ub.blocked_user_id = c.author_user_id)
                           OR (ub.blocker_user_id = c.author_user_id AND ub.blocked_user_id = ? AND ub.block_mode = 'block')
                    )
                )
                """
            )
            params.extend([viewer_user_id, viewer_user_id])

        if cursor:
            c_path, c_id = decode_cursor(cursor)
            clauses.append("(c.path > ? OR (c.path = ? AND c.id > ?))")
            params.extend([c_path, c_path, c_id])

        where_sql = " AND ".join(clauses)
        col_list = ", ".join(f"c.{col}" for col in COMMENT_COLUMNS)
        rows = await self.session.execute(
            f"""
            SELECT {col_list}
            FROM comments c
            WHERE {where_sql}
            ORDER BY c.path ASC, c.id ASC
            LIMIT ?
            """,
            tuple(params + [safe_limit + 1]),
        )

        has_more = len(rows) > safe_limit
        sliced = rows[:safe_limit]

        items: List[PublicCommentResponse] = []
        for r in sliced:
            c_dict = _row_to_dict(COMMENT_COLUMNS, r)
            items.append(
                await self._build_comment_response(c_dict, viewer_user_id=viewer_user_id)
            )

        next_cur: Optional[str] = None
        if has_more and items:
            last = items[-1]
            next_cur = encode_cursor(last.path, last.id)

        return CursorCommentListResponse(
            items=items,
            next_cursor=next_cur,
            has_more=has_more,
        )

    async def update_comment(
        self,
        *,
        comment_id: str,
        actor_user_id: str,
        payload: UpdateCommentRequest,
    ) -> PublicCommentResponse:
        rows = await self.session.execute(
            f"SELECT {', '.join(COMMENT_COLUMNS)} FROM comments WHERE id = ?",
            (comment_id,),
        )
        if not rows:
            raise AppError(
                code="COMMENT_NOT_FOUND",
                message="The requested comment was not found.",
                status_code=404,
            )
        c_dict = _row_to_dict(COMMENT_COLUMNS, rows[0])
        if c_dict.get("deleted_at") is not None:
            raise AppError(
                code="COMMENT_REMOVED",
                message="Deleted comments cannot be edited.",
                status_code=410,
            )
        if str(c_dict.get("author_user_id")) != actor_user_id:
            raise AppError(
                code="FORBIDDEN_NOT_AUTHOR",
                message="You are only permitted to edit your own comments.",
                status_code=403,
            )

        new_body = validate_and_normalize_comment_body(payload.body)
        pii_warnings = enforce_prepublish_pii_guardrail(
            title="",
            body=new_body,
            acknowledge_pii_warning=payload.acknowledge_pii_warning,
        )

        now_str = _now_iso()
        await self.session.execute(
            "UPDATE comments SET body = ?, updated_at = ? WHERE id = ?",
            (new_body, now_str, comment_id),
        )

        updated_rows = await self.session.execute(
            f"SELECT {', '.join(COMMENT_COLUMNS)} FROM comments WHERE id = ?",
            (comment_id,),
        )
        updated_dict = _row_to_dict(COMMENT_COLUMNS, updated_rows[0])
        return await self._build_comment_response(
            updated_dict, viewer_user_id=actor_user_id, pii_warnings=pii_warnings
        )

    async def delete_comment(self, *, comment_id: str, actor_user_id: str) -> None:
        rows = await self.session.execute(
            "SELECT id, post_id, author_user_id, deleted_at FROM comments WHERE id = ?",
            (comment_id,),
        )
        if not rows:
            raise AppError(
                code="COMMENT_NOT_FOUND",
                message="The requested comment was not found.",
                status_code=404,
            )
        _, post_id, author_user_id, deleted_at = rows[0]
        if deleted_at is not None:
            return
        if str(author_user_id) != actor_user_id:
            raise AppError(
                code="FORBIDDEN_NOT_AUTHOR",
                message="You are only permitted to delete your own comments.",
                status_code=403,
            )

        now_str = _now_iso()
        # Preserve row for child reply tree continuity while scrubbing author & body
        await self.session.execute(
            """
            UPDATE comments
            SET body = '[deleted by author]',
                author_user_id = NULL,
                professional_snapshot = NULL,
                identity_mode = 'anonymous',
                anonymous_thread_label = '[deleted]',
                deleted_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (now_str, now_str, comment_id),
        )
        await self.session.execute(
            "UPDATE posts SET comment_count = CASE WHEN comment_count > 0 THEN comment_count - 1 ELSE 0 END WHERE id = ?",
            (str(post_id),),
        )
