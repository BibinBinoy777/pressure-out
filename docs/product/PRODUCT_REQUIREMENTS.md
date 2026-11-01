# Product Requirements Document (PRD) — Pressure Out

**Document ID:** PRD-PO-001  
**Version:** 2.0.0  
**Status:** Baseline Approved for Phase 2 Implementation  

## 1. Product Vision & Positioning

### 1.1 Vision Statement
**Pressure Out** is the social home for the unfiltered side of working life. It provides employees, job seekers, recent graduates, freelancers, and managers with an expressive, community-driven platform to laugh about workplace absurdity, vent frustrations, create and share memes, discuss compensation and career moves, share resignation stories, and support one another—without the pressure of maintaining a polished corporate persona.

### 1.2 Brand Identity
* **Product Name:** Pressure Out
* **Primary Tagline:** *Your Work. Your Chaos. Your People.*
* **Secondary Brand Message:** *Work is serious. Talking about it doesn't have to be.*

### 1.3 Market Differentiation
Existing platforms force working people into an uncomfortable compromise:
1. **Polished Professional Networks (e.g., LinkedIn):** Require real-world identity, employer visibility, and performative positivity. Candid discussion of burnout, bad management, or salary disparities carries immediate career risk.
2. **Corporate-Verified Boards (e.g., Blind):** Require work email verification, excluding employees at smaller companies, students/freshers, contractors, and workers who rightly distrust entering corporate credentials into third-party apps. Their culture also skews heavily toward narrow Big Tech compensation anxiety rather than relatable everyday humour.
3. **Generalist Forums (e.g., Reddit, X):** Lack dedicated per-post workplace identity toggles (forcing users to juggle burner accounts) and lack built-in creative tools tailored for workplace memes and structured exit stories.

Pressure Out bridges this gap by combining **Reddit-style topic communities**, **per-post identity switching (Pseudonymous, Anonymous, Professional)** under a single account, **first-class AI Meme Studio creation**, and **multilingual inclusivity from Day 1**.

## 2. Core Product Principles as Architectural Requirements

### Principle 1: Freedom of Workplace Expression
The platform must support the full emotional spectrum of working life—from light-hearted office memes and Friday celebrations to serious discussions about burnout, toxic management, layoffs, interviews, and salary transparency.
* **Architectural Impact:** A unified, polymorphic `posts` content model supporting 8 distinct post types (`discussion`, `question`, `rant`, `story`, `meme`, `poll`, `advice_request`, `workplace_experience`) with rich tagging and optional structured attachments (polls, meme assets, exit-story metadata).

### Principle 2: Identity Is Optional & User-Controlled Per Post
Real names, employer verification, and employment documents must never be required for registration or ordinary participation.
* **Architectural Impact:** Strict separation between `users` (private authentication & ownership) and `public_profiles` (pseudonymous handle) plus `professional_profiles` (optional role/industry/experience fields). Every post and comment explicitly stores an `identity_mode` (`pseudonymous`, `anonymous`, `professional`), and backend response serializers strip all author linkage when `anonymous` mode is active.

### Principle 3: Honest Anonymity Boundaries
Pressure Out must never make false promises of "cryptographic untraceability" or "absolute anonymity."
* **Architectural Impact:** The system maintains an internal database foreign key (`author_user_id`) on all posts and comments so authors can edit/delete their own anonymous content, receive reply notifications, and remain subject to anti-abuse moderation. Simultaneously, the UI displays pre-publish reminders warning users that self-disclosed contextual details (specific dates, niche job titles, project names) can still allow coworkers to infer their identity.

### Principle 4: Multilingual by Design
Workplace culture is global and frequently code-switched (e.g., English mixed with Hindi, Tamil, Malayalam, Spanish, or Tagalog).
* **Architectural Impact:** Full UTF-8 support across database, API, and UI; BCP 47 language tags on posts and comments (including `und` for undetermined and `mul` for mixed-language); externalized UI localization strings; and non-destructive derived translations stored alongside—never overwriting—the authoritative original text.

