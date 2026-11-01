"""Public profile lookup, public profile posts, and identity display preview endpoints."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_identity_service,
    get_optional_authenticated_context,
    get_post_service,
    require_authenticated_context,
)
from app.modules.identity.schemas import (
    IdentityPreviewRequest,
    PublicAuthorDisplay,
    PublicProfileResponse,
)
from app.modules.identity.service import IdentityService
from app.modules.posts.schemas import CursorPostListResponse
from app.modules.posts.service import PostService

router = APIRouter(tags=["profiles"])


@router.get(
    "/profiles/{handle}",
    response_model=PublicProfileResponse,
    summary="Retrieve a public pseudonymous profile by handle (never exposes private fields)",
)
async def get_public_profile(
    handle: str,
    service: IdentityService = Depends(get_identity_service),
) -> PublicProfileResponse:
    return await service.get_public_profile_by_handle(handle)


@router.get(
    "/profiles/{handle}/posts",
    response_model=CursorPostListResponse,
    summary="List public posts by @handle (strictly excludes anonymous posts)",
)
async def get_public_profile_posts(
    handle: str,
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    opt_auth: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    post_service: PostService = Depends(get_post_service),
) -> CursorPostListResponse:
    viewer_id = str(opt_auth["user"]["id"]) if opt_auth else None
    return await post_service.list_public_profile_posts(
        handle=handle,
        cursor=cursor,
        limit=limit,
        viewer_user_id=viewer_id,
    )


@router.post(
    "/identity/preview-display",
    response_model=PublicAuthorDisplay,
    summary="Preview the exact public author block serialized for a chosen identity mode",
)
async def preview_identity_display(
    payload: IdentityPreviewRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: IdentityService = Depends(get_identity_service),
) -> PublicAuthorDisplay:
    return await service.preview_display_identity(
        user_id=str(auth_ctx["user"]["id"]),
        identity_mode=payload.identity_mode,
        is_anonymous_op=payload.is_anonymous_op,
    )
