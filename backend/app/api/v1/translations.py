"""FastAPI endpoints for Phase 10 Language Capabilities & On-Demand Content Translation."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request

from app.api.deps import (
    get_optional_authenticated_context,
    get_request_settings,
    get_translation_service,
)
from app.config import Settings
from app.core.errors import AppError
from app.core.security import verify_csrf_token
from app.modules.translations.schemas import (
    DerivedTranslationResponse,
    LanguageCapabilitiesResponse,
    TranslateContentRequest,
)
from app.modules.translations.service import TranslationService

router = APIRouter(tags=["translations"])


def _enforce_csrf_if_cookie_present(
    request: Request,
    auth_ctx: Optional[dict[str, Any]],
    settings: Settings,
) -> None:
    """When an authenticated session cookie is sent on POST, enforce X-CSRF-Token."""
    if auth_ctx is not None or request.cookies.get(settings.session_cookie_name):
        if auth_ctx is None:
            raise AppError(
                code="UNAUTHORIZED",
                message="Invalid or expired session cookie.",
                status_code=401,
            )
        provided_csrf = request.headers.get("X-CSRF-Token")
        expected_csrf = str(auth_ctx["session"]["csrf_secret"])
        if not verify_csrf_token(expected_csrf, provided_csrf):
            raise AppError(
                code="CSRF_VALIDATION_FAILED",
                message="Invalid or missing CSRF token for state-changing request.",
                status_code=403,
            )


@router.get("/languages/capabilities", response_model=LanguageCapabilitiesResponse)
async def get_language_capabilities_endpoint(
    service: TranslationService = Depends(get_translation_service),
) -> LanguageCapabilitiesResponse:
    """Return the supported UI locales, translation target locales, and script capability matrix."""
    return service.get_language_capabilities()


@router.post("/posts/{post_id}/translations", response_model=DerivedTranslationResponse)
async def translate_post_endpoint(
    post_id: str,
    payload: TranslateContentRequest,
    request: Request,
    auth_ctx: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    settings: Settings = Depends(get_request_settings),
    service: TranslationService = Depends(get_translation_service),
) -> DerivedTranslationResponse:
    """Request or retrieve a cached non-destructive derived translation for an eligible post."""
    _enforce_csrf_if_cookie_present(request, auth_ctx, settings)
    viewer_user = auth_ctx["user"] if auth_ctx else None
    client_ip = request.client.host if request.client else "127.0.0.1"
    return await service.translate_content(
        source_type="post",
        source_id=post_id,
        payload=payload,
        viewer_user=viewer_user,
        rate_limit_key=client_ip,
    )


@router.post("/comments/{comment_id}/translations", response_model=DerivedTranslationResponse)
async def translate_comment_endpoint(
    comment_id: str,
    payload: TranslateContentRequest,
    request: Request,
    auth_ctx: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    settings: Settings = Depends(get_request_settings),
    service: TranslationService = Depends(get_translation_service),
) -> DerivedTranslationResponse:
    """Request or retrieve a cached non-destructive derived translation for an eligible comment."""
    _enforce_csrf_if_cookie_present(request, auth_ctx, settings)
    viewer_user = auth_ctx["user"] if auth_ctx else None
    client_ip = request.client.host if request.client else "127.0.0.1"
    return await service.translate_content(
        source_type="comment",
        source_id=comment_id,
        payload=payload,
        viewer_user=viewer_user,
        rate_limit_key=client_ip,
    )
