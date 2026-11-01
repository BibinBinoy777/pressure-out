"""REST API endpoints for Phase 7 Feeds, Explore Discovery, Topic Preferences, and Search."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_feed_service,
    get_optional_authenticated_context,
    require_authenticated_context,
)
from app.modules.feed.schemas import (
    ExploreDiscoveryResponse,
    TopicPreferenceInput,
    TopicPreferenceResponse,
)
from app.modules.feed.service import FeedService
from app.modules.posts.schemas import CursorPostListResponse

router = APIRouter(tags=["feed"])


@router.get(
    "/feed",
    response_model=CursorPostListResponse,
    summary="Retrieve Latest, Popular, Following, or Explore feed with cursor pagination",
)
async def get_feed(
    mode: str = Query("latest", description="latest | popular | following | explore"),
    community_slug: Optional[str] = Query(None),
    post_type: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    lang: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    opt_auth: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    service: FeedService = Depends(get_feed_service),
) -> CursorPostListResponse:
    viewer_user = opt_auth["user"] if opt_auth else None
    return await service.get_feed(
        mode=mode,
        community_slug=community_slug,
        post_type=post_type,
        tag=tag,
        content_language=lang,
        cursor=cursor,
        limit=limit,
        viewer_user=viewer_user,
    )


@router.get(
    "/explore",
    response_model=ExploreDiscoveryResponse,
    summary="Retrieve curated Explore discovery payload (trending tags, communities, fresh posts)",
)
async def get_explore(
    lang: Optional[str] = Query(None),
    opt_auth: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    service: FeedService = Depends(get_feed_service),
) -> ExploreDiscoveryResponse:
    viewer_user = opt_auth["user"] if opt_auth else None
    return await service.get_explore_discovery(lang=lang, viewer_user=viewer_user)


@router.put(
    "/feed/topics/{tag_slug}",
    response_model=TopicPreferenceResponse,
    summary="Follow, mute, or clear preference on a topic tag",
)
async def update_topic_preference(
    tag_slug: str,
    payload: TopicPreferenceInput,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: FeedService = Depends(get_feed_service),
) -> TopicPreferenceResponse:
    return await service.set_topic_preference(
        user_id=str(auth_ctx["user"]["id"]),
        tag_slug=tag_slug,
        preference=payload.preference,
    )


@router.get(
    "/search",
    response_model=CursorPostListResponse,
    summary="Search public published posts across titles, bodies, and tags",
)
async def search_posts(
    q: str = Query(..., description="Search query (2 to 120 characters)"),
    community_slug: Optional[str] = Query(None),
    post_type: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    lang: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    opt_auth: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    service: FeedService = Depends(get_feed_service),
) -> CursorPostListResponse:
    viewer_user = opt_auth["user"] if opt_auth else None
    return await service.search_public_posts(
        q=q,
        community_slug=community_slug,
        post_type=post_type,
        tag=tag,
        content_language=lang,
        cursor=cursor,
        limit=limit,
        viewer_user=viewer_user,
    )
