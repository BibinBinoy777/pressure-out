# High-Level System Architecture

**Document ID:** ARCH-PO-001  
**Version:** 2.0.0  
**Related Diagrams:** [SYSTEM_CONTEXT.md](../diagrams/SYSTEM_CONTEXT.md), [SYSTEM_COMPONENTS.md](../diagrams/SYSTEM_COMPONENTS.md)

## 1. Architectural Philosophy: The Modular Monolith

Pressure Out adopts a **Modular Monolith** architecture for its initial build and public launch. Rather than splitting the application prematurely into distributed microservices—which introduces network serialization overhead, distributed transaction failures, schema drift, and operational complexity—all backend domain logic resides in a single deployable **FastAPI** codebase divided into strictly bounded Python packages (`modules/*`), backed by a single authoritative **PostgreSQL** database.

### 1.1 Core Architectural Invariants
1. **Single Source of Truth:** PostgreSQL 16+ is the authoritative store for all relational entities, full-text search indexes, rate-limit counters, and asynchronous job queues.
2. **Strict Public/Private Serialization Boundary:** Private identity attributes (`users.id`, `users.email_encrypted`, session metadata, IP hashes) are never passed into public response schemas. All public endpoints serialize exclusively through privacy-hardened Pydantic response models (`PublicPostResponse`, `PublicCommentResponse`, `PublicProfileResponse`).
3. **Provider-Neutral External Adapters:** External AI captioning, AI image generation, translation, object storage, and email delivery are isolated behind explicit Python `Protocol` / ABC adapter interfaces (`app/modules/*/adapters/`).
4. **Stateless API Tier + Shared Codebase Worker:** The HTTP API process is completely stateless so multiple replicas can run behind a load balancer. Slow, retryable, or externally dependent tasks (AI image generation, derived translation, media cleanup, email dispatch) execute in a separate **Background Worker** process launched from the exact same container image, polling PostgreSQL using `SELECT ... FOR UPDATE SKIP LOCKED`.

## 2. System Component Responsibilities

| Component | Technology | Primary Responsibilities | Explicit Non-Responsibilities |
| :--- | :--- | :--- | :--- |
| **Web Frontend** | Next.js (App Router), React, TypeScript, Tailwind CSS | Server-side rendering (SSR) for public SEO/discovery pages; interactive client components for post composer, identity selector, meme canvas editor, and moderation queue; locale string rendering. | Never enforces authoritative permissions; never filters private identity fields client-side; never holds AI provider API keys. |
| **Backend API** | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (Async) | Authentication, session validation, CSRF verification, role-based access control (RBAC), business rules, pre-publish PII checks, synchronous template meme rendering, database transactions, and privacy-safe serialization. | Never blocks HTTP worker threads on slow synchronous third-party AI image generation calls. |
| **Background Worker** | Python 3.12+ async worker loop (`app/workers/runner.py`) | Polls `meme_jobs` and `background_tasks` via `SKIP LOCKED`; executes AI image generation and translation adapter calls with bounded retries, timeouts, and cost logging; cleans up expired draft assets. | Never serves public HTTP traffic directly. |
| **Primary Database** | PostgreSQL 16+ (`citext`, `ltree`, `pg_trgm`, `uuid-ossp`) | ACID persistence for accounts, profiles, posts, nested comments, communities, votes, moderation queues, audit trails, full-text search (`tsvector`), and durable job queueing. | Never exposed directly to the public internet or frontend client. |
| **Object Storage** | Local filesystem volume (dev) / Private S3 or Cloudflare R2 (prod) | Stores curated meme template masters, rendered user memes, and AI-generated image assets. | Never configured as an unauthenticated public write bucket; all writes pass through backend MIME/size validation. |

## 3. Principal Data Flows

### 3.1 Synchronous Social Read/Write Flow
1. Browser sends request to `/api/v1/...` with `HttpOnly` session cookie and `X-CSRF-Token` header (on mutations).
2. FastAPI middleware resolves the session from `user_sessions`, checks account status (`active` vs. `suspended`/`cooldown`), and checks rate limits.
3. Domain service executes business logic inside an async SQLAlchemy transaction (`async with session.begin():`).
4. Domain service returns an internal domain DTO to the router.
5. Router maps the internal DTO through a privacy-enforcing Pydantic response schema (`PublicPostResponse`) that strips `author_user_id` whenever `identity_mode == 'anonymous'`.

### 3.2 Asynchronous AI Meme Generation Flow
1. Browser submits `POST /api/v1/memes/jobs` with prompt, style, language tag, and `Idempotency-Key`.
2. FastAPI validates quota limits and prompt policy synchronously, inserts a `meme_jobs` record with `status = 'queued'`, and immediately returns `202 Accepted` with the `job_id`.
3. Background Worker claims the `queued` job atomically using `SELECT ... FROM meme_jobs WHERE status = 'queued' ORDER BY created_at ASC FOR UPDATE SKIP LOCKED LIMIT 1`, sets `status = 'generating'`, and calls `ImageProviderAdapter.generate_image()`.
4. On completion, the worker validates the image bytes, uploads the asset via `StorageAdapter`, creates a `meme_assets` record and `ai_provider_usage` cost entry, and marks the job `ready`.
5. Browser polls `GET /api/v1/memes/jobs/{job_id}` (with exponential backoff: 1s, 2s, 4s) until `status == 'ready'`, then renders the image in the Meme Studio preview editor.

## 4. Supporting Infrastructure Evaluation & Staging

In accordance with Section 5 of the Phase 1 specification, optional infrastructure is evaluated against concrete operational thresholds:

| Infrastructure | MVP Decision | Justification & Threshold for Adoption |
| :--- | :--- | :--- |
| **PostgreSQL Full-Text Search (`tsvector`)** | **Included in MVP** | Native GIN indexes over title and body handle tens of thousands of posts with sub-50ms latency and zero synchronization lag. Dedicated search (Meilisearch/OpenSearch) is deferred until index size > 10 GB or complex CJK/Indic morphological tokenization requires it. |
| **PostgreSQL `SKIP LOCKED` Queue** | **Included in MVP** | Eliminates the need for Redis/RabbitMQ in MVP while providing transactional guarantees (a job is never queued if its database transaction rolls back). |
| **Redis (Cache / Rate Limit / Broker)** | **Deferred Post-MVP** | Unpooled or multi-service complexity is unnecessary at launch. Introduce Redis only when session/rate-limit lookups exceed 15% of PostgreSQL IOPS or when WebSocket real-time push is added. |
| **CDN & Edge WAF** | **Staging / Production Only** | Local dev runs directly against Next.js/FastAPI. Production places Cloudflare/CloudFront in front of the app for TLS termination, DDoS mitigation, and signed media caching. |
