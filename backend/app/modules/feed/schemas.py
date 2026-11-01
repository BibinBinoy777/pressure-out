"""Pydantic schemas for Phase 7 Feed, Explore Discovery, Topic Preferences, and Search."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.modules.communities.schemas import CommunitySummaryResponse
from app.modules.posts.schemas import PublicPostResponse

VALID_FEED_MODES: tuple[str, ...] = ("latest", "popular", "following", "explore")
VALID_TOPIC_PREF_TYPES: tuple[str, ...] = ("follow", "mute", "none")


def validate_feed_mode(mode: str) -> str:
    cleaned = mode.strip().lower()
    if cleaned not in VALID_FEED_MODES:
        raise AppError(
            code="INVALID_FEED_MODE",
            message=f"Feed mode must be one of: {', '.join(VALID_FEED_MODES)}.",
            status_code=422,
        )
    return cleaned


class TopicPreferenceInput(BaseModel):
    preference: str = Field(..., description="'follow', 'mute', or 'none' (to clear preference)")


class TopicPreferenceResponse(BaseModel):
    tag_slug: str
    preference: str


class TrendingTagItem(BaseModel):
    slug: str
    display_name: str
    usage_count: int
    viewer_preference: Optional[str] = None


class ExploreDiscoveryResponse(BaseModel):
    """Structured discovery payload combining trending tags, communities, and fresh posts."""

    trending_tags: List[TrendingTagItem]
    featured_communities: List[CommunitySummaryResponse]
    fresh_community_posts: List[PublicPostResponse]
    popular_posts: List[PublicPostResponse]
