"""Transactional business logic for Phase 5 Communities, Memberships, and Community Moderation."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from app.core.errors import AppError
from app.core.unicode import normalize_unicode_nfc
from app.modules.communities.schemas import (
    CommunityDetailResponse,
    CommunityMemberModerationRequest,
    CommunityRuleResponse,
    CommunitySummaryResponse,
    CommunityViewerContext,
    CreateCommunityRequest,
    MembershipActionResponse,
    UpdateCommunityStatusRequest,
    VALID_COMMUNITY_STATUSES,
    VALID_MEMBERSHIP_ACTIONS,
    VALID_MEMBERSHIP_ROLES,
    VALID_MEMBERSHIP_STATUSES,
)
from app.modules.identity.schemas import validate_bcp47_tag

COMMUNITY_COLUMNS = (
    "id",
    "slug",
    "name",
    "description",
    "icon_name",
    "primary_language",
    "status",
    "member_count",
    "post_count",
    "created_by_user_id",
    "created_at",
    "updated_at",
)


def _row_to_dict(columns: tuple[str, ...], row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(columns, row))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CommunityService:
    """Manages community directory, rules, memberships, and community-level moderation."""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def _fetch_community_by_slug(self, slug: str) -> Optional[dict[str, Any]]:
        cleaned = slug.strip().lower()
        rows = await self.session.execute(
            f"SELECT {', '.join(COMMUNITY_COLUMNS)} FROM communities WHERE slug = ?",
            (cleaned,),
        )
        return _row_to_dict(COMMUNITY_COLUMNS, rows[0]) if rows else None

    async def _fetch_membership(
        self, community_id: str, user_id: Optional[str]
    ) -> Optional[dict[str, Any]]:
        if not user_id:
            return None
        rows = await self.session.execute(
            """
            SELECT user_id, community_id, role, status, joined_at
            FROM community_memberships
            WHERE community_id = ? AND user_id = ?
            """,
            (community_id, user_id),
        )
        if not rows:
            return None
        u_id, c_id, role, status, joined_at = rows[0]
        return {
            "user_id": str(u_id),
            "community_id": str(c_id),
            "role": str(role),
            "status": str(status),
            "joined_at": str(joined_at),
        }

    async def _build_viewer_context(
        self,
        comm_row: dict[str, Any],
        viewer_user: Optional[dict[str, Any]],
    ) -> CommunityViewerContext:
        if not viewer_user:
            return CommunityViewerContext(
                is_member=False,
                role=None,
                is_banned=False,
                can_post=(str(comm_row["status"]) == "active"),
                can_moderate=False,
            )

        user_id = str(viewer_user["id"])
        global_role = str(viewer_user.get("role", "member"))
        membership = await self._fetch_membership(str(comm_row["id"]), user_id)

        is_banned = bool(membership and membership["status"] == "banned")
        is_active_member = bool(membership and membership["status"] == "active")
        comm_role = membership["role"] if is_active_member and membership else None

        can_moderate = bool(
            global_role in {"admin", "global_moderator"}
            or (is_active_member and comm_role == "moderator")
        )

        comm_status = str(comm_row["status"])
        if is_banned or comm_status == "archived":
            can_post = False
        elif comm_status == "restricted":
            can_post = can_moderate
        else:
            can_post = True

        return CommunityViewerContext(
            is_member=is_active_member,
            role=comm_role,
            is_banned=is_banned,
            can_post=can_post,
            can_moderate=can_moderate,
        )

    async def _recalculate_member_count(self, community_id: str) -> int:
        rows = await self.session.execute(
            """
            SELECT COUNT(*) FROM community_memberships
            WHERE community_id = ? AND status = 'active'
            """,
            (community_id,),
        )
        count = int(rows[0][0]) if rows else 0
        await self.session.execute(
            "UPDATE communities SET member_count = ?, updated_at = ? WHERE id = ?",
            (count, _now_iso(), community_id),
        )
        return count

    async def list_communities(
        self,
        *,
        q: Optional[str] = None,
        lang: Optional[str] = None,
        joined_only: bool = False,
        viewer_user: Optional[dict[str, Any]] = None,
    ) -> List[CommunitySummaryResponse]:
        clauses = ["c.status IN ('active', 'restricted')"]
        params: List[Any] = []

        if lang:
            clauses.append("c.primary_language = ?")
            params.append(validate_bcp47_tag(lang))

        if q and q.strip():
            like_pat = f"%{q.strip().lower()}%"
            clauses.append(
                "(LOWER(c.name) LIKE ? OR LOWER(c.slug) LIKE ? OR LOWER(c.description) LIKE ?)"
            )
            params.extend([like_pat, like_pat, like_pat])

        if joined_only:
            if not viewer_user:
                return []
            clauses.append(
                "EXISTS (SELECT 1 FROM community_memberships cm WHERE cm.community_id = c.id AND cm.user_id = ? AND cm.status = 'active')"
            )
            params.append(str(viewer_user["id"]))

        where_sql = " AND ".join(clauses)
        col_list = ", ".join(f"c.{col}" for col in COMMUNITY_COLUMNS)
        rows = await self.session.execute(
            f"""
            SELECT {col_list}
            FROM communities c
            WHERE {where_sql}
            ORDER BY c.member_count DESC, c.slug ASC
            """,
            tuple(params),
        )

        results: List[CommunitySummaryResponse] = []
        for r in rows:
            c_dict = _row_to_dict(COMMUNITY_COLUMNS, r)
            v_ctx = await self._build_viewer_context(c_dict, viewer_user)
            results.append(
                CommunitySummaryResponse(
                    id=str(c_dict["id"]),
                    slug=str(c_dict["slug"]),
                    name=str(c_dict["name"]),
                    description=str(c_dict["description"]),
                    icon_name=c_dict.get("icon_name"),
                    primary_language=str(c_dict["primary_language"]),
                    status=str(c_dict["status"]),
                    member_count=int(c_dict["member_count"]),
                    post_count=int(c_dict["post_count"]),
                    viewer_context=v_ctx,
                )
            )
        return results

    async def get_community_detail(
        self,
        slug: str,
        *,
        viewer_user: Optional[dict[str, Any]] = None,
    ) -> CommunityDetailResponse:
        c_dict = await self._fetch_community_by_slug(slug)
        if c_dict is None:
            raise AppError(
                code="COMMUNITY_NOT_FOUND",
                message=f"Community 'c/{slug}' was not found.",
                status_code=404,
            )

        rule_rows = await self.session.execute(
            """
            SELECT rule_number, title, description
            FROM community_rules
            WHERE community_id = ?
            ORDER BY rule_number ASC
            """,
            (str(c_dict["id"]),),
        )
        rules = [
            CommunityRuleResponse(
                rule_number=int(r[0]),
                title=str(r[1]),
                description=str(r[2]),
            )
            for r in rule_rows
        ]
        v_ctx = await self._build_viewer_context(c_dict, viewer_user)

        return CommunityDetailResponse(
            id=str(c_dict["id"]),
            slug=str(c_dict["slug"]),
            name=str(c_dict["name"]),
            description=str(c_dict["description"]),
            icon_name=c_dict.get("icon_name"),
            primary_language=str(c_dict["primary_language"]),
            status=str(c_dict["status"]),
            member_count=int(c_dict["member_count"]),
            post_count=int(c_dict["post_count"]),
            viewer_context=v_ctx,
            rules=rules,
            created_at=str(c_dict["created_at"]),
        )

    async def update_membership(
        self,
        *,
        slug: str,
        user_id: str,
        action: str,
    ) -> MembershipActionResponse:
        cleaned_action = action.strip().lower()
        if cleaned_action not in VALID_MEMBERSHIP_ACTIONS:
            raise AppError(
                code="INVALID_MEMBERSHIP_ACTION",
                message="Membership action must be 'join' or 'leave'.",
                status_code=422,
            )

        c_dict = await self._fetch_community_by_slug(slug)
        if c_dict is None:
            raise AppError(
                code="COMMUNITY_NOT_FOUND",
                message=f"Community 'c/{slug}' was not found.",
                status_code=404,
            )
        comm_id = str(c_dict["id"])

        if str(c_dict["status"]) == "archived" and cleaned_action == "join":
            raise AppError(
                code="COMMUNITY_ARCHIVED",
                message="This community is archived and is not accepting new members.",
                status_code=403,
            )

        existing = await self._fetch_membership(comm_id, user_id)
        if existing and existing["status"] == "banned":
            raise AppError(
                code="COMMUNITY_BANNED",
                message="You are banned from participating in this community.",
                status_code=403,
            )

        if cleaned_action == "join":
            if not existing:
                await self.session.execute(
                    """
                    INSERT INTO community_memberships (user_id, community_id, role, status, joined_at)
                    VALUES (?, ?, 'member', 'active', ?)
                    """,
                    (user_id, comm_id, _now_iso()),
                )
            role_out: Optional[str] = existing["role"] if existing else "member"
            is_mem = True
        else:
            if existing:
                await self.session.execute(
                    "DELETE FROM community_memberships WHERE community_id = ? AND user_id = ?",
                    (comm_id, user_id),
                )
            role_out = None
            is_mem = False

        new_count = await self._recalculate_member_count(comm_id)
        return MembershipActionResponse(
            community_slug=str(c_dict["slug"]),
            is_member=is_mem,
            role=role_out,
            member_count=new_count,
        )

    async def create_community(
        self,
        *,
        actor_user: dict[str, Any],
        payload: CreateCommunityRequest,
    ) -> CommunityDetailResponse:
        """Admin-controlled community creation (Phase 5 MVP policy)."""
        actor_role = str(actor_user.get("role", "member"))
        if actor_role not in {"admin", "global_moderator"}:
            raise AppError(
                code="FORBIDDEN_ROLE",
                message="In the initial release, creating new communities requires administrator or global moderator permissions.",
                status_code=403,
            )

        norm = payload.normalized()
        existing = await self._fetch_community_by_slug(norm.slug)
        if existing is not None:
            raise AppError(
                code="COMMUNITY_SLUG_TAKEN",
                message=f"Community 'c/{norm.slug}' already exists.",
                status_code=409,
            )

        comm_id = str(uuid.uuid4())
        user_id = str(actor_user["id"])
        now_str = _now_iso()

        await self.session.execute(
            """
            INSERT INTO communities (
                id, slug, name, description, icon_name, primary_language,
                status, member_count, post_count, created_by_user_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'active', 1, 0, ?, ?, ?)
            """,
            (
                comm_id,
                norm.slug,
                norm.name,
                norm.description,
                norm.icon_name,
                norm.primary_language,
                user_id,
                now_str,
                now_str,
            ),
        )

        # Creator becomes initial moderator of the community
        await self.session.execute(
            """
            INSERT INTO community_memberships (user_id, community_id, role, status, joined_at)
            VALUES (?, ?, 'moderator', 'active', ?)
            """,
            (user_id, comm_id, now_str),
        )

        for r in norm.rules:
            await self.session.execute(
                """
                INSERT INTO community_rules (id, community_id, rule_number, title, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    comm_id,
                    r.rule_number,
                    normalize_unicode_nfc(r.title).strip(),
                    normalize_unicode_nfc(r.description).strip(),
                ),
            )

        return await self.get_community_detail(norm.slug, viewer_user=actor_user)

    async def update_community_status(
        self,
        *,
        slug: str,
        actor_user: dict[str, Any],
        payload: UpdateCommunityStatusRequest,
    ) -> CommunityDetailResponse:
        c_dict = await self._fetch_community_by_slug(slug)
        if c_dict is None:
            raise AppError(
                code="COMMUNITY_NOT_FOUND",
                message=f"Community 'c/{slug}' was not found.",
                status_code=404,
            )
        v_ctx = await self._build_viewer_context(c_dict, actor_user)
        if not v_ctx.can_moderate:
            raise AppError(
                code="FORBIDDEN_ROLE",
                message="Only community moderators or administrators can update community status.",
                status_code=403,
            )

        new_status = payload.status.strip().lower()
        if new_status not in VALID_COMMUNITY_STATUSES:
            raise AppError(
                code="VALIDATION_ERROR",
                message=f"Community status must be one of: {', '.join(VALID_COMMUNITY_STATUSES)}.",
                status_code=422,
            )

        new_desc = (
            normalize_unicode_nfc(payload.description).strip()
            if payload.description is not None
            else str(c_dict["description"])
        )
        await self.session.execute(
            "UPDATE communities SET status = ?, description = ?, updated_at = ? WHERE id = ?",
            (new_status, new_desc, _now_iso(), str(c_dict["id"])),
        )
        return await self.get_community_detail(slug, viewer_user=actor_user)

    async def moderate_community_member(
        self,
        *,
        slug: str,
        target_handle: str,
        actor_user: dict[str, Any],
        payload: CommunityMemberModerationRequest,
    ) -> dict[str, str]:
        c_dict = await self._fetch_community_by_slug(slug)
        if c_dict is None:
            raise AppError(
                code="COMMUNITY_NOT_FOUND",
                message=f"Community 'c/{slug}' was not found.",
                status_code=404,
            )
        v_ctx = await self._build_viewer_context(c_dict, actor_user)
        if not v_ctx.can_moderate:
            raise AppError(
                code="FORBIDDEN_ROLE",
                message="Moderator permissions required for this community.",
                status_code=403,
            )

        prof_rows = await self.session.execute(
            "SELECT user_id FROM public_profiles WHERE handle_normalized = ?",
            (target_handle.strip().lower(),),
        )
        if not prof_rows:
            raise AppError(
                code="USER_NOT_FOUND",
                message=f"User '@{target_handle}' was not found.",
                status_code=404,
            )
        target_user_id = str(prof_rows[0][0])
        comm_id = str(c_dict["id"])

        existing = await self._fetch_membership(comm_id, target_user_id)
        new_status = (
            payload.status.strip().lower()
            if payload.status
            else (existing["status"] if existing else "active")
        )
        new_role = (
            payload.role.strip().lower()
            if payload.role
            else (existing["role"] if existing else "member")
        )
        if new_status not in VALID_MEMBERSHIP_STATUSES or new_role not in VALID_MEMBERSHIP_ROLES:
            raise AppError(
                code="VALIDATION_ERROR",
                message="Invalid membership status or role.",
                status_code=422,
            )

        if existing:
            await self.session.execute(
                """
                UPDATE community_memberships
                SET status = ?, role = ?
                WHERE community_id = ? AND user_id = ?
                """,
                (new_status, new_role, comm_id, target_user_id),
            )
        else:
            await self.session.execute(
                """
                INSERT INTO community_memberships (user_id, community_id, role, status, joined_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (target_user_id, comm_id, new_role, new_status, _now_iso()),
            )

        await self._recalculate_member_count(comm_id)
        return {
            "community_slug": str(c_dict["slug"]),
            "handle": target_handle,
            "status": new_status,
            "role": new_role,
        }

    async def verify_can_post_and_get_community(
        self,
        *,
        slug: str,
        author_user: dict[str, Any],
    ) -> dict[str, Any]:
        """Enforce that the target community exists, is active, and the user is not banned."""
        c_dict = await self._fetch_community_by_slug(slug)
        if c_dict is None:
            raise AppError(
                code="COMMUNITY_NOT_FOUND",
                message=f"Community 'c/{slug}' does not exist.",
                status_code=404,
            )
        v_ctx = await self._build_viewer_context(c_dict, author_user)
        if v_ctx.is_banned:
            raise AppError(
                code="COMMUNITY_BANNED",
                message=f"You are banned from posting in c/{c_dict['slug']}.",
                status_code=403,
            )
        if not v_ctx.can_post:
            raise AppError(
                code="COMMUNITY_RESTRICTED",
                message=f"Community c/{c_dict['slug']} is currently {c_dict['status']} and not accepting public posts.",
                status_code=403,
            )
        return c_dict
