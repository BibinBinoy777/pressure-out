"""Pydantic request and response schemas for Phase 3 Identity, Auth, and Privacy."""
from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.core.unicode import normalize_optional_unicode_nfc, normalize_unicode_nfc

HANDLE_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
BCP47_RE = re.compile(r"^[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*$")

VALID_IDENTITY_MODES = ("pseudonymous", "anonymous", "professional")
VALID_EXPERIENCE_BANDS = (
    "fresher_0_1",
    "junior_1_3",
    "mid_3_6",
    "senior_6_10",
    "lead_10_plus",
)


def validate_handle(handle: str) -> str:
    cleaned = handle.strip()
    if not HANDLE_RE.match(cleaned):
        raise AppError(
            code="INVALID_HANDLE",
            message="Handle must be 3 to 32 characters and contain only letters, numbers, or underscores.",
            status_code=422,
        )
    return cleaned


def validate_identity_mode(mode: str) -> str:
    cleaned = mode.strip().lower()
    if cleaned not in VALID_IDENTITY_MODES:
        raise AppError(
            code="INVALID_IDENTITY_MODE",
            message=f"Identity mode must be one of: {', '.join(VALID_IDENTITY_MODES)}.",
            status_code=422,
        )
    return cleaned


def validate_experience_band(band: str) -> str:
    cleaned = band.strip().lower()
    if cleaned not in VALID_EXPERIENCE_BANDS:
        raise AppError(
            code="INVALID_EXPERIENCE_BAND",
            message=f"Experience band must be one of: {', '.join(VALID_EXPERIENCE_BANDS)}.",
            status_code=422,
        )
    return cleaned


def validate_bcp47_tag(tag: str) -> str:
    cleaned = tag.strip().lower()
    if not BCP47_RE.match(cleaned):
        raise AppError(
            code="INVALID_LANGUAGE_TAG",
            message=f"Invalid BCP 47 language tag: '{tag}'.",
            status_code=422,
        )
    return cleaned


class RegisterRequest(BaseModel):
    handle: str = Field(..., description="Unique pseudonymous username (3-32 chars, alphanumeric/underscore)")
    password: str = Field(..., description="Account password (min 10 chars)")
    recovery_email: Optional[str] = Field(None, description="Optional recovery email (encrypted at rest)")
    preferred_ui_locale: str = Field("en", description="Preferred UI locale (BCP 47)")


class LoginRequest(BaseModel):
    handle: str
    password: str


class RecoveryInitiateRequest(BaseModel):
    recovery_email: str


class RecoveryResetRequest(BaseModel):
    handle: str
    recovery_code_or_token: str
    new_password: str


class ProfessionalProfileInput(BaseModel):
    role_title: str = Field(..., min_length=2, max_length=80)
    industry: str = Field(..., min_length=2, max_length=64)
    experience_band: str
    region_label: Optional[str] = Field(None, max_length=64)
    is_enabled: bool = True

    def normalized(self) -> "ProfessionalProfileInput":
        role_clean = normalize_unicode_nfc(self.role_title).strip()
        ind_clean = normalize_unicode_nfc(self.industry).strip()
        if len(role_clean) < 2 or len(role_clean) > 80:
            raise AppError(
                code="VALIDATION_ERROR",
                message="Professional role title must be between 2 and 80 characters.",
                status_code=422,
            )
        if len(ind_clean) < 2 or len(ind_clean) > 64:
            raise AppError(
                code="VALIDATION_ERROR",
                message="Industry must be between 2 and 64 characters.",
                status_code=422,
            )
        band_clean = validate_experience_band(self.experience_band)
        region_clean = normalize_optional_unicode_nfc(self.region_label)
        if region_clean is not None:
            region_clean = region_clean.strip() or None
        return ProfessionalProfileInput(
            role_title=role_clean,
            industry=ind_clean,
            experience_band=band_clean,
            region_label=region_clean,
            is_enabled=self.is_enabled,
        )


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(None, max_length=64)
    bio: Optional[str] = Field(None, max_length=500)
    show_karma: Optional[bool] = None
    professional_profile: Optional[ProfessionalProfileInput] = None


class UpdateSettingsRequest(BaseModel):
    default_identity_mode: Optional[str] = None
    preferred_ui_locale: Optional[str] = None
    preferred_content_locales: Optional[List[str]] = None
    recovery_email: Optional[str] = None


class DeleteAccountRequest(BaseModel):
    password_confirmation: str
    delete_published_posts: bool = False


class IdentityPreviewRequest(BaseModel):
    identity_mode: str
    is_anonymous_op: bool = False


# ============================================================================
# PUBLIC vs. PRIVATE RESPONSE MODELS (Strict Serializer Isolation)
# ============================================================================


class VoluntaryProfessionalBadge(BaseModel):
    """Voluntary, self-declared workplace context (explicitly marked unverified in MVP)."""

    role_title: str
    industry: str
    experience_band: str
    region_label: Optional[str] = None
    is_verified: bool = False


class PublicProfileResponse(BaseModel):
    """Publicly visible pseudonymous profile.

    NEVER includes `user_id`, `email`, `email_hash`, `role`, `account_status`,
    `default_identity_mode`, or `csrf_token`.
    """

    handle: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    show_karma: bool = True
    professional_badge: Optional[VoluntaryProfessionalBadge] = None
    created_at: str


class PublicAuthorDisplay(BaseModel):
    """Per-post / per-comment public author representation enforced by serializer."""

    identity_mode: str
    display_name: str
    handle: Optional[str] = None
    avatar_url: Optional[str] = None
    professional_badge: Optional[VoluntaryProfessionalBadge] = None
    is_anonymous_op: bool = False


class PrivateProfessionalProfileResponse(BaseModel):
    role_title: str
    industry: str
    experience_band: str
    region_label: Optional[str] = None
    is_enabled: bool
    is_verified: bool = False


class PrivateAccountResponse(BaseModel):
    """Private account representation returned ONLY to the authenticated owner."""

    user_id: str
    handle: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    show_karma: bool = True
    account_status: str
    role: str
    default_identity_mode: str
    preferred_ui_locale: str
    preferred_content_locales: List[str]
    has_recovery_email: bool
    masked_recovery_email: Optional[str] = None
    professional_profile: Optional[PrivateProfessionalProfileResponse] = None
    csrf_token: Optional[str] = None
    one_time_recovery_code: Optional[str] = None
    created_at: str


class ActiveSessionItem(BaseModel):
    session_id: str
    user_agent_summary: Optional[str] = None
    is_current: bool
    created_at: str
    last_active_at: str
    expires_at: str
