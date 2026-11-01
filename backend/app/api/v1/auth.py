"""Authentication, registration, recovery, and session management endpoints (`/api/v1/auth`)."""
from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import (
    get_identity_service,
    get_request_settings,
    require_authenticated_context,
)
from app.config import Settings
from app.core.rate_limit import rate_limiter
from app.modules.identity.schemas import (
    ActiveSessionItem,
    LoginRequest,
    PrivateAccountResponse,
    RecoveryInitiateRequest,
    RecoveryResetRequest,
    RegisterRequest,
)
from app.modules.identity.serializers import serialize_private_account
from app.modules.identity.service import IdentityService

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def _set_session_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )


@router.post(
    "/register",
    response_model=PrivateAccountResponse,
    status_code=201,
    summary="Register a new pseudonymous account without real name or employer",
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    service: IdentityService = Depends(get_identity_service),
    settings: Settings = Depends(get_request_settings),
) -> PrivateAccountResponse:
    ip = _client_ip(request)
    rate_limiter.check_and_record(
        bucket="auth_register", key=ip, limit=5, window_seconds=3600
    )
    account_resp, raw_session_token = await service.register_user(
        payload,
        user_agent=request.headers.get("User-Agent"),
        client_ip=ip,
    )
    _set_session_cookie(response, raw_session_token, settings)
    return account_resp


@router.post(
    "/login",
    response_model=PrivateAccountResponse,
    summary="Sign in with pseudonymous handle and password",
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: IdentityService = Depends(get_identity_service),
    settings: Settings = Depends(get_request_settings),
) -> PrivateAccountResponse:
    ip = _client_ip(request)
    rate_key = f"{ip}:{payload.handle.strip().lower()}"
    rate_limiter.check_and_record(
        bucket="auth_login", key=rate_key, limit=10, window_seconds=900
    )
    account_resp, raw_session_token = await service.login_user(
        payload,
        user_agent=request.headers.get("User-Agent"),
        client_ip=ip,
    )
    _set_session_cookie(response, raw_session_token, settings)
    return account_resp


@router.post("/logout", summary="Revoke current session and clear cookie")
async def logout(
    response: Response,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: IdentityService = Depends(get_identity_service),
    settings: Settings = Depends(get_request_settings),
) -> dict[str, str]:
    await service.logout_session(str(auth_ctx["session"]["id"]))
    _clear_session_cookie(response, settings)
    return {"status": "logged_out"}


@router.get(
    "/session",
    response_model=PrivateAccountResponse,
    summary="Return current authenticated account and CSRF token",
)
async def get_current_session(
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
    "/sessions",
    response_model=List[ActiveSessionItem],
    summary="List active sessions for the current account",
)
async def list_sessions(
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: IdentityService = Depends(get_identity_service),
) -> List[ActiveSessionItem]:
    return await service.list_active_sessions(
        user_id=str(auth_ctx["user"]["id"]),
        current_session_id=str(auth_ctx["session"]["id"]),
    )


@router.post(
    "/sessions/revoke-all",
    summary="Revoke all active sessions for the current account",
)
async def revoke_all_sessions(
    response: Response,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: IdentityService = Depends(get_identity_service),
    settings: Settings = Depends(get_request_settings),
) -> dict[str, str]:
    await service.revoke_all_sessions(str(auth_ctx["user"]["id"]))
    _clear_session_cookie(response, settings)
    return {"status": "all_sessions_revoked"}


@router.post(
    "/recovery/request",
    summary="Initiate account recovery (constant-shape response to prevent email enumeration)",
)
async def request_recovery(
    payload: RecoveryInitiateRequest,
    request: Request,
    service: IdentityService = Depends(get_identity_service),
) -> dict[str, str]:
    ip = _client_ip(request)
    rate_limiter.check_and_record(
        bucket="auth_recovery", key=ip, limit=5, window_seconds=3600
    )
    await service.initiate_email_recovery(payload.recovery_email)
    return {
        "status": "recovery_initiated",
        "message": "If an active account matches that recovery email, reset instructions have been prepared.",
    }


@router.post(
    "/recovery/reset",
    summary="Reset password using backup recovery code or email recovery token",
)
async def reset_password(
    payload: RecoveryResetRequest,
    request: Request,
    response: Response,
    service: IdentityService = Depends(get_identity_service),
    settings: Settings = Depends(get_request_settings),
) -> dict[str, str]:
    ip = _client_ip(request)
    rate_limiter.check_and_record(
        bucket="auth_recovery_reset", key=ip, limit=5, window_seconds=3600
    )
    await service.reset_password_with_recovery(payload)
    _clear_session_cookie(response, settings)
    return {"status": "password_reset_complete"}