### Principle 5: AI Meme Studio Is a Core Product Feature
Humour is the primary antidote to workplace burnout and the strongest organic growth loop for the platform.
* **Architectural Impact:** The AI Meme Studio is designed as a core domain module (`modules/memes`) supporting instant deterministic template rendering, AI-assisted workplace caption generation, and asynchronous AI image generation behind vendor-neutral provider adapters with strict per-user quotas and spend circuit breakers.

### Principle 6: Privacy and Responsible Moderation
Candid workplace criticism must coexist with robust protection against doxxing, targeted harassment, defamation of named private individuals, and spam.
* **Architectural Impact:** Pre-publish PII detection warnings, risk-tiered moderation queues, community and platform moderator RBAC, user-level blocking/muting, and an immutable administrative audit log (`audit_events`) that prevents casual staff snooping on anonymous authors.

## 3. Functional Requirements Summary

### 3.1 Account & Identity Requirements
* **FR-ID-01:** Users can register using only a unique pseudonymous `handle` and password (with an optional recovery email hashed/encrypted at rest). No real name, phone number, employer name, or work email is required.
* **FR-ID-02:** Users may optionally configure a **Professional Profile** containing voluntary fields: `role_title`, `industry`, `years_experience_band`, and `region`. These fields are clearly marked as unverified self-disclosures in the UI.
* **FR-ID-03:** When composing any post or comment, the user selects their `identity_mode`:
  * `pseudonymous`: Displays `@handle` and links to the public profile.
  * `anonymous`: Displays `Anonymous Member` (or `Anonymous OP` if replying in their own anonymous post thread) with a thread-scoped deterministic alias hash where helpful, and zero link to `@handle` or `user_id`.
  * `professional`: Displays `@handle` plus their configured professional badge (e.g., *Senior QA Engineer • FinTech • 5–8 yrs*), or allows anonymous+professional role context if selected.
* **FR-ID-04:** **Sticky OP Anonymity Guardrail:** When the author of an `anonymous` post comments inside their own post's discussion thread, the comment composer defaults to `anonymous` (`Anonymous OP`) and requires an explicit confirmation modal if the user attempts to switch to `pseudonymous` or `professional`, preventing accidental self-doxxing.
* **FR-ID-05:** Users can manage active sessions, revoke sessions across devices, export their data, and request full account deletion/anonymization.

