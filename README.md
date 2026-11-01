# Pressure Out

> **Your Work. Your Chaos. Your People.**  
> *Work is serious. Talking about it doesn't have to be.*

**Implementation Status:** Implementation documented through Phase 12.3, including Windows local development, security hardening, and qualification tooling.  
**Project Stage:** Local development and qualification; production deployment has not been performed.  

## 1. Project Purpose

**Pressure Out** is a work-focused social platform dedicated to workplace discussions, candid rants, office humour, salary and career conversations, structured resignation stories, and AI-assisted workplace memes. Its foundational product principle is that **people must be able to express themselves without being required to reveal their real-world identity**.

This repository contains:

1. **Product and Architecture Documentation (`docs/`)** - Product requirements, user journeys, system architecture, database design, API specifications, identity and privacy, AI Meme Studio, multilingual support, moderation, operations, roadmaps, and architecture diagrams.

2. **Application Implementation (`backend/`, `frontend/`)** - FastAPI backend, modular domain services, PostgreSQL migrations, authentication, privacy controls, workplace social features, AI-assisted meme workflows, moderation, translation, and Next.js frontend.

3. **Development and Operations (`docker-compose*.yml`, `.env*.example`, `scripts/`)** - Docker Compose configurations, Windows PowerShell automation, database backup and restore, qualification tooling, automated smoke checks, and operational documentation.

## 2. Technology Stack

| Layer | Technology Baseline |
| :--- | :--- |
| **Frontend** | Next.js (App Router), React 19, TypeScript (strict mode), Tailwind CSS, Vitest |
| **Backend** | Python 3.11 / 3.12, FastAPI, Pydantic, SQLAlchemy 2.x (Async), Alembic, Pytest, Ruff |
| **Database** | PostgreSQL 16 (`pgcrypto`, `citext`, `ltree`, `pg_trgm`), UTF-8 encoding |
| **Local Orchestration** | Docker Compose (`db`, `backend`, `frontend` with health checks and named volume persistence) |

## 3. Prerequisites

* **Docker Compose Workflow (Recommended):** Docker Engine 24+ and Docker Compose v2+.
* **Direct Host Workflow:**
  * Python 3.11+ (`pip`, `venv`)
  * Node.js 18.20+ or 20+ (`npm`)
  * PostgreSQL 16+ running locally (or via the `db` service in `docker-compose.yml`)



## 5. Environment Configuration

1. Copy the template environment file:
   ```bash
   cp .env.example .env
   ```
2. Review `.env`. All defaults in `.env.example` use safe development-only placeholders:
   * **Database:** `DATABASE_URL=postgresql+asyncpg://po_dev_user:po_dev_local_only_password_change_me@localhost:5432/pressure_out_dev`
   * **Browser -> Backend URL:** `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`
   * **Container SSR -> Backend URL:** `INTERNAL_API_BASE_URL=http://backend:8000` (inside Docker Compose) or `http://localhost:8000` (on host).
   * **Offline AI / Translation Defaults:** `AI_CAPTION_PROVIDER=disabled`, `AI_IMAGE_PROVIDER=disabled`, `TRANSLATION_PROVIDER=disabled`. No external API keys are required to start or test the application foundation.

## 6. Starting the Application Locally

### 6.1 Starting with Docker Compose (Recommended)
Start PostgreSQL 16, the FastAPI backend (which automatically runs `alembic upgrade head`), and the Next.js frontend:
```bash
docker compose up --build
```
* **Frontend Application:** `http://localhost:3000`
* **Backend Health Check:** `http://localhost:8000/api/v1/health`
* **OpenAPI Interactive Docs (Dev Mode):** `http://localhost:8000/api/v1/docs`

To stop the services while preserving PostgreSQL data in the `pressure_out_pgdata` volume:
```bash
docker compose down
```

### 6.2 Running the Backend Directly on the Host
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 6.3 Running the Frontend Directly on the Host
```bash
cd frontend
npm install
npm run dev
```

## 7. Executing Database Migrations

From `backend/` (with PostgreSQL running and `DATABASE_URL` configured):
```bash
# Apply migrations up to latest revision (establishes pgcrypto, citext, ltree, pg_trgm)
alembic upgrade head

# Check current migration revision
alembic current

# Roll back baseline migration (only drops extensions created by 0001; preserves pre-existing ones)
alembic downgrade base
```

