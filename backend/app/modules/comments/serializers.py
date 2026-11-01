"""Privacy-enforcing serializers for Phase 6 Threaded Comments."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional

from app.modules.comments.schemas import (
    CommentStatsResponse,
    CommentViewerContext,
    PublicCommentResponse,
)
from app.modules.identity.schemas import PublicAuthorDisplay, VoluntaryProfessionalBadge


def _serialize_comment_author(
    *,
    comment_row: Mapping[str, Any],
    profile_row: Optional[Mapping[str, Any]],
    prof_row: Optional[Mapping[str, Any]],
) -> PublicAuthorDisplay:
    mode = str(comment_row["identity_mode"])
    is_op = bool(comment_row.get("is_anonymous_op", False))

    if comment_row.get("deleted_at") is not None:
        return PublicAuthorDisplay(
            identity_mode="anonymous",
            display_name="[deleted]",
            handle=None,
            avatar_url=None,
            professional_badge=None,
            is_anonymous_op=False,
        )

    if mode == "anonymous" or profile_row is None:
        label = str(
            comment_row.get("anonymous_thread_label")
            or ("Anonymous OP" if is_op else "Anonymous Member")
        )
        return PublicAuthorDisplay(
            identity_mode="anonymous",
            display_name=label,
            handle=None,
            avatar_url=None,
            professional_badge=None,
            is_anonymous_op=is_op,
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

    badge: Optional[VoluntaryProfessionalBadge] = None
    snapshot_raw = comment_row.get("professional_snapshot")
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


def serialize_public_comment(
    *,
    comment_row: Mapping[str, Any],
    profile_row: Optional[Mapping[str, Any]],
    prof_row: Optional[Mapping[str, Any]],
    viewer_user_id: Optional[str] = None,
    viewer_vote: int = 0,
    viewer_reactions: Optional[List[str]] = None,
    pii_warnings: Optional[List[Dict[str, str]]] = None,
) -> PublicCommentResponse:
    author_user_id = comment_row.get("author_user_id")
    is_deleted = comment_row.get("deleted_at") is not None
    is_author = bool(
        not is_deleted
        and viewer_user_id is not None
        and author_user_id is not None
        and str(author_user_id) == str(viewer_user_id)
    )

    raw_reactions = comment_row.get("reaction_counts") or "{}"
    try:
        reactions_dict = (
            json.loads(str(raw_reactions))
            if isinstance(raw_reactions, str)
            else dict(raw_reactions)
        )
    except Exception:
        reactions_dict = {}

    author_block = _serialize_comment_author(
        comment_row=comment_row,
        profile_row=profile_row,
        prof_row=prof_row,
    )

    return PublicCommentResponse(
        id=str(comment_row["id"]),
        post_id=str(comment_row["post_id"]),
        parent_comment_id=comment_row.get("parent_comment_id"),
        path=str(comment_row["path"]),
        depth=int(comment_row["depth"]),
        identity_mode="anonymous" if is_deleted else str(comment_row["identity_mode"]),
        author=author_block,
        body="[deleted by author]" if is_deleted else str(comment_row["body"]),
        content_language=str(comment_row["content_language"]),
        is_deleted=is_deleted,
        stats=CommentStatsResponse(
            score=int(comment_row.get("score", 0)),
            upvote_count=int(comment_row.get("upvote_count", 0)),
            downvote_count=int(comment_row.get("downvote_count", 0)),
            reaction_counts=reactions_dict,
        ),
        viewer_context=CommentViewerContext(
            is_author=is_author,
            can_edit=is_author,
            can_delete=is_author,
            viewer_vote=viewer_vote,
            viewer_reactions=viewer_reactions or [],
        ),
        pii_warnings=pii_warnings or [],
        created_at=str(comment_row["created_at"]),
        updated_at=str(comment_row["updated_at"]),
    )
