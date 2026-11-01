# Architecture Decision Records (ADRs)

**Document ID:** ADR-PO-001  
**Version:** 2.0.0  

This document records the 10 foundational architecture decisions governing Pressure Out, including alternatives evaluated, trade-offs, and explicit triggers for revisiting each decision.

---

## ADR-01: Adopt a Modular Monolith Over Microservices for Initial Launch
* **Chosen Approach:** Build the backend as a single deployable FastAPI application organized into strict internal domain packages (`identity`, `posts`, `communities`, `feed`, `memes`, `languages`, `moderation`, `notifications`) sharing a single PostgreSQL database.
* **Alternatives Considered:** (A) Separate microservices for Auth, Social Feed, Meme Studio, and Moderation communicating via gRPC/Kafka; (B) Serverless functions per endpoint.
* **Reasoning:** Microservices introduce distributed transaction failures, network latency, deployment orchestration complexity, and duplicate schema boilerplate before product-market fit is proven. A modular monolith gives us ACID transactions across domain boundaries and rapid local development.
* **Trade-offs:** Developers must respect package import boundaries (enforced via linting/tests) so modules do not become tightly coupled.
* **Revisit Trigger:** Extract the `memes` worker or `moderation` service into an independent deployment only when team size exceeds 15+ engineers or resource scaling profiles diverge sharply.

## ADR-02: Separate Next.js Frontend and FastAPI Backend
* **Chosen Approach:** Decouple the presentation layer (Next.js + React + TypeScript) from the core API and business logic layer (Python + FastAPI) communicating over a versioned `/api/v1` REST contract.
* **Alternatives Considered:** (A) Full-stack Next.js (Node.js Server Actions / Prisma only); (B) Server-rendered Python templates (Jinja2 + HTMX).
* **Reasoning:** Next.js provides best-in-class React interactivity (essential for the Meme Studio canvas editor and responsive feeds) plus SSR for public discovery pages. Python + FastAPI provides a superior ecosystem for image manipulation (Pillow/HarfBuzz), AI provider SDKs, NLP/PII scanning, and clean Pydantic schema serialization.
* **Trade-offs:** Requires maintaining contract synchronization between FastAPI Pydantic schemas and TypeScript interfaces (mitigated via automated OpenAPI TypeScript code generation).
* **Revisit Trigger:** None anticipated; this split cleanly supports future mobile clients consuming the same `/api/v1` contract.

## ADR-03: PostgreSQL as the Single Authoritative Data Store (Including FTS & Job Queue)
* **Chosen Approach:** Use PostgreSQL 16+ as the sole persistent database for relational records, Full-Text Search (`tsvector` + GIN), hierarchical comment trees (`ltree`), and background job queuing (`FOR UPDATE SKIP LOCKED`).
* **Alternatives Considered:** (A) MongoDB/NoSQL document store; (B) Adding Elasticsearch and Redis/RabbitMQ from Day 1.
* **Reasoning:** Social identity boundaries, unique voting constraints, and account deletion cascades require strict relational integrity (`FOREIGN KEY`, `UNIQUE`, `CHECK`). PostgreSQL's native `tsvector` and `SKIP LOCKED` eliminate two entire external infrastructure services in the MVP.
* **Trade-offs:** Write-heavy tables (`votes`, `meme_jobs`) require careful indexing and vacuum tuning as load grows.
* **Revisit Trigger:** Introduce Redis when session/rate-limit queries exceed 15% of DB CPU; introduce a dedicated search engine if multilingual search latency exceeds 500ms p95 at > 1M posts.

## ADR-04: Five-Layer Separation of Private Account Identity and Public Display Identity
* **Chosen Approach:** Separate `users` (private authentication) from `public_profiles` (pseudonymous `@handle`) and `professional_profiles` (optional role/industry), and store an explicit `identity_mode` (`pseudonymous`, `anonymous`, `professional`) on every post and comment while retaining private `author_user_id` ownership.
* **Alternatives Considered:** (A) Storing `NULL` in `author_user_id` for anonymous posts (true orphan posts); (B) Requiring a single fixed identity per account (forcing users to create multiple accounts).
* **Reasoning:** If `author_user_id` were `NULL`, authors could never edit or delete their own anonymous posts, could not receive reply notifications, could not be auto-tagged as `Anonymous OP` in their own thread, and repeat spammers/doxxers could not be rate-limited or suspended. Keeping `author_user_id` private in the database while stripping it in `PublicPostSerializer` delivers both safety and usability.
* **Trade-offs:** Requires rigorous serializer discipline and automated security regression tests so `author_user_id` never leaks in any public API payload.
* **Revisit Trigger:** Never weaken the serializer isolation; consider optional client-side encrypted drafts in future versions.

