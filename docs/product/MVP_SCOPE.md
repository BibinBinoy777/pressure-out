# MVP Scope, Feature Matrix & Infrastructure Staging

**Document ID:** MVP-PO-003  
**Version:** 2.0.0  

## 1. Scoping Philosophy

Pressure Out's MVP must feel like a **complete, distinctive product**—not a barebones CRUD forum—while avoiding premature enterprise bloat. The MVP includes the signature **AI Meme Studio**, **per-post three-mode identity switching**, **core communities and threaded discussions**, **multilingual Unicode/locale foundations**, and **essential trust & safety controls**.

## 2. Feature Scope Matrix (MVP vs. Post-MVP)

| Domain | Capability | Priority | Phase Introduced | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Identity & Auth** | Pseudonymous handle + password registration, optional recovery email, server-managed HttpOnly sessions | **P0 (MVP)** | Phase 3 | Core low-friction onboarding requirement. |
| **Identity & Auth** | Optional self-declared Professional Profile (`role`, `industry`, `experience_band`) | **P0 (MVP)** | Phase 3 | Enables credible career advice without forced employer verification. |
| **Identity & Auth** | Per-post & per-comment Identity Selector (`pseudonymous`, `anonymous`, `professional`) + Sticky `Anonymous OP` replies | **P0 (MVP)** | Phase 3 & 4 | Defining privacy differentiator of Pressure Out. |
| **Identity & Auth** | OAuth / Passkeys / Work-email cryptographic zero-knowledge verification | **Deferred (Post-MVP)** | Post-Phase 12 | Avoids early third-party identity coupling and user distrust. |
| **Social Core** | Unified post composer supporting `discussion`, `question`, `rant`, `story`, `meme`, `poll`, `advice_request`, `workplace_experience` | **P0 (MVP)** | Phase 4 | Shared `posts` table handles all core workplace expression. |
| **Social Core** | Admin-seeded topic communities (11 starter spaces), join/leave, community feeds, community rules | **P0 (MVP)** | Phase 5 | Prevents empty community sprawl at launch. |
| **Social Core** | User-created communities with approval workflow | **P2 (Later)** | Post-Phase 12 | Deferred until active user density supports new sub-communities. |
| **Engagement** | Nested threaded comments (`ltree` path), cursor pagination, up/down voting, workplace reactions, saved bookmarks | **P0 (MVP)** | Phase 6 | Core community interaction loops. |
| **Feed & Search** | `Latest`, `Popular` (time-decayed), `Following`, `Explore`, PostgreSQL Full-Text Search (`tsvector`), tag/language filters | **P0 (MVP)** | Phase 7 | Explainable discovery without ML or external search clusters. |
| **AI Meme Studio** | Template Meme Maker (curated templates, top/bottom/freeform text, server/canvas render, download & publish) | **P0 (MVP)** | Phase 8 | Predictable, zero-marginal-cost baseline for meme creation. |
| **AI Meme Studio** | AI Caption Assistant & Asynchronous AI Image Generation behind provider adapters + quotas + cost controls | **P0 (MVP)** | Phase 8 | Signature product feature differentiating Pressure Out. |
| **AI Meme Studio** | Meme remixing / derivative attribution chains | **P2 (Later)** | Post-Phase 12 | Requires mature copyright/attribution rules first. |
| **Trust & Safety** | Pre-publish PII warning regex, content/user reporting, user blocking/muting, moderator queue, action log, appeals | **P0 (MVP)** | Phase 9 | Mandatory before any real users generate anonymous content. |
| **Notifications** | In-app notifications (replies, moderation outcomes, meme job completion) + user preferences | **P1 (MVP Polish)** | Phase 6 & 9 | Drives retention and keeps users informed of async jobs. |
| **Multilingual** | End-to-end UTF-8, BCP 47 language tags on posts, externalized UI locale catalogs (`en` default + starter locales), on-demand derived translation adapter | **P0 Foundation / P1 Translation** | Phase 2 (UTF-8) & Phase 10 (Locales/Translation) | Prevents schema rewrites while staging translation API spend. |
| **Workplace Insights** | Structured Exit Stories (`exit_story_details`) + k-anonymity aggregated insights (`n >= 25` threshold) | **P1 (Late MVP)** | Phase 11 | High-value workplace feature; aggregation requires sample size guards. |
| **Company Pages** | Dedicated company profiles, employer dispute/response workflows, verified company ratings | **Deferred (Post-MVP)** | Post-Phase 12 | High legal/defamation overhead and requires critical mass per company. |
| **Real-Time / Media** | Direct Messaging (DMs), live chat rooms, user-uploaded video feeds, native iOS/Android apps | **Out of Scope** | Post-Phase 12 | DMs create severe harassment/moderation vectors on anonymous platforms; responsive web PWA covers mobile initially. |

