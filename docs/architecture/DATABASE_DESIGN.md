# Relational Database Architecture & Production SQL Schema

**Document ID:** ARCH-PO-004  
**Version:** 2.0.0  
**Related Diagram:** [DATABASE_RELATIONSHIPS.md](../diagrams/DATABASE_RELATIONSHIPS.md)

## 1. Data Modeling Principles & Justifications

PostgreSQL 16+ is the authoritative data store for Pressure Out. Every table in this schema is justified by a concrete product requirement—no speculative tables are created without a clear relationship and lifecycle.

### 1.1 Table Justification Matrix

| Table Name | Domain Group | Justification & Design Rationale |
| :--- | :--- | :--- |
| `users` | Accounts (Private) | Stores private authentication credentials (`password_hash`), optional encrypted recovery email, account status, and locale preferences. Completely isolated from public queries. |
| `user_sessions` | Accounts (Private) | Server-managed session tokens supporting instant revocation, sliding expiry, and device management without exposing JWT secrets or unrevocable tokens. |
| `public_profiles` | Public Identity | 1:1 with `users`. Holds the pseudonymous `@handle` (`citext` for case-insensitive uniqueness), display name, bio, and avatar. Separated from `users` so public joins never touch auth columns. |
| `professional_profiles` | Public Identity | 1:0..1 with `users`. Stores optional self-declared workplace context (`role_title`, `industry`, `experience_band`, `region_label`). Snapshotted onto posts when `identity_mode = 'professional'`. |
| `communities` | Communities | Stores topic-based spaces (`c/workplace-rants`, `c/corporate-memes`, etc.), visibility status, and posting permissions. |
| `community_rules` | Communities | Normalized per-community rule items used both for user display and structured report reason references. |
| `community_memberships` | Communities | Tracks which users follow/join a community and their community-scoped role (`member`, `moderator`). |
| `posts` | Social Content | Polymorphic core table for all 8 post types (`discussion`, `question`, `rant`, `story`, `meme`, `poll`, `advice_request`, `workplace_experience`). Stores private `author_user_id` alongside explicit public `identity_mode`. |
| `polls`, `poll_options`, `poll_votes` | Social Content | Structured attachment tables for `post_type = 'poll'`, enforcing single-vote or multi-choice constraints via composite unique keys. |
| `exit_story_details` | Workplace Insights | Structured 1:1 attachment for resignation/exit stories (`departure_reasons`, `industry`, `tenure_band`, `would_recommend`), enabling privacy-safe k-anonymity aggregation. |
| `tags`, `post_tags` | Discovery | Normalized topic tags (`#layoffs`, `#wfh`, `#appraisal`) for cross-community discovery and filtering. |
| `comments` | Engagement | Nested discussion replies using PostgreSQL `ltree` (`path`) + `parent_comment_id` for efficient subtree pagination and `is_anonymous_op` tracking. |
| `votes` | Engagement | Polymorphic or target-checked upvote/downvote (`+1` / `-1`) table with `UNIQUE (user_id, target_type, target_id)`. |
| `reactions` | Engagement | Expressive workplace reactions (`relatable`, `laugh`, `support`, `oof`, `respect`) with `UNIQUE (user_id, target_type, target_id, reaction_kind)`. |
| `saved_posts` | Engagement | Private user bookmarks (`PRIMARY KEY (user_id, post_id)`). |
| `meme_templates` | AI Meme Studio | Curated library of meme templates with predefined text-box coordinate metadata (`jsonb`) and license attribution. |
| `meme_jobs` | AI Meme Studio | Durable asynchronous job state machine (`draft -> queued -> generating -> validating -> ready | failed | cancelled`) with `idempotency_key`. |
| `meme_assets` | AI Meme Studio | Validated output image records stored in Object Storage, tracking ownership (`owner_user_id`), dimensions, `alt_text`, and lifecycle retention. |
| `ai_provider_usage` | AI Meme Studio | Append-only metering ledger tracking provider latency, token/image counts, and estimated USD cost per job for quota and circuit-breaker enforcement. |
| `content_translations` | Multilingual | Stores derived translations keyed by `(source_type, source_id, target_locale)` so original post/comment text is never overwritten. |
| `reports` | Trust & Safety | User-submitted flags on posts, comments, or profiles with structured `reason_code` and triage status. |
| `moderation_actions` | Trust & Safety | Immutable record of moderator decisions (`dismiss`, `redact_pii`, `restrict`, `remove`, `cooldown`, `suspend`). |
| `moderation_appeals` | Trust & Safety | Allows an affected author to submit one structured appeal per `moderation_action_id`. |
| `user_blocks` | Trust & Safety | Bidirectional-effect user blocking/muting (`PRIMARY KEY (blocker_user_id, blocked_user_id)`). |
| `notifications` | Notifications | In-app notification inbox for replies, job completions, and moderation outcomes. |
| `audit_events` | Security & Compliance | Restricted append-only security log recording privileged admin/moderator actions and sensitive data access. |