## 8. Running Automated Tests & Quality Gates

### 8.1 Backend Tests & Linters (`backend/`)
```bash
cd backend

# Standard unittest discovery (works both offline and with full dev dependencies)
PYTHONPATH=. python3 -m unittest discover -s tests -p "test_*.py" -v

# Pytest & Ruff (when dev dependencies are installed)
pytest -v
ruff check .
```

### 8.2 Frontend Tests, Linters & Type Checks (`frontend/`)
```bash
cd frontend

# Offline-capable Node.js + Babel TypeScript/React AST + ESLint verification suite
npm run test:vm

# Standard Vitest, TypeScript compiler, ESLint, and production build (when node_modules installed)
npm test
npm run typecheck
npm run lint
npm run build
```

## 9. Inspecting Service Logs & Troubleshooting

### 9.1 Inspecting Logs
```bash
# View live logs across all Docker Compose services
docker compose logs -f

# View structured JSON logs for the FastAPI backend only
docker compose logs -f backend
```
Every backend log entry is emitted as single-line JSON containing `timestamp`, `level`, `logger`, `message`, and `correlation_id`, with passwords, session cookies, CSRF tokens, DSN passwords, recovery emails, and post/prompt bodies automatically scrubbed to `[REDACTED]`.

### 9.2 Troubleshooting Common Startup Problems
* **Frontend shows "Backend API Currently Unreachable":**
  * Verify the FastAPI server is running on port `8000` (`curl -i http://127.0.0.1:8000/api/v1/health`).
  * Ensure `NEXT_PUBLIC_API_BASE_URL` in `.env` matches the host/port reachable from your browser (`http://localhost:8000`), while `INTERNAL_API_BASE_URL` inside Docker Compose points to `http://backend:8000`.
* **PostgreSQL port `5432` conflict on host:**
  * If another local PostgreSQL instance is bound to `127.0.0.1:5432`, set `POSTGRES_PORT=5433` in `.env` and update `DATABASE_URL` accordingly.
* **Resetting a corrupted local development database volume:**
  * Run `docker compose down -v` (warning: destroys local dev database data) and re-run `docker compose up --build`.

## 10. Documented Phase 2 Implementation Decisions & Reconciliations

In accordance with Section 2 and Section 13 of the Phase 2 specification, all 24 Phase 1 specification documents in `docs/` are preserved intact, and the following minor directory path reconciliations between Phase 1's illustrative tree and Phase 2's target layout are recorded:

1. **Flattened Frontend Root (`frontend/app/` vs. `frontend/src/app/`):** Phase 2 adopts the top-level `frontend/app/`, `frontend/components/`, `frontend/lib/`, `frontend/locales/en/common.json`, and `frontend/tests/` structure specified in Phase 2 Section 4 rather than nesting under `frontend/src/`.
2. **Explicit Backend Module Separation (`backend/app/config.py`, `logging_config.py`, `database/`, `middleware/`):** Phase 2 places `config.py` and `logging_config.py` at the top of `backend/app/` and names the database package `backend/app/database/` and middleware package `backend/app/middleware/` to match the Phase 2 Section 4 layout, while keeping `backend/app/core/` for shared error-envelope (`errors.py`) and Unicode (`unicode.py`) utilities.
3. **Migration Scope Boundary (`0001_phase2_foundation_extensions.py`):** While `docs/architecture/DATABASE_DESIGN.md` specifies the complete 29-table target DDL across all 12 phases, Phase 2's initial migration strictly establishes only the PostgreSQL extension prerequisites (`pgcrypto`, `citext`, `ltree`, `pg_trgm`) and their ownership tracking table `_alembic_extension_ownership`, leaving domain tables to be introduced in Phases 3–11.

## Phase 8: AI Meme Studio (`0007_phase8_memes`)

- **Database Schema (`0007_phase8_ai_meme_studio.py`):** Adds `meme_templates` (seeded with 6 original CC0 workplace templates), `meme_assets`, `meme_jobs`, and `ai_provider_usage`, while linking published meme posts via `posts.meme_asset_id`.
- **Always-On Server `TemplateRenderer`:** Uses Pillow + HarfBuzz (`raqm`) and installed Noto fonts (`NotoSans`, `NotoSansMalayalam`, `NotoSansDevanagari`, `NotoSansTamil`) to deterministically render multi-region captions in PNG and WebP even when external AI providers are disabled.
- **Provider-Neutral AI Adapters:** Implements `CaptionProviderAdapter` and `ImageProviderAdapter` with `LocalMockCaptionProvider` / `LocalMockImageProvider` (explicitly marked `is_mock_provider: true`) and configurable daily quotas, concurrency limits, PII stripping, and a daily USD spend circuit breaker.
- **Frontend Studio (`/meme-studio`):** Provides template browsing, multilingual caption editing, AI caption suggestions, asynchronous image job polling/cancellation, alt-text editing, asset download, and direct community publishing across all 3 identity modes.