## ADR-05: Voluntary, Unverified Professional Profiles in MVP
* **Chosen Approach:** Allow users to configure optional professional context (`role_title`, `industry`, `experience_band`, `region_label`) without requiring corporate email verification or employment documents, and clearly label these badges as self-declared in the UI.
* **Alternatives Considered:** (A) Mandatory work email verification (Blind model); (B) Uploading offer letters/ID cards for manual review.
* **Reasoning:** Work email verification alienates workers at small companies, blue-collar/service workers, fresh graduates, and privacy-conscious employees who fear employer IT monitoring. Manual document review is a massive privacy and operational liability.
* **Trade-offs:** A user can self-declare a senior title without proof; therefore, the UI never displays a "Verified Employee" checkmark in MVP.
* **Revisit Trigger:** In Phase 11+ (Company Insights), evaluate optional zero-knowledge cryptographic domain verification where the work email is verified and immediately discarded.

## ADR-06: Multilingual Foundation from Day 1 with Non-Destructive Derived Translations
* **Chosen Approach:** Enforce UTF-8 everywhere, attach a BCP 47 `content_language` tag (`en`, `hi`, `ml`, `ta`, `es`, `mul`, `und`) to every post/comment, externalize UI strings into locale JSON catalogs, and store translations in a separate `content_translations` table keyed by `source_version_hash`.
* **Alternatives Considered:** (A) English-only schema in MVP; (B) Overwriting post text with auto-translated text on save.
* **Reasoning:** Retrofitting character encodings, font shaping, and language tags onto an existing social database is expensive and error-prone. Overwriting original text destroys cultural nuance, humour, and mixed-language wordplay.
* **Trade-offs:** Slightly wider post/comment schema and need to bundle Noto fonts in the meme renderer container.
* **Revisit Trigger:** Expand active UI locale catalogs and translation provider coverage progressively based on user language telemetry.

## ADR-07: Isolate AI Meme Studio Providers Behind Server-Side Adapters
* **Chosen Approach:** Define strict Python `Protocol` interfaces (`CaptionProviderAdapter`, `ImageProviderAdapter`) in `app/modules/memes/adapters/`, ship a deterministic `LocalMockAIProvider` for local dev/CI, and keep all commercial AI vendor calls asynchronous, quota-capped, and server-side.
* **Alternatives Considered:** (A) Calling OpenAI/Stability SDKs directly inside FastAPI route handlers; (B) Client-side AI generation using user-supplied keys.
* **Reasoning:** Generative AI pricing, model quality, latency, and safety policies change rapidly. An adapter boundary allows swapping providers via configuration without touching frontend or post-publishing code, and ensures template meme creation works even during complete AI provider outages.
* **Trade-offs:** Requires maintaining normalized error mapping and job polling (`meme_jobs`).
* **Revisit Trigger:** Add streaming WebSocket/SSE job notifications only if polling `GET /api/v1/memes/jobs/{id}` creates measurable load.

## ADR-08: Materialized Path (`ltree`) for Nested Comment Threads
* **Chosen Approach:** Store both `parent_comment_id` and a PostgreSQL `ltree` materialized path (`path`) on `comments`, capped at a maximum visual nesting depth of 10.
* **Alternatives Considered:** (A) Naive adjacency list loading all comments for a post in memory; (B) Nested Sets (`lft`/`rgt`).
* **Reasoning:** Loading all comments at once fails on viral workplace threads with 2,000+ replies. Nested sets suffer from write lock contention on every insert. PostgreSQL `ltree` with a GiST index allows fast O(1) subtree queries and cursor pagination of top-level branches.
* **Trade-offs:** PostgreSQL-specific extension (acceptable since PostgreSQL is our committed primary database).
* **Revisit Trigger:** None.

## ADR-09: Risk-Tiered Moderation with Pre-Publish PII Guardrails and Blind Mod Queues
* **Chosen Approach:** Run synchronous pre-publish regex/heuristic checks for PII/secrets, publish normal posts immediately, auto-hold posts that cross high-severity report velocity thresholds (`doxxing_pii`, `threat`), and hide private author identity from moderators.
* **Alternatives Considered:** (A) Manual pre-moderation of every post before publication; (B) Showing moderators the author's `@handle` and email on anonymous posts.
* **Reasoning:** Manual pre-moderation kills real-time conversational energy and requires a massive moderation staff. Exposing anonymous authors to volunteer or community moderators breaks user trust.
* **Trade-offs:** Sophisticated coded harassment can bypass regex checks and relies on community reporting + moderator triage.
* **Revisit Trigger:** Add lightweight automated toxicity/PII classifier scoring in the background worker as post volume scales.

## ADR-10: Defer Redis, Dedicated Search, Real-Time DMs, and Company Pages from MVP
* **Chosen Approach:** Explicitly exclude Direct Messaging (DMs), live video, dedicated Company Pages, Redis, and Elasticsearch from the MVP build.
* **Alternatives Considered:** Including 1:1 DMs and company rating pages in the first release.
* **Reasoning:** Anonymous 1:1 DMs are a notorious vector for untraceable harassment, scams, and extortion. Company Pages with small sample sizes (< 25 employees) easily identify whistleblowers and invite employer defamation lawsuits.
* **Trade-offs:** Users cannot privately message another poster in v1; all interactions happen in public/moderated community threads.
* **Revisit Trigger:** Revisit opt-in, double-consent messaging and k-anonymized company insights only after Phase 12 pilot validation.
