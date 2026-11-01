# Testing & Quality Assurance Strategy

**Document ID:** ROAD-PO-002  
**Version:** 2.0.0  

## 1. Testing Philosophy &Honesty Principle

Testing in Pressure Out verifies **real user workflows, strict identity-privacy boundaries, relational constraints, and external provider failure handling**—not superficial line-coverage vanity metrics. Furthermore, automated tests are necessary release gates, but passing tests alone never substitute for threat modeling, code review, and ongoing operational monitoring.

## 2. Multi-Layer Test Matrix

| Test Layer | Tooling | Scope & Target Scenarios | Mandatory Phase Gate |
| :--- | :--- | :--- | :--- |
| **1. Backend Unit Tests** | `pytest` | Pure domain logic: Argon2id/AES-GCM helpers, PII regex scanner (`pii_guard.py`), BCP 47 tag validator, feed hot-rank scoring formula, quota math, and `PublicPostSerializer` field stripping. | 100% pass; required from Phase 2+. |
| **2. Database Constraint & Migration Tests** | `pytest` + Test PostgreSQL container + `alembic` | Verifies `alembic upgrade head` & `downgrade` cleanly; tests DB-level `UNIQUE` constraints (duplicate votes, duplicate handles under case-folding, idempotency keys), `CHECK` constraints, `ltree` queries, and account deletion cascades. | Required before merging any schema change (Phase 2+). |
| **3. API Integration & Authorization Tests** | `pytest` + `httpx.AsyncClient` | Full HTTP request-to-DB round trips for `/api/v1/*`: session cookie auth, missing CSRF rejection (`403`), non-author edit/delete rejection (`403`), moderator RBAC scope enforcement, and cursor pagination determinism. | Required for every endpoint (Phase 3+). |
| **4. Identity-Privacy Leakage Suite** | `pytest` (`tests/security/test_privacy_leaks.py`) | Dedicated adversarial test suite that creates `anonymous` posts and comments and inspects raw JSON responses across `/feed`, `/posts/{id}`, `/comments`, `/search`, `/profiles/{handle}`, and `/moderation/queue` to assert zero presence of `author_user_id`, `handle`, `email`, or `profile_id`. Also tests Sticky `Anonymous OP` lock (`409` without explicit override). | **Zero-tolerance release blocker** on every commit from Phase 3+. |
| **5. AI & Translation Provider Resilience Tests** | `pytest` + fault-injecting mock adapters | Simulates provider timeouts (`httpx.TimeoutException`), `429` upstream rate limits, `500` malformed responses, safety rejections, duplicate `Idempotency-Key` retries, and global daily spend cap trips. Verifies bounded retries, zero double-charging, and clean fallback to Template Meme Maker. | Required for Phase 8 & Phase 10 completion. |
| **6. Frontend Component & State Tests** | `Vitest` + `React Testing Library` | Tests `IdentityModeSelector` visual states, `AnonymousOpLockBanner`, `PiiWarningAlert` interaction, `MemeCanvasEditor` caption bindings, `ContentTranslationToggle`, and loading/empty/error states. | Required from Phase 3+. |
| **7. Accessibility & Multilingual Rendering Tests** | `Playwright` + `@axe-core/playwright` | Automated WCAG AA contrast checks, full keyboard tab order (`Tab`, `Enter`, `Escape` in modals), `alt_text` presence on memes, and layout integrity with long Devanagari, Malayalam, Tamil, and RTL Arabic sample strings. | Zero critical/serious axe violations in MVP flows. |
| **8. End-to-End (E2E) Browser Workflows** | `Playwright` | Full browser journeys: (1) Sign up -> join community -> post anonymously -> reply as Anonymous OP; (2) Open Meme Studio -> generate AI caption -> render meme -> publish; (3) Report doxxing post -> moderator removes -> author sees notification & submits appeal. | Required gate for Phases 4, 8, 9, and 12. |

## 3. Concrete Privacy-Leakage Test Specification (`test_privacy_leaks.py`)

Every build from Phase 4 onward must execute the following automated verification sequence:
1. Create User A (`handle="secret_worker"`, `email="worker@example.com"`, `role_title="Staff SRE"`).
2. Authenticate as User A and create Post P1 with `identity_mode="anonymous"` and Comment C1 on Post P1 with `identity_mode="anonymous"`.
3. Create User B (`handle="curious_coworker"`) and Moderator M (`role="global_moderator"`).
4. Authenticate as User B (and also test unauthenticated Guest) and fetch:
   * `GET /api/v1/posts/{P1.id}`
   * `GET /api/v1/posts/{P1.id}/comments`
   * `GET /api/v1/feed?mode=latest`
   * `GET /api/v1/search?q=<keyword_from_P1>`
   * `GET /api/v1/profiles/secret_worker`
5. **Assertions:**
   * Convert the entire raw HTTP response body and headers to a string and assert that `str(UserA.id)`, `"secret_worker"`, `"worker@example.com"`, and `"Staff SRE"` **do not appear as substrings anywhere** in the responses for P1 or C1.
   * Assert that `GET /api/v1/profiles/secret_worker` does **not** contain `P1.id`.
6. Authenticate as Moderator M, report P1, and fetch `GET /api/v1/moderation/queue`:
   * Assert that Moderator M's payload for P1 **also** does not contain `str(UserA.id)`, `"secret_worker"`, or `"worker@example.com"`.
