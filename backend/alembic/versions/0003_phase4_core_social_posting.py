"""Phase 4 Core Social Posting schema: posts, polls, poll_options, poll_votes, tags, post_tags.

Revision ID: 0003_phase4_posts
Revises: 0002_phase3_identity
Create Date: 2026-10-29 12:11:00
"""
from __future__ import annotations

from typing import Any, Sequence, Union

revision: str = "0003_phase4_posts"
down_revision: Union[str, None] = "0002_phase3_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PHASE4_TABLES: tuple[str, ...] = (
    "post_tags",
    "tags",
    "poll_votes",
    "poll_options",
    "polls",
    "posts",
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
    CREATE TABLE IF NOT EXISTS posts (
        id VARCHAR(36) PRIMARY KEY,
        author_user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
        community_slug VARCHAR(64) NOT NULL DEFAULT 'general-workplace',
        post_type VARCHAR(32) NOT NULL
            CHECK (post_type IN (
                'discussion', 'question', 'rant', 'story',
                'meme', 'poll', 'advice_request', 'workplace_experience'
            )),
        identity_mode VARCHAR(24) NOT NULL
            CHECK (identity_mode IN ('pseudonymous', 'anonymous', 'professional')),
        professional_snapshot TEXT,
        anonymous_alias VARCHAR(32) NOT NULL DEFAULT 'Anonymous Member',
        title VARCHAR(220) NOT NULL,
        body TEXT NOT NULL,
        meme_asset_id VARCHAR(36),
        content_language VARCHAR(16) NOT NULL DEFAULT 'en',
        moderation_status VARCHAR(24) NOT NULL DEFAULT 'published'
            CHECK (moderation_status IN ('draft', 'published', 'awaiting_review', 'restricted', 'removed')),
        upvote_count INTEGER NOT NULL DEFAULT 0 CHECK (upvote_count >= 0),
        downvote_count INTEGER NOT NULL DEFAULT 0 CHECK (downvote_count >= 0),
        score INTEGER NOT NULL DEFAULT 0,
        reaction_counts TEXT NOT NULL DEFAULT '{}',
        comment_count INTEGER NOT NULL DEFAULT 0 CHECK (comment_count >= 0),
        hot_rank_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        deleted_at TIMESTAMP WITH TIME ZONE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_posts_feed_latest ON posts(created_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_posts_author_public ON posts(author_user_id, identity_mode, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_posts_community_slug ON posts(community_slug, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_posts_language ON posts(content_language, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS polls (
        post_id VARCHAR(36) PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
        allows_multiple BOOLEAN NOT NULL DEFAULT FALSE,
        closes_at TIMESTAMP WITH TIME ZONE,
        total_votes INTEGER NOT NULL DEFAULT 0 CHECK (total_votes >= 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS poll_options (
        id VARCHAR(36) PRIMARY KEY,
        poll_post_id VARCHAR(36) NOT NULL REFERENCES polls(post_id) ON DELETE CASCADE,
        position SMALLINT NOT NULL CHECK (position BETWEEN 1 AND 8),
        option_text VARCHAR(140) NOT NULL,
        vote_count INTEGER NOT NULL DEFAULT 0 CHECK (vote_count >= 0),
        UNIQUE (poll_post_id, position)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_poll_options_poll ON poll_options(poll_post_id, position ASC)",
    """
    CREATE TABLE IF NOT EXISTS poll_votes (
        poll_post_id VARCHAR(36) NOT NULL REFERENCES polls(post_id) ON DELETE CASCADE,
        option_id VARCHAR(36) NOT NULL REFERENCES poll_options(id) ON DELETE CASCADE,
        user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (poll_post_id, user_id, option_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tags (
        id VARCHAR(36) PRIMARY KEY,
        slug VARCHAR(64) NOT NULL UNIQUE,
        display_name VARCHAR(64) NOT NULL,
        usage_count INTEGER NOT NULL DEFAULT 0 CHECK (usage_count >= 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS post_tags (
        post_id VARCHAR(36) NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        tag_id VARCHAR(36) NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
        PRIMARY KEY (post_id, tag_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_post_tags_tag_id ON post_tags(tag_id, post_id)",
)


def upgrade(bind: Any = None) -> None:
    """Create Phase 4 Core Social Posting tables (`posts`, `polls`, `poll_options`, `poll_votes`, `tags`, `post_tags`)."""
    conn = _get_connection(bind)
    for stmt in UPGRADE_STATEMENTS:
        _exec_sql(conn, stmt)


def downgrade(bind: Any = None) -> None:
    """Drop Phase 4 Core Social Posting tables in reverse dependency order."""
    conn = _get_connection(bind)
    for table_name in PHASE4_TABLES:
        _exec_sql(conn, f"DROP TABLE IF EXISTS {table_name}")
