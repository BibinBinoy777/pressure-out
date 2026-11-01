"""Service layer for Latest, Popular, Following, Explore feeds, Topic Preferences, and Search."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from app.core.errors import AppError
from app.core.unicode import normalize_unicode_nfc
from app.modules.communities.service import CommunityService
from app.modules.feed.ranking import compute_hot_rank_score
from app.modules.feed.schemas import (
    ExploreDiscoveryResponse,
    TopicPreferenceResponse,
    TrendingTagItem,
    VALID_TOPIC_PREF_TYPES,
    validate_feed_mode,
)
from app.modules.identity.schemas import validate_bcp47_tag
from app.modules.posts.schemas import (
    CursorPostListResponse,
    PublicPostResponse,
    normalize_tag_slug,
    validate_community_slug,
    validate_post_type,
)
from app.modules.posts.service import (
    POST_COLUMNS,
    PostService,
    _row_to_dict,
    decode_cursor,
    encode_cursor,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode_popular_cursor(hot_rank_score: float, created_at: str, post_id: str) -> str:
    payload = json.dumps({"r": round(hot_rank_score, 6), "c": created_at, "i": post_id})
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_popular_cursor(cursor: str) -> Tuple[float, str, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        data = json.loads(raw)
        return float(data["r"]), str(data["c"]), str(data["i"])
    except Exception:
        raise AppError(
            code="INVALID_CURSOR",
            message="Invalid pagination cursor for popular feed.",
            status_code=422,
        )


async def refresh_post_hot_rank(session: Any, post_id: str) -> float:
    """Recalculate and persist `posts.hot_rank_score` from current engagement rows."""
    rows = await session.execute(
        """
        SELECT upvote_count, downvote_count, reaction_counts, comment_count, post_type, created_at
        FROM posts WHERE id = ?
        """,
        (post_id,),
    )
    if not rows:
        return 0.0
    up_c, down_c, raw_reacts, comm_c, ptype, created_at = rows[0]
    try:
        reacts = json.loads(str(raw_reacts)) if isinstance(raw_reacts, str) else dict(raw_reacts)
    except Exception:
        reacts = {}

    score = compute_hot_rank_score(
        upvote_count=int(up_c),
        downvote_count=int(down_c),
        reaction_counts=reacts,
        comment_count=int(comm_c),
        post_type=str(ptype),
        created_at_iso=str(created_at),
    )
    await session.execute(
        "UPDATE posts SET hot_rank_score = ? WHERE id = ?",
        (score, post_id),
    )
    return score


class FeedService:
    """Provides Latest, Popular, Following, Explore feeds, Topic Muting/Following, and Search."""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def set_topic_preference(
        self,
        *,
        user_id: str,
        tag_slug: str,
        preference: str,
    ) -> TopicPreferenceResponse:
        slug = normalize_tag_slug(tag_slug)
        pref = preference.strip().lower()
        if pref not in VALID_TOPIC_PREF_TYPES:
            raise AppError(
                code="VALIDATION_ERROR",
                message="Topic preference must be 'follow', 'mute', or 'none'.",
                status_code=422,
            )

        if pref == "none":
            await self.session.execute(
                "DELETE FROM user_topic_preferences WHERE user_id = ? AND tag_slug = ?",
                (user_id, slug),
            )
        else:
            existing = await self.session.execute(
                "SELECT 1 FROM user_topic_preferences WHERE user_id = ? AND tag_slug = ?",
                (user_id, slug),
            )
            if existing:
                await self.session.execute(
                    """
                    UPDATE user_topic_preferences
                    SET preference_type = ?, created_at = ?
                    WHERE user_id = ? AND tag_slug = ?
                    """,
                    (pref, _now_iso(), user_id, slug),
                )
            else:
                await self.session.execute(
                    """
                    INSERT INTO user_topic_preferences (user_id, tag_slug, preference_type, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, slug, pref, _now_iso()),
                )

        return TopicPreferenceResponse(tag_slug=slug, preference=pref)

    async def get_feed(
        self,
        *,
        mode: str = "latest",
        community_slug: Optional[str] = None,
        post_type: Optional[str] = None,
        tag: Optional[str] = None,
        content_language: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 20,
        viewer_user: Optional[dict[str, Any]] = None,
    ) -> CursorPostListResponse:
        feed_mode = validate_feed_mode(mode)
        viewer_id = str(viewer_user["id"]) if viewer_user else None
        safe_limit = max(1, min(limit, 50))

        clauses = ["p.moderation_status = 'published'", "p.deleted_at IS NULL"]
        params: List[Any] = []

        if community_slug:
            clauses.append("p.community_slug = ?")
            params.append(validate_community_slug(community_slug))
        if post_type:
            clauses.append("p.post_type = ?")
            params.append(validate_post_type(post_type))
        if content_language:
            clauses.append("p.content_language = ?")
            params.append(validate_bcp47_tag(content_language))
        if tag:
            norm_tag = normalize_tag_slug(tag)
            clauses.append(
                "EXISTS (SELECT 1 FROM post_tags pt JOIN tags t ON t.id = pt.tag_id WHERE pt.post_id = p.id AND t.slug = ?)"
            )
            params.append(norm_tag)

        # Exclude posts tagged with any muted topic OR authored by blocked/muted accounts
        if viewer_id:
            clauses.append(
                """
                NOT EXISTS (
                    SELECT 1 FROM post_tags pt_mute
                    JOIN tags t_mute ON t_mute.id = pt_mute.tag_id
                    JOIN user_topic_preferences utp ON utp.tag_slug = t_mute.slug
                    WHERE pt_mute.post_id = p.id
                      AND utp.user_id = ?
                      AND utp.preference_type = 'mute'
                )
                AND (
                    p.author_user_id IS NULL
                    OR NOT EXISTS (
                        SELECT 1 FROM user_blocks ub
                        WHERE (ub.blocker_user_id = ? AND ub.blocked_user_id = p.author_user_id)
                           OR (ub.blocker_user_id = p.author_user_id AND ub.blocked_user_id = ? AND ub.block_mode = 'block')
                    )
                )
                """
            )
            params.extend([viewer_id, viewer_id, viewer_id])

        if feed_mode == "following":
            if not viewer_id:
                raise AppError(
                    code="UNAUTHORIZED",
                    message="Sign in to view your personalized Following feed.",
                    status_code=401,
                )
            clauses.append(
                """
                (
                    EXISTS (
                        SELECT 1 FROM community_memberships cm
                        JOIN communities c ON c.id = cm.community_id
                        WHERE cm.user_id = ? AND cm.status = 'active' AND c.slug = p.community_slug
                    )
                    OR EXISTS (
                        SELECT 1 FROM post_tags pt_fol
                        JOIN tags t_fol ON t_fol.id = pt_fol.tag_id
                        JOIN user_topic_preferences utp_fol ON utp_fol.tag_slug = t_fol.slug
                        WHERE pt_fol.post_id = p.id
                          AND utp_fol.user_id = ?
                          AND utp_fol.preference_type = 'follow'
                    )
                )
                """
            )
            params.extend([viewer_id, viewer_id])

        if feed_mode == "popular":
            if cursor:
                c_rank, c_time, c_id = decode_popular_cursor(cursor)
                clauses.append(
                    "(p.hot_rank_score < ? OR (p.hot_rank_score = ? AND p.created_at < ?) OR (p.hot_rank_score = ? AND p.created_at = ? AND p.id < ?))"
                )
                params.extend([c_rank, c_rank, c_time, c_rank, c_time, c_id])
            order_sql = "p.hot_rank_score DESC, p.created_at DESC, p.id DESC"
        else:
            if cursor:
                c_time, c_id = decode_cursor(cursor)
                clauses.append("(p.created_at < ? OR (p.created_at = ? AND p.id < ?))")
                params.extend([c_time, c_time, c_id])
            order_sql = "p.created_at DESC, p.id DESC"

        where_sql = " AND ".join(clauses)
        col_list = ", ".join(f"p.{c}" for c in POST_COLUMNS)
        rows = await self.session.execute(
            f"""
            SELECT {col_list}
            FROM posts p
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT ?
            """,
            tuple(params + [safe_limit + 1]),
        )

        has_more = len(rows) > safe_limit
        sliced = rows[:safe_limit]

        post_service = PostService(self.session)
        items: List[PublicPostResponse] = []
        last_rank = 0.0
        for r in sliced:
            post_dict = _row_to_dict(POST_COLUMNS, r)
            last_rank = float(post_dict.get("hot_rank_score", 0.0))
            items.append(
                await post_service._build_public_post_response(
                    post_dict, viewer_user_id=viewer_id
                )
            )

        next_cur: Optional[str] = None
        if has_more and items:
            last = items[-1]
            if feed_mode == "popular":
                next_cur = encode_popular_cursor(last_rank, last.created_at, last.id)
            else:
                next_cur = encode_cursor(last.created_at, last.id)

        return CursorPostListResponse(
            items=items,
            next_cursor=next_cur,
            has_more=has_more,
        )

    async def get_explore_discovery(
        self,
        *,
        lang: Optional[str] = None,
        viewer_user: Optional[dict[str, Any]] = None,
    ) -> ExploreDiscoveryResponse:
        viewer_id = str(viewer_user["id"]) if viewer_user else None

        # 1. Trending tags + viewer preference
        tag_rows = await self.session.execute(
            "SELECT slug, display_name, usage_count FROM tags WHERE usage_count > 0 ORDER BY usage_count DESC, slug ASC LIMIT 15"
        )
        prefs_map: dict[str, str] = {}
        if viewer_id:
            pref_rows = await self.session.execute(
                "SELECT tag_slug, preference_type FROM user_topic_preferences WHERE user_id = ?",
                (viewer_id,),
            )
            prefs_map = {str(r[0]): str(r[1]) for r in pref_rows}

        trending_tags = [
            TrendingTagItem(
                slug=str(r[0]),
                display_name=str(r[1]),
                usage_count=int(r[2]),
                viewer_preference=prefs_map.get(str(r[0])),
            )
            for r in tag_rows
        ]

        # 2. Featured communities
        comm_service = CommunityService(self.session)
        all_comms = await comm_service.list_communities(
            lang=lang, viewer_user=viewer_user
        )
        featured_communities = all_comms[:8]

        # 3. "New Communities / Fresh Posts" discovery path (Section 13 requirement)
        # Samples recent published posts from communities with <= 5 posts so early communities avoid empty feeds
        col_list = ", ".join(f"p.{c}" for c in POST_COLUMNS)
        fresh_clauses = [
            "p.moderation_status = 'published'",
            "p.deleted_at IS NULL",
            "EXISTS (SELECT 1 FROM communities c WHERE c.slug = p.community_slug AND c.post_count <= 5 AND c.status = 'active')",
        ]
        fresh_params: List[Any] = []
        if lang:
            fresh_clauses.append("p.content_language = ?")
            fresh_params.append(validate_bcp47_tag(lang))
        if viewer_id:
            fresh_clauses.append(
                """
                NOT EXISTS (
                    SELECT 1 FROM post_tags pt_m
                    JOIN tags t_m ON t_m.id = pt_m.tag_id
                    JOIN user_topic_preferences utp_m ON utp_m.tag_slug = t_m.slug
                    WHERE pt_m.post_id = p.id AND utp_m.user_id = ? AND utp_m.preference_type = 'mute'
                )
                """
            )
            fresh_params.append(viewer_id)

        fresh_rows = await self.session.execute(
            f"""
            SELECT {col_list}
            FROM posts p
            WHERE {' AND '.join(fresh_clauses)}
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT 6
            """,
            tuple(fresh_params),
        )
        post_service = PostService(self.session)
        fresh_posts = [
            await post_service._build_public_post_response(
                _row_to_dict(POST_COLUMNS, r), viewer_user_id=viewer_id
            )
            for r in fresh_rows
        ]

        # 4. Popular posts sample
        pop_feed = await self.get_feed(
            mode="popular",
            content_language=lang,
            limit=10,
            viewer_user=viewer_user,
        )

        return ExploreDiscoveryResponse(
            trending_tags=trending_tags,
            featured_communities=featured_communities,
            fresh_community_posts=fresh_posts,
            popular_posts=pop_feed.items,
        )

    async def search_public_posts(
        self,
        *,
        q: str,
        community_slug: Optional[str] = None,
        post_type: Optional[str] = None,
        tag: Optional[str] = None,
        content_language: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 20,
        viewer_user: Optional[dict[str, Any]] = None,
    ) -> CursorPostListResponse:
        """Search public, eligible content across title, body, and tags.

        Guarantees (Section 13 & 14):
        - Indexes/queries ONLY `moderation_status = 'published' AND deleted_at IS NULL`.
        - Never searches against private `author_user_id` or `@handle` on anonymous posts.
        - Preserves full Unicode (English, Malayalam, Hindi, Tamil, Emoji, Mixed).
        """
        cleaned_q = normalize_unicode_nfc(q).strip()
        if len(cleaned_q) < 2 or len(cleaned_q) > 120:
            raise AppError(
                code="QUERY_TOO_SHORT",
                message="Search query must be between 2 and 120 characters.",
                status_code=422,
            )

        viewer_id = str(viewer_user["id"]) if viewer_user else None
        safe_limit = max(1, min(limit, 50))

        tokens = [tok.lower() for tok in cleaned_q.split() if tok.strip()][:6]
        clauses = ["p.moderation_status = 'published'", "p.deleted_at IS NULL"]
        params: List[Any] = []

        if viewer_id:
            clauses.append(
                """
                (
                    p.author_user_id IS NULL
                    OR NOT EXISTS (
                        SELECT 1 FROM user_blocks ub
                        WHERE (ub.blocker_user_id = ? AND ub.blocked_user_id = p.author_user_id)
                           OR (ub.blocker_user_id = p.author_user_id AND ub.blocked_user_id = ? AND ub.block_mode = 'block')
                    )
                )
                """
            )
            params.extend([viewer_id, viewer_id])
        for tok in tokens:
            like_pat = f"%{tok}%"
            clauses.append(
                """
                (
                    LOWER(p.title) LIKE ?
                    OR LOWER(p.body) LIKE ?
                    OR EXISTS (
                        SELECT 1 FROM post_tags pt_s
                        JOIN tags t_s ON t_s.id = pt_s.tag_id
                        WHERE pt_s.post_id = p.id AND LOWER(t_s.slug) LIKE ?
                    )
                )
                """
            )
            params.extend([like_pat, like_pat, like_pat])

        if community_slug:
            clauses.append("p.community_slug = ?")
            params.append(validate_community_slug(community_slug))
        if post_type:
            clauses.append("p.post_type = ?")
            params.append(validate_post_type(post_type))
        if content_language:
            clauses.append("p.content_language = ?")
            params.append(validate_bcp47_tag(content_language))
        if tag:
            norm_tag = normalize_tag_slug(tag)
            clauses.append(
                "EXISTS (SELECT 1 FROM post_tags pt_t JOIN tags t_t ON t_t.id = pt_t.tag_id WHERE pt_t.post_id = p.id AND t_t.slug = ?)"
            )
            params.append(norm_tag)

        if cursor:
            c_time, c_id = decode_cursor(cursor)
            clauses.append("(p.created_at < ? OR (p.created_at = ? AND p.id < ?))")
            params.extend([c_time, c_time, c_id])

        where_sql = " AND ".join(clauses)
        col_list = ", ".join(f"p.{c}" for c in POST_COLUMNS)
        rows = await self.session.execute(
            f"""
            SELECT {col_list}
            FROM posts p
            WHERE {where_sql}
            ORDER BY p.hot_rank_score DESC, p.created_at DESC, p.id DESC
            LIMIT ?
            """,
            tuple(params + [safe_limit + 1]),
        )

        has_more = len(rows) > safe_limit
        sliced = rows[:safe_limit]

        post_service = PostService(self.session)
        items: List[PublicPostResponse] = []
        for r in sliced:
            post_dict = _row_to_dict(POST_COLUMNS, r)
            items.append(
                await post_service._build_public_post_response(
                    post_dict, viewer_user_id=viewer_id
                )
            )

        next_cur: Optional[str] = None
        if has_more and items:
            last = items[-1]
            next_cur = encode_cursor(last.created_at, last.id)

        return CursorPostListResponse(
            items=items,
            next_cursor=next_cur,
            has_more=has_more,
        )
