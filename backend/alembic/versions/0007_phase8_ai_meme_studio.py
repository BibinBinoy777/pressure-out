"""Phase 8 AI Meme Studio: templates, assets, jobs, and AI provider usage ledger.

Revision ID: 0007_phase8_memes
Revises: 0006_phase7_feed
Create Date: 2026-10-29
"""
from __future__ import annotations

import json
from typing import Any

revision = "0007_phase8_memes"
down_revision = "0006_phase7_feed"
branch_labels = None
depends_on = None

SEEDED_TEMPLATES = [
    {
        "id": "tmpl-01-friday-deploy",
        "slug": "friday-455pm-deploy",
        "name": "Friday 4:55 PM Deploy",
        "description": "Two-panel split contrasting calm weekend plans with a sudden production incident or last-minute manager request.",
        "category": "engineering",
        "storage_key": "templates/friday-455pm-deploy.png",
        "width": 800,
        "height": 800,
        "aspect_ratio": "1:1",
        "text_regions": [
            {
                "id": "top",
                "label": "Top Caption (Expectation / Calm)",
                "x": 40,
                "y": 36,
                "width": 720,
                "height": 180,
                "align": "center",
                "max_chars": 160,
                "default_font_size": 36,
                "min_font_size": 18,
            },
            {
                "id": "bottom",
                "label": "Bottom Caption (Reality / Chaos)",
                "x": 40,
                "y": 584,
                "width": 720,
                "height": 180,
                "align": "center",
                "max_chars": 160,
                "default_font_size": 36,
                "min_font_size": 18,
            },
        ],
        "default_typography": {
            "text_color": "#FFFFFF",
            "stroke_color": "#0F172A",
            "stroke_width": 4,
            "uppercase": False,
        },
        "default_alt_text": "Two-panel workplace meme contrasting peaceful weekend plans with a Friday 4:55 PM surprise task.",
        "category_tags": ["engineering", "on-call", "friday", "deadlines"],
        "license_info": "CC0-1.0 / Pressure Out Original Programmatic Artwork",
    },
    {
        "id": "tmpl-02-could-have-been-email",
        "slug": "could-have-been-an-email",
        "name": "This Meeting Could Have Been an Email",
        "description": "Classic top-and-bottom banner meme illustrating an exhausting 60-minute calendar invite for a 2-sentence status update.",
        "category": "meetings",
        "storage_key": "templates/could-have-been-an-email.png",
        "width": 800,
        "height": 800,
        "aspect_ratio": "1:1",
        "text_regions": [
            {
                "id": "top",
                "label": "Top Setup",
                "x": 40,
                "y": 32,
                "width": 720,
                "height": 160,
                "align": "center",
                "max_chars": 150,
                "default_font_size": 36,
                "min_font_size": 18,
            },
            {
                "id": "bottom",
                "label": "Bottom Punchline",
                "x": 40,
                "y": 608,
                "width": 720,
                "height": 160,
                "align": "center",
                "max_chars": 150,
                "default_font_size": 36,
                "min_font_size": 18,
            },
        ],
        "default_typography": {
            "text_color": "#FFFFFF",
            "stroke_color": "#0F172A",
            "stroke_width": 4,
            "uppercase": False,
        },
        "default_alt_text": "Workplace meeting meme showing a calendar block that could have been a short email.",
        "category_tags": ["meetings", "calendar", "corporate-life"],
        "license_info": "CC0-1.0 / Pressure Out Original Programmatic Artwork",
    },
    {
        "id": "tmpl-03-scope-creep-highway",
        "slug": "scope-creep-exit-ramp",
        "name": "Scope Creep Exit Ramp",
        "description": "Decision fork contrasting 'Stick to original sprint scope' vs. 'Add 4 unestimated features before launch'.",
        "category": "product",
        "storage_key": "templates/scope-creep-exit-ramp.png",
        "width": 800,
        "height": 800,
        "aspect_ratio": "1:1",
        "text_regions": [
            {
                "id": "top",
                "label": "Sensible Path (Left Lane)",
                "x": 40,
                "y": 36,
                "width": 720,
                "height": 160,
                "align": "center",
                "max_chars": 150,
                "default_font_size": 34,
                "min_font_size": 18,
            },
            {
                "id": "bottom",
                "label": "Chaotic Detour (Sharp Exit)",
                "x": 40,
                "y": 600,
                "width": 720,
                "height": 164,
                "align": "center",
                "max_chars": 150,
                "default_font_size": 34,
                "min_font_size": 18,
            },
            {
                "id": "custom_badge",
                "label": "Center Badge / Label (Optional)",
                "x": 200,
                "y": 360,
                "width": 400,
                "height": 90,
                "align": "center",
                "max_chars": 80,
                "default_font_size": 26,
                "min_font_size": 16,
            },
        ],
        "default_typography": {
            "text_color": "#FFFFFF",
            "stroke_color": "#0F172A",
            "stroke_width": 4,
            "uppercase": False,
        },
        "default_alt_text": "Workplace decision fork meme contrasting realistic project scope with sudden scope creep.",
        "category_tags": ["product", "sprint", "scope-creep", "management"],
        "license_info": "CC0-1.0 / Pressure Out Original Programmatic Artwork",
    },
    {
        "id": "tmpl-04-salary-pizza-party",
        "slug": "record-profits-pizza-party",
        "name": "Record Profits vs. Pizza Party",
        "description": "Satirical announcement board contrasting 'Record quarterly revenue' with 'Two slices of lukewarm pepperoni in Conference Room B'.",
        "category": "compensation",
        "storage_key": "templates/record-profits-pizza-party.png",
        "width": 800,
        "height": 800,
        "aspect_ratio": "1:1",
        "text_regions": [
            {
                "id": "top",
                "label": "Executive Announcement",
                "x": 40,
                "y": 36,
                "width": 720,
                "height": 165,
                "align": "center",
                "max_chars": 160,
                "default_font_size": 34,
                "min_font_size": 18,
            },
            {
                "id": "bottom",
                "label": "Actual Reward",
                "x": 40,
                "y": 596,
                "width": 720,
                "height": 168,
                "align": "center",
                "max_chars": 160,
                "default_font_size": 34,
                "min_font_size": 18,
            },
        ],
        "default_typography": {
            "text_color": "#FFFFFF",
            "stroke_color": "#0F172A",
            "stroke_width": 4,
            "uppercase": False,
        },
        "default_alt_text": "Workplace appreciation meme comparing record company profits with an office pizza party.",
        "category_tags": ["compensation", "appraisal", "pizza-party", "corporate-memes"],
        "license_info": "CC0-1.0 / Pressure Out Original Programmatic Artwork",
    },
    {
        "id": "tmpl-05-entry-level-10yrs",
        "slug": "entry-level-ten-years-experience",
        "name": "Entry-Level Role: 10 Years Required",
        "description": "Job hunting card highlighting absurd recruiter requirements for junior roles.",
        "category": "job-hunting",
        "storage_key": "templates/entry-level-ten-years-experience.png",
        "width": 800,
        "height": 800,
        "aspect_ratio": "1:1",
        "text_regions": [
            {
                "id": "top",
                "label": "Job Title & Pay Band",
                "x": 40,
                "y": 36,
                "width": 720,
                "height": 165,
                "align": "center",
                "max_chars": 160,
                "default_font_size": 34,
                "min_font_size": 18,
            },
            {
                "id": "bottom",
                "label": "Mandatory Requirements List",
                "x": 40,
                "y": 596,
                "width": 720,
                "height": 168,
                "align": "center",
                "max_chars": 160,
                "default_font_size": 34,
                "min_font_size": 18,
            },
        ],
        "default_typography": {
            "text_color": "#FFFFFF",
            "stroke_color": "#0F172A",
            "stroke_width": 4,
            "uppercase": False,
        },
        "default_alt_text": "Job listing meme contrasting an entry-level title with ten years of required experience.",
        "category_tags": ["job-hunting", "interviews", "freshers", "recruiting"],
        "license_info": "CC0-1.0 / Pressure Out Original Programmatic Artwork",
    },
    {
        "id": "tmpl-06-urgent-ping-no-context",
        "slug": "hi-with-no-context",
        "name": "The 'Hi' Message With Zero Context",
        "description": "Chat bubble suspense card when a coworker sends just 'Hi' or 'Quick question?' and goes typing for 12 minutes.",
        "category": "communication",
        "storage_key": "templates/hi-with-no-context.png",
        "width": 800,
        "height": 800,
        "aspect_ratio": "1:1",
        "text_regions": [
            {
                "id": "top",
                "label": "Incoming Ping",
                "x": 40,
                "y": 36,
                "width": 720,
                "height": 165,
                "align": "center",
                "max_chars": 160,
                "default_font_size": 36,
                "min_font_size": 18,
            },
            {
                "id": "bottom",
                "label": "Internal Reaction",
                "x": 40,
                "y": 596,
                "width": 720,
                "height": 168,
                "align": "center",
                "max_chars": 160,
                "default_font_size": 36,
                "min_font_size": 18,
            },
        ],
        "default_typography": {
            "text_color": "#FFFFFF",
            "stroke_color": "#0F172A",
            "stroke_width": 4,
            "uppercase": False,
        },
        "default_alt_text": "Chat notification meme showing a coworker sending 'Hi' with no follow-up context.",
        "category_tags": ["communication", "slack", "teams", "remote-work"],
        "license_info": "CC0-1.0 / Pressure Out Original Programmatic Artwork",
    },
]


