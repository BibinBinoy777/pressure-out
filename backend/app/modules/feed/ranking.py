"""Explainable, deterministic feed ranking formula with anti-outrage guardrails (Phase 7).

Design Rationale (Section 13 & 14 of Specification):
1. No black-box ML: Every ranking input is transparent, deterministic, and unit-tested.
2. Engagement Inputs:
   - `net_votes = upvote_count - downvote_count`: Captures peer endorsement.
   - `reaction_total = sum(reaction_counts.values())`: Captures supportive/humorous reactions
     (`relatable`, `laugh`, `support`, `oof`, `respect`) weighted at 0.75 points each.
   - `discussion_signal = 1.5 * ln(1 + min(comment_count, 50))`: Rewards active discussion
     while logarithmically capping comment velocity at 50 so 500-comment flamewars cannot
     dominate the `Popular` feed.
3. Anti-Outrage & Anti-Brigading Dampener:
   - High-controversy posts (`upvote_count + downvote_count >= 6` and
     `min(up, down) / max(up, down) >= 0.65`) or "ratioed" outrage posts
     (`comment_count >= 10` and `comment_count > 3 * max(1, upvote_count + reaction_total)`)
     receive a `0.50x` controversy dampener.
4. Constructive & Humour Diversity Bonus:
   - Posts of type `meme`, `story`, or `advice_request` receive a `1.15x` multiplier so
     humour and mutual help stay visible alongside workplace rants.
5. Age Decay (Gravity):
   - Divides positive engagement by `((age_hours + 2.0) ** 1.5)` so fresh discussions
     steadily overtake older posts.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Mapping, Optional

DIVERSITY_POST_TYPES: frozenset[str] = frozenset({"meme", "story", "advice_request"})
GRAVITY_EXPONENT: float = 1.5
BASE_OFFSET_HOURS: float = 2.0


def compute_hot_rank_score(
    *,
    upvote_count: int,
    downvote_count: int,
    reaction_counts: Mapping[str, int],
    comment_count: int,
    post_type: str,
    created_at_iso: str,
    reference_time: Optional[datetime] = None,
) -> float:
    """Compute a deterministic hot-rank score for the `Popular` feed."""
    now = reference_time or datetime.now(timezone.utc)
    try:
        created_dt = datetime.fromisoformat(created_at_iso)
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)
    except Exception:
        created_dt = now

    age_seconds = max(0.0, (now - created_dt).total_seconds())
    age_hours = age_seconds / 3600.0

    net_votes = float(upvote_count - downvote_count)
    reaction_total = sum(max(0, int(v)) for v in reaction_counts.values())
    reaction_points = 0.75 * float(reaction_total)

    capped_comments = min(max(0, int(comment_count)), 50)
    discussion_points = 1.5 * math.log1p(capped_comments)

    raw_engagement = 1.0 + net_votes + reaction_points + discussion_points

    # Anti-outrage / controversy guardrail
    total_votes = max(0, int(upvote_count)) + max(0, int(downvote_count))
    is_polarized_votes = False
    if total_votes >= 6 and max(upvote_count, downvote_count) > 0:
        balance_ratio = min(upvote_count, downvote_count) / max(upvote_count, downvote_count)
        if balance_ratio >= 0.65:
            is_polarized_votes = True

    positive_signals = max(0, int(upvote_count)) + reaction_total
    is_ratioed_outrage = (
        comment_count >= 10 and comment_count > 3 * max(1, positive_signals)
    )

    controversy_multiplier = 0.50 if (is_polarized_votes or is_ratioed_outrage) else 1.0

    # Humour & constructive diversity bonus
    diversity_multiplier = (
        1.15 if post_type in DIVERSITY_POST_TYPES and raw_engagement > 0 else 1.0
    )

    decay_denominator = math.pow(age_hours + BASE_OFFSET_HOURS, GRAVITY_EXPONENT)
    adjusted = raw_engagement * controversy_multiplier * diversity_multiplier

    return round(adjusted / decay_denominator, 6)
