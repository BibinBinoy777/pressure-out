"""Pydantic schemas and validators for Phase 4 Core Social Posting."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.core.unicode import normalize_unicode_nfc
from app.modules.workplace.schemas import PublicWorkplaceDetailSummary, WorkplaceExperienceDetailInput
from app.modules.identity.schemas import (
    PublicAuthorDisplay,
    validate_bcp47_tag,
    validate_identity_mode,
)

VALID_POST_TYPES: tuple[str, ...] = (
    "discussion",
    "question",
    "rant",
    "story",
    "meme",
    "poll",
    "advice_request",
    "workplace_experience",
)

TAG_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{1,31}$")
COMMUNITY_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,62}$")


def validate_post_type(post_type: str) -> str:
    cleaned = post_type.strip().lower()
    if cleaned not in VALID_POST_TYPES:
        raise AppError(
            code="INVALID_POST_TYPE",
            message=f"Post type must be one of: {', '.join(VALID_POST_TYPES)}.",
            status_code=422,
        )
    return cleaned


def validate_and_normalize_title(title: str) -> str:
    norm = normalize_unicode_nfc(title).strip()
    if len(norm) < 3 or len(norm) > 220:
        raise AppError(
            code="VALIDATION_ERROR",
            message="Post title must be between 3 and 220 characters.",
            status_code=422,
        )
    return norm


def validate_and_normalize_body(body: str) -> str:
    norm = normalize_unicode_nfc(body).strip()
    if len(norm) < 1 or len(norm) > 15000:
        raise AppError(
            code="VALIDATION_ERROR",
            message="Post body must be between 1 and 15,000 characters.",
            status_code=422,
        )
    return norm


def normalize_tag_slug(raw_tag: str) -> str:
    cleaned = normalize_unicode_nfc(raw_tag).strip().lower().lstrip("#")
    cleaned = re.sub(r"[\s_]+", "-", cleaned)
    if not TAG_SLUG_RE.match(cleaned):
        raise AppError(
            code="INVALID_TAG",
            message=f"Tag '{raw_tag}' must be 2 to 32 lowercase alphanumeric or hyphen characters.",
            status_code=422,
        )
    return cleaned


def validate_community_slug(slug: Optional[str]) -> str:
    if not slug or not slug.strip():
        return "general-workplace"
    cleaned = slug.strip().lower()
    if not COMMUNITY_SLUG_RE.match(cleaned):
        raise AppError(
            code="INVALID_COMMUNITY_SLUG",
            message="Invalid community slug format.",
            status_code=422,
        )
    return cleaned


class PollCreateInput(BaseModel):
    options: List[str] = Field(..., description="2 to 8 poll option labels")
    allows_multiple: bool = False

    def normalized_options(self) -> List[str]:
        if len(self.options) < 2 or len(self.options) > 8:
            raise AppError(
                code="INVALID_POLL_OPTIONS",
                message="A poll must have between 2 and 8 options.",
                status_code=422,
            )
        cleaned_list: List[str] = []
        seen: set[str] = set()
        for opt in self.options:
            norm = normalize_unicode_nfc(opt).strip()
            if len(norm) < 1 or len(norm) > 140:
                raise AppError(
                    code="INVALID_POLL_OPTIONS",
                    message="Each poll option must be between 1 and 140 characters.",
                    status_code=422,
                )
            key = norm.lower()
            if key in seen:
                raise AppError(
                    code="DUPLICATE_POLL_OPTION",
                    message="Poll options must be distinct.",
                    status_code=422,
                )
            seen.add(key)
            cleaned_list.append(norm)
        return cleaned_list


class CreatePostRequest(BaseModel):
    community_slug: str = Field("general-workplace", description="Target community slug")
    post_type: str = Field("discussion", description="One of the 8 supported post types")
    identity_mode: Optional[str] = Field(
        None,
        description="Per-post identity mode (pseudonymous, anonymous, professional); defaults to user setting",
    )
    title: str = Field(..., min_length=3, max_length=220)
    body: str = Field(..., min_length=1, max_length=15000)
    content_language: str = Field("en", description="BCP 47 language tag (e.g. en, hi, ml, ta, mul, und)")
    tags: List[str] = Field(default_factory=list, description="Up to 5 topic tags")
    poll: Optional[PollCreateInput] = None
    meme_asset_id: Optional[str] = None
    workplace_detail: Optional[WorkplaceExperienceDetailInput] = None
    acknowledge_pii_warning: bool = False


class UpdatePostRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=220)
    body: Optional[str] = Field(None, min_length=1, max_length=15000)
    identity_mode: Optional[str] = None
    content_language: Optional[str] = None
    tags: Optional[List[str]] = None
    acknowledge_pii_warning: bool = False


class PollVoteRequest(BaseModel):
    option_ids: List[str] = Field(..., description="Selected poll option ID(s)")


class PollOptionResponse(BaseModel):
    id: str
    position: int
    option_text: str
    vote_count: int
    percentage: float


class PublicPollResponse(BaseModel):
    allows_multiple: bool
    total_votes: int
    options: List[PollOptionResponse]
    viewer_selected_option_ids: List[str] = Field(default_factory=list)


class PostStatsResponse(BaseModel):
    score: int
    upvote_count: int
    downvote_count: int
    comment_count: int
    reaction_counts: Dict[str, int]


class PostViewerContext(BaseModel):
    is_author: bool
    can_edit: bool
    can_delete: bool


class CommunitySummaryRef(BaseModel):
    slug: str
    name: str


class PublicMemeAssetSummary(BaseModel):
    id: str
    source_type: str
    mime_type: str
    width: int
    height: int
    alt_text: str
    caption_language: str
    download_url: str


class PublicPostResponse(BaseModel):
    """Privacy-safe public representation of a post.

    NEVER contains `author_user_id`! When `identity_mode == 'anonymous'`,
    `author` contains zero link to the author's handle, profile, or professional badge.
    """

    id: str
    community: CommunitySummaryRef
    post_type: str
    identity_mode: str
    author: PublicAuthorDisplay
    title: str
    body: str
    content_language: str
    tags: List[str]
    meme_asset_id: Optional[str] = None
    meme_asset: Optional[PublicMemeAssetSummary] = None
    workplace_detail: Optional[PublicWorkplaceDetailSummary] = None
    poll: Optional[PublicPollResponse] = None
    stats: PostStatsResponse
    viewer_context: PostViewerContext
    pii_warnings: List[Dict[str, str]] = Field(default_factory=list)
    created_at: str
    updated_at: str


class CursorPostListResponse(BaseModel):
    items: List[PublicPostResponse]
    next_cursor: Optional[str] = None
    has_more: bool
