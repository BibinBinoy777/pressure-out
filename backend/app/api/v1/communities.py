"""REST API endpoints for Phase 5 Communities (`/api/v1/communities`)."""
from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_community_service,
    get_optional_authenticated_context,
    get_post_service,
    require_authenticated_context,
)
from app.modules.communities.schemas import (
    CommunityDetailResponse,
    CommunityMemberModerationRequest,
    CommunitySummaryResponse,
    CreateCommunityRequest,
    MembershipActionRequest,
    MembershipActionResponse,
    UpdateCommunityStatusRequest,
)
from app.modules.communities.service import CommunityService
from app.modules.posts.schemas import CursorPostListResponse
from app.modules.posts.service import PostService

router = APIRouter(prefix="/communities", tags=["communities"])


@router.get(
    "",
    response_model=List[CommunitySummaryResponse],
    summary="Explore and search workplace communities",
)
async def list_communities(
    q: Optional[str] = Query(None, description="Search community name, slug, or description"),
    lang: Optional[str] = Query(None, description="Filter by primary BCP 47 language"),
    joined_only: bool = Query(False, description="Only return communities joined by the viewer"),
    opt_auth: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    service: CommunityService = Depends(get_community_service),
) -> List[CommunitySummaryResponse]:
    viewer_user = opt_auth["user"] if opt_auth else None
    return await service.list_communities(
        q=q,
        lang=lang,
        joined_only=joined_only,
        viewer_user=viewer_user,
    )


@router.post(
    "",
    response_model=CommunityDetailResponse,
    status_code=201,
    summary="Create a new community (Admin / Global Moderator controlled in MVP)",
)
async def create_community(
    payload: CreateCommunityRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: CommunityService = Depends(get_community_service),
) -> CommunityDetailResponse:
    return await service.create_community(
        actor_user=auth_ctx["user"],
        payload=payload,
    )


@router.get(
    "/{slug}",
    response_model=CommunityDetailResponse,
    summary="Retrieve a community's metadata, rules, and viewer membership context",
)
async def get_community(
    slug: str,
    opt_auth: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    service: CommunityService = Depends(get_community_service),
) -> CommunityDetailResponse:
    viewer_user = opt_auth["user"] if opt_auth else None
    return await service.get_community_detail(slug, viewer_user=viewer_user)


@router.post(
    "/{slug}/membership",
    response_model=MembershipActionResponse,
    summary="Join or leave a community",
)
async def update_membership(
    slug: str,
    payload: MembershipActionRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: CommunityService = Depends(get_community_service),
) -> MembershipActionResponse:
    return await service.update_membership(
        slug=slug,
        user_id=str(auth_ctx["user"]["id"]),
        action=payload.action,
    )


@router.get(
    "/{slug}/posts",
    response_model=CursorPostListResponse,
    summary="Retrieve cursor-paginated feed for a specific community",
)
async def get_community_feed(
    slug: str,
    post_type: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    lang: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    opt_auth: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    comm_service: CommunityService = Depends(get_community_service),
    post_service: PostService = Depends(get_post_service),
) -> CursorPostListResponse:
    # Verify community exists first (raises 404 COMMUNITY_NOT_FOUND if unknown)
    viewer_user = opt_auth["user"] if opt_auth else None
    comm = await comm_service.get_community_detail(slug, viewer_user=viewer_user)
    viewer_id = str(viewer_user["id"]) if viewer_user else None

    return await post_service.list_posts(
        community_slug=comm.slug,
        post_type=post_type,
        tag=tag,
        content_language=lang,
        cursor=cursor,
        limit=limit,
        viewer_user_id=viewer_id,
    )


@router.patch(
    "/{slug}/status",
    response_model=CommunityDetailResponse,
    summary="Update community status or description (Community Moderator / Admin only)",
)
async def update_community_status(
    slug: str,
    payload: UpdateCommunityStatusRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: CommunityService = Depends(get_community_service),
) -> CommunityDetailResponse:
    return await service.update_community_status(
        slug=slug,
        actor_user=auth_ctx["user"],
        payload=payload,
    )


@router.patch(
    "/{slug}/members/{handle}",
    summary="Ban/unban a community member or grant community moderator role",
)
async def moderate_member(
    slug: str,
    handle: str,
    payload: CommunityMemberModerationRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: CommunityService = Depends(get_community_service),
) -> dict[str, str]:
    return await service.moderate_community_member(
        slug=slug,
        target_handle=handle,
        actor_user=auth_ctx["user"],
        payload=payload,
    )
