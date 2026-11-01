"""Transactional service for idempotent voting, workplace reactions, and saved bookmarks."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.errors import AppError
from app.modules.engagement.schemas import (
    ReactionResultResponse,
    SavePostResponse,
    VoteResultResponse,
    validate_reaction_kind,
)
from app.modules.posts.schemas import CursorPostListResponse, PublicPostResponse
from app.modules.feed.service import refresh_post_hot_rank
from app.modules.moderation.guards import is_interaction_blocked
from app.modules.posts.service import POST_COLUMNS, PostService, _row_to_dict, decode_cursor, encode_cursor


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EngagementService:
    """Enforces one active vote per user per target and atomic derived counter updates."""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def _verify_target_exists(
        self, target_type: str, target_id: str, actor_user_id: Optional[str] = None
    ) -> None:
        table = "posts" if target_type == "post" else "comments"
        rows = await self.session.execute(
            f"SELECT id, author_user_id, deleted_at, moderation_status FROM {table} WHERE id = ?",
            (target_id,),
        )
        if not rows:
            raise AppError(
                code=f"{target_type.upper()}_NOT_FOUND",
                message=f"The target {target_type} was not found.",
                status_code=404,
            )
        _, author_id, deleted_at, mod_status = rows[0]
        if deleted_at is not None or str(mod_status) in {"removed", "restricted", "awaiting_review"}:
            raise AppError(
                code=f"{target_type.upper()}_REMOVED",
                message=f"Cannot interact with a removed or restricted {target_type}.",
                status_code=410,
            )
        if actor_user_id and await is_interaction_blocked(
            self.session, actor_user_id, str(author_id) if author_id else None
        ):
            raise AppError(
                code="INTERACTION_BLOCKED",
                message="You cannot interact with this content due to an active account block.",
                status_code=403,
            )

    async def set_vote(
        self,
        *,
        user_id: str,
        target_type: str,
        target_id: str,
        value: int,
    ) -> VoteResultResponse:
        if target_type not in {"post", "comment"}:
            raise AppError(
                code="VALIDATION_ERROR",
                message="Invalid vote target type.",
                status_code=422,
            )
        if value not in {-1, 0, 1}:
            raise AppError(
                code="INVALID_VOTE_VALUE",
                message="Vote value must be +1, -1, or 0.",
                status_code=422,
            )

        await self._verify_target_exists(target_type, target_id, user_id)
        now_str = _now_iso()

        if value == 0:
            await self.session.execute(
                "DELETE FROM votes WHERE user_id = ? AND target_type = ? AND target_id = ?",
                (user_id, target_type, target_id),
            )
        else:
            existing = await self.session.execute(
                "SELECT id FROM votes WHERE user_id = ? AND target_type = ? AND target_id = ?",
                (user_id, target_type, target_id),
            )
            if existing:
                await self.session.execute(
                    "UPDATE votes SET value = ?, updated_at = ? WHERE id = ?",
                    (value, now_str, str(existing[0][0])),
                )
            else:
                await self.session.execute(
                    """
                    INSERT INTO votes (id, user_id, target_type, target_id, value, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), user_id, target_type, target_id, value, now_str, now_str),
                )

        # Recalculate derived counts from underlying vote rows (Section 11 & 13 guardrail)
        up_rows = await self.session.execute(
            "SELECT COUNT(*) FROM votes WHERE target_type = ? AND target_id = ? AND value = 1",
            (target_type, target_id),
        )
        down_rows = await self.session.execute(
            "SELECT COUNT(*) FROM votes WHERE target_type = ? AND target_id = ? AND value = -1",
            (target_type, target_id),
        )
        up_count = int(up_rows[0][0]) if up_rows else 0
        down_count = int(down_rows[0][0]) if down_rows else 0
        score = up_count - down_count

        table = "posts" if target_type == "post" else "comments"
        await self.session.execute(
            f"UPDATE {table} SET upvote_count = ?, downvote_count = ?, score = ? WHERE id = ?",
            (up_count, down_count, score, target_id),
        )
        if target_type == "post":
            await refresh_post_hot_rank(self.session, target_id)

        return VoteResultResponse(
            target_type=target_type,
            target_id=target_id,
            score=score,
            upvote_count=up_count,
            downvote_count=down_count,
            viewer_vote=value,
        )

    async def set_reaction(
        self,
        *,
        user_id: str,
        target_type: str,
        target_id: str,
        reaction_kind: str,
        active: bool,
    ) -> ReactionResultResponse:
        if target_type not in {"post", "comment"}:
            raise AppError(
                code="VALIDATION_ERROR",
                message="Invalid reaction target type.",
                status_code=422,
            )
        kind = validate_reaction_kind(reaction_kind)
        await self._verify_target_exists(target_type, target_id, user_id)

        if active:
            existing = await self.session.execute(
                """
                SELECT 1 FROM reactions
                WHERE user_id = ? AND target_type = ? AND target_id = ? AND reaction_kind = ?
                """,
                (user_id, target_type, target_id, kind),
            )
            if not existing:
                await self.session.execute(
                    """
                    INSERT INTO reactions (id, user_id, target_type, target_id, reaction_kind, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), user_id, target_type, target_id, kind, _now_iso()),
                )
        else:
            await self.session.execute(
                """
                DELETE FROM reactions
                WHERE user_id = ? AND target_type = ? AND target_id = ? AND reaction_kind = ?
                """,
                (user_id, target_type, target_id, kind),
            )

        count_rows = await self.session.execute(
            """
            SELECT reaction_kind, COUNT(*)
            FROM reactions
            WHERE target_type = ? AND target_id = ?
            GROUP BY reaction_kind
            """,
            (target_type, target_id),
        )
        counts: Dict[str, int] = {str(r[0]): int(r[1]) for r in count_rows}

        table = "posts" if target_type == "post" else "comments"
        await self.session.execute(
            f"UPDATE {table} SET reaction_counts = ? WHERE id = ?",
            (json.dumps(counts), target_id),
        )
        if target_type == "post":
            await refresh_post_hot_rank(self.session, target_id)

        viewer_rows = await self.session.execute(
            """
            SELECT reaction_kind FROM reactions
            WHERE user_id = ? AND target_type = ? AND target_id = ?
            ORDER BY reaction_kind ASC
            """,
            (user_id, target_type, target_id),
        )
        viewer_reactions = [str(r[0]) for r in viewer_rows]

        return ReactionResultResponse(
            target_type=target_type,
            target_id=target_id,
            reaction_counts=counts,
            viewer_reactions=viewer_reactions,
        )

    async def set_saved_post(
        self,
        *,
        user_id: str,
        post_id: str,
        saved: bool,
    ) -> SavePostResponse:
        await self._verify_target_exists("post", post_id, user_id)
        if saved:
            existing = await self.session.execute(
                "SELECT 1 FROM saved_posts WHERE user_id = ? AND post_id = ?",
                (user_id, post_id),
            )
            if not existing:
                await self.session.execute(
                    "INSERT INTO saved_posts (user_id, post_id, created_at) VALUES (?, ?, ?)",
                    (user_id, post_id, _now_iso()),
                )
        else:
            await self.session.execute(
                "DELETE FROM saved_posts WHERE user_id = ? AND post_id = ?",
                (user_id, post_id),
            )
        return SavePostResponse(post_id=post_id, saved=saved)

    async def list_saved_posts(
        self,
        *,
        user_id: str,
        cursor: Optional[str] = None,
        limit: int = 20,
    ) -> CursorPostListResponse:
        safe_limit = max(1, min(limit, 50))
        clauses = ["sp.user_id = ?", "p.moderation_status = 'published'", "p.deleted_at IS NULL"]
        params: List[Any] = [user_id]

        if cursor:
            c_time, c_id = decode_cursor(cursor)
            clauses.append("(sp.created_at < ? OR (sp.created_at = ? AND sp.post_id < ?))")
            params.extend([c_time, c_time, c_id])

        where_sql = " AND ".join(clauses)
        col_list = ", ".join(f"p.{c}" for c in POST_COLUMNS)
        rows = await self.session.execute(
            f"""
            SELECT {col_list}, sp.created_at AS saved_at
            FROM saved_posts sp
            JOIN posts p ON p.id = sp.post_id
            WHERE {where_sql}
            ORDER BY sp.created_at DESC, sp.post_id DESC
            LIMIT ?
            """,
            tuple(params + [safe_limit + 1]),
        )

        has_more = len(rows) > safe_limit
        sliced = rows[:safe_limit]

        post_service = PostService(self.session)
        items: List[PublicPostResponse] = []
        last_saved_at: Optional[str] = None
        last_post_id: Optional[str] = None

        for r in sliced:
            post_dict = _row_to_dict(POST_COLUMNS, r[:-1])
            last_saved_at = str(r[-1])
            last_post_id = str(post_dict["id"])
            resp = await post_service._build_public_post_response(
                post_dict, viewer_user_id=user_id
            )
            items.append(resp)

        next_cur: Optional[str] = None
        if has_more and last_saved_at and last_post_id:
            next_cur = encode_cursor(last_saved_at, last_post_id)

        return CursorPostListResponse(
            items=items,
            next_cursor=next_cur,
            has_more=has_more,
        )
