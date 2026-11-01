"""REST API endpoints for Phase 4 & Phase 6 Social Posts, Comments, Votes, Reactions, and Bookmarks."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import (
    get_comment_service,
    get_engagement_service,
    get_optional_authenticated_context,
    get_post_service,
    require_authenticated_context,
)
from app.core.rate_limit import rate_limiter
from app.modules.comments.schemas import (
    CreateCommentRequest,
    CursorCommentListResponse,
    PublicCommentResponse,
)
from app.modules.comments.service import CommentService
from app.modules.engagement.schemas import (
    ReactionResultResponse,
    ReactionToggleInput,
    SavePostInput,
    SavePostResponse,
    VoteInput,
    VoteResultResponse,
)
from app.modules.engagement.service import EngagementService
from app.modules.posts.schemas import (
    CreatePostRequest,
    CursorPostListResponse,
    PollVoteRequest,
    PublicPollResponse,
    PublicPostResponse,
    UpdatePostRequest,
)
from app.modules.posts.service import PostService

router = APIRouter(prefix="/posts", tags=["posts"])


@router.post(
    "",
    response_model=PublicPostResponse,
    status_code=201,
    summary="Create a new workplace post with explicit or default identity mode",
)
async def create_post(
    payload: CreatePostRequest,
    request: Request,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: PostService = Depends(get_post_service),
) -> PublicPostResponse:
    user_id = str(auth_ctx["user"]["id"])
    effective_mode = (
        payload.identity_mode
        or str(auth_ctx["user"].get("default_identity_mode", "pseudonymous"))
    ).strip().lower()

    if effective_mode == "anonymous":
        rate_limiter.check_and_record(
            bucket="post_create_anonymous", key=user_id, limit=5, window_seconds=900
        )
    else:
        rate_limiter.check_and_record(
            bucket="post_create", key=user_id, limit=10, window_seconds=900
        )

    return await service.create_post(author_user=auth_ctx["user"], payload=payload)


@router.get(
    "",
    response_model=CursorPostListResponse,
    summary="List published posts with cursor pagination and optional filters",
)
async def list_posts(
    community_slug: Optional[str] = Query(None),
    post_type: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    lang: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    opt_auth: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    service: PostService = Depends(get_post_service),
) -> CursorPostListResponse:
    viewer_id = str(opt_auth["user"]["id"]) if opt_auth else None
    return await service.list_posts(
        community_slug=community_slug,
        post_type=post_type,
        tag=tag,
        content_language=lang,
        cursor=cursor,
        limit=limit,
        viewer_user_id=viewer_id,
    )


@router.get(
    "/{post_id}",
    response_model=PublicPostResponse,
    summary="Retrieve a single post by ID with privacy-safe author serialization",
)
async def get_post(
    post_id: str,
    opt_auth: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    service: PostService = Depends(get_post_service),
) -> PublicPostResponse:
    viewer_id = str(opt_auth["user"]["id"]) if opt_auth else None
    return await service.get_post_by_id(post_id, viewer_user_id=viewer_id)


@router.patch(
    "/{post_id}",
    response_model=PublicPostResponse,
    summary="Edit a post (Author only; works for both pseudonymous and anonymous posts)",
)
async def update_post(
    post_id: str,
    payload: UpdatePostRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: PostService = Depends(get_post_service),
) -> PublicPostResponse:
    return await service.update_post(
        post_id=post_id,
        actor_user_id=str(auth_ctx["user"]["id"]),
        payload=payload,
    )


@router.delete(
    "/{post_id}",
    summary="Delete a post (Author only; works for both pseudonymous and anonymous posts)",
)
async def delete_post(
    post_id: str,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: PostService = Depends(get_post_service),
) -> dict[str, str]:
    await service.delete_post(
        post_id=post_id,
        actor_user_id=str(auth_ctx["user"]["id"]),
    )
    return {"status": "deleted", "id": post_id}


@router.post(
    "/{post_id}/poll/vote",
    response_model=PublicPollResponse,
    summary="Cast a vote on a poll post",
)
async def vote_on_poll(
    post_id: str,
    payload: PollVoteRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: PostService = Depends(get_post_service),
) -> PublicPollResponse:
    return await service.vote_on_poll(
        post_id=post_id,
        user_id=str(auth_ctx["user"]["id"]),
        payload=payload,
    )


@router.put(
    "/{post_id}/vote",
    response_model=VoteResultResponse,
    summary="Cast or update an upvote (+1), downvote (-1), or clear vote (0) on a post",
)
async def vote_on_post(
    post_id: str,
    payload: VoteInput,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    engagement: EngagementService = Depends(get_engagement_service),
) -> VoteResultResponse:
    return await engagement.set_vote(
        user_id=str(auth_ctx["user"]["id"]),
        target_type="post",
        target_id=post_id,
        value=payload.value,
    )


@router.delete(
    "/{post_id}/vote",
    response_model=VoteResultResponse,
    summary="Remove the authenticated user's vote from a post",
)
async def remove_post_vote(
    post_id: str,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    engagement: EngagementService = Depends(get_engagement_service),
) -> VoteResultResponse:
    return await engagement.set_vote(
        user_id=str(auth_ctx["user"]["id"]),
        target_type="post",
        target_id=post_id,
        value=0,
    )


@router.put(
    "/{post_id}/reactions/{kind}",
    response_model=ReactionResultResponse,
    summary="Toggle a workplace reaction (relatable, laugh, support, oof, respect) on a post",
)
async def toggle_post_reaction(
    post_id: str,
    kind: str,
    payload: ReactionToggleInput,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    engagement: EngagementService = Depends(get_engagement_service),
) -> ReactionResultResponse:
    return await engagement.set_reaction(
        user_id=str(auth_ctx["user"]["id"]),
        target_type="post",
        target_id=post_id,
        reaction_kind=kind,
        active=payload.active,
    )


@router.post(
    "/{post_id}/save",
    response_model=SavePostResponse,
    summary="Bookmark or unbookmark a post",
)
async def save_post(
    post_id: str,
    payload: SavePostInput,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    engagement: EngagementService = Depends(get_engagement_service),
) -> SavePostResponse:
    return await engagement.set_saved_post(
        user_id=str(auth_ctx["user"]["id"]),
        post_id=post_id,
        saved=payload.saved,
    )


@router.get(
    "/{post_id}/comments",
    response_model=CursorCommentListResponse,
    summary="List threaded comments for a post with cursor pagination and subtree filtering",
)
async def list_post_comments(
    post_id: str,
    parent_id: Optional[str] = Query(None, description="Filter to subtree under parent comment"),
    cursor: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=50),
    opt_auth: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    comment_service: CommentService = Depends(get_comment_service),
) -> CursorCommentListResponse:
    viewer_id = str(opt_auth["user"]["id"]) if opt_auth else None
    return await comment_service.list_comments(
        post_id=post_id,
        parent_comment_id=parent_id,
        cursor=cursor,
        limit=limit,
        viewer_user_id=viewer_id,
    )


@router.post(
    "/{post_id}/comments",
    response_model=PublicCommentResponse,
    status_code=201,
    summary="Create a comment or nested reply (enforces Sticky Anonymous OP protection)",
)
async def create_post_comment(
    post_id: str,
    payload: CreateCommentRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    comment_service: CommentService = Depends(get_comment_service),
) -> PublicCommentResponse:
    user_id = str(auth_ctx["user"]["id"])
    rate_limiter.check_and_record(
        bucket="comment_create", key=user_id, limit=20, window_seconds=600
    )
    return await comment_service.create_comment(
        post_id=post_id,
        author_user=auth_ctx["user"],
        payload=payload,
    )
