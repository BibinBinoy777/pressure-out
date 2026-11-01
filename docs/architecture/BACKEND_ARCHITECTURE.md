# Backend Application Architecture

**Document ID:** ARCH-PO-003  
**Version:** 2.0.0  

## 1. Modular Monolith Design Principles

The Pressure Out backend is a **Python 3.12+ FastAPI Modular Monolith**. It is structured so each domain module (`identity`, `posts`, `communities`, `feed`, `memes`, `languages`, `moderation`, `notifications`) encapsulates its own SQLAlchemy models, Pydantic schemas, repository queries, and business service layer.

### 1.1 Inter-Module Dependency Rules
To prevent the monolith from degenerating into a "big ball of mud," modules obey strict directional dependencies:
* **`core/` and `db/`** are foundational layers imported by any module.
* **`identity`** is the base domain module (provides authenticated `CurrentUser` context and profile resolution).
* **`communities`**, **`languages`**, and **`memes`** depend on `identity`.
* **`posts`** depends on `identity`, `communities`, `memes` (for linking `meme_asset_id`), and `languages`.
* **`feed`** and **`moderation`** read across `posts`, `communities`, and `identity` via explicit service interfaces.
* **Cross-module writes** must pass through the target module's service class within a shared SQLAlchemy `AsyncSession` transaction rather than mutating another module's tables directly in ad-hoc router code.

## 2. Backend Package Layout (`backend/`)

```text
backend/
├── pyproject.toml                  # Dependencies (fastapi, pydantic, sqlalchemy[asyncio], asyncpg, alembic, argon2-cffi, pillow, httpx, pytest)
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/                   # Sequential, reversible schema migrations
├── app/
│   ├── main.py                     # FastAPI application entrypoint, middleware registration, lifespan
│   ├── core/
│   │   ├── config.py               # Pydantic BaseSettings (env vars, quotas, secrets, CORS)
│   │   ├── security.py             # Argon2id password hashing, AES-GCM email encryption, CSRF tokens, session IDs
│   │   ├── exceptions.py           # DomainException hierarchy & unified JSON error handler
│   │   ├── logging.py              # Structured JSON logger with correlation_id & PII redaction filter
│   │   └── rate_limit.py           # Account & IP bucket rate limiter backed by PostgreSQL / memory TTL
│   ├── db/
│   │   ├── session.py              # AsyncEngine & async_sessionmaker setup
│   │   ├── base.py                 # DeclarativeBase with UTC timestamps & UUID v4/v7 PK mixins
│   │   └── locks.py                # Helpers for SELECT ... FOR UPDATE SKIP LOCKED
│   ├── api/
│   │   ├── deps.py                 # FastAPI Depends: get_db, get_current_user, require_moderator, require_admin
│   │   └── v1/
│   │       ├── router.py           # Master /api/v1 router aggregator
│   │       ├── auth.py             # /api/v1/auth/* & /api/v1/me/*
│   │       ├── profiles.py         # /api/v1/profiles/*
│   │       ├── posts.py            # /api/v1/posts/*
│   │       ├── comments.py         # /api/v1/posts/{id}/comments & /api/v1/comments/*
│   │       ├── communities.py      # /api/v1/communities/*
│   │       ├── feed.py             # /api/v1/feed & /api/v1/search
│   │       ├── memes.py            # /api/v1/memes/*
│   │       ├── languages.py        # /api/v1/languages/* & translation endpoints
│   │       ├── moderation.py       # /api/v1/reports, /api/v1/moderation/*, /api/v1/appeals
│   │       └── notifications.py    # /api/v1/notifications/*
│   ├── modules/
│   │   ├── identity/               # models.py, schemas.py, service.py, serializers.py
│   │   ├── posts/                  # models.py, schemas.py, service.py, serializers.py, pii_guard.py
│   │   ├── communities/            # models.py, schemas.py, service.py
│   │   ├── feed/                   # ranking.py, search.py, service.py
│   │   ├── memes/
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   ├── template_renderer.py # Deterministic Pillow/Cairo Unicode text-on-image compositor
│   │   │   └── adapters/
│   │   │       ├── base.py         # CaptionProviderAdapter & ImageProviderAdapter Protocols
│   │   │       ├── mock_provider.py # Deterministic local/CI provider
│   │   │       └── http_provider.py # Configurable external AI vendor adapter
│   │   ├── languages/
│   │   │   ├── bcp47.py            # Language tag validator & normalizer
│   │   │   ├── service.py
│   │   │   └── adapters/           # TranslationProviderAdapter
│   │   ├── moderation/             # models.py, schemas.py, service.py, audit.py
│   │   └── notifications/          # models.py, schemas.py, service.py
│   └── workers/
│       └── runner.py               # Async loop processing queued meme_jobs, translations & cleanup
└── tests/
    ├── conftest.py                 # Isolated test PostgreSQL transaction fixtures
    ├── unit/
    ├── integration/
    ├── security/                   # Identity leak & RBAC penetration test suite
    └── contract/                   # OpenAPI schema stability tests
```

## 3. Core Backend Patterns

### 3.1 Explicit Public vs. Private Serializer Pattern
Never use SQLAlchemy models directly as FastAPI `response_model` types, and never share a single Pydantic model between internal account management and public social views.
* `InternalPostRecord`: Contains `author_user_id`, `moderation_notes`, and internal flags.
* `PublicPostResponse`: Built exclusively via `serialize_public_post(post, viewer_user_id)`:
  * Sets `is_viewer_author: bool = (viewer_user_id is not None and post.author_user_id == viewer_user_id)` so the author's own UI can render "Edit / Delete" and lock "Anonymous OP" replies.
  * When `post.identity_mode == 'anonymous'`, sets `author = PublicAuthorInfo(identity_mode='anonymous', display_name='Anonymous Member', handle=None, avatar_url=None, professional_badge=None)`. Even if a developer accidentally passes `post.author` into the serializer, the serializer discards it.

### 3.2 Transaction Boundaries & Atomicity
* **Read Operations:** Execute using read-only async sessions without open transaction locks.
* **Write Operations:** Execute inside an explicit database transaction (`async with db.begin():`). For example, creating a poll post inserts the `posts` row, `polls` row, `poll_options` rows, and `post_tags` rows atomically—if any validation or constraint fails, the entire operation rolls back cleanly.

### 3.3 Standardized Error Envelope
All HTTP `4xx` and `5xx` errors return a uniform JSON structure so the frontend can display localized, user-safe messages while logging correlation IDs for engineering triage:

```json
{
  "error": {
    "code": "MEME_QUOTA_EXCEEDED",
    "message": "You have reached your daily limit of 5 AI image generations. You can still create unlimited memes using templates!",
    "details": {
      "quota_type": "ai_image_daily",
      "limit": 5,
      "reset_at": "2026-10-29T00:00:00Z"
    },
    "correlation_id": "req_01jc8x9z2p4m6n8q0r2s4t6v8w"
  }
}
```