## Phase 9: Trust, Safety, Reporting, Moderation & Abuse Prevention (`0008_phase9_moderation`)

- **Database Schema (`0008_phase9_trust_safety_moderation.py`):** Adds `reports`, `moderation_actions`, `moderation_appeals`, `user_blocks`, and `audit_events` (enforced as append-only via `trg_audit_events_no_update` and `trg_audit_events_no_delete` triggers).
- **High-Severity Velocity Safeguard:** Reports with `reason_code IN ('doxxing_pii', 'threat')` receive `priority_score = 10`. Receiving `>= 3` distinct user reports within a rolling 30-minute window automatically transitions a `published` post/comment to `awaiting_review` (protective hold) and records a `system_auto_hold` action and audit event without permanently deleting the content or suspending the author.
- **Privacy-Blind Moderation Queue (`/moderation/queue`):** Scopes access by role (community moderators for assigned `c/[slug]`, global moderators/admins platform-wide), strips private author and reporter identifiers on anonymous content, and supports `Escalate — Language Specialist Needed`.
- **Appeals & Separation of Duties (`/moderation/appeals`):** Allows affected users to submit one structured appeal per moderation action and enforces backend separation of duties (`403 SEPARATION_OF_DUTIES_VIOLATION` if the original moderator attempts to decide their own appeal).
- **User Blocking & Muting (`PUT /api/v1/users/{handle}/block`, `/settings/privacy`):** Enforces bidirectional interaction blocks (`403 INTERACTION_BLOCKED` on comments/votes/reactions) and per-viewer feed/search filtering for both `block` and `mute` while preserving anonymous post privacy.

## Phase 10: Multilingual Experience, Localization & Derived Content Translation (`0009_phase10_translations`)

- **Database Schema (`0009_phase10_multilingual_translations.py`):** Adds `content_translations` keyed by `(source_type, source_id, target_locale, source_version_hash, provider_name)` where `source_version_hash` is the SHA-256 fingerprint of the canonical NFC-normalized source text.
- **Complete 5-Locale UI Localization (`en`, `ml`, `hi`, `ta`, `es`):** Full JSON catalogs under `frontend/locales/{en,ml,hi,ta,es}/common.json` with 100% key parity and an accessible `UiLocaleSwitcher` in the navigation bar.
- **On-Demand Non-Destructive Translation (`POST /api/v1/posts/{id}/translations`, `POST /api/v1/comments/{id}/translations`):** Translates eligible posts and comments via `TranslationProviderAdapter` (`LocalMockTranslationProvider` and `DisabledTranslationProvider`), invalidates cached translations automatically when source text is edited, enforces user blocks and moderation holds before serving cached translations, and preserves original content and anonymous author privacy.

## Phase 11: Workplace Experiences, Resignation Stories & Privacy-Safe Aggregated Insights (`0010_phase11_workplace`)

- **Database Schema (`0010_phase11_workplace_experiences.py`):** Adds `workplace_experience_details` (1:1 optional structured metadata linked to `posts.id`) and `workplace_insight_contributions` (`UNIQUE(user_id)` private structured contribution records completely separated from public narrative posts).
- **Workplace Experiences & Resignation Stories (`/workplace/experiences`, `/workplace/resignations`):** Reuses the canonical `posts` lifecycle and 3-mode identity system (`pseudonymous`, `anonymous`, `professional`) with 12 experience categories and 13 controlled resignation-reason categories.
- **Privacy-Safe Aggregation Engine (`/api/v1/workplace/insights`, `/insights/workplace`):** Computes statistical summaries exclusively from consented `workplace_insight_contributions` (`aggregation_consent = 1`), enforcing `n >= 10` distinct contributors for general metrics, `n >= 20` for sensitive metrics (`compensation_satisfaction` and `resignation_reasons`), complementary small-bucket suppression (`n < 3`), coarse sample-size banding (`10+`, `15+`, `20+`), and a maximum of 2 simultaneous filter dimensions with zero employer leaderboards.