## 3. Page-by-Page MVP Classification

| Route / Page | Access Level | Classification | Notes |
| :--- | :--- | :--- | :--- |
| `/` (Landing / Home Feed) | Public (Guest & Auth) | **Essential MVP** | Guests see Popular/Latest public feed + registration callout. |
| `/explore` | Public | **Essential MVP** | Curated starter communities, trending tags, and fresh posts. |
| `/communities` & `/c/[slug]` | Public read / Auth join | **Essential MVP** | Directory of topic communities and individual community feeds. |
| `/p/[postId]` | Public read / Auth reply | **Essential MVP** | Full post view, poll widget, meme display, paginated comment tree. |
| `/search` | Public | **Essential MVP** | Keyword, community, post-type, and language filtered search. |
| `/auth/login`, `/auth/register`, `/auth/recovery` | Public (Unauthenticated) | **Essential MVP** | Pseudonymous registration, session login, optional recovery flow. |
| `/create` | Authenticated | **Essential MVP** | Unified post composer with Identity Mode & Language selectors. |
| `/meme-studio` | Authenticated | **Essential MVP** | Template editor, AI Caption Assistant, and AI Image Generation studio. |
| `/u/[handle]` | Public | **Essential MVP** | Public pseudonymous profile (shows only `pseudonymous` & `professional` posts; **never** `anonymous` posts). |
| `/settings/profile` & `/settings/privacy` | Authenticated | **Essential MVP** | Manage handle, optional professional fields, sessions, blocks, account deletion. |
| `/saved` & `/notifications` | Authenticated | **Essential MVP** | Bookmarked posts and in-app notification center. |
| `/moderation/queue` & `/moderation/audit` | Moderator / Admin RBAC | **Essential MVP** | Triage reports, execute moderation actions, review appeals & audit logs. |
| `/insights/exit-stories` | Public / Auth | **Phase 11 Enhancement** | Aggregated resignation trends (only rendered when sample size rules pass). |

## 4. Supporting Infrastructure Classification

To obey the principle of **conservative infrastructure, ambitious product experience**, every supporting component is strictly classified:

| Component | Classification | MVP Implementation Approach | Trigger to Upgrade / Introduce |
| :--- | :--- | :--- | :--- |
| **PostgreSQL 16+** | **Required for MVP** | Single primary instance (Docker container locally; managed Postgres with automated daily backups in staging/prod). Handles relational data, FTS (`tsvector`), rate-limit counters, and job queue (`FOR UPDATE SKIP LOCKED`). | Read replicas when CPU > 65% sustained; partitioning when `posts`/`votes` exceed 50M rows. |
| **Background Worker** | **Required for MVP** | Lightweight async Python worker process running from the same FastAPI codebase, polling PostgreSQL `meme_jobs` and `background_tasks` via `SKIP LOCKED`. | Dedicated Celery/Arq + Redis broker only if background job throughput exceeds 100 jobs/sec. |
| **Object Storage** | **Required for MVP** | Local mounted volume (`./storage/media`) behind a storage adapter in dev; private S3/R2 bucket with short-lived signed URLs or CDN proxy in staging/prod. | Mandatory before any public pilot so container restarts do not lose generated memes. |
| **AI Provider Integration** | **Required Interface / Configurable Provider** | `CaptionProviderAdapter` and `ImageProviderAdapter` defined in code with a deterministic `LocalMockAIProvider` for offline dev/CI and pluggable HTTP adapters for OpenAI/Anthropic/Stability/Flux in staging/prod. | Activated via environment variables once provider benchmarking & budget caps are signed off. |
| **Redis** | **Deferred (Not in MVP)** | Rate limiting and session validation run against indexed PostgreSQL tables (with short in-memory TTL caches where safe). | Introduce Redis when DB session/rate-limit queries exceed 15% of total DB load or when multi-instance distributed rate limiting is needed. |
| **Dedicated Search Engine (Meilisearch / OpenSearch)** | **Deferred (Not in MVP)** | PostgreSQL `tsvector` GIN indexes + `pg_trgm` handle keyword and tag search. | Introduce when multilingual morphological search needs or p95 search latency > 500ms justify operational cost. |
| **Email Delivery Service** | **Optional in MVP** | Abstracted behind `EmailProviderAdapter`. Local dev uses console/Mailpit. Accounts without recovery email use recovery codes. | Required before public pilot if email-based password reset is enabled. |
