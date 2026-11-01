# Phase 1 & MVP Acceptance Criteria

**Document ID:** AC-PO-004  
**Version:** 2.0.0  

## 1. Phase 1 Completion Matrix (Architecture & Specification Gate)

Phase 1 is verified against the mandatory criteria defined in the project specification:

| Category | Acceptance Criterion | Verification Artifact | Status |
| :--- | :--- | :--- | :--- |
| **Product Requirements** | Product vision, target personas, and core user journeys are documented. | `PRODUCT_REQUIREMENTS.md`, `USER_JOURNEYS.md` | **Satisfied** |
| **Product Requirements** | MVP features and deferred features/infrastructure are explicitly distinguished. | `MVP_SCOPE.md` | **Satisfied** |
| **Product Requirements** | Account identity, optional professional profile, and per-post/comment identity modes are explicitly defined. | `IDENTITY_AND_PRIVACY.md`, `PRODUCT_REQUIREMENTS.md` | **Satisfied** |
| **Product Requirements** | AI Meme Studio workflows, quotas, and fallbacks are specified. | `AI_MEME_STUDIO.md` | **Satisfied** |
| **Product Requirements** | Multilingual Unicode, BCP 47 tagging, UI localization, and non-destructive translation rules are documented. | `MULTILINGUAL_SUPPORT.md` | **Satisfied** |
| **Product Requirements** | Trust, privacy, PII guardrails, and moderation workflows are identified. | `SECURITY_AND_MODERATION.md` | **Satisfied** |
| **System Architecture** | Frontend and backend responsibilities and modular-monolith boundaries are clear. | `SYSTEM_ARCHITECTURE.md`, `FRONTEND_ARCHITECTURE.md`, `BACKEND_ARCHITECTURE.md` | **Satisfied** |
| **System Architecture** | Principal data flows, external service adapters, and mandatory vs. optional infrastructure are justified. | `SYSTEM_ARCHITECTURE.md`, `DEPLOYMENT_AND_OPERATIONS.md` | **Satisfied** |
| **Data & API** | Conceptual ER model and production-oriented PostgreSQL DDL cover all MVP workflows, constraints, and indexes. | `DATABASE_DESIGN.md`, `DATABASE_RELATIONSHIPS.md` | **Satisfied** |
| **Data & API** | Versioned `/api/v1` REST API contract defines schemas, auth, cursor pagination, rate limits, and error envelopes. | `API_SPECIFICATION.md` | **Satisfied** |
| **Data & API** | Public API serializers strictly isolate private account identifiers on anonymous content. | `API_SPECIFICATION.md`, `IDENTITY_AND_PRIVACY.md` | **Satisfied** |
| **AI Meme Studio** | Template rendering, AI captioning, async AI image generation, provider abstraction, storage, quotas, and privacy rules are defined. | `AI_MEME_STUDIO.md`, `MEME_GENERATION_FLOW.md` | **Satisfied** |
| **Security & Privacy** | Auth/session security, anonymous ownership, data retention/deletion, reporting, RBAC, and threat mitigations are recorded. | `IDENTITY_AND_PRIVACY.md`, `SECURITY_AND_MODERATION.md` | **Satisfied** |
| **Documentation Quality** | All 8 required architecture/flow diagrams exist in Mermaid format and match written specs; ADRs, testing strategy, risks, and 12-phase roadmap are complete. | `docs/diagrams/*.md`, `ARCHITECTURE_DECISIONS.md`, `DEVELOPMENT_PHASES.md`, `TESTING_STRATEGY.md`, `RISKS_AND_DEPENDENCIES.md` | **Satisfied** |

## 2. Measurable Acceptance Criteria for Subsequent Implementation Phases (Phases 2–12)

Each implementation phase must pass these concrete, automated and manual verification gates before advancing:

### 2.1 Account & Identity Gate (Phase 3)
* **AC-IMP-01 (Zero Real-Name Registration):** Automated API test verifies `POST /api/v1/auth/register` succeeds with only `handle` and `password` (no `full_name`, `employer`, or `work_email` required).
* **AC-IMP-02 (Cookie & CSRF Security):** Login issues an `HttpOnly`, `Secure` (in prod), `SameSite=Lax` session cookie, and state-changing requests (`POST`, `PATCH`, `DELETE`) without a valid CSRF token are rejected with `403 Forbidden`.
* **AC-IMP-03 (Strict Serializer Isolation):** Automated privacy test creates a post and a comment with `identity_mode = 'anonymous'`, queries `GET /api/v1/posts/{id}`, `GET /api/v1/feed`, `GET /api/v1/search`, and `GET /api/v1/profiles/{handle}`, and asserts that:
  1. Neither the raw `user_id`, `handle`, `email`, nor `public_profile_id` appears anywhere in the JSON response or response headers.
  2. Querying the author's public profile `GET /api/v1/profiles/{handle}/posts` does **not** include any of their `anonymous` posts.
