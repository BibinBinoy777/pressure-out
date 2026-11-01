"""FastAPI dependency injection helpers for database sessions, authentication, and CSRF guards."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Optional

from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import verify_csrf_token
from app.database.session import DatabaseManager, get_database_manager
from app.modules.comments.service import CommentService
from app.modules.communities.service import CommunityService
from app.modules.engagement.service import EngagementService
from app.modules.feed.service import FeedService
from app.modules.identity.service import IdentityService
from app.modules.memes.service import MemeStudioService
from app.modules.moderation.service import ModerationService
from app.modules.translations.service import TranslationService
from app.modules.workplace.service import WorkplaceService
from app.modules.notifications.service import NotificationService
from app.modules.posts.service import PostService


def get_request_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def get_request_db_manager(request: Request) -> DatabaseManager:
    return getattr(request.app.state, "db_manager", None) or get_database_manager()


async def get_db_session(
    db_manager: DatabaseManager = Depends(get_request_db_manager),
) -> AsyncGenerator[Any, None]:
    async with db_manager.session_scope() as session:
        yield session


def get_identity_service(
    session: Any = Depends(get_db_session),
    settings: Settings = Depends(get_request_settings),
) -> IdentityService:
    return IdentityService(session=session, settings=settings)


def get_post_service(
    session: Any = Depends(get_db_session),
) -> PostService:
    return PostService(session=session)


def get_community_service(
    session: Any = Depends(get_db_session),
) -> CommunityService:
    return CommunityService(session=session)


def get_comment_service(
    session: Any = Depends(get_db_session),
    settings: Settings = Depends(get_request_settings),
) -> CommentService:
    return CommentService(session=session, settings=settings)


def get_engagement_service(
    session: Any = Depends(get_db_session),
) -> EngagementService:
    return EngagementService(session=session)


def get_feed_service(
    session: Any = Depends(get_db_session),
) -> FeedService:
    return FeedService(session=session)


def get_notification_service(
    session: Any = Depends(get_db_session),
) -> NotificationService:
    return NotificationService(session=session)


async def get_optional_authenticated_context(
    request: Request,
    service: IdentityService = Depends(get_identity_service),
    settings: Settings = Depends(get_request_settings),
) -> Optional[dict[str, Any]]:
    """Return authenticated user context if a valid session cookie is present, else None."""
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        return None
    try:
        return await service.authenticate_session(raw_token)
    except AppError:
        return None


async def require_authenticated_context(
    request: Request,
    service: IdentityService = Depends(get_identity_service),
    settings: Settings = Depends(get_request_settings),
) -> dict[str, Any]:
    """Validate session cookie and enforce CSRF header on state-changing methods."""
    raw_token = request.cookies.get(settings.session_cookie_name)
    auth_ctx = await service.authenticate_session(raw_token)

    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        origin_hdr = request.headers.get("Origin", "").strip()
        if origin_hdr and settings.cors_origins and origin_hdr not in settings.cors_origins:
            raise AppError(
                code="UNTRUSTED_ORIGIN",
                message="Cross-origin state-changing request from untrusted Origin rejected.",
                status_code=403,
            )
        provided_csrf = request.headers.get("X-CSRF-Token")
        expected_csrf = str(auth_ctx["session"]["csrf_secret"])
        if not verify_csrf_token(expected_csrf, provided_csrf):
            raise AppError(
                code="CSRF_VALIDATION_FAILED",
                message="Invalid or missing CSRF token for state-changing request.",
                status_code=403,
            )

    return auth_ctx


def get_meme_studio_service(
    session: Any = Depends(get_db_session),
    settings: Settings = Depends(get_request_settings),
) -> MemeStudioService:
    return MemeStudioService(session=session, settings=settings)


def get_moderation_service(
    session: Any = Depends(get_db_session),
) -> ModerationService:
    return ModerationService(session=session)


def get_translation_service(
    session: Any = Depends(get_db_session),
    settings: Settings = Depends(get_request_settings),
) -> TranslationService:
    return TranslationService(session=session, settings=settings)


def get_workplace_service(
    session: Any = Depends(get_db_session),
    settings: Settings = Depends(get_request_settings),
) -> WorkplaceService:
    return WorkplaceService(session=session, settings=settings)
