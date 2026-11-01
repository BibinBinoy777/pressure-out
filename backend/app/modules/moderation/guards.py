"""Lightweight account-restriction and user-block guard helpers (zero circular imports)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.core.errors import AppError


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def check_user_can_contribute(session: Any, user_dict: dict[str, Any]) -> None:
    """Verify the authenticated user is not currently suspended or in an active cooldown."""
    user_id = str(user_dict["id"])
    rows = await session.execute(
        "SELECT account_status, cooldown_until FROM users WHERE id = ?",
        (user_id,),
    )
    if not rows:
        return
    status, cooldown_until = str(rows[0][0]), rows[0][1]
    if status == "suspended":
        raise AppError(
            code="ACCOUNT_RESTRICTED",
            message="Your account is currently suspended from posting or commenting. Visit /moderation/appeals to review or appeal this decision.",
            status_code=403,
        )
    if status == "cooldown" and cooldown_until:
        now_str = _now_iso()
        if str(cooldown_until) > now_str:
            raise AppError(
                code="ACCOUNT_RESTRICTED",
                message=f"Your account is on a temporary posting cooldown until {cooldown_until}.",
                status_code=403,
            )
        else:
            await session.execute(
                "UPDATE users SET account_status = 'active', cooldown_until = NULL WHERE id = ? AND account_status = 'cooldown'",
                (user_id,),
            )


async def is_interaction_blocked(
    session: Any, user_a_id: Optional[str], user_b_id: Optional[str]
) -> bool:
    """Return True if either user has an active 'block' against the other."""
    if not user_a_id or not user_b_id or str(user_a_id) == str(user_b_id):
        return False
    rows = await session.execute(
        """
        SELECT 1 FROM user_blocks
        WHERE block_mode = 'block'
          AND (
              (blocker_user_id = ? AND blocked_user_id = ?)
              OR (blocker_user_id = ? AND blocked_user_id = ?)
          )
        LIMIT 1
        """,
        (str(user_a_id), str(user_b_id), str(user_b_id), str(user_a_id)),
    )
    return bool(rows)


async def should_suppress_notification(
    session: Any, recipient_user_id: Optional[str], actor_user_id: Optional[str]
) -> bool:
    """Return True if `recipient_user_id` has blocked or muted `actor_user_id` (or vice versa for block)."""
    if not recipient_user_id or not actor_user_id or str(recipient_user_id) == str(actor_user_id):
        return False
    rows = await session.execute(
        """
        SELECT 1 FROM user_blocks
        WHERE (blocker_user_id = ? AND blocked_user_id = ?)
           OR (blocker_user_id = ? AND blocked_user_id = ? AND block_mode = 'block')
        LIMIT 1
        """,
        (
            str(recipient_user_id),
            str(actor_user_id),
            str(actor_user_id),
            str(recipient_user_id),
        ),
    )
    return bool(rows)