### 3.2 Social Posting & Community Requirements
* **FR-SOC-01:** Support 8 core post types sharing a common lifecycle: `discussion`, `question`, `rant`, `story`, `meme`, `poll`, `advice_request`, and `workplace_experience` (including structured resignation/exit stories).
* **FR-SOC-02:** Support topic-based communities (e.g., *Workplace Rants*, *Corporate Memes*, *Career Advice*, *IT & Software*, *Salary Talk*, *Job Hunting*, *Freshers' Corner*, *Work-Life Balance*, *Startup Life*, *Office Humour*, *Resignation Stories*).
* **FR-SOC-03:** Support nested threaded comments using a materialized path (`ltree` / path string) and parent ID, allowing efficient paginated retrieval of comment subtrees without loading 10,000 comments into memory at once.
* **FR-SOC-04:** Support one active upvote/downvote (`+1` / `-1`) per user per post or comment, lightweight expressive workplace reactions (`relatable`, `laugh`, `support`, `oof`, `respect`), and private post bookmarks (`saved_posts`).
* **FR-SOC-05:** Provide four core feed views: `Latest` (chronological), `Popular` (time-decayed engagement score with anti-outrage dampening), `Following` (joined communities and followed tags), and `Explore` (curated trending communities and fresh discussions).

### 3.3 AI Meme Studio Requirements
* **FR-MEME-01:** **Template Meme Maker:** Users select from curated, copyright-safe workplace meme templates, edit top/bottom/custom text boxes, preview in real time, render a final image, download, or publish directly to a community.
* **FR-MEME-02:** **AI Caption Assistant:** Users submit a short workplace scenario prompt (e.g., *"My manager scheduled a sync at 4:45 PM on Friday"*), select a tone (`sarcastic`, `wholesome`, `dramatic`, `absurd`, `deadpan`), and receive 3–5 editable caption suggestions generated via the `CaptionProviderAdapter`.
* **FR-MEME-03:** **AI Image Generation:** Users submit a text prompt to generate a custom workplace meme illustration via the asynchronous `ImageProviderAdapter`, track job status (`draft -> queued -> generating -> validating -> ready | failed | cancelled`), overlay captions, and publish.
* **FR-MEME-04:** All AI capabilities enforce strict per-user daily quotas, concurrency caps, prompt length limits, pre-generation safety validation, and graceful degradation to template mode if external providers fail or exceed budget ceilings.

### 3.4 Multilingual & Localization Requirements
* **FR-I18N-01:** Preserve UTF-8 Unicode across all text fields (posts, comments, handles, display names, tags, meme captions, search queries).
* **FR-I18N-02:** Allow users to tag posts with a content language (BCP 47 code such as `en`, `hi`, `ta`, `ml`, `es`, `mul` for mixed/code-switched text) and filter feeds by preferred languages.
* **FR-I18N-03:** Support optional, on-demand derived translations (`post_translations`, `comment_translations`) that display alongside a clear *"Translated from [Language] — View Original"* toggle without ever mutating the original text.

### 3.5 Trust, Safety & Moderation Requirements
* **FR-MOD-01:** Pre-publish content check warns users if their post matches common PII patterns (phone numbers, email addresses, government IDs, or patterns suggesting a named private individual).
* **FR-MOD-02:** Any authenticated user can report a post, comment, or profile with structured reason codes (`doxxing_pii`, `harassment`, `threat`, `impersonation`, `spam`, `hate_speech`, `confidential_ip`, `other`) and optional context.
* **FR-MOD-03:** Community moderators and platform administrators review flagged items via a prioritized Moderation Queue, apply proportionate actions (`dismiss`, `redact_pii`, `restrict_visibility`, `remove_content`, `temp_cooldown`, `suspend_account`), and record reason-coded entries in an append-only `audit_events` log.
* **FR-MOD-04:** Authors receive clear in-app notifications when their content is restricted or removed and can submit one structured **Appeal** per moderation action.

## 4. Non-Functional Requirements (NFRs)

| Category | Requirement Specification | Target Metric / Gate |
| :--- | :--- | :--- |
| **Privacy Isolation** | Public API endpoints (`/api/v1/posts`, `/api/v1/feed`, `/api/v1/comments`) must never serialize `author_user_id`, email, IP address, or session metadata when `identity_mode = 'anonymous'`. | 100% pass rate on automated schema & payload inspection tests. |
| **API Latency** | Core read endpoints (`GET /api/v1/feed`, `GET /api/v1/posts/{id}`) using cursor pagination over indexed PostgreSQL tables. | p95 < 250ms under local/staging benchmark with 100k synthetic posts. |
| **Availability & Graceful Degradation** | Outage or rate-limiting of external AI or translation providers must never block standard post creation, feed browsing, or template meme rendering. | 0% error propagation from AI/translation adapters to core social endpoints. |
| **Accessibility (a11y)** | Semantic HTML, full keyboard navigation, visible focus rings, WCAG AA colour contrast (≥ 4.5:1), reduced-motion support, and auto-populated/editable `alt_text` on all memes. | Zero critical/serious axe-core violations on MVP user flows. |
| **Data Integrity** | All multi-table mutations (post creation with tags/polls, vote toggles with counter updates, account deletion cascades) execute inside ACID PostgreSQL transactions. | Enforced via DB foreign keys, unique constraints, and check constraints. |
