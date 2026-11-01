"""Phase 9 Trust, Safety, Reporting, Moderation, Appeals, User Blocks & Immutable Audit Trail.

Revision ID: 0008_phase9_moderation
Revises: 0007_phase8_memes
Create Date: 2026-10-29
"""
from __future__ import annotations

from typing import Any

revision = "0008_phase9_moderation"
down_revision = "0007_phase8_memes"
branch_labels = None
depends_on = None


def upgrade(conn: Any) -> None:
    """Create Phase 9 tables, indexes, and append-only audit triggers."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id VARCHAR(36) PRIMARY KEY,
            reporter_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            target_type VARCHAR(16) NOT NULL
                CHECK (target_type IN ('post', 'comment', 'profile', 'meme_asset')),
            target_id VARCHAR(36) NOT NULL,
            community_slug VARCHAR(64),
            content_language VARCHAR(16) NOT NULL DEFAULT 'en',
            reason_code VARCHAR(32) NOT NULL
                CHECK (reason_code IN (
                    'doxxing_pii', 'harassment', 'threat', 'impersonation',
                    'spam', 'hate_speech', 'confidential_ip', 'misleading_allegation', 'other'
                )),
            details TEXT CHECK (details IS NULL OR length(details) <= 1000),
            priority_score INTEGER NOT NULL DEFAULT 1,
            status VARCHAR(32) NOT NULL DEFAULT 'open'
                CHECK (status IN (
                    'open', 'in_review', 'escalated_language_specialist',
                    'resolved_actioned', 'resolved_dismissed'
                )),
            resolved_by_action_id VARCHAR(36),
            created_at VARCHAR(40) NOT NULL,
            updated_at VARCHAR(40) NOT NULL,
            UNIQUE (reporter_user_id, target_type, target_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reports_queue ON reports(status, priority_score DESC, created_at ASC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reports_target_velocity ON reports(target_type, target_id, reason_code, created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reports_reporter ON reports(reporter_user_id, created_at DESC)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS moderation_actions (
            id VARCHAR(36) PRIMARY KEY,
            moderator_user_id VARCHAR(36) REFERENCES users(id) ON DELETE RESTRICT,
            actor_type VARCHAR(24) NOT NULL DEFAULT 'moderator'
                CHECK (actor_type IN ('moderator', 'admin', 'system_auto_hold')),
            target_type VARCHAR(16) NOT NULL
                CHECK (target_type IN ('post', 'comment', 'user', 'meme_asset')),
            target_id VARCHAR(36) NOT NULL,
            affected_user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
            community_slug VARCHAR(64),
            action_type VARCHAR(32) NOT NULL
                CHECK (action_type IN (
                    'dismiss_reports', 'redact_pii', 'restrict_visibility',
                    'place_under_review', 'remove_content', 'restore_content',
                    'escalate_language_specialist', 'user_cooldown',
                    'user_suspend', 'restore_user'
                )),
            reason_code VARCHAR(32) NOT NULL
                CHECK (reason_code IN (
                    'doxxing_pii', 'harassment', 'threat', 'impersonation',
                    'spam', 'hate_speech', 'confidential_ip', 'misleading_allegation',
                    'other', 'no_violation_found', 'appeal_overturned',
                    'auto_velocity_hold', 'language_specialist_needed'
                )),
            internal_note TEXT NOT NULL CHECK (length(internal_note) BETWEEN 3 AND 1000),
            public_explanation VARCHAR(500) NOT NULL,
            previous_state VARCHAR(64),
            new_state VARCHAR(64),
            is_appealable INTEGER NOT NULL DEFAULT 1,
            created_at VARCHAR(40) NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mod_actions_target ON moderation_actions(target_type, target_id, created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mod_actions_affected_user ON moderation_actions(affected_user_id, created_at DESC)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS moderation_appeals (
            id VARCHAR(36) PRIMARY KEY,
            moderation_action_id VARCHAR(36) NOT NULL UNIQUE REFERENCES moderation_actions(id) ON DELETE CASCADE,
            appellant_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            appeal_statement TEXT NOT NULL CHECK (length(appeal_statement) BETWEEN 10 AND 2000),
            status VARCHAR(24) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'accepted', 'rejected')),
            reviewed_by_user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
            decision_reason_code VARCHAR(32),
            review_decision_note TEXT,
            created_at VARCHAR(40) NOT NULL,
            resolved_at VARCHAR(40)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mod_appeals_status ON moderation_appeals(status, created_at ASC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mod_appeals_appellant ON moderation_appeals(appellant_user_id, created_at DESC)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_blocks (
            blocker_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            blocked_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            block_mode VARCHAR(16) NOT NULL DEFAULT 'block'
                CHECK (block_mode IN ('block', 'mute')),
            created_at VARCHAR(40) NOT NULL,
            PRIMARY KEY (blocker_user_id, blocked_user_id),
            CHECK (blocker_user_id != blocked_user_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_blocks_blocker ON user_blocks(blocker_user_id, block_mode)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_blocks_blocked ON user_blocks(blocked_user_id, block_mode)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id VARCHAR(36) PRIMARY KEY,
            actor_user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
            actor_role VARCHAR(24) NOT NULL,
            event_category VARCHAR(32) NOT NULL
                CHECK (event_category IN (
                    'moderation', 'appeal_review', 'auto_protective_hold',
                    'admin_role_change', 'account_security', 'legal_preservation'
                )),
            action_name VARCHAR(64) NOT NULL,
            target_type VARCHAR(32) NOT NULL,
            target_id VARCHAR(36),
            reason_code VARCHAR(64) NOT NULL,
            redacted_metadata TEXT NOT NULL DEFAULT '{}',
            correlation_id VARCHAR(64) NOT NULL,
            created_at VARCHAR(40) NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at DESC, event_category, action_name)"
    )

    # Database-level append-only triggers for audit_events
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_update
        BEFORE UPDATE ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'AUDIT_EVENTS_IMMUTABLE: Historical audit events are append-only and cannot be modified.');
        END;
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_delete
        BEFORE DELETE ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'AUDIT_EVENTS_IMMUTABLE: Historical audit events are append-only and cannot be deleted.');
        END;
        """
    )


def downgrade(conn: Any) -> None:
    """Drop Phase 9 triggers and tables in reverse dependency order."""
    conn.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_delete")
    conn.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_update")
    conn.execute("DROP TABLE IF EXISTS audit_events")
    conn.execute("DROP TABLE IF EXISTS user_blocks")
    conn.execute("DROP TABLE IF EXISTS moderation_appeals")
    conn.execute("DROP TABLE IF EXISTS moderation_actions")
    conn.execute("DROP TABLE IF EXISTS reports")
