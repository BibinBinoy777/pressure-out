"""Phase 10 Multilingual Experience & Derived Content Translations cache table.

Revision ID: 0009_phase10_translations
Revises: 0008_phase9_moderation
Create Date: 2026-10-29
"""
from __future__ import annotations

from typing import Any

revision = "0009_phase10_translations"
down_revision = "0008_phase9_moderation"
branch_labels = None
depends_on = None


def upgrade(conn: Any) -> None:
    """Create `content_translations` table and lookup indexes."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS content_translations (
            id VARCHAR(36) PRIMARY KEY,
            source_type VARCHAR(16) NOT NULL
                CHECK (source_type IN ('post', 'comment')),
            source_id VARCHAR(36) NOT NULL,
            source_version_hash VARCHAR(64) NOT NULL,
            source_language VARCHAR(16) NOT NULL,
            detected_source_language VARCHAR(16),
            target_locale VARCHAR(16) NOT NULL,
            translated_title VARCHAR(300),
            translated_body TEXT NOT NULL,
            provider_name VARCHAR(64) NOT NULL,
            model_name VARCHAR(64) NOT NULL,
            is_mock_provider INTEGER NOT NULL DEFAULT 0,
            created_at VARCHAR(40) NOT NULL,
            UNIQUE (source_type, source_id, target_locale, source_version_hash, provider_name)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_content_translations_lookup
        ON content_translations(source_type, source_id, target_locale, source_version_hash)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_content_translations_source
        ON content_translations(source_type, source_id, created_at DESC)
        """
    )


def downgrade(conn: Any) -> None:
    """Drop `content_translations` table and indexes."""
    conn.execute("DROP TABLE IF EXISTS content_translations")
