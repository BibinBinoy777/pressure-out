"""Pydantic schemas and validators for Phase 5 Communities."""
from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.core.unicode import normalize_unicode_nfc
from app.modules.identity.schemas import validate_bcp47_tag

COMMUNITY_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{2,62}$")
VALID_COMMUNITY_STATUSES = ("active", "restricted", "archived")
VALID_MEMBERSHIP_ACTIONS = ("join", "leave")
VALID_MEMBERSHIP_ROLES = ("member", "moderator")
VALID_MEMBERSHIP_STATUSES = ("active", "banned")


def validate_community_slug_strict(slug: str) -> str:
    cleaned = slug.strip().lower()
    if not COMMUNITY_SLUG_RE.match(cleaned):
        raise AppError(
            code="INVALID_COMMUNITY_SLUG",
            message="Community slug must be 3 to 63 lowercase alphanumeric or hyphen characters.",
            status_code=422,
        )
    return cleaned


class CommunityRuleInput(BaseModel):
    rule_number: int = Field(..., ge=1, le=25)
    title: str = Field(..., min_length=3, max_length=120)
    description: str = Field(..., min_length=5, max_length=500)


class CommunityRuleResponse(BaseModel):
    rule_number: int
    title: str
    description: str


class CommunityViewerContext(BaseModel):
    is_member: bool = False
    role: Optional[str] = None
    is_banned: bool = False
    can_post: bool = True
    can_moderate: bool = False


class CommunitySummaryResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    icon_name: Optional[str] = None
    primary_language: str
    status: str
    member_count: int
    post_count: int
    viewer_context: CommunityViewerContext


class CommunityDetailResponse(CommunitySummaryResponse):
    rules: List[CommunityRuleResponse] = Field(default_factory=list)
    created_at: str


class MembershipActionRequest(BaseModel):
    action: str = Field(..., description="'join' or 'leave'")


class MembershipActionResponse(BaseModel):
    community_slug: str
    is_member: bool
    role: Optional[str] = None
    member_count: int


class CreateCommunityRequest(BaseModel):
    slug: str
    name: str = Field(..., min_length=3, max_length=80)
    description: str = Field(..., min_length=10, max_length=1000)
    icon_name: Optional[str] = Field("users", max_length=64)
    primary_language: str = Field("en")
    rules: List[CommunityRuleInput] = Field(default_factory=list)

    def normalized(self) -> "CreateCommunityRequest":
        return CreateCommunityRequest(
            slug=validate_community_slug_strict(self.slug),
            name=normalize_unicode_nfc(self.name).strip(),
            description=normalize_unicode_nfc(self.description).strip(),
            icon_name=self.icon_name,
            primary_language=validate_bcp47_tag(self.primary_language),
            rules=self.rules,
        )


class UpdateCommunityStatusRequest(BaseModel):
    status: str = Field(..., description="'active' | 'restricted' | 'archived'")
    description: Optional[str] = Field(None, min_length=10, max_length=1000)


class CommunityMemberModerationRequest(BaseModel):
    status: Optional[str] = Field(None, description="'active' | 'banned'")
    role: Optional[str] = Field(None, description="'member' | 'moderator'")
