"""Phase 5 Communities schema: communities, community_rules, community_memberships, and starter seed data.

Revision ID: 0004_phase5_communities
Revises: 0003_phase4_posts
Create Date: 2026-10-29 12:22:00
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Sequence, Union

revision: str = "0004_phase5_communities"
down_revision: Union[str, None] = "0003_phase4_posts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PHASE5_TABLES: tuple[str, ...] = (
    "community_memberships",
    "community_rules",
    "communities",
)

STARTER_COMMUNITIES: tuple[tuple[str, str, str, str], ...] = (
    (
        "workplace-rants",
        "Workplace Rants",
        "Unfiltered vents about micromanagement, pointless meetings, scope creep, and daily office chaos.",
        "flame",
    ),
    (
        "corporate-memes",
        "Corporate Memes",
        "Visual humour, standup comedy, sprint retro memes, and AI Meme Studio creations about working life.",
        "laugh",
    ),
    (
        "career-advice",
        "Career Advice",
        "Practical guidance on promotions, role switches, PIPs, difficult managers, and long-term career growth.",
        "compass",
    ),
    (
        "it-software",
        "IT & Software",
        "Discussions for developers, QA, SREs, designers, and product folks navigating tech workplaces.",
        "code",
    ),
    (
        "salary-talk",
        "Salary Talk",
        "Candid conversations about compensation bands, appraisals, bonuses, and offer negotiations.",
        "banknote",
    ),
    (
        "job-hunting",
        "Job Hunting",
        "Interview experiences, resume feedback, ghosting recruiters, and navigating the job market.",
        "briefcase",
    ),
    (
        "freshers-corner",
        "Freshers' Corner",
        "A welcoming space for recent graduates, interns, and first-time employees learning workplace survival.",
        "sparkles",
    ),
    (
        "work-life-balance",
        "Work-Life Balance",
        "Burnout recovery, setting boundaries, RTO mandates, remote work, and protecting personal time.",
        "scale",
    ),
    (
        "startup-life",
        "Startup Life",
        "The highs, lows, equity questions, and fast-paced chaos of working at early-stage and growth startups.",
        "rocket",
    ),
    (
        "office-humour",
        "Office Humour",
        "Funny watercooler stories, absurd corporate jargon, and light-hearted workplace moments.",
        "smile",
    ),
    (
        "resignation-stories",
        "Resignation Stories",
        "Notice period tales, exit interviews, lessons learned, and moving on from toxic or stagnant roles.",
        "door-open",
    ),
    (
        "general-workplace",
        "General Workplace",
        "Open conversations, polls, and everyday experiences from across the world of work.",
        "MessageSquare",
    ),
)

DEFAULT_COMMUNITY_RULES: tuple[tuple[int, str, str], ...] = (
    (
        1,
        "No Doxxing or Private Contact Information",
        "Never post personal phone numbers, email addresses, home addresses, or identify non-public coworkers by full name.",
    ),
    (
        2,
        "Critique Workplace Systems, Not Protected Groups",
        "Harassment, threats of violence, and hate speech are strictly prohibited.",
    ),
    (
        3,
        "Protect Confidential & Client Secrets",
        "Do not share proprietary source code, API keys, credentials, or confidential client documents.",
    ),
    (
        4,
        "Respect Multilingual & Honest Expression",
        "Posts in English, regional languages, and mixed code-switched scripts are welcome. Downvotes do not invalidate personal experiences.",
    ),
)


def _get_connection(bind_or_op: Any = None) -> Any:
    if bind_or_op is not None:
        return bind_or_op
    from alembic import op  # type: ignore[import-not-found]

    return op.get_bind()


def _exec_sql(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    if hasattr(conn, "exec_driver_sql"):
        res = conn.exec_driver_sql(sql, params)
        if res.returns_rows:
            return list(res.fetchall())
        return []
    cursor = conn.cursor()
    cursor.execute(sql, params)
    try:
        return list(cursor.fetchall())
    except Exception:
        return []


UPGRADE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS communities (
        id VARCHAR(36) PRIMARY KEY,
        slug VARCHAR(64) NOT NULL UNIQUE,
        name VARCHAR(80) NOT NULL,
        description TEXT NOT NULL,
        icon_name VARCHAR(64),
        primary_language VARCHAR(16) NOT NULL DEFAULT 'en',
        status VARCHAR(24) NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'restricted', 'archived')),
        member_count INTEGER NOT NULL DEFAULT 0 CHECK (member_count >= 0),
        post_count INTEGER NOT NULL DEFAULT 0 CHECK (post_count >= 0),
        created_by_user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_communities_status_members ON communities(status, member_count DESC)",
    """
    CREATE TABLE IF NOT EXISTS community_rules (
        id VARCHAR(36) PRIMARY KEY,
        community_id VARCHAR(36) NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
        rule_number SMALLINT NOT NULL CHECK (rule_number BETWEEN 1 AND 25),
        title VARCHAR(120) NOT NULL,
        description TEXT NOT NULL,
        UNIQUE (community_id, rule_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS community_memberships (
        user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        community_id VARCHAR(36) NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
        role VARCHAR(24) NOT NULL DEFAULT 'member'
            CHECK (role IN ('member', 'moderator')),
        status VARCHAR(24) NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'banned')),
        joined_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (user_id, community_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_comm_memberships_community ON community_memberships(community_id, role, status)",
)


def seed_starter_communities(conn: Any) -> None:
    """Idempotently seed the 12 core workplace communities and their default rules."""
    now_str = datetime.now(timezone.utc).isoformat()
    is_pg = getattr(getattr(conn, "dialect", None), "name", "").startswith("postgresql")

    for slug, name, description, icon_name in STARTER_COMMUNITIES:
        check_sql = (
            "SELECT id FROM communities WHERE slug = %s"
            if is_pg
            else "SELECT id FROM communities WHERE slug = ?"
        )
        existing = _exec_sql(conn, check_sql, (slug,))
        if existing:
            continue

        comm_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"pressure-out.community.{slug}"))
        ins_comm_sql = (
            """
            INSERT INTO communities (
                id, slug, name, description, icon_name, primary_language,
                status, member_count, post_count, created_by_user_id, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, 'en', 'active', 0, 0, NULL, %s, %s)
            """
            if is_pg
            else """
            INSERT INTO communities (
                id, slug, name, description, icon_name, primary_language,
                status, member_count, post_count, created_by_user_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'en', 'active', 0, 0, NULL, ?, ?)
            """
        )
        _exec_sql(conn, ins_comm_sql, (comm_id, slug, name, description, icon_name, now_str, now_str))

        for rule_num, r_title, r_desc in DEFAULT_COMMUNITY_RULES:
            rule_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"pressure-out.rule.{slug}.{rule_num}"))
            ins_rule_sql = (
                """
                INSERT INTO community_rules (id, community_id, rule_number, title, description)
                VALUES (%s, %s, %s, %s, %s)
                """
                if is_pg
                else """
                INSERT INTO community_rules (id, community_id, rule_number, title, description)
                VALUES (?, ?, ?, ?, ?)
                """
            )
            _exec_sql(conn, ins_rule_sql, (rule_id, comm_id, rule_num, r_title, r_desc))


def upgrade(bind: Any = None) -> None:
    """Create Phase 5 tables and seed starter communities."""
    conn = _get_connection(bind)
    for stmt in UPGRADE_STATEMENTS:
        _exec_sql(conn, stmt)
    seed_starter_communities(conn)


def downgrade(bind: Any = None) -> None:
    """Drop Phase 5 tables in reverse dependency order."""
    conn = _get_connection(bind)
    for table_name in PHASE5_TABLES:
        _exec_sql(conn, f"DROP TABLE IF EXISTS {table_name}")
