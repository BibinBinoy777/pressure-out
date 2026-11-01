"""Phase 7 Feed, Ranking, and Discovery schema: user_topic_preferences and ranking indexes.

Revision ID: 0006_phase7_feed
Revises: 0005_phase6_engagement
Create Date: 2026-10-29 12:46:00
"""
from __future__ import annotations

from typing import Any, Sequence, Union

revision: str = "0006_phase7_feed"
down_revision: Union[str, None] = "0005_phase6_engagement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PHASE7_TABLES: tuple[str, ...] = (
    "user_topic_preferences",
)


def _get_connection(bind_or_op: Any = None) -> Any:
    if bind_or_op is not None:
        return bind_or_op
    from alembic import op  # type: ignore[import-not-found]

    return op.get_bind()


def _exec_sql(conn: Any, sql: str) -> None:
    if hasattr(conn, "exec_driver_sql"):
        conn.exec_driver_sql(sql)
        return
    cursor = conn.cursor()
    cursor.execute(sql)


UPGRADE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS user_topic_preferences (
        user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        tag_slug VARCHAR(64) NOT NULL,
        preference_type VARCHAR(16) NOT NULL
            CHECK (preference_type IN ('follow', 'mute')),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (user_id, tag_slug)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_topic_prefs_user ON user_topic_preferences(user_id, preference_type)",
    "CREATE INDEX IF NOT EXISTS idx_posts_feed_popular_rank ON posts(hot_rank_score DESC, created_at DESC, id DESC)",
)


def upgrade(bind: Any = None) -> None:
    """Create Phase 7 `user_topic_preferences` table and feed ranking indexes."""
    conn = _get_connection(bind)
    for stmt in UPGRADE_STATEMENTS:
        _exec_sql(conn, stmt)


def downgrade(bind: Any = None) -> None:
    """Drop Phase 7 tables and indexes."""
    conn = _get_connection(bind)
    _exec_sql(conn, "DROP INDEX IF EXISTS idx_posts_feed_popular_rank")
    for table_name in PHASE7_TABLES:
        _exec_sql(conn, f"DROP TABLE IF EXISTS {table_name}")
