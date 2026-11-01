"""Phase 3 Identity and Privacy schema: users, sessions, public & professional profiles, recovery tokens.

Revision ID: 0002_phase3_identity
Revises: 0001_phase2_foundation
Create Date: 2026-10-29 11:36:00
"""
from __future__ import annotations

from typing import Any, Sequence, Union

revision: str = "0002_phase3_identity"
down_revision: Union[str, None] = "0001_phase2_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PHASE3_TABLES: tuple[str, ...] = (
    "password_recovery_tokens",
    "professional_profiles",
    "public_profiles",
    "user_sessions",
    "users",
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


PG_UPGRADE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id VARCHAR(36) PRIMARY KEY,
        email_hash VARCHAR(64) UNIQUE,
        email_encrypted BYTEA,
        recovery_code_hash VARCHAR(255),
        password_hash VARCHAR(255) NOT NULL,
        account_status VARCHAR(24) NOT NULL DEFAULT 'active'
            CHECK (account_status IN ('active', 'cooldown', 'suspended', 'deleted')),
        role VARCHAR(24) NOT NULL DEFAULT 'member'
            CHECK (role IN ('member', 'global_moderator', 'admin')),
        default_identity_mode VARCHAR(24) NOT NULL DEFAULT 'pseudonymous'
            CHECK (default_identity_mode IN ('pseudonymous', 'anonymous', 'professional')),
        preferred_ui_locale VARCHAR(16) NOT NULL DEFAULT 'en',
        preferred_content_locales TEXT NOT NULL DEFAULT '["en"]',
        cooldown_until TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        deleted_at TIMESTAMP WITH TIME ZONE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_sessions (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash VARCHAR(64) NOT NULL UNIQUE,
        csrf_secret VARCHAR(64) NOT NULL,
        user_agent_summary VARCHAR(255),
        ip_subnet_hash VARCHAR(64),
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        revoked_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        last_active_at TIMESTAMP WITH TIME ZONE NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_sessions_token_hash ON user_sessions(token_hash)",
    """
    CREATE TABLE IF NOT EXISTS public_profiles (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        handle VARCHAR(32) NOT NULL UNIQUE,
        handle_normalized VARCHAR(32) NOT NULL UNIQUE,
        display_name VARCHAR(64),
        bio TEXT,
        avatar_storage_key VARCHAR(255),
        show_karma BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_public_profiles_handle_norm ON public_profiles(handle_normalized)",
    """
    CREATE TABLE IF NOT EXISTS professional_profiles (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        role_title VARCHAR(80) NOT NULL,
        industry VARCHAR(64) NOT NULL,
        experience_band VARCHAR(16) NOT NULL
            CHECK (experience_band IN ('fresher_0_1', 'junior_1_3', 'mid_3_6', 'senior_6_10', 'lead_10_plus')),
        region_label VARCHAR(64),
        is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS password_recovery_tokens (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash VARCHAR(64) NOT NULL UNIQUE,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        used_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL
    )
    """,
)


def upgrade(bind: Any = None) -> None:
    """Create Phase 3 Identity & Privacy tables (`users`, `user_sessions`, `public_profiles`, `professional_profiles`, `password_recovery_tokens`)."""
    conn = _get_connection(bind)
    for stmt in PG_UPGRADE_STATEMENTS:
        _exec_sql(conn, stmt)


def downgrade(bind: Any = None) -> None:
    """Drop Phase 3 Identity & Privacy tables in reverse dependency order."""
    conn = _get_connection(bind)
    for table_name in PHASE3_TABLES:
        _exec_sql(conn, f"DROP TABLE IF EXISTS {table_name}")
