"""REST API endpoints for individual comment editing, deletion, voting, and reactions (`/api/v1/comments`)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_comment_service,
    get_engagement_service,
    require_authenticated_context,
)
from app.modules.comments.schemas import PublicCommentResponse, UpdateCommentRequest
from app.modules.comments.service import CommentService
from app.modules.engagement.schemas import (
    ReactionResultResponse,
    ReactionToggleInput,
    VoteInput,
    VoteResultResponse,
)
from app.modules.engagement.service import EngagementService

router = APIRouter(prefix="/comments", tags=["comments"])


@router.patch(
    "/{comment_id}",
    response_model=PublicCommentResponse,
    summary="Edit a comment (Author only)",
)
async def update_comment(
    comment_id: str,
    payload: UpdateCommentRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: CommentService = Depends(get_comment_service),
) -> PublicCommentResponse:
    return await service.update_comment(
        comment_id=comment_id,
        actor_user_id=str(auth_ctx["user"]["id"]),
        payload=payload,
    )


@router.delete(
    "/{comment_id}",
    summary="Soft-delete a comment while preserving child reply tree continuity (Author only)",
)
async def delete_comment(
    comment_id: str,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: CommentService = Depends(get_comment_service),
) -> dict[str, str]:
    await service.delete_comment(
        comment_id=comment_id,
        actor_user_id=str(auth_ctx["user"]["id"]),
    )
    return {"status": "deleted", "id": comment_id}


@router.put(
    "/{comment_id}/vote",
    response_model=VoteResultResponse,
    summary="Cast or update an upvote (+1), downvote (-1), or clear vote (0) on a comment",
)
async def vote_on_comment(
    comment_id: str,
    payload: VoteInput,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    engagement: EngagementService = Depends(get_engagement_service),
) -> VoteResultResponse:
    return await engagement.set_vote(
        user_id=str(auth_ctx["user"]["id"]),
        target_type="comment",
        target_id=comment_id,
        value=payload.value,
    )


@router.put(
    "/{comment_id}/reactions/{kind}",
    response_model=ReactionResultResponse,
    summary="Toggle a workplace reaction on a comment",
)
async def toggle_comment_reaction(
    comment_id: str,
    kind: str,
    payload: ReactionToggleInput,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    engagement: EngagementService = Depends(get_engagement_service),
) -> ReactionResultResponse:
    return await engagement.set_reaction(
        user_id=str(auth_ctx["user"]["id"]),
        target_type="comment",
        target_id=comment_id,
        reaction_kind=kind,
        active=payload.active,
    )
