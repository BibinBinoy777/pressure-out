"""Five-Layer Identity Serializers enforcing strict public/private separation (Phase 3).

Guarantees:
1. `serialize_public_profile` NEVER emits `user_id`, `email`, `email_hash`, `role`,
   `default_identity_mode`, or session metadata.
2. `serialize_author_for_identity_mode` enforces per-post/per-comment disclosure:
   - `anonymous`: strips `@handle`, `display_name`, `avatar_url`, and `professional_badge`.
   - `pseudonymous`: shows `@handle` and `display_name`, omits `professional_badge`.
   - `professional`: shows `@handle` and voluntary unverified `professional_badge`.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from app.core.errors import AppError
from app.core.security import decrypt_recovery_email, mask_email_for_owner
from app.modules.identity.schemas import (
    PrivateAccountResponse,
    PrivateProfessionalProfileResponse,
    PublicAuthorDisplay,
    PublicProfileResponse,
    VoluntaryProfessionalBadge,
    validate_identity_mode,
)


def serialize_voluntary_professional_badge(
    prof_row: Optional[Mapping[str, Any]]
) -> Optional[VoluntaryProfessionalBadge]:
    """Build a public voluntary professional badge only if enabled by the user."""
    if not prof_row or not bool(prof_row.get("is_enabled")):
        return None
    return VoluntaryProfessionalBadge(
        role_title=str(prof_row["role_title"]),
        industry=str(prof_row["industry"]),
        experience_band=str(prof_row["experience_band"]),
        region_label=prof_row.get("region_label"),
        is_verified=False,
    )


def serialize_public_profile(
    profile_row: Mapping[str, Any],
    prof_row: Optional[Mapping[str, Any]] = None,
) -> PublicProfileResponse:
    """Serialize a public pseudonymous profile with zero private account fields."""
    avatar_key = profile_row.get("avatar_storage_key")
    return PublicProfileResponse(
        handle=str(profile_row["handle"]),
        display_name=profile_row.get("display_name"),
        bio=profile_row.get("bio"),
        avatar_url=f"/media/{avatar_key}" if avatar_key else None,
        show_karma=bool(profile_row.get("show_karma", True)),
        professional_badge=serialize_voluntary_professional_badge(prof_row),
        created_at=str(profile_row["created_at"]),
    )


def serialize_author_for_identity_mode(
    *,
    identity_mode: str,
    profile_row: Mapping[str, Any],
    prof_row: Optional[Mapping[str, Any]] = None,
    is_anonymous_op: bool = False,
) -> PublicAuthorDisplay:
    """Serialize an author block according to the chosen per-post/comment `identity_mode`."""
    mode = validate_identity_mode(identity_mode)

    if mode == "anonymous":
        # HARD PRIVACY BOUNDARY: discard profile_row and prof_row completely
        return PublicAuthorDisplay(
            identity_mode="anonymous",
            display_name="Anonymous OP" if is_anonymous_op else "Anonymous Member",
            handle=None,
            avatar_url=None,
            professional_badge=None,
            is_anonymous_op=is_anonymous_op,
        )

    handle = str(profile_row["handle"])
    display_name = profile_row.get("display_name") or f"@{handle}"
    avatar_key = profile_row.get("avatar_storage_key")
    avatar_url = f"/media/{avatar_key}" if avatar_key else None

    if mode == "pseudonymous":
        return PublicAuthorDisplay(
            identity_mode="pseudonymous",
            display_name=str(display_name),
            handle=handle,
            avatar_url=avatar_url,
            professional_badge=None,
            is_anonymous_op=False,
        )

    # mode == "professional"
    badge = serialize_voluntary_professional_badge(prof_row)
    if badge is None:
        raise AppError(
            code="PROFESSIONAL_PROFILE_REQUIRED",
            message="To use Professional display mode, please enable and fill out your optional Professional Profile in Settings.",
            status_code=422,
        )

    return PublicAuthorDisplay(
        identity_mode="professional",
        display_name=str(display_name),
        handle=handle,
        avatar_url=avatar_url,
        professional_badge=badge,
        is_anonymous_op=False,
    )


def serialize_private_account(
    *,
    user_row: Mapping[str, Any],
    profile_row: Mapping[str, Any],
    prof_row: Optional[Mapping[str, Any]],
    email_encryption_key_b64: str,
    csrf_token: Optional[str] = None,
    one_time_recovery_code: Optional[str] = None,
) -> PrivateAccountResponse:
    """Serialize the owner's private account response (for `/api/v1/me` and auth endpoints only)."""
    raw_locales = user_row.get("preferred_content_locales", '["en"]')
    if isinstance(raw_locales, str):
        try:
            content_locales = list(json.loads(raw_locales))
        except Exception:
            content_locales = ["en"]
    else:
        content_locales = list(raw_locales)

    encrypted_email = user_row.get("email_encrypted")
    has_email = bool(user_row.get("email_hash") and encrypted_email)
    masked_email: Optional[str] = None
    if has_email and encrypted_email:
        try:
            decrypted = decrypt_recovery_email(bytes(encrypted_email), email_encryption_key_b64)
            masked_email = mask_email_for_owner(decrypted)
        except Exception:
            masked_email = "***@***"

    priv_prof: Optional[PrivateProfessionalProfileResponse] = None
    if prof_row is not None:
        priv_prof = PrivateProfessionalProfileResponse(
            role_title=str(prof_row["role_title"]),
            industry=str(prof_row["industry"]),
            experience_band=str(prof_row["experience_band"]),
            region_label=prof_row.get("region_label"),
            is_enabled=bool(prof_row.get("is_enabled", True)),
            is_verified=False,
        )

    return PrivateAccountResponse(
        user_id=str(user_row["id"]),
        handle=str(profile_row["handle"]),
        display_name=profile_row.get("display_name"),
        bio=profile_row.get("bio"),
        show_karma=bool(profile_row.get("show_karma", True)),
        account_status=str(user_row["account_status"]),
        role=str(user_row["role"]),
        default_identity_mode=str(user_row["default_identity_mode"]),
        preferred_ui_locale=str(user_row["preferred_ui_locale"]),
        preferred_content_locales=content_locales,
        has_recovery_email=has_email,
        masked_recovery_email=masked_email,
        professional_profile=priv_prof,
        csrf_token=csrf_token,
        one_time_recovery_code=one_time_recovery_code,
        created_at=str(user_row["created_at"]),
    )
