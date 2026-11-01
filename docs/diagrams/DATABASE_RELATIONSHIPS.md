# Database Entity Relationship Diagram (ERD)

**Document ID:** DIAG-PO-003  
**Related Spec:** [DATABASE_DESIGN.md](../architecture/DATABASE_DESIGN.md)

## 1. Relational Entity Diagram (Diagram 3)

This Mermaid Entity Relationship Diagram models the core PostgreSQL tables, highlighting how **private authentication identity** (`users`, `user_sessions`) is decoupled from **public profiles** (`public_profiles`, `professional_profiles`) and how `posts` and `comments` preserve private ownership (`author_user_id`) while enforcing explicit public `identity_mode` rendering.

```mermaid
erDiagram
    USERS ||--o{ USER_SESSIONS : "authenticates via"
    USERS ||--|| PUBLIC_PROFILES : "owns 1:1"
    USERS ||--o| PROFESSIONAL_PROFILES : "optionally configures 1:0..1"
    USERS ||--o{ COMMUNITIES : "creates (admin/mod)"
    USERS ||--o{ COMMUNITY_MEMBERSHIPS : "joins"
    COMMUNITIES ||--o{ COMMUNITY_MEMBERSHIPS : "has members"
    COMMUNITIES ||--o{ COMMUNITY_RULES : "enforces"

    USERS ||--o{ POSTS : "authors privately (author_user_id)"
    COMMUNITIES ||--o{ POSTS : "hosts"
    POSTS ||--o| POLLS : "attaches (if post_type=poll)"
    POLLS ||--|{ POLL_OPTIONS : "contains"
    POLL_OPTIONS ||--o{ POLL_VOTES : "receives"
    USERS ||--o{ POLL_VOTES : "casts"

    POSTS ||--o| EXIT_STORY_DETAILS : "attaches (if exit story)"
    POSTS ||--o{ POST_TAGS : "tagged with"
    TAGS ||--o{ POST_TAGS : "categorizes"

    POSTS ||--o{ COMMENTS : "has discussion thread"
    USERS ||--o{ COMMENTS : "authors privately"
    COMMENTS ||--o{ COMMENTS : "replies to (parent_comment_id + ltree)"

    USERS ||--o{ VOTES : "casts (+1 / -1)"
    USERS ||--o{ REACTIONS : "reacts with"
    USERS ||--o{ SAVED_POSTS : "bookmarks"
    POSTS ||--o{ SAVED_POSTS : "saved in"

    MEME_TEMPLATES ||--o{ MEME_JOBS : "used by"
    USERS ||--o{ MEME_JOBS : "initiates"
    MEME_JOBS ||--o| MEME_ASSETS : "produces"
    USERS ||--o{ MEME_ASSETS : "owns"
    MEME_ASSETS ||--o{ POSTS : "published in (meme_asset_id)"
    MEME_JOBS ||--o{ AI_PROVIDER_USAGE : "meters cost/tokens"

    POSTS ||--o{ CONTENT_TRANSLATIONS : "has derived translations"
    COMMENTS ||--o{ CONTENT_TRANSLATIONS : "has derived translations"

    USERS ||--o{ REPORTS : "submits"
    REPORTS ||--o{ MODERATION_ACTIONS : "resolved by"
    USERS ||--o{ MODERATION_ACTIONS : "executes (moderator_user_id)"
    MODERATION_ACTIONS ||--o| MODERATION_APPEALS : "appealed via"
    USERS ||--o{ USER_BLOCKS : "blocks/mutes"
    USERS ||--o{ NOTIFICATIONS : "receives"
    USERS ||--o{ AUDIT_EVENTS : "logged in (actor_user_id)"

    USERS {
        uuid id PK
        varchar email_hash UK "Nullable; SHA-256 for lookup"
        bytea email_encrypted "Nullable; AES-GCM for recovery"
        varchar password_hash "Argon2id hash"
        varchar account_status "active | cooldown | suspended | deleted"
        varchar preferred_ui_locale "Default en"
        jsonb preferred_content_locales "Array of BCP 47 tags"
        timestamptz created_at
        timestamptz deleted_at
    }

    PUBLIC_PROFILES {
        uuid id PK
        uuid user_id FK,UK "1:1 reference to users.id"
        citext handle UK "Unique pseudonymous username"
        varchar display_name
        text bio
        varchar avatar_key
        boolean show_karma
        timestamptz created_at
    }

    PROFESSIONAL_PROFILES {
        uuid id PK
        uuid user_id FK,UK "1:0..1 reference to users.id"
        varchar role_title "e.g., Senior Backend Engineer"
        varchar industry "e.g., FinTech, Healthcare"
        varchar experience_band "0-1 | 2-4 | 5-8 | 9-12 | 12+"
        varchar region_label "e.g., South Asia, Europe"
        boolean is_enabled
        timestamptz updated_at
    }

    POSTS {
        uuid id PK
        uuid author_user_id FK "NEVER serialized in anonymous mode"
        uuid community_id FK
        varchar post_type "discussion|question|rant|story|meme|poll|advice_request|workplace_experience"
        varchar identity_mode "pseudonymous | anonymous | professional"
        jsonb professional_snapshot "Captured role/industry if identity_mode=professional"
        varchar anonymous_alias "e.g., Anonymous Member"
        varchar title
        text body
        varchar content_language "BCP 47 tag: en, hi, mul, und"
        uuid meme_asset_id FK "Nullable"
        varchar moderation_status "published | awaiting_review | restricted | removed"
        integer upvote_count
        integer downvote_count
        integer score
        integer comment_count
        timestamptz created_at
    }

    COMMENTS {
        uuid id PK
        uuid post_id FK
        uuid author_user_id FK "NEVER serialized in anonymous mode"
        uuid parent_comment_id FK "Nullable self-reference"
        ltree path "Materialized path for subtree pagination"
        integer depth
        varchar identity_mode "pseudonymous | anonymous | professional"
        boolean is_anonymous_op "True if post author replying anonymously"
        varchar anonymous_thread_label "Deterministic per-thread label e.g. Anon-4F2"
        text body
        varchar content_language
        varchar moderation_status
        integer score
        timestamptz created_at
    }

    MEME_JOBS {
        uuid id PK
        uuid user_id FK
        varchar idempotency_key UK
        varchar job_type "template_render | ai_caption | ai_image"
        uuid template_id FK "Nullable"
        text user_prompt
        varchar prompt_language
        varchar style_tone
        varchar status "draft | queued | generating | validating | ready | failed | cancelled"
        varchar provider_name
        uuid result_asset_id FK "Nullable"
        varchar error_code
        timestamptz created_at
    }
```