## Phase 12: Production Readiness, Security Hardening, Performance & Launch Verification

- **Production Fail-Fast Startup Guard (`backend/app/config.py`):** Rejects startup when `APP_ENV=production` if `DATABASE_URL` is non-PostgreSQL or uses development credentials, if `SESSION_COOKIE_SECURE` is false, if `EMAIL_HMAC_PEPPER` or `EMAIL_ENCRYPTION_KEY_BASE64` uses development defaults, if `CORS_ORIGINS` is empty/wildcard/HTTP, or if `AI_CAPTION_PROVIDER`, `AI_IMAGE_PROVIDER`, or `TRANSLATION_PROVIDER` is set to `local_mock`. Disables `/api/v1/docs`, `/api/v1/redoc`, and `/api/v1/openapi.json` in production.
- **HTTP Security Headers, Body-Size Guard & CSRF Trusted-Origin Enforcement (`backend/app/middleware/security_headers.py`, `backend/app/api/deps.py`, `frontend/next.config.ts`):** Enforces a 1 MB JSON request body limit (`413 PAYLOAD_TOO_LARGE`), attaches `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, and conditional `Strict-Transport-Security`, and blocks state-changing requests from untrusted `Origin` headers (`403 UNTRUSTED_ORIGIN`).
- **Liveness, Readiness & Redacted Operational Metrics (`GET /api/v1/health/live`, `GET /api/v1/health/ready`, `GET /api/v1/health/metrics`):** Verifies database `SELECT 1` connectivity and media storage readiness (`503` when degraded) and exposes privacy-safe HTTP latency percentiles (`p50`, `p95`), status class counters, rate-limit `429` counts, DB pool bounds, and `meme_jobs` worker queue counts.
- **Worker Crash Recovery & CLI Runner (`backend/app/workers/meme_worker.py`, `backend/app/workers/runner.py`):** `recover_stale_generating_jobs()` re-queues or fails jobs left in `generating`/`validating` during an unexpected worker restart, and `python3 -m app.workers.runner` provides a production worker loop with graceful `SIGINT`/`SIGTERM` shutdown.
- **Full-Lifecycle Account Deletion & Self-Service Data Export (`DELETE /api/v1/me`, `GET /api/v1/me/export`):** Scrubs comments, deletes private `workplace_insight_contributions` (removing deleted users from future k-anonymity cohorts), bookmarks, blocks, notifications, and unpublished meme assets while preserving immutable `audit_events`.
- **Production Deployment, Backup Drill & Benchmark Tooling (`docker-compose.prod.yml`, `scripts/backup_restore_postgres.sh`, `scripts/performance_benchmark.py`, `docs/operations/PRODUCTION_READINESS_AND_RUNBOOKS.md`):** Reference production Compose topology, PostgreSQL `pg_dump`/`pg_restore` verification script, reproducible latency benchmark, and operational runbooks.


## Phase 12.1: Pre-Staging Hardening & Infrastructure Qualification

- **Shared Multi-Worker Redis Rate Limiting (`backend/app/core/rate_limit.py`, `backend/app/config.py`, `docker-compose.prod.yml`):** Introduces `RateLimitStore` with `InMemoryRateLimitStore` (`RATE_LIMIT_BACKEND=memory`) and `RedisRateLimitStore` (`RATE_LIMIT_BACKEND=redis`) backed by an atomic server-side Redis Lua script (`EVAL`), SHA-256 subject key hashing (`po:rl:{bucket}:{sha256}`), bounded TTLs (`PEXPIRE`), and a strict fail-closed policy (`503 RATE_LIMIT_BACKEND_UNAVAILABLE` when Redis is unreachable). Rejects `WEB_CONCURRENCY > 1` with `memory` rate limiting and requires `RATE_LIMIT_BACKEND=redis` in `production`.
- **Separated Request-Size Policies & Anti-Bypass Stream Guard (`backend/app/middleware/security_headers.py`, `backend/app/api/v1/memes.py`):** Enforces a `1 MB` limit on JSON/standard requests (`413 PAYLOAD_TOO_LARGE`) and a `6 MB` multipart envelope (`413 UPLOAD_TOO_LARGE`) + `5 MB` inner image limit (`422 IMAGE_TOO_LARGE`) on `POST /api/v1/memes/upload`, counting streamed ASGI body chunks incrementally so missing or falsified `Content-Length` headers cannot bypass limits.
- **24-Table Account Export & Deletion Lifecycle (`backend/app/modules/identity/service.py`):** Expands `GET /api/v1/me/export` to include all owner-scoped records (`account` with decrypted `recovery_email`, profiles, posts with `workplace_detail`, comments, votes, reactions, poll votes, bookmarks, community memberships, topic preferences, blocks/mutes by public handle, notifications, meme assets/jobs, submitted reports, appeals, and structured workplace contribution) and upgrades `DELETE /api/v1/me` to delete underlying media files from storage, purge cached `content_translations`, decrement `communities.member_count`, remove `workplace_insight_contributions`, and record a redacted append-only `account_self_deleted` audit event.
- **Process-Aware Operational Metrics (`backend/app/core/metrics.py`, `GET /api/v1/health/metrics`):** Explicitly tags HTTP counters/percentiles with `collection_scope: "process_local"`, `is_cluster_wide`, `worker_pid`, and `configured_web_concurrency`, and tags `worker_queue` with `collection_scope: "database_global"`.
- **Durable Object Storage Adapter (`backend/app/modules/memes/storage.py`):** Adds `S3CompatibleStorageAdapter` supporting AWS S3 and Cloudflare R2 (`STORAGE_BACKEND=s3|r2`) with AWS Signature Version 4 (`AWS4-HMAC-SHA256`), private ACLs (`x-amz-acl: private`), bounded timeouts, and time-limited presigned GET URLs alongside `LocalFilesystemStorageAdapter`.
- **16-Step PostgreSQL 16 Staging Qualification & Hardened Backup/Restore (`scripts/qualify_postgres_staging.py`, `scripts/backup_restore_postgres.sh`, `scripts/performance_benchmark.py`):** Provides reproducible 16-step PostgreSQL 16 qualification, hardened `umask 077` / `pressure_out_restore_drill_*` backup-restore scripts, and configurable multi-threaded synthetic benchmarking.


## Phase 12.2: Networked Staging Qualification & Eviction Hardening

- **Redis `noeviction` Policy & Wire-Protocol Qualification (`docker-compose.prod.yml`, `backend/app/core/rate_limit.py`):** Replaced `--maxmemory-policy volatile-ttl` with `--maxmemory-policy noeviction` on the dedicated rate-limiting Redis service so active rate-limit keys (which carry `PEXPIRE` TTLs) can never be silently evicted under memory pressure; `OOM` write errors fail closed with `503 RATE_LIMIT_BACKEND_UNAVAILABLE`. Verified `RedisRespClient` over real TCP loopback sockets (`LocalResp2TestServer`) across multiple workers and 20-thread bursts.
- **Staging Safety Verifier (`scripts/qualify_postgres_staging.py`):** Added `verify_staging_safety_guards()` requiring `APP_ENV=staging`, rejecting `prod`/`production` database, Redis, or CORS identifiers, and enforcing `^pressure_out_restore_drill_[0-9]{8,16}$` on restore target names.
- **S3/R2 Presigned URL Expiration & Log Redaction (`backend/app/modules/memes/storage.py`, `backend/app/logging_config.py`):** Canonicalized SigV4 object URI paths, added presigned URL expiration/tamper verification in `InMemoryS3Transport`, and expanded `logging_config.py` to scrub `X-Amz-Signature`, `X-Amz-Credential`, `X-Amz-Security-Token`, `s3_secret_access_key`, and `rediss?://` passwords.


## Phase 12.3: Local Windows Setup & D: Drive Development Guide

For complete local Windows 10/11 setup instructions—including **`D:\PressureOut` storage configuration** to protect a low-space `C:` drive, `docker-compose.local.yml` (local PostgreSQL 16 on `127.0.0.1:54329` and Redis 7 with `noeviction` on `127.0.0.1:63799`), `.env.local.example`, the 8 PowerShell automation scripts in `scripts/windows/`, and the 35-step local end-to-end smoke runner (`scripts/run_local_smoke_35.py`)—see **[`docs/development/WINDOWS_LOCAL_DEVELOPMENT.md`](docs/development/WINDOWS_LOCAL_DEVELOPMENT.md)**.