def upgrade(conn: Any) -> None:
    """Create Phase 8 AI Meme Studio tables and seed original workplace templates."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meme_templates (
            id VARCHAR(36) PRIMARY KEY,
            slug VARCHAR(80) NOT NULL UNIQUE,
            name VARCHAR(120) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category VARCHAR(48) NOT NULL DEFAULT 'general',
            storage_key VARCHAR(255) NOT NULL,
            width INTEGER NOT NULL CHECK (width > 0),
            height INTEGER NOT NULL CHECK (height > 0),
            aspect_ratio VARCHAR(16) NOT NULL DEFAULT '1:1',
            text_regions TEXT NOT NULL DEFAULT '[]',
            default_typography TEXT NOT NULL DEFAULT '{}',
            default_alt_text VARCHAR(255) NOT NULL,
            category_tags TEXT NOT NULL DEFAULT '[]',
            license_info VARCHAR(255) NOT NULL DEFAULT 'CC0-1.0 / Pressure Out Original',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at VARCHAR(40) NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_meme_templates_category ON meme_templates(category, is_active)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meme_assets (
            id VARCHAR(36) PRIMARY KEY,
            owner_user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
            source_type VARCHAR(24) NOT NULL
                CHECK (source_type IN ('template_render', 'ai_generated', 'remix')),
            template_id VARCHAR(36) REFERENCES meme_templates(id) ON DELETE SET NULL,
            storage_key VARCHAR(255) NOT NULL UNIQUE,
            mime_type VARCHAR(32) NOT NULL
                CHECK (mime_type IN ('image/png', 'image/webp', 'image/jpeg')),
            file_size_bytes INTEGER NOT NULL
                CHECK (file_size_bytes > 0 AND file_size_bytes <= 5242880),
            sha256_hash VARCHAR(64) NOT NULL,
            width INTEGER NOT NULL CHECK (width > 0 AND width <= 4096),
            height INTEGER NOT NULL CHECK (height > 0 AND height <= 4096),
            captions_json TEXT NOT NULL DEFAULT '[]',
            caption_language VARCHAR(16) NOT NULL DEFAULT 'en',
            alt_text VARCHAR(500) NOT NULL,
            safety_status VARCHAR(24) NOT NULL DEFAULT 'approved'
                CHECK (safety_status IN ('pending', 'approved', 'rejected')),
            is_published INTEGER NOT NULL DEFAULT 0,
            expires_at VARCHAR(40),
            created_at VARCHAR(40) NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_meme_assets_owner ON meme_assets(owner_user_id, created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_meme_assets_cleanup ON meme_assets(is_published, expires_at)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meme_jobs (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            idempotency_key VARCHAR(64) NOT NULL,
            job_type VARCHAR(24) NOT NULL
                CHECK (job_type IN ('template_render', 'ai_caption', 'ai_image')),
            template_id VARCHAR(36) REFERENCES meme_templates(id) ON DELETE SET NULL,
            user_prompt TEXT CHECK (length(user_prompt) <= 500),
            prompt_language VARCHAR(16) NOT NULL DEFAULT 'en',
            style_tone VARCHAR(32) NOT NULL DEFAULT 'sarcastic',
            options_json TEXT NOT NULL DEFAULT '{}',
            status VARCHAR(24) NOT NULL DEFAULT 'queued'
                CHECK (status IN ('draft', 'queued', 'generating', 'validating', 'ready', 'failed', 'cancelled')),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 5),
            provider_name VARCHAR(64),
            model_version VARCHAR(64),
            is_mock_provider INTEGER NOT NULL DEFAULT 0,
            caption_suggestions TEXT,
            result_asset_id VARCHAR(36) REFERENCES meme_assets(id) ON DELETE SET NULL,
            error_code VARCHAR(64),
            error_message_safe VARCHAR(255),
            estimated_cost_micros INTEGER NOT NULL DEFAULT 0,
            created_at VARCHAR(40) NOT NULL,
            updated_at VARCHAR(40) NOT NULL,
            started_at VARCHAR(40),
            completed_at VARCHAR(40),
            UNIQUE (user_id, idempotency_key)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_meme_jobs_queue ON meme_jobs(status, created_at ASC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_meme_jobs_user_daily ON meme_jobs(user_id, job_type, created_at DESC)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_provider_usage (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
            meme_job_id VARCHAR(36) REFERENCES meme_jobs(id) ON DELETE SET NULL,
            operation_type VARCHAR(32) NOT NULL
                CHECK (operation_type IN ('ai_caption', 'ai_image', 'translation')),
            provider_name VARCHAR(64) NOT NULL,
            model_name VARCHAR(64) NOT NULL,
            is_mock INTEGER NOT NULL DEFAULT 0,
            input_units INTEGER NOT NULL DEFAULT 0,
            output_units INTEGER NOT NULL DEFAULT 0,
            estimated_cost_micros INTEGER NOT NULL DEFAULT 0,
            currency VARCHAR(8) NOT NULL DEFAULT 'USD',
            latency_ms INTEGER NOT NULL DEFAULT 0,
            succeeded INTEGER NOT NULL DEFAULT 1,
            created_at VARCHAR(40) NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_usage_daily_spend ON ai_provider_usage(created_at DESC, operation_type)"
    )

    # Seed original copyright-safe templates idempotently
    for tmpl in SEEDED_TEMPLATES:
        conn.execute(
            """
            INSERT OR IGNORE INTO meme_templates (
                id, slug, name, description, category, storage_key,
                width, height, aspect_ratio, text_regions, default_typography,
                default_alt_text, category_tags, license_info, is_active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, '2026-10-29T00:00:00+00:00')
            """,
            (
                tmpl["id"],
                tmpl["slug"],
                tmpl["name"],
                tmpl["description"],
                tmpl["category"],
                tmpl["storage_key"],
                tmpl["width"],
                tmpl["height"],
                tmpl["aspect_ratio"],
                json.dumps(tmpl["text_regions"], ensure_ascii=False),
                json.dumps(tmpl["default_typography"], ensure_ascii=False),
                tmpl["default_alt_text"],
                json.dumps(tmpl["category_tags"], ensure_ascii=False),
                tmpl["license_info"],
            ),
        )


def downgrade(conn: Any) -> None:
    """Drop Phase 8 AI Meme Studio tables in reverse dependency order."""
    conn.execute("DROP TABLE IF EXISTS ai_provider_usage")
    conn.execute("DROP TABLE IF EXISTS meme_jobs")
    conn.execute("DROP TABLE IF EXISTS meme_assets")
    conn.execute("DROP TABLE IF EXISTS meme_templates")
