# Technical Risks, Assumptions, Open Decisions & Mitigations

**Document ID:** ROAD-PO-003  
**Version:** 2.0.0  

## 1. Explicit Architectural Assumptions (Made in Phase 1)

To make Phase 1 concrete and immediately actionable for Phase 2 implementation without blocking on external procurement, the following reasonable engineering assumptions are established and documented:

| ID | Assumption | Impact if Changed |
| :--- | :--- | :--- |
| **ASM-01** | **Web-First Responsive PWA Delivery:** The MVP targets desktop and mobile web browsers via Next.js rather than native Swift/Kotlin mobile apps. | Because all business logic lives behind `/api/v1`, native iOS/Android clients can be added later without changing backend modules. |
| **ASM-02** | **Curated Starter Meme Templates Only in MVP:** Users create memes from platform-provided, copyright-safe templates or AI generation rather than uploading arbitrary unmoderated local photos in Phase 8. | Eliminates CSAM/malware/copyright upload scanning overhead in early phases; general image upload can be added once automated media moderation is wired. |
| **ASM-03** | **PostgreSQL Handles Queue & Search in MVP:** Initial pilot volume (< 50,000 MAU) fits comfortably within a single PostgreSQL 16 instance using `SKIP LOCKED` and `tsvector`. | Adapter boundaries allow swapping in Redis or Meilisearch later without altering API contracts. |
| **ASM-04** | **No Mandatory Email at Registration:** Users can sign up with `handle` + `password` and receive a backup recovery code if they decline to enter an email address. | Maximizes user trust for workplace venting while keeping account recovery possible. |

## 2. Unresolved Decisions (To Confirm Before Production Launch)

These decisions are intentionally deferred from Phase 1 coding because they depend on commercial benchmarking, legal review, or hosting procurement—and our adapter architecture isolates them so Phase 2–8 engineering is **not blocked**:

| Decision ID | Open Decision | Target Resolution Phase | Architectural Isolation Mechanism |
| :--- | :--- | :--- | :--- |
| **DEC-OPEN-01** | **Commercial AI Caption & Image Provider Selection** (e.g., OpenAI `gpt-4o-mini` / `gpt-image-1`, Google Gemini / Imagen, Flux, or Stability AI). | Before Phase 8 Staging Pilot | Isolated behind `CaptionProviderAdapter` and `ImageProviderAdapter`. Phase 2–8 local dev and CI run deterministically against `LocalMockAIProvider`. |
| **DEC-OPEN-02** | **Commercial Translation Provider Selection** (e.g., Google Cloud Translation, DeepL, or LLM-based translation). | Before Phase 10 Staging Pilot | Isolated behind `TranslationProviderAdapter`. |
| **DEC-OPEN-03** | **Production Cloud Hosting & Managed DB Vendor** (e.g., AWS ECS + RDS + S3, Render/Fly.io + Neon/Supabase + Cloudflare R2, or GCP Cloud Run + Cloud SQL). | Before Phase 12 Production Prep | Containerized `Dockerfile` + standard PostgreSQL 16 + S3-compatible `StorageAdapter` work on any major cloud provider. |
| **DEC-OPEN-04** | **Jurisdictional Legal & Intermediary Liability Review** (Terms of Service, Privacy Policy, DMCA/copyright agent, and regional grievance officer compliance such as India IT Rules / EU DSA / GDPR). | Before Phase 12 Public Pilot | Technical controls (audit logs, takedown queues, account deletion, PII redaction) are built into the schema from Phase 3 & 9; legal counsel reviews policy text prior to public access. |

## 3. Risk Register & Mitigation Matrix

| Risk ID | Risk Description | Category | Severity | Likelihood | Concrete Architectural & Product Mitigation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RSK-01** | **Accidental Deanonymization via API Bug or OP Reply** — A serializer change or careless OP comment leaks a user's `@handle` on an anonymous post. | Privacy / Trust | **Critical** | Medium | Separate `PublicPostResponse` Pydantic models; Sticky `Anonymous OP` comment lock (`409` guard); automated `test_privacy_leaks.py` CI gate on every PR. |
| **RSK-02** | **Doxxing & Defamation of Named Individuals** — Users post full names, phone numbers, or unverified accusations against named coworkers/managers. | Legal / Safety | **High** | High | Synchronous pre-publish PII/name heuristic guardrail (`pii_guard.py`); velocity auto-hold on ≥ 3 `doxxing_pii` reports; moderator one-click PII redaction. |
| **RSK-03** | **Runaway AI Generation Spend or Quota Abuse** — Automated bots or viral usage trigger thousands of expensive AI image generation calls. | Financial / Ops | **High** | Medium | Strict per-user daily caps (5 images/day), 1 concurrent job limit, `Idempotency-Key` deduplication, and hard global daily spend circuit breaker (`AI_DAILY_SPEND_CAP_USD`) that falls back to Template Maker. |
| **RSK-04** | **User Self-Doxxing via Contextual Workplace Details** — Users assume "Anonymous Mode" hides self-disclosed niche project details in their text. | Product / Privacy | **Medium** | High | Prominent pre-publish reminder in composer explaining what Anonymous Mode does and does not protect; PII warning banner. |
| **RSK-05** | **Multilingual Moderation & AI Quality Gaps** — Regional slang or mixed-language (Hinglish/Manglish/Tanglish) posts are misclassified by automated checks or poorly generated by AI. | Product / i18n | **Medium** | Medium | Maintain explicit Supported-Language Capability Matrix; allow users to edit all AI captions before publishing; require moderators to escalate unfamiliar languages rather than auto-removing. |
| **RSK-06** | **Cold-Start Empty Communities or Negativity Spiral** — Too many empty communities or 100% bleak rants drive away casual users. | Product / Growth | **Medium** | Medium | Launch with only 11 curated communities; include "Fresh Posts" discovery rail; rank `Popular` feed with humour/meme diversity rather than pure outrage velocity. |
| **RSK-07** | **Small-Sample Re-Identification in Exit Stories** — Aggregating resignation data over a small cohort reveals individual employees. | Privacy | **Medium** | Low | Enforce strict k-anonymity (`n >= 25` minimum sample size per cohort/window) before any aggregate workplace insight is displayed in Phase 11. |
