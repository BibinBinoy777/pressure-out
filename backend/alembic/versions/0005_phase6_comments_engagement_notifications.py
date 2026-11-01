"""Phase 6 Comments, Engagement, and Notifications schema: comments, votes, reactions, saved_posts, notifications.

Revision ID: 0005_phase6_engagement
Revises: 0004_phase5_communities
Create Date: 2026-10-29 12:35:00
"""
from __future__ import annotations

from typing import Any, Sequence, Union

revision: str = "0005_phase6_engagement"
down_revision: Union[str, None] = "0004_phase5_communities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PHASE6_TABLES: tuple[str, ...] = (
    "notifications",
    "saved_posts",
    "reactions",
    "votes",
    "comments",
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
    CREATE TABLE IF NOT EXISTS comments (
        id VARCHAR(36) PRIMARY KEY,
        post_id VARCHAR(36) NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        author_user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
        parent_comment_id VARCHAR(36) REFERENCES comments(id) ON DELETE RESTRICT,
        path VARCHAR(512) NOT NULL,
        depth SMALLINT NOT NULL DEFAULT 0 CHECK (depth BETWEEN 0 AND 10),
        identity_mode VARCHAR(24) NOT NULL
            CHECK (identity_mode IN ('pseudonymous', 'anonymous', 'professional')),
        professional_snapshot TEXT,
        is_anonymous_op BOOLEAN NOT NULL DEFAULT FALSE,
        anonymous_thread_label VARCHAR(32),
        body TEXT NOT NULL,
        content_language VARCHAR(16) NOT NULL DEFAULT 'en',
        moderation_status VARCHAR(24) NOT NULL DEFAULT 'published'
            CHECK (moderation_status IN ('published', 'awaiting_review', 'restricted', 'removed')),
        upvote_count INTEGER NOT NULL DEFAULT 0 CHECK (upvote_count >= 0),
        downvote_count INTEGER NOT NULL DEFAULT 0 CHECK (downvote_count >= 0),
        score INTEGER NOT NULL DEFAULT 0,
        reaction_counts TEXT NOT NULL DEFAULT '{}',
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        deleted_at TIMESTAMP WITH TIME ZONE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_comments_post_path ON comments(post_id, path ASC)",
    "CREATE INDEX IF NOT EXISTS idx_comments_post_created ON comments(post_id, created_at ASC, id ASC)",
    "CREATE INDEX IF NOT EXISTS idx_comments_parent ON comments(parent_comment_id, created_at ASC)",
    """
    CREATE TABLE IF NOT EXISTS votes (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        target_type VARCHAR(16) NOT NULL CHECK (target_type IN ('post', 'comment')),
        target_id VARCHAR(36) NOT NULL,
        value SMALLINT NOT NULL CHECK (value IN (-1, 1)),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        UNIQUE (user_id, target_type, target_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_votes_target ON votes(target_type, target_id)",
    """
    CREATE TABLE IF NOT EXISTS reactions (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        target_type VARCHAR(16) NOT NULL CHECK (target_type IN ('post', 'comment')),
        target_id VARCHAR(36) NOT NULL,
        reaction_kind VARCHAR(24) NOT NULL
            CHECK (reaction_kind IN ('relatable', 'laugh', 'support', 'oof', 'respect')),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        UNIQUE (user_id, target_type, target_id, reaction_kind)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_reactions_target ON reactions(target_type, target_id)",
    """
    CREATE TABLE IF NOT EXISTS saved_posts (
        user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id VARCHAR(36) NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (user_id, post_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_saved_posts_user ON saved_posts(user_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id VARCHAR(36) PRIMARY KEY,
        recipient_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        notification_type VARCHAR(32) NOT NULL
            CHECK (notification_type IN (
                'post_reply', 'comment_reply', 'meme_job_ready', 'moderation_notice', 'appeal_update'
            )),
        reference_type VARCHAR(24) NOT NULL,
        reference_id VARCHAR(36) NOT NULL,
        title VARCHAR(160) NOT NULL,
        body_preview VARCHAR(255),
        is_read BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_user_id, is_read, created_at DESC)",
)


def upgrade(bind: Any = None) -> None:
    """Create Phase 6 tables (`comments`, `votes`, `reactions`, `saved_posts`, `notifications`)."""
    conn = _get_connection(bind)
    for stmt in UPGRADE_STATEMENTS:
        _exec_sql(conn, stmt)


def downgrade(bind: Any = None) -> None:
    """Drop Phase 6 tables in reverse dependency order."""
    conn = _get_connection(bind)
    for table_name in PHASE6_TABLES:
        _exec_sql(conn, f"DROP TABLE IF EXISTS {table_name}")
