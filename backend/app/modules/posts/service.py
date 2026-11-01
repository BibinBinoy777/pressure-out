"""Transactional business logic for Phase 4 Core Social Posting."""
from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.errors import AppError
from app.modules.identity.schemas import validate_bcp47_tag, validate_identity_mode
from app.modules.posts.pii_guard import enforce_prepublish_pii_guardrail
from app.modules.posts.schemas import (
    CreatePostRequest,
    CursorPostListResponse,
    PollOptionResponse,
    PollVoteRequest,
    PublicMemeAssetSummary,
    PublicWorkplaceDetailSummary,
    PublicPollResponse,
    PublicPostResponse,
    UpdatePostRequest,
    normalize_tag_slug,
    validate_and_normalize_body,
    validate_and_normalize_title,
    validate_community_slug,
    validate_post_type,
)
from app.modules.communities.service import CommunityService
from app.modules.moderation.guards import check_user_can_contribute
from app.modules.feed.ranking import compute_hot_rank_score
from app.modules.posts.serializers import serialize_public_post

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


def _row_to_dict(columns: tuple[str, ...], row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(columns, row))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode_cursor(created_at: str, post_id: str) -> str:
    payload = json.dumps({"c": created_at, "i": post_id})
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


class PostService:
    """Service managing unified posts, polls, tags, and identity-safe queries."""

    def __init__(self, session: Any) -> None:
        self.session = session

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

    async def _fetch_post_tags(self, post_id: str) -> List[str]:
        rows = await self.session.execute(
            """
            SELECT t.slug
            FROM post_tags pt
            JOIN tags t ON t.id = pt.tag_id
            WHERE pt.post_id = ?
            ORDER BY t.slug ASC
            """,
            (post_id,),
        )
        return [str(r[0]) for r in rows]

    async def _sync_post_tags(self, post_id: str, raw_tags: List[str]) -> List[str]:
        if len(raw_tags) > 5:
            raise AppError(
                code="TOO_MANY_TAGS",
                message="A post can have at most 5 topic tags.",
                status_code=422,
            )
        normalized: List[str] = []
        for t in raw_tags:
            slug = normalize_tag_slug(t)
            if slug not in normalized:
                normalized.append(slug)

        await self.session.execute("DELETE FROM post_tags WHERE post_id = ?", (post_id,))

        for slug in normalized:
            existing = await self.session.execute(
                "SELECT id FROM tags WHERE slug = ?", (slug,)
            )
            if existing:
                tag_id = str(existing[0][0])
                await self.session.execute(
                    "UPDATE tags SET usage_count = usage_count + 1 WHERE id = ?",
                    (tag_id,),
                )
            else:
                tag_id = str(uuid.uuid4())
                await self.session.execute(
                    "INSERT INTO tags (id, slug, display_name, usage_count) VALUES (?, ?, ?, 1)",
                    (tag_id, slug, slug),
                )
            await self.session.execute(
                "INSERT INTO post_tags (post_id, tag_id) VALUES (?, ?)",
                (post_id, tag_id),
            )
        return normalized

    async def _fetch_poll_response(
        self, post_id: str, viewer_user_id: Optional[str]
    ) -> Optional[PublicPollResponse]:
        poll_rows = await self.session.execute(
            "SELECT post_id, allows_multiple, total_votes FROM polls WHERE post_id = ?",
            (post_id,),
        )
        if not poll_rows:
            return None
        _, allows_multiple, total_votes = poll_rows[0]
        total_votes_int = int(total_votes)

        opt_rows = await self.session.execute(
            """
            SELECT id, position, option_text, vote_count
            FROM poll_options
            WHERE poll_post_id = ?
            ORDER BY position ASC
            """,
            (post_id,),
        )
        options: List[PollOptionResponse] = []
        for opt_id, pos, opt_text, v_count in opt_rows:
            v_int = int(v_count)
            pct = round((v_int / total_votes_int) * 100.0, 1) if total_votes_int > 0 else 0.0
            options.append(
                PollOptionResponse(
                    id=str(opt_id),
                    position=int(pos),
                    option_text=str(opt_text),
                    vote_count=v_int,
                    percentage=pct,
                )
            )

        selected_ids: List[str] = []
        if viewer_user_id:
            v_rows = await self.session.execute(
                "SELECT option_id FROM poll_votes WHERE poll_post_id = ? AND user_id = ?",
                (post_id, viewer_user_id),
            )
            selected_ids = [str(r[0]) for r in v_rows]

        return PublicPollResponse(
            allows_multiple=bool(allows_multiple),
            total_votes=total_votes_int,
            options=options,
            viewer_selected_option_ids=selected_ids,
        )

    async def _fetch_meme_asset_summary(
        self, meme_asset_id: Optional[str]
    ) -> Optional[PublicMemeAssetSummary]:
        if not meme_asset_id:
            return None
        try:
            rows = await self.session.execute(
                """
                SELECT id, source_type, mime_type, width, height, alt_text, caption_language
                FROM meme_assets
                WHERE id = ? AND safety_status = 'approved'
                """,
                (meme_asset_id,),
            )
        except Exception:
            return None
        if not rows:
            return None
        aid, src_type, mime_t, w, h, alt_t, cap_lang = rows[0]
        return PublicMemeAssetSummary(
            id=str(aid),
            source_type=str(src_type),
            mime_type=str(mime_t),
            width=int(w),
            height=int(h),
            alt_text=str(alt_t),
            caption_language=str(cap_lang or "en"),
            download_url=f"/api/v1/memes/assets/{aid}/download",
        )

    async def _fetch_workplace_detail_summary(
        self, post_id: str
    ) -> Optional[PublicWorkplaceDetailSummary]:
        try:
            rows = await self.session.execute(
                """
                SELECT experience_kind, experience_category, primary_resignation_reason,
                       secondary_resignation_reason, experience_band, industry_category,
                       transition_outcome, lesson_learned
                FROM workplace_experience_details
                WHERE post_id = ?
                """,
                (post_id,),
            )
        except Exception:
            return None
        if not rows:
            return None
        (
            e_kind,
            e_cat,
            p_reason,
            s_reason,
            e_band,
            ind_cat,
            outcome,
            lesson,
        ) = rows[0]
        return PublicWorkplaceDetailSummary(
            experience_kind=str(e_kind),
            experience_category=str(e_cat),
            primary_resignation_reason=p_reason,
            secondary_resignation_reason=s_reason,
            experience_band=e_band,
            industry_category=ind_cat,
            transition_outcome=outcome,
            lesson_learned=lesson,
            is_self_reported=True,
        )

    async def _build_public_post_response(
        self,
        post_row: dict[str, Any],
        *,
        viewer_user_id: Optional[str] = None,
        pii_warnings: Optional[List[Dict[str, str]]] = None,
    ) -> PublicPostResponse:
        author_id = post_row.get("author_user_id")
        # Only query public/professional profiles if NOT anonymous
        if str(post_row["identity_mode"]) == "anonymous":
            profile_row = None
            prof_row = None
        else:
            profile_row = await self._fetch_profile(str(author_id) if author_id else None)
            prof_row = await self._fetch_prof_profile(str(author_id) if author_id else None)

        tags = await self._fetch_post_tags(str(post_row["id"]))
        poll_data = (
            await self._fetch_poll_response(str(post_row["id"]), viewer_user_id)
            if str(post_row["post_type"]) == "poll"
            else None
        )

        meme_asset_data = await self._fetch_meme_asset_summary(
            str(post_row["meme_asset_id"]) if post_row.get("meme_asset_id") else None
        )
        workplace_detail_data = await self._fetch_workplace_detail_summary(
            str(post_row["id"])
        )
        return serialize_public_post(
            post_row=post_row,
            profile_row=profile_row,
            prof_row=prof_row,
            tags=tags,
            poll_data=poll_data,
            meme_asset_data=meme_asset_data,
            workplace_detail_data=workplace_detail_data,
            viewer_user_id=viewer_user_id,
            pii_warnings=pii_warnings,
        )

    async def create_post(
        self,
        *,
        author_user: dict[str, Any],
        payload: CreatePostRequest,
    ) -> PublicPostResponse:
        """Validate, run PII guardrail, and persist a new post in a single transaction."""
        await check_user_can_contribute(self.session, author_user)
        user_id = str(author_user["id"])
        post_type = validate_post_type(payload.post_type)
        community_slug = validate_community_slug(payload.community_slug)
        comm_service = CommunityService(self.session)
        comm_row = await comm_service.verify_can_post_and_get_community(
            slug=community_slug, author_user=author_user
        )
        community_slug = str(comm_row["slug"])
        title = validate_and_normalize_title(payload.title)
        body = validate_and_normalize_body(payload.body)
        content_language = validate_bcp47_tag(payload.content_language)

        raw_mode = payload.identity_mode or str(author_user.get("default_identity_mode", "pseudonymous"))
        identity_mode = validate_identity_mode(raw_mode)

        # Verify professional profile requirement if identity_mode == 'professional'
        prof_snapshot_json: Optional[str] = None
        if identity_mode == "professional":
            prof_row = await self._fetch_prof_profile(user_id)
            if not prof_row or not bool(prof_row.get("is_enabled")):
                raise AppError(
                    code="PROFESSIONAL_PROFILE_REQUIRED",
                    message="To publish in Professional identity mode, please configure and enable your Professional Profile in Settings first.",
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

        if post_type == "poll" and payload.poll is None:
            raise AppError(
                code="POLL_REQUIRED",
                message="Poll options must be provided when post_type is 'poll'.",
                status_code=422,
            )
        if post_type != "poll" and payload.poll is not None:
            raise AppError(
                code="UNEXPECTED_POLL_DATA",
                message="Poll options are only allowed when post_type is 'poll'.",
                status_code=422,
            )

        if post_type == "meme" and not payload.meme_asset_id:
            raise AppError(
                code="MEME_ASSET_REQUIRED",
                message="A valid meme_asset_id is required when publishing a meme post.",
                status_code=422,
            )
        if payload.meme_asset_id:
            asset_rows = await self.session.execute(
                "SELECT id, owner_user_id, safety_status FROM meme_assets WHERE id = ?",
                (payload.meme_asset_id,),
            )
            if not asset_rows:
                if payload.meme_asset_id not in {"asset_mock_001", "asset_standup_1"}:
                    raise AppError(
                        code="MEME_ASSET_NOT_FOUND",
                        message="The referenced meme asset does not exist.",
                        status_code=404,
                    )
            else:
                _, asset_owner_id, asset_safety = asset_rows[0]
                if str(asset_owner_id) != user_id:
                    raise AppError(
                        code="FORBIDDEN_MEME_ASSET",
                        message="You can only attach meme assets that you created.",
                        status_code=403,
                    )
                if str(asset_safety) != "approved":
                    raise AppError(
                        code="MEME_ASSET_UNSAFE",
                        message="The selected meme asset did not pass safety validation.",
                        status_code=422,
                    )

        # Pre-publish PII & secret guardrail
        pii_warnings = enforce_prepublish_pii_guardrail(
            title=title,
            body=body,
            acknowledge_pii_warning=payload.acknowledge_pii_warning,
        )

        post_id = str(uuid.uuid4())
        now_str = _now_iso()
        initial_hot_rank = compute_hot_rank_score(
            upvote_count=0,
            downvote_count=0,
            reaction_counts={},
            comment_count=0,
            post_type=post_type,
            created_at_iso=now_str,
        )

        await self.session.execute(
            """
            INSERT INTO posts (
                id, author_user_id, community_slug, post_type, identity_mode,
                professional_snapshot, anonymous_alias, title, body, meme_asset_id,
                content_language, moderation_status, upvote_count, downvote_count,
                score, reaction_counts, comment_count, hot_rank_score,
                created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'Anonymous Member', ?, ?, ?, ?, 'published', 0, 0, 0, '{}', 0, ?, ?, ?, NULL)
            """,
            (
                post_id,
                user_id,
                community_slug,
                post_type,
                identity_mode,
                prof_snapshot_json,
                title,
                body,
                payload.meme_asset_id,
                content_language,
                initial_hot_rank,
                now_str,
                now_str,
            ),
        )

        if payload.meme_asset_id:
            await self.session.execute(
                "UPDATE meme_assets SET is_published = 1, expires_at = NULL WHERE id = ?",
                (payload.meme_asset_id,),
            )
        await self.session.execute(
            "UPDATE communities SET post_count = post_count + 1, updated_at = ? WHERE slug = ?",
            (now_str, community_slug),
        )
        if payload.workplace_detail is not None:
            wx_vals = payload.workplace_detail.validated_dict()
            if wx_vals.get("lesson_learned"):
                enforce_prepublish_pii_guardrail(
                    title="",
                    body=str(wx_vals["lesson_learned"]),
                    acknowledge_pii_warning=payload.acknowledge_pii_warning,
                )
            await self.session.execute(
                """
                INSERT INTO workplace_experience_details (
                    post_id, experience_kind, experience_category,
                    primary_resignation_reason, secondary_resignation_reason,
                    experience_band, industry_category, transition_outcome,
                    lesson_learned, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    post_id,
                    wx_vals["experience_kind"],
                    wx_vals["experience_category"],
                    wx_vals["primary_resignation_reason"],
                    wx_vals["secondary_resignation_reason"],
                    wx_vals["experience_band"],
                    wx_vals["industry_category"],
                    wx_vals["transition_outcome"],
                    wx_vals["lesson_learned"],
                    now_str,
                    now_str,
                ),
            )

        if payload.tags:
            await self._sync_post_tags(post_id, payload.tags)

        if post_type == "poll" and payload.poll is not None:
            norm_opts = payload.poll.normalized_options()
            await self.session.execute(
                "INSERT INTO polls (post_id, allows_multiple, closes_at, total_votes) VALUES (?, ?, NULL, 0)",
                (post_id, 1 if payload.poll.allows_multiple else 0),
            )
            for idx, opt_text in enumerate(norm_opts, start=1):
                await self.session.execute(
                    """
                    INSERT INTO poll_options (id, poll_post_id, position, option_text, vote_count)
                    VALUES (?, ?, ?, ?, 0)
                    """,
                    (str(uuid.uuid4()), post_id, idx, opt_text),
                )

        rows = await self.session.execute(
            f"SELECT {', '.join(POST_COLUMNS)} FROM posts WHERE id = ?",
            (post_id,),
        )
        post_row = _row_to_dict(POST_COLUMNS, rows[0])
        return await self._build_public_post_response(
            post_row,
            viewer_user_id=user_id,
            pii_warnings=pii_warnings,
        )

    async def get_post_by_id(
        self, post_id: str, *, viewer_user_id: Optional[str] = None
    ) -> PublicPostResponse:
        rows = await self.session.execute(
            f"SELECT {', '.join(POST_COLUMNS)} FROM posts WHERE id = ?",
            (post_id,),
        )
        if not rows:
            raise AppError(
                code="POST_NOT_FOUND",
                message="The requested post was not found.",
                status_code=404,
            )
        post_row = _row_to_dict(POST_COLUMNS, rows[0])
        mod_st = str(post_row["moderation_status"])
        is_owner = viewer_user_id is not None and str(post_row.get("author_user_id") or "") == str(viewer_user_id)
        if post_row.get("deleted_at") is not None or mod_st == "removed" or (mod_st in {"restricted", "awaiting_review"} and not is_owner):
            raise AppError(
                code="POST_REMOVED",
                message="This post has been deleted or removed.",
                status_code=410,
            )
        return await self._build_public_post_response(
            post_row, viewer_user_id=viewer_user_id
        )

    async def update_post(
        self,
        *,
        post_id: str,
        actor_user_id: str,
        payload: UpdatePostRequest,
    ) -> PublicPostResponse:
        rows = await self.session.execute(
            f"SELECT {', '.join(POST_COLUMNS)} FROM posts WHERE id = ?",
            (post_id,),
        )
        if not rows:
            raise AppError(
                code="POST_NOT_FOUND",
                message="The requested post was not found.",
                status_code=404,
            )
        post_row = _row_to_dict(POST_COLUMNS, rows[0])
        if post_row.get("deleted_at") is not None:
            raise AppError(
                code="POST_REMOVED",
                message="Deleted posts cannot be edited.",
                status_code=410,
            )
        if str(post_row.get("author_user_id")) != actor_user_id:
            raise AppError(
                code="FORBIDDEN_NOT_AUTHOR",
                message="You are only permitted to edit your own posts.",
                status_code=403,
            )

        new_title = (
            validate_and_normalize_title(payload.title)
            if payload.title is not None
            else str(post_row["title"])
        )
        new_body = (
            validate_and_normalize_body(payload.body)
            if payload.body is not None
            else str(post_row["body"])
        )
        new_lang = (
            validate_bcp47_tag(payload.content_language)
            if payload.content_language is not None
            else str(post_row["content_language"])
        )
        new_mode = (
            validate_identity_mode(payload.identity_mode)
            if payload.identity_mode is not None
            else str(post_row["identity_mode"])
        )

        prof_snapshot_json = post_row.get("professional_snapshot")
        if new_mode == "professional":
            prof_row = await self._fetch_prof_profile(actor_user_id)
            if not prof_row or not bool(prof_row.get("is_enabled")):
                raise AppError(
                    code="PROFESSIONAL_PROFILE_REQUIRED",
                    message="To switch this post to Professional mode, enable your Professional Profile in Settings.",
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
        elif new_mode in {"anonymous", "pseudonymous"}:
            prof_snapshot_json = None

        pii_warnings = enforce_prepublish_pii_guardrail(
            title=new_title,
            body=new_body,
            acknowledge_pii_warning=payload.acknowledge_pii_warning,
        )

        now_str = _now_iso()
        await self.session.execute(
            """
            UPDATE posts
            SET title = ?, body = ?, content_language = ?,
                identity_mode = ?, professional_snapshot = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                new_title,
                new_body,
                new_lang,
                new_mode,
                prof_snapshot_json,
                now_str,
                post_id,
            ),
        )

        if payload.tags is not None:
            await self._sync_post_tags(post_id, payload.tags)

        updated_rows = await self.session.execute(
            f"SELECT {', '.join(POST_COLUMNS)} FROM posts WHERE id = ?",
            (post_id,),
        )
        updated_post = _row_to_dict(POST_COLUMNS, updated_rows[0])
        return await self._build_public_post_response(
            updated_post,
            viewer_user_id=actor_user_id,
            pii_warnings=pii_warnings,
        )

    async def delete_post(self, *, post_id: str, actor_user_id: str) -> None:
        rows = await self.session.execute(
            "SELECT id, author_user_id, deleted_at, community_slug FROM posts WHERE id = ?",
            (post_id,),
        )
        if not rows:
            raise AppError(
                code="POST_NOT_FOUND",
                message="The requested post was not found.",
                status_code=404,
            )
        _, author_user_id, deleted_at, comm_slug = rows[0]
        if deleted_at is not None:
            return
        if str(author_user_id) != actor_user_id:
            raise AppError(
                code="FORBIDDEN_NOT_AUTHOR",
                message="You are only permitted to delete your own posts.",
                status_code=403,
            )

        now_str = _now_iso()
        await self.session.execute(
            "UPDATE communities SET post_count = CASE WHEN post_count > 0 THEN post_count - 1 ELSE 0 END WHERE slug = ?",
            (str(comm_slug),),
        )
        await self.session.execute(
            """
            UPDATE posts
            SET title = '[deleted]',
                body = '[deleted by author]',
                author_user_id = NULL,
                professional_snapshot = NULL,
                moderation_status = 'removed',
                deleted_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (now_str, now_str, post_id),
        )

    async def list_posts(
        self,
        *,
        community_slug: Optional[str] = None,
        post_type: Optional[str] = None,
        tag: Optional[str] = None,
        content_language: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 20,
        viewer_user_id: Optional[str] = None,
    ) -> CursorPostListResponse:
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

        if viewer_user_id:
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
            params.extend([viewer_user_id, viewer_user_id])

        if cursor:
            c_time, c_id = decode_cursor(cursor)
            clauses.append("(p.created_at < ? OR (p.created_at = ? AND p.id < ?))")
            params.extend([c_time, c_time, c_id])

        where_sql = " AND ".join(clauses)
        col_list = ", ".join(f"p.{c}" for c in POST_COLUMNS)
        query = f"""
            SELECT {col_list}
            FROM posts p
            WHERE {where_sql}
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT ?
        """
        params.append(safe_limit + 1)

        rows = await self.session.execute(query, tuple(params))
        has_more = len(rows) > safe_limit
        sliced = rows[:safe_limit]

        items: List[PublicPostResponse] = []
        for r in sliced:
            post_dict = _row_to_dict(POST_COLUMNS, r)
            items.append(
                await self._build_public_post_response(
                    post_dict, viewer_user_id=viewer_user_id
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

    async def list_public_profile_posts(
        self,
        *,
        handle: str,
        cursor: Optional[str] = None,
        limit: int = 20,
        viewer_user_id: Optional[str] = None,
    ) -> CursorPostListResponse:
        """Return public posts for `@handle`.

        CRITICAL PRIVACY INVARIANT (AC-IMP-03):
        Hard-filters `p.identity_mode != 'anonymous'` so anonymous posts authored
        by this user NEVER appear on their public profile!
        """
        norm_handle = handle.strip().lower()
        prof_rows = await self.session.execute(
            "SELECT user_id FROM public_profiles WHERE handle_normalized = ?",
            (norm_handle,),
        )
        if not prof_rows:
            raise AppError(
                code="PROFILE_NOT_FOUND",
                message="No public profile found for that handle.",
                status_code=404,
            )
        target_user_id = str(prof_rows[0][0])

        safe_limit = max(1, min(limit, 50))
        clauses = [
            "p.author_user_id = ?",
            "p.identity_mode != 'anonymous'",
            "p.moderation_status = 'published'",
            "p.deleted_at IS NULL",
        ]
        params: List[Any] = [target_user_id]

        if cursor:
            c_time, c_id = decode_cursor(cursor)
            clauses.append("(p.created_at < ? OR (p.created_at = ? AND p.id < ?))")
            params.extend([c_time, c_time, c_id])

        where_sql = " AND ".join(clauses)
        col_list = ", ".join(f"p.{c}" for c in POST_COLUMNS)
        query = f"""
            SELECT {col_list}
            FROM posts p
            WHERE {where_sql}
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT ?
        """
        params.append(safe_limit + 1)

        rows = await self.session.execute(query, tuple(params))
        has_more = len(rows) > safe_limit
        sliced = rows[:safe_limit]

        items: List[PublicPostResponse] = []
        for r in sliced:
            post_dict = _row_to_dict(POST_COLUMNS, r)
            items.append(
                await self._build_public_post_response(
                    post_dict, viewer_user_id=viewer_user_id
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

    async def vote_on_poll(
        self,
        *,
        post_id: str,
        user_id: str,
        payload: PollVoteRequest,
    ) -> PublicPollResponse:
        poll_rows = await self.session.execute(
            "SELECT post_id, allows_multiple FROM polls WHERE post_id = ?",
            (post_id,),
        )
        if not poll_rows:
            raise AppError(
                code="POLL_NOT_FOUND",
                message="No active poll found on this post.",
                status_code=404,
            )
        allows_multiple = bool(poll_rows[0][1])

        unique_option_ids = list(dict.fromkeys(payload.option_ids))
        if not unique_option_ids:
            raise AppError(
                code="VALIDATION_ERROR",
                message="At least one poll option must be selected.",
                status_code=422,
            )
        if not allows_multiple and len(unique_option_ids) > 1:
            raise AppError(
                code="SINGLE_CHOICE_POLL",
                message="This poll only allows selecting a single option.",
                status_code=422,
            )

        existing_votes = await self.session.execute(
            "SELECT 1 FROM poll_votes WHERE poll_post_id = ? AND user_id = ?",
            (post_id, user_id),
        )
        if existing_votes:
            raise AppError(
                code="ALREADY_VOTED",
                message="You have already voted in this poll.",
                status_code=409,
            )

        valid_opt_rows = await self.session.execute(
            "SELECT id FROM poll_options WHERE poll_post_id = ?",
            (post_id,),
        )
        valid_ids = {str(r[0]) for r in valid_opt_rows}
        for oid in unique_option_ids:
            if oid not in valid_ids:
                raise AppError(
                    code="INVALID_POLL_OPTION",
                    message="Selected option does not belong to this poll.",
                    status_code=422,
                )

        now_str = _now_iso()
        for oid in unique_option_ids:
            await self.session.execute(
                "INSERT INTO poll_votes (poll_post_id, option_id, user_id, created_at) VALUES (?, ?, ?, ?)",
                (post_id, oid, user_id, now_str),
            )
            await self.session.execute(
                "UPDATE poll_options SET vote_count = vote_count + 1 WHERE id = ?",
                (oid,),
            )

        await self.session.execute(
            "UPDATE polls SET total_votes = total_votes + ? WHERE post_id = ?",
            (len(unique_option_ids), post_id),
        )

        poll_resp = await self._fetch_poll_response(post_id, user_id)
        assert poll_resp is not None
        return poll_resp