* **AC-IMP-04 (Author Ownership Preserved):** The authenticated author of an `anonymous` post can still edit (`PATCH /api/v1/posts/{id}`) and delete (`DELETE /api/v1/posts/{id}`) their post, while any other non-moderator user receives `403 Forbidden`.

### 2.2 Core Social, Communities & Engagement Gate (Phases 4–7)
* **AC-IMP-05 (Polymorphic Post Lifecycle):** Users can create, view, edit, and soft-delete all 8 post types (`discussion`, `question`, `rant`, `story`, `meme`, `poll`, `advice_request`, `workplace_experience`) with valid tag and community associations.
* **AC-IMP-06 (Sticky Anonymous OP Replies):** When User A creates Post X with `identity_mode = 'anonymous'` and submits a comment on Post X without explicitly overriding `identity_mode`, the comment is saved as `anonymous` and rendered as `Anonymous OP`.
* **AC-IMP-07 (Vote Idempotency):** Concurrent `PUT /api/v1/posts/{id}/vote` requests from the same user enforce the database `UNIQUE (user_id, target_type, target_id)` constraint, preventing duplicate vote inflation, and cached `score` matches `SUM(value)`.
* **AC-IMP-08 (Stable Cursor Pagination):** Fetching `Latest` and `Popular` feeds and nested comment lists via `cursor` parameter returns deterministic pages with zero duplicate or skipped items even when new posts are inserted concurrently.

### 2.3 AI Meme Studio Gate (Phase 8)
* **AC-IMP-09 (Template Independence):** With external AI providers disabled or returning `503 Service Unavailable`, a user can still select a meme template, add top/bottom Unicode text, render the final image, download it, and publish it to a community feed.
* **AC-IMP-10 (Async Job Lifecycle & Idempotency):** Submitting `POST /api/v1/memes/jobs` with an `Idempotency-Key` header creates exactly one job, transitions cleanly through `queued -> generating -> validating -> ready`, enforces per-user daily quota limits (`429 Too Many Requests` when exceeded), and allows cancellation while `queued`.
* **AC-IMP-11 (Prompt Privacy Stripping):** Unit tests verify that `CaptionProviderAdapter` and `ImageProviderAdapter` receive only the sanitized prompt text, target language tag, and style enum—never the caller's `user_id`, `handle`, `email`, or session metadata.

### 2.4 Multilingual & Trust/Safety Gate (Phases 9–10)
* **AC-IMP-12 (Unicode Round-Trip Integrity):** Automated integration test submits posts, comments, and meme captions containing Devanagari (Hindi), Tamil, Malayalam, Arabic (RTL), Spanish, CJK, and emoji characters, verifying lossless UTF-8 storage, search indexing, and JSON serialization.
* **AC-IMP-13 (Non-Destructive Translation):** Requesting a translation creates a derived row in `content_translations` linked to `source_id` while leaving `posts.body` byte-for-byte unchanged.
* **AC-IMP-14 (Moderation RBAC & Audit Trail):** Every moderator action (`restrict`, `remove`, `restore`, `cooldown`) requires a valid `reason_code`, writes an immutable record to `audit_events`, andmoderator endpoints never expose private `users.email_encrypted` or IP hashes.

## 3. Recommended Controlled Pilot Metrics (Phase 12)

When the MVP enters its controlled pilot cohort, evaluate product-market fit and operational health using these metrics (avoiding toxic outrage-maximization metrics):

| Metric Category | Key Indicator | Healthy Pilot Target |
| :--- | :--- | :--- |
| **Activation & Creation** | % of registered users who publish a post, comment, reaction, or meme within 7 days | ≥ 35% |
| **Meme Studio Adoption** | Meme creation completion rate (started in Studio -> downloaded or published) | ≥ 50% |
| **Community Responsiveness** | First-response rate (% of discussion/question/advice posts receiving ≥ 1 reply within 24h) | ≥ 60% |
| **Identity Mode Mix** | Distribution across `Pseudonymous`, `Anonymous`, and `Professional` posts | Healthy mix across all 3 modes |
| **AI Cost & Reliability** | AI caption/image job failure rate & average AI spend per daily active creator | < 3% failure rate; within capped budget |
| **Safety & Moderation Health** | Median time-to-triage for high-priority (`doxxing_pii`, `threat`) reports | < 2 hours |
| **Privacy Integrity** | Confirmed public API identity leakage incidents | **0 (Zero tolerance)** |
