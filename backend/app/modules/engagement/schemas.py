"""Pydantic schemas for Votes, Reactions, and Saved Posts."""
from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field

from app.core.errors import AppError

VALID_REACTION_KINDS: tuple[str, ...] = (
    "relatable",
    "laugh",
    "support",
    "oof",
    "respect",
)


def validate_reaction_kind(kind: str) -> str:
    cleaned = kind.strip().lower()
    if cleaned not in VALID_REACTION_KINDS:
        raise AppError(
            code="INVALID_REACTION",
            message=f"Reaction kind must be one of: {', '.join(VALID_REACTION_KINDS)}.",
            status_code=422,
        )
    return cleaned


class VoteInput(BaseModel):
    value: int = Field(..., description="+1 (upvote), -1 (downvote), or 0 (remove vote)")


class VoteResultResponse(BaseModel):
    target_type: str
    target_id: str
    score: int
    upvote_count: int
    downvote_count: int
    viewer_vote: int


class ReactionToggleInput(BaseModel):
    active: bool = True


class ReactionResultResponse(BaseModel):
    target_type: str
    target_id: str
    reaction_counts: Dict[str, int]
    viewer_reactions: List[str]


class SavePostInput(BaseModel):
    saved: bool = True


class SavePostResponse(BaseModel):
    post_id: str
    saved: bool