*Note on Deferred Tables:* Dedicated `companies` and `company_post_links` tables are intentionally deferred until Phase 11/Post-MVP validation so the MVP does not encourage unverified targeted defamation against small employers. `user_follows` is also omitted in MVP in favor of community and tag following (per Section 5 of the baseline PDF).

## 2. Production-Oriented PostgreSQL DDL Specification

```sql
-- Required PostgreSQL Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "citext";
CREATE EXTENSION IF NOT EXISTS "ltree";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================================
-- 1. PRIVATE ACCOUNTS, SESSIONS & PUBLIC/PROFESSIONAL PROFILES
-- ============================================================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_hash VARCHAR(64) UNIQUE, -- Nullable; HMAC-SHA256 of normalized email for lookup if provided
    email_encrypted BYTEA,         -- Nullable; AES-256-GCM encrypted email for recovery only
    password_hash VARCHAR(255) NOT NULL, -- Argon2id hash
    account_status VARCHAR(24) NOT NULL DEFAULT 'active'
        CHECK (account_status IN ('active', 'cooldown', 'suspended', 'deleted')),
    role VARCHAR(24) NOT NULL DEFAULT 'member'
        CHECK (role IN ('member', 'global_moderator', 'admin')),
    default_identity_mode VARCHAR(24) NOT NULL DEFAULT 'pseudonymous'
        CHECK (default_identity_mode IN ('pseudonymous', 'anonymous', 'professional')),
    preferred_ui_locale VARCHAR(16) NOT NULL DEFAULT 'en',
    preferred_content_locales JSONB NOT NULL DEFAULT '["en"]'::jsonb,
    cooldown_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    csrf_secret VARCHAR(64) NOT NULL,
    user_agent_summary VARCHAR(255),
    ip_subnet_hash VARCHAR(64), -- Privacy-preserving hashed subnet for brute-force/abuse detection
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_user_sessions_user_active ON user_sessions(user_id) WHERE revoked_at IS NULL;

CREATE TABLE public_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    handle CITEXT NOT NULL UNIQUE
        CHECK (char_length(handle) BETWEEN 3 AND 32 AND handle ~ '^[a-zA-Z0-9_]+$'),
    display_name VARCHAR(64),
    bio TEXT CHECK (char_length(bio) <= 500),
    avatar_storage_key VARCHAR(255),
    show_karma BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE professional_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    role_title VARCHAR(80) NOT NULL CHECK (char_length(role_title) BETWEEN 2 AND 80),
    industry VARCHAR(64) NOT NULL,
    experience_band VARCHAR(16) NOT NULL
        CHECK (experience_band IN ('fresher_0_1', 'junior_1_3', 'mid_3_6', 'senior_6_10', 'lead_10_plus')),
    region_label VARCHAR(64),
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 2. COMMUNITIES, RULES & MEMBERSHIPS
-- ============================================================================

CREATE TABLE communities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug CITEXT NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9-]+$'),
    name VARCHAR(80) NOT NULL,
    description TEXT NOT NULL CHECK (char_length(description) <= 1000),
    icon_name VARCHAR(64),
    primary_language VARCHAR(16) NOT NULL DEFAULT 'en',
    status VARCHAR(24) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'restricted', 'archived')),
    member_count INTEGER NOT NULL DEFAULT 0 CHECK (member_count >= 0),
    created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE community_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    community_id UUID NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    rule_number SMALLINT NOT NULL CHECK (rule_number BETWEEN 1 AND 25),
    title VARCHAR(120) NOT NULL,
    description TEXT NOT NULL,
    UNIQUE (community_id, rule_number)
);

CREATE TABLE community_memberships (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    community_id UUID NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    role VARCHAR(24) NOT NULL DEFAULT 'member'
        CHECK (role IN ('member', 'moderator')),
    status VARCHAR(24) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'banned')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, community_id)
);
CREATE INDEX idx_comm_memberships_community ON community_memberships(community_id, role);

-- ============================================================================
-- 3. AI MEME STUDIO TEMPLATES, JOBS, ASSETS & USAGE METERING
-- ============================================================================

CREATE TABLE meme_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug CITEXT NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    storage_key VARCHAR(255) NOT NULL,
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    text_regions JSONB NOT NULL DEFAULT '[]'::jsonb, -- Predefined top/bottom/custom box coordinates
    default_alt_text VARCHAR(255) NOT NULL,
    category_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE meme_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    source_type VARCHAR(24) NOT NULL
        CHECK (source_type IN ('template_render', 'ai_generated', 'remix')),
    template_id UUID REFERENCES meme_templates(id) ON DELETE SET NULL,
    storage_key VARCHAR(255) NOT NULL UNIQUE,
    mime_type VARCHAR(32) NOT NULL CHECK (mime_type IN ('image/png', 'image/webp', 'image/jpeg')),
    file_size_bytes INTEGER NOT NULL CHECK (file_size_bytes > 0 AND file_size_bytes <= 10485760),
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    captions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    caption_language VARCHAR(16) NOT NULL DEFAULT 'en',
    alt_text VARCHAR(500) NOT NULL,
    safety_status VARCHAR(24) NOT NULL DEFAULT 'approved'
        CHECK (safety_status IN ('pending', 'approved', 'rejected')),
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ, -- Used to garbage-collect unpublished draft assets after 7 days
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_meme_assets_owner ON meme_assets(owner_user_id, created_at DESC);
CREATE INDEX idx_meme_assets_cleanup ON meme_assets(expires_at) WHERE is_published = FALSE AND expires_at IS NOT NULL;

CREATE TABLE meme_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    idempotency_key VARCHAR(64) NOT NULL,
    job_type VARCHAR(24) NOT NULL
        CHECK (job_type IN ('template_render', 'ai_caption', 'ai_image')),
    template_id UUID REFERENCES meme_templates(id) ON DELETE SET NULL,
    user_prompt TEXT CHECK (char_length(user_prompt) <= 500),
    prompt_language VARCHAR(16) NOT NULL DEFAULT 'en',
    style_tone VARCHAR(32) DEFAULT 'sarcastic',
    status VARCHAR(24) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('draft', 'queued', 'generating', 'validating', 'ready', 'failed', 'cancelled')),
    attempt_count SMALLINT NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 3),
    provider_name VARCHAR(64),
    model_version VARCHAR(64),
    caption_suggestions JSONB, -- Populated when job_type = 'ai_caption'
    result_asset_id UUID REFERENCES meme_assets(id) ON DELETE SET NULL,
    error_code VARCHAR(64),
    error_message_safe VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE (user_id, idempotency_key)
);
CREATE INDEX idx_meme_jobs_queue ON meme_jobs(status, created_at ASC) WHERE status = 'queued';
CREATE INDEX idx_meme_jobs_user_daily ON meme_jobs(user_id, job_type, created_at DESC);

CREATE TABLE ai_provider_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    meme_job_id UUID REFERENCES meme_jobs(id) ON DELETE SET NULL,
    operation_type VARCHAR(32) NOT NULL CHECK (operation_type IN ('ai_caption', 'ai_image', 'translation')),
    provider_name VARCHAR(64) NOT NULL,
    model_name VARCHAR(64) NOT NULL,
    input_units INTEGER NOT NULL DEFAULT 0,
    output_units INTEGER NOT NULL DEFAULT 0,
    estimated_cost_micros BIGINT NOT NULL DEFAULT 0, -- Cost in 1/1,000,000 USD for exact integer math
    latency_ms INTEGER NOT NULL DEFAULT 0,
    succeeded BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ai_usage_daily_spend ON ai_provider_usage(created_at DESC, operation_type);

-- ============================================================================
-- 4. SOCIAL CONTENT: POSTS, POLLS, EXIT STORIES, TAGS & COMMENTS
-- ============================================================================

CREATE TABLE posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_user_id UUID REFERENCES users(id) ON DELETE SET NULL, -- Private ownership; NULL only if user purged
    community_id UUID NOT NULL REFERENCES communities(id) ON DELETE RESTRICT,
    post_type VARCHAR(32) NOT NULL
        CHECK (post_type IN (
            'discussion', 'question', 'rant', 'story',
            'meme', 'poll', 'advice_request', 'workplace_experience'
        )),
    identity_mode VARCHAR(24) NOT NULL
        CHECK (identity_mode IN ('pseudonymous', 'anonymous', 'professional')),
    professional_snapshot JSONB, -- Stores {"role_title": ..., "industry": ..., "experience_band": ...} at post time
    anonymous_alias VARCHAR(32) NOT NULL DEFAULT 'Anonymous Member',
    title VARCHAR(220) NOT NULL CHECK (char_length(title) BETWEEN 3 AND 220),
    body TEXT CHECK (char_length(body) <= 15000),
    meme_asset_id UUID REFERENCES meme_assets(id) ON DELETE SET NULL,
    content_language VARCHAR(16) NOT NULL DEFAULT 'en', -- BCP 47 tag (en, hi, ta, ml, es, mul, und)
    moderation_status VARCHAR(24) NOT NULL DEFAULT 'published'
        CHECK (moderation_status IN ('draft', 'published', 'awaiting_review', 'restricted', 'removed')),
    upvote_count INTEGER NOT NULL DEFAULT 0 CHECK (upvote_count >= 0),
    downvote_count INTEGER NOT NULL DEFAULT 0 CHECK (downvote_count >= 0),
    score INTEGER NOT NULL DEFAULT 0,
    reaction_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    comment_count INTEGER NOT NULL DEFAULT 0 CHECK (comment_count >= 0),
    hot_rank_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(body, '')), 'B')
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT chk_meme_post_has_asset CHECK (post_type != 'meme' OR meme_asset_id IS NOT NULL)
);

CREATE INDEX idx_posts_feed_latest ON posts(created_at DESC, id DESC)
    WHERE moderation_status = 'published' AND deleted_at IS NULL;
CREATE INDEX idx_posts_feed_popular ON posts(hot_rank_score DESC, created_at DESC, id DESC)
    WHERE moderation_status = 'published' AND deleted_at IS NULL;
CREATE INDEX idx_posts_community_latest ON posts(community_id, created_at DESC, id DESC)
    WHERE moderation_status = 'published' AND deleted_at IS NULL;
CREATE INDEX idx_posts_author_public ON posts(author_user_id, created_at DESC)
    WHERE identity_mode != 'anonymous' AND moderation_status = 'published' AND deleted_at IS NULL;
CREATE INDEX idx_posts_author_private ON posts(author_user_id, created_at DESC);
CREATE INDEX idx_posts_language ON posts(content_language, created_at DESC)
    WHERE moderation_status = 'published' AND deleted_at IS NULL;
CREATE INDEX idx_posts_search_gin ON posts USING GIN (search_vector);

CREATE TABLE polls (
    post_id UUID PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
    allows_multiple BOOLEAN NOT NULL DEFAULT FALSE,
    closes_at TIMESTAMPTZ,
    total_votes INTEGER NOT NULL DEFAULT 0 CHECK (total_votes >= 0)
);

CREATE TABLE poll_options (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    poll_post_id UUID NOT NULL REFERENCES polls(post_id) ON DELETE CASCADE,
    position SMALLINT NOT NULL CHECK (position BETWEEN 1 AND 8),
    option_text VARCHAR(140) NOT NULL,
    vote_count INTEGER NOT NULL DEFAULT 0 CHECK (vote_count >= 0),
    UNIQUE (poll_post_id, position)
);

CREATE TABLE poll_votes (
    poll_post_id UUID NOT NULL REFERENCES polls(post_id) ON DELETE CASCADE,
    option_id UUID NOT NULL REFERENCES poll_options(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (poll_post_id, user_id, option_id)
);

CREATE TABLE exit_story_details (
    post_id UUID PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
    primary_reasons JSONB NOT NULL, -- Array of validated reason codes e.g. ["compensation", "burnout"]
    industry VARCHAR(64),
    role_level VARCHAR(32),
    tenure_band VARCHAR(24) CHECK (tenure_band IN ('under_1yr', '1_to_3yrs', '3_to_5yrs', '5_plus_yrs')),
    notice_period_days SMALLINT CHECK (notice_period_days BETWEEN 0 AND 180),
    morale_rating SMALLINT CHECK (morale_rating BETWEEN 1 AND 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug CITEXT NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9-]+$'),
    display_name VARCHAR(64) NOT NULL,
    usage_count INTEGER NOT NULL DEFAULT 0 CHECK (usage_count >= 0)
);

CREATE TABLE post_tags (
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, tag_id)
);
CREATE INDEX idx_post_tags_tag ON post_tags(tag_id, post_id);

CREATE TABLE comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    author_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    parent_comment_id UUID REFERENCES comments(id) ON DELETE RESTRICT,
    path LTREE NOT NULL, -- Materialized path of short hex IDs for O(1) subtree queries
    depth SMALLINT NOT NULL DEFAULT 0 CHECK (depth BETWEEN 0 AND 10),
    identity_mode VARCHAR(24) NOT NULL
        CHECK (identity_mode IN ('pseudonymous', 'anonymous', 'professional')),
    professional_snapshot JSONB,
    is_anonymous_op BOOLEAN NOT NULL DEFAULT FALSE,
    anonymous_thread_label VARCHAR(32), -- e.g. "Anonymous OP" or thread-scoped "Anonymous #3"
    body TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 5000),
    content_language VARCHAR(16) NOT NULL DEFAULT 'en',
    moderation_status VARCHAR(24) NOT NULL DEFAULT 'published'
        CHECK (moderation_status IN ('published', 'awaiting_review', 'restricted', 'removed')),
    upvote_count INTEGER NOT NULL DEFAULT 0,
    downvote_count INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);
CREATE INDEX idx_comments_post_top ON comments(post_id, score DESC, created_at ASC)
    WHERE parent_comment_id IS NULL;
CREATE INDEX idx_comments_path_gist ON comments USING GIST (path);
CREATE INDEX idx_comments_parent ON comments(parent_comment_id, created_at ASC);

-- ============================================================================
-- 5. ENGAGEMENT: VOTES, REACTIONS & SAVED POSTS
-- ============================================================================

CREATE TABLE votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_type VARCHAR(16) NOT NULL CHECK (target_type IN ('post', 'comment')),
    target_id UUID NOT NULL,
    value SMALLINT NOT NULL CHECK (value IN (-1, 1)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, target_type, target_id)
);
CREATE INDEX idx_votes_target ON votes(target_type, target_id);

CREATE TABLE reactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_type VARCHAR(16) NOT NULL CHECK (target_type IN ('post', 'comment')),
    target_id UUID NOT NULL,
    reaction_kind VARCHAR(24) NOT NULL
        CHECK (reaction_kind IN ('relatable', 'laugh', 'support', 'oof', 'respect')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, target_type, target_id, reaction_kind)
);

CREATE TABLE saved_posts (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, post_id)
);

-- ============================================================================
-- 6. MULTILINGUAL DERIVED TRANSLATIONS
-- ============================================================================

CREATE TABLE content_translations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type VARCHAR(16) NOT NULL CHECK (source_type IN ('post', 'comment')),
    source_id UUID NOT NULL,
    source_version_hash VARCHAR(64) NOT NULL, -- SHA-256 of original text so edits invalidate stale translations
    source_language VARCHAR(16) NOT NULL,
    target_locale VARCHAR(16) NOT NULL,
    translated_title VARCHAR(300),
    translated_body TEXT NOT NULL,
    provider_name VARCHAR(64) NOT NULL,
    model_name VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_type, source_id, target_locale, source_version_hash)
);

-- ============================================================================
-- 7. TRUST, SAFETY, MODERATION, BLOCKS, NOTIFICATIONS & AUDIT TRAIL
-- ============================================================================

CREATE TABLE reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reporter_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_type VARCHAR(16) NOT NULL CHECK (target_type IN ('post', 'comment', 'profile', 'meme_asset')),
    target_id UUID NOT NULL,
    community_id UUID REFERENCES communities(id) ON DELETE SET NULL,
    reason_code VARCHAR(32) NOT NULL
        CHECK (reason_code IN (
            'doxxing_pii', 'harassment', 'threat', 'impersonation',
            'spam', 'hate_speech', 'confidential_ip', 'misleading_allegation', 'other'
        )),
    details TEXT CHECK (char_length(details) <= 1000),
    priority_score SMALLINT NOT NULL DEFAULT 1,
    status VARCHAR(24) NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_review', 'resolved_actioned', 'resolved_dismissed')),
    resolved_by_action_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (reporter_user_id, target_type, target_id)
);
CREATE INDEX idx_reports_queue ON reports(status, priority_score DESC, created_at ASC) WHERE status IN ('open', 'in_review');

CREATE TABLE moderation_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    moderator_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    target_type VARCHAR(16) NOT NULL CHECK (target_type IN ('post', 'comment', 'user', 'meme_asset')),
    target_id UUID NOT NULL,
    action_type VARCHAR(32) NOT NULL
        CHECK (action_type IN (
            'dismiss_reports', 'redact_pii', 'restrict_visibility',
            'remove_content', 'restore_content', 'user_cooldown', 'user_suspend'
        )),
    reason_code VARCHAR(32) NOT NULL,
    internal_note TEXT NOT NULL CHECK (char_length(internal_note) BETWEEN 5 AND 1000),
    public_explanation VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE moderation_appeals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    moderation_action_id UUID NOT NULL UNIQUE REFERENCES moderation_actions(id) ON DELETE CASCADE,
    appellant_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    appeal_statement TEXT NOT NULL CHECK (char_length(appeal_statement) BETWEEN 10 AND 2000),
    status VARCHAR(24) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'upheld', 'overturned')),
    reviewed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    review_decision_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE TABLE user_blocks (
    blocker_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    blocked_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    block_mode VARCHAR(16) NOT NULL DEFAULT 'block' CHECK (block_mode IN ('block', 'mute')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (blocker_user_id, blocked_user_id),
     CHECK (blocker_user_id != blocked_user_id)
);

CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notification_type VARCHAR(32) NOT NULL
        CHECK (notification_type IN ('post_reply', 'comment_reply', 'meme_job_ready', 'moderation_notice', 'appeal_update')),
    reference_type VARCHAR(24) NOT NULL,
    reference_id UUID NOT NULL,
    title VARCHAR(160) NOT NULL,
    body_preview VARCHAR(255),
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_notifications_recipient ON notifications(recipient_user_id, is_read, created_at DESC);

CREATE TABLE audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    actor_role VARCHAR(24) NOT NULL,
    event_category VARCHAR(32) NOT NULL
        CHECK (event_category IN ('moderation', 'admin_role_change', 'account_security', 'legal_preservation')),
    action_name VARCHAR(64) NOT NULL,
    target_type VARCHAR(32) NOT NULL,
    target_id UUID,
    reason_code VARCHAR(64) NOT NULL,
    redacted_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    correlation_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_events_created ON audit_events(created_at DESC);
```

## 3. Deletion, Anonymization & Data Retention Rules

| Entity / Event | Deletion & Retention Behavior |
| :--- | :--- |
| **User Deletes Single Post/Comment** | Sets `deleted_at = NOW()`, replaces `body` with `"[deleted by author]"`, sets `author_user_id = NULL` (unless under active legal/safety hold), and removes any unreferenced draft `meme_assets` from Object Storage. |
| **User Deletes Entire Account (`DELETE /api/v1/me`)** | Immediately revokes all `user_sessions`, deletes `public_profiles` and `professional_profiles`, clears `email_hash`/`email_encrypted`, sets `users.account_status = 'deleted'`, and dissociates `author_user_id = NULL` on remaining community discussions (or deletes them if the user chooses "Delete my posts & account"). |
| **Unpublished Draft Meme Assets** | `meme_assets` with `is_published = FALSE` have `expires_at = created_at + INTERVAL '7 days'`. Background worker deletes the object from storage and purges the row. |
| **Session & Rate-Limit Records** | Expired/revoked `user_sessions` are purged 30 days after `expires_at`. |
| **Security & Moderation Audit Logs** | `audit_events` and `moderation_actions` are retained for 365 days with redacted metadata (no raw emails or cleartext passwords ever written to logs). |
