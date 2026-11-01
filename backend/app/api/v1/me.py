"""Authenticated owner profile, privacy settings, saved bookmarks, and account deletion endpoints (`/api/v1/me`)."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import (
    get_engagement_service,
    get_identity_service,
    get_request_settings,
    require_authenticated_context,
)
from app.config import Settings
from app.modules.engagement.service import EngagementService
from app.modules.identity.schemas import (
    DeleteAccountRequest,
    PrivateAccountResponse,
    UpdateProfileRequest,
    UpdateSettingsRequest,
)
from app.modules.identity.serializers import serialize_private_account
from app.modules.identity.service import IdentityService
from app.modules.posts.schemas import CursorPostListResponse

router = APIRouter(prefix="/me", tags=["me"])


@router.get(
    "",
    response_model=PrivateAccountResponse,
    summary="Retrieve the authenticated owner's private account and profile settings",
)
async def get_me(
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    settings: Settings = Depends(get_request_settings),
) -> PrivateAccountResponse:
    return serialize_private_account(
        user_row=auth_ctx["user"],
        profile_row=auth_ctx["profile"],
        prof_row=auth_ctx["prof"],
        email_encryption_key_b64=settings.email_encryption_key_base64,
        csrf_token=str(auth_ctx["session"]["csrf_secret"]),
    )


@router.get(
    "/saved",
    response_model=CursorPostListResponse,
    summary="Retrieve the authenticated user's private bookmarked posts",
)
async def get_saved_posts(
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    engagement: EngagementService = Depends(get_engagement_service),
) -> CursorPostListResponse:
    return await engagement.list_saved_posts(
        user_id=str(auth_ctx["user"]["id"]),
        cursor=cursor,
        limit=limit,
    )


@router.patch(
    "/profile",
    response_model=PrivateAccountResponse,
    summary="Update public pseudonymous profile and optional professional profile",
)
async def update_my_profile(
    payload: UpdateProfileRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: IdentityService = Depends(get_identity_service),
) -> PrivateAccountResponse:
    return await service.update_profile(
        user_id=str(auth_ctx["user"]["id"]),
        payload=payload,
        csrf_token=str(auth_ctx["session"]["csrf_secret"]),
    )


@router.patch(
    "/settings",
    response_model=PrivateAccountResponse,
    summary="Update default identity mode, language preferences, and recovery email",
)
async def update_my_settings(
    payload: UpdateSettingsRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: IdentityService = Depends(get_identity_service),
) -> PrivateAccountResponse:
    return await service.update_settings(
        user_id=str(auth_ctx["user"]["id"]),
        payload=payload,
        csrf_token=str(auth_ctx["session"]["csrf_secret"]),
    )


@router.delete(
    "",
    summary="Delete and anonymize the authenticated user's account",
)
async def delete_my_account(
    payload: DeleteAccountRequest,
    response: Response,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: IdentityService = Depends(get_identity_service),
    settings: Settings = Depends(get_request_settings),
) -> dict[str, str]:
    await service.delete_account(
        user_id=str(auth_ctx["user"]["id"]),
        payload=payload,
    )
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return {"status": "account_deleted"}


@router.get(
    "/export",
    summary="Export the authenticated owner's personal account data, posts, comments, and structured contribution",
)
async def export_my_account_data(
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: IdentityService = Depends(get_identity_service),
) -> dict[str, Any]:
    return await service.export_my_data(user_id=str(auth_ctx["user"]["id"]))
