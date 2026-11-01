"""Privacy-enforcing serializers for Phase 4 Social Posts.

Guarantees:
1. `author_user_id` is NEVER included in `PublicPostResponse`.
2. When `post_row["identity_mode"] == "anonymous"`, the serializer ignores
   `profile_row` and `prof_row` completely and returns `Anonymous Member`.
3. When `post_row["identity_mode"] == "professional"`, the serializer uses the
   immutable `professional_snapshot` captured when the post was published (or current
   professional profile) marked `is_verified=False`.
4. `viewer_context.is_author` is True ONLY when the authenticated caller's
   `viewer_user_id` matches `post_row["author_user_id"]`.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional

from app.modules.identity.schemas import PublicAuthorDisplay, VoluntaryProfessionalBadge
from app.modules.posts.schemas import (
    CommunitySummaryRef,
    PollOptionResponse,
    PostStatsResponse,
    PostViewerContext,
    PublicMemeAssetSummary,
    PublicWorkplaceDetailSummary,
    PublicPollResponse,
    PublicPostResponse,
)

COMMUNITY_DISPLAY_NAMES: dict[str, str] = {
    "general-workplace": "General Workplace",
    "workplace-rants": "Workplace Rants",
    "corporate-memes": "Corporate Memes",
    "career-advice": "Career Advice",
    "it-software": "IT & Software",
    "salary-talk": "Salary Talk",
    "job-hunting": "Job Hunting",
    "freshers-corner": "Freshers' Corner",
    "work-life-balance": "Work-Life Balance",
    "startup-life": "Startup Life",
    "office-humour": "Office Humour",
    "resignation-stories": "Resignation Stories",
}


def _serialize_post_author(
    *,
    post_row: Mapping[str, Any],
    profile_row: Optional[Mapping[str, Any]],
    prof_row: Optional[Mapping[str, Any]],
) -> PublicAuthorDisplay:
    mode = str(post_row["identity_mode"])

    if mode == "anonymous" or profile_row is None:
        alias = str(post_row.get("anonymous_alias") or "Anonymous Member")
        return PublicAuthorDisplay(
            identity_mode="anonymous",
            display_name=alias,
            handle=None,
            avatar_url=None,
            professional_badge=None,
            is_anonymous_op=False,
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
    badge: Optional[VoluntaryProfessionalBadge] = None
    snapshot_raw = post_row.get("professional_snapshot")
    if snapshot_raw:
        try:
            snap = json.loads(str(snapshot_raw)) if isinstance(snapshot_raw, str) else snapshot_raw
            badge = VoluntaryProfessionalBadge(
                role_title=str(snap["role_title"]),
                industry=str(snap["industry"]),
                experience_band=str(snap["experience_band"]),
                region_label=snap.get("region_label"),
                is_verified=False,
            )
        except Exception:
            badge = None

    if badge is None and prof_row and bool(prof_row.get("is_enabled")):
        badge = VoluntaryProfessionalBadge(
            role_title=str(prof_row["role_title"]),
            industry=str(prof_row["industry"]),
            experience_band=str(prof_row["experience_band"]),
            region_label=prof_row.get("region_label"),
            is_verified=False,
        )

    return PublicAuthorDisplay(
        identity_mode="professional",
        display_name=str(display_name),
        handle=handle,
        avatar_url=avatar_url,
        professional_badge=badge,
        is_anonymous_op=False,
    )


def serialize_public_post(
    *,
    post_row: Mapping[str, Any],
    profile_row: Optional[Mapping[str, Any]],
    prof_row: Optional[Mapping[str, Any]],
    tags: List[str],
    poll_data: Optional[PublicPollResponse],
    meme_asset_data: Optional[PublicMemeAssetSummary] = None,
    workplace_detail_data: Optional[PublicWorkplaceDetailSummary] = None,
    viewer_user_id: Optional[str] = None,
    pii_warnings: Optional[List[Dict[str, str]]] = None,
) -> PublicPostResponse:
    """Serialize a post row into a privacy-safe PublicPostResponse."""
    author_user_id = post_row.get("author_user_id")
    is_author = bool(
        viewer_user_id is not None
        and author_user_id is not None
        and str(author_user_id) == str(viewer_user_id)
    )

    comm_slug = str(post_row.get("community_slug") or "general-workplace")
    comm_name = COMMUNITY_DISPLAY_NAMES.get(
        comm_slug, comm_slug.replace("-", " ").title()
    )

    raw_reactions = post_row.get("reaction_counts") or "{}"
    try:
        reactions_dict = (
            json.loads(str(raw_reactions))
            if isinstance(raw_reactions, str)
            else dict(raw_reactions)
        )
    except Exception:
        reactions_dict = {}

    author_block = _serialize_post_author(
        post_row=post_row,
        profile_row=profile_row,
        prof_row=prof_row,
    )

    return PublicPostResponse(
        id=str(post_row["id"]),
        community=CommunitySummaryRef(slug=comm_slug, name=comm_name),
        post_type=str(post_row["post_type"]),
        identity_mode=str(post_row["identity_mode"]),
        author=author_block,
        title=str(post_row["title"]),
        body=str(post_row["body"]),
        content_language=str(post_row["content_language"]),
        tags=tags,
        meme_asset_id=post_row.get("meme_asset_id"),
        meme_asset=meme_asset_data,
        workplace_detail=workplace_detail_data,
        poll=poll_data,
        stats=PostStatsResponse(
            score=int(post_row.get("score", 0)),
            upvote_count=int(post_row.get("upvote_count", 0)),
            downvote_count=int(post_row.get("downvote_count", 0)),
            comment_count=int(post_row.get("comment_count", 0)),
            reaction_counts=reactions_dict,
        ),
        viewer_context=PostViewerContext(
            is_author=is_author,
            can_edit=is_author,
            can_delete=is_author,
        ),
        pii_warnings=pii_warnings or [],
        created_at=str(post_row["created_at"]),
        updated_at=str(post_row["updated_at"]),
    )
