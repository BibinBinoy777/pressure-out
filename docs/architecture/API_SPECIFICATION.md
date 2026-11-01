# REST API Architecture & `/api/v1` Specification

**Document ID:** ARCH-PO-005  
**Version:** 2.0.0  

## 1. API Design Principles & Conventions

* **Base Prefix:** All endpoints are versioned under `/api/v1`.
* **Content Type:** `application/json; charset=utf-8` (preserving full Unicode characters without lossy ASCII escaping).
* **Authentication & CSRF:**
  * Authenticated endpoints read the `HttpOnly`, `Secure`, `SameSite=Lax` cookie `po_session`.
  * All state-changing methods (`POST`, `PUT`, `PATCH`, `DELETE`) require the `X-CSRF-Token` header matching the session's CSRF token.
  * **Zero Client-Supplied Ownership:** Endpoints **never** accept `author_user_id` or `reporter_user_id` in request bodies; ownership is derived strictly from the server-validated session.
* **Cursor Pagination Standard:** All list endpoints (`feed`, `comments`, `notifications`, `moderation/queue`) accept `?cursor=<opaque_base64>&limit=<1..50>` and return:
  ```json
  {
    "items": [ ... ],
    "next_cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNi0xMC0yOFQyMjozMDowMFoiLCJpZCI6Ij..." ,
    "has_more": true
  }
  ```

## 2. Endpoint Catalog (`/api/v1`)

### 2.1 Authentication, Identity & Profiles

| Method & Path | Auth | Rate Limit | Request Body / Params | Response (`200`/`201`) | Error Codes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `POST /api/v1/auth/register` | Public | 5 / hr / IP | `{ "handle": "code_monk", "password": "...", "recovery_email": "opt@...", "preferred_ui_locale": "en" }` | `PrivateAccountResponse` + Sets `po_session` cookie | `HANDLE_TAKEN` (409), `VALIDATION_ERROR` (422), `RATE_LIMITED` (429) |
| `POST /api/v1/auth/login` | Public | 10 / 15m / IP+Handle | `{ "handle": "code_monk", "password": "..." }` | `PrivateAccountResponse` + Sets `po_session` cookie | `INVALID_CREDENTIALS` (401), `ACCOUNT_SUSPENDED` (403) |
| `POST /api/v1/auth/logout` | User | 30 / min | Empty | `{ "status": "logged_out" }` + Clears cookie | `UNAUTHORIZED` (401) |
| `POST /api/v1/auth/recovery/request` | Public | 3 / hr / IP | `{ "email": "opt@..." }` | `{ "message": "If registered, instructions were sent." }` (Constant-time response) | `RATE_LIMITED` (429) |
| `GET /api/v1/me` | User | 120 / min | None | `PrivateAccountResponse` (includes private settings & professional profile) | `UNAUTHORIZED` (401) |
| `PATCH /api/v1/me/profile` | User | 20 / min | `{ "display_name": "...", "bio": "...", "professional_profile": { "role_title": "SDE II", "industry": "SaaS", "experience_band": "mid_3_6", "is_enabled": true } }` | `PrivateAccountResponse` | `VALIDATION_ERROR` (422) |
| `PATCH /api/v1/me/settings` | User | 20 / min | `{ "default_identity_mode": "anonymous", "preferred_ui_locale": "en", "preferred_content_locales": ["en", "hi"] }` | `PrivateAccountResponse` | `VALIDATION_ERROR` (422) |
| `DELETE /api/v1/me` | User | 2 / hr | `{ "password_confirmation": "...", "delete_published_posts": false }` | `{ "status": "account_deleted" }` | `INVALID_CREDENTIALS` (401) |
| `GET /api/v1/profiles/{handle}` | Public | 60 / min | Path `handle` | `PublicProfileResponse` (excludes private data & excludes `anonymous` posts) | `PROFILE_NOT_FOUND` (404) |

### 2.2 Social Posts, Polls, Exit Stories & Feeds

| Method & Path | Auth | Rate Limit | Request Body / Params | Response (`200`/`201`) | Error Codes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET /api/v1/feed` | Optional | 120 / min | `?mode=latest\|popular\|following&community_slug=...&post_type=...&lang=...&cursor=...&limit=25` | `CursorPage<PublicPostResponse>` | `VALIDATION_ERROR` (422) |
| `POST /api/v1/posts` | User | 10 / 15m (5 / 15m if `anonymous`) | `CreatePostRequest` (see Section 3.1) | `PublicPostResponse` (with `pii_warnings` if applicable) | `PII_CONFIRMATION_REQUIRED` (422), `COMMUNITY_RESTRICTED` (403) |
| `GET /api/v1/posts/{id}` | Optional | 120 / min | Path `id`, `?translate_to=en` (optional) | `PublicPostDetailResponse` | `POST_NOT_FOUND` (404), `POST_REMOVED` (410) |
| `PATCH /api/v1/posts/{id}` | Author | 20 / min | `{ "title": "...", "body": "...", "identity_mode": "anonymous" }` | `PublicPostResponse` | `FORBIDDEN_NOT_AUTHOR` (403) |
| `DELETE /api/v1/posts/{id}` | Author | 20 / min | None | `{ "status": "deleted", "id": "..." }` | `FORBIDDEN_NOT_AUTHOR` (403) |
| `PUT /api/v1/posts/{id}/vote` | User | 60 / min | `{ "value": 1 \| -1 \| 0 }` (`0` removes vote) | `{ "score": 42, "viewer_vote": 1 }` | `POST_NOT_FOUND` (404) |
| `PUT /api/v1/posts/{id}/reactions/{kind}` | User | 60 / min | Path `kind` (`relatable\|laugh\|support\|oof\|respect`), `{ "active": true }` | `{ "reaction_counts": { "relatable": 12 }, "viewer_reactions": ["relatable"] }` | `INVALID_REACTION` (422) |
| `POST /api/v1/posts/{id}/save` | User | 60 / min | `{ "saved": true \| false }` | `{ "saved": true }` | `UNAUTHORIZED` (401) |
| `POST /api/v1/posts/{id}/poll/vote` | User | 30 / min | `{ "option_ids": ["uuid-1"] }` | `PublicPollResponse` | `POLL_CLOSED` (409), `ALREADY_VOTED` (409) |

### 2.3 Nested Comments & Communities

| Method & Path | Auth | Rate Limit | Request Body / Params | Response (`200`/`201`) | Error Codes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET /api/v1/posts/{id}/comments` | Optional | 120 / min | `?sort=top\|latest&parent_id=...&cursor=...&limit=30` | `CursorPage<PublicCommentResponse>` | `POST_NOT_FOUND` (404) |
| `POST /api/v1/posts/{id}/comments` | User | 20 / 10m | `{ "parent_comment_id": null, "body": "...", "identity_mode": "anonymous", "confirm_op_identity_reveal": false, "content_language": "en" }` | `PublicCommentResponse` | `OP_ANONYMITY_MISMATCH` (409 — if OP tries to reply non-anonymously without `confirm_op_identity_reveal=true`) |
| `PATCH /api/v1/comments/{id}` | Author | 20 / min | `{ "body": "..." }` | `PublicCommentResponse` | `FORBIDDEN_NOT_AUTHOR` (403) |
| `DELETE /api/v1/comments/{id}` | Author | 20 / min | None | `{ "status": "deleted" }` | `FORBIDDEN_NOT_AUTHOR` (403) |
| `GET /api/v1/communities` | Optional | 120 / min | `?q=...&lang=...` | `List<CommunitySummaryResponse>` | None |
| `GET /api/v1/communities/{slug}` | Optional | 120 / min | Path `slug` | `CommunityDetailResponse` (includes rules & viewer membership status) | `COMMUNITY_NOT_FOUND` (404) |
| `POST /api/v1/communities/{slug}/membership` | User | 30 / min | `{ "action": "join" \| "leave" }` | `{ "is_member": true, "member_count": 1420 }` | `COMMUNITY_BANNED` (403) |

### 2.4 AI Meme Studio & Multilingual Endpoints

| Method & Path | Auth | Rate Limit | Request Body / Params | Response (`200`/`201`/`202`) | Error Codes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET /api/v1/memes/templates` | User | 60 / min | `?category=...` | `List<MemeTemplateResponse>` | None |
| `POST /api/v1/memes/captions/suggest` | User | 15 / day / user | `{ "prompt": "Friday 4:55pm meeting", "tone": "sarcastic", "language": "en" }` | `{ "suggestions": [{ "top": "...", "bottom": "..." }], "quota_remaining": 14 }` | `MEME_QUOTA_EXCEEDED` (429), `AI_PROVIDER_UNAVAILABLE` (503) |
| `POST /api/v1/memes/render-template` | User | 30 / hr / user | `{ "template_id": "...", "captions": [...], "alt_text": "..." }` | `MemeAssetResponse` (`201 Created`) | `TEMPLATE_NOT_FOUND` (404) |
| `POST /api/v1/memes/jobs` | User | 5 / day / user | Header `Idempotency-Key`, `{ "job_type": "ai_image", "prompt": "...", "style_tone": "absurd", "language": "en" }` | `MemeJobResponse` (`202 Accepted`, `status: "queued"`) | `MEME_QUOTA_EXCEEDED` (429), `UNSAFE_PROMPT` (422) |
| `GET /api/v1/memes/jobs/{id}` | Job Owner | 60 / min | Path `id` | `MemeJobResponse` (`queued\|generating\|validating\|ready\|failed`) | `FORBIDDEN` (403), `JOB_NOT_FOUND` (404) |
| `POST /api/v1/memes/jobs/{id}/cancel` | Job Owner | 20 / min | Path `id` | `MemeJobResponse` (`status: "cancelled"`) | `JOB_NOT_CANCELLABLE` (409) |
| `POST /api/v1/posts/{id}/translations` | Optional | 20 / hr / user | `{ "target_locale": "en" }` | `DerivedTranslationResponse` | `TRANSLATION_UNAVAILABLE` (503) |

### 2.5 Search, Notifications, Trust & Safety

| Method & Path | Auth | Rate Limit | Request Body / Params | Response (`200`/`201`) | Error Codes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET /api/v1/search` | Optional | 30 / min | `?q=...&community_slug=...&post_type=...&lang=...&cursor=...` | `CursorPage<PublicPostResponse>` | `QUERY_TOO_SHORT` (422) |
| `GET /api/v1/notifications` | User | 60 / min | `?unread_only=false&cursor=...` | `CursorPage<NotificationResponse>` | `UNAUTHORIZED` (401) |
| `PATCH /api/v1/notifications/read` | User | 30 / min | `{ "notification_ids": ["..."], "mark_all": false }` | `{ "updated_count": 3 }` | `UNAUTHORIZED` (401) |
| `POST /api/v1/reports` | User | 15 / hr / user | `{ "target_type": "post", "target_id": "...", "reason_code": "doxxing_pii", "details": "..." }` | `{ "report_id": "...", "status": "open" }` (`201`) | `DUPLICATE_REPORT` (409) |
| `PUT /api/v1/users/{handle}/block` | User | 30 / min | `{ "active": true, "mode": "block" \| "mute" }` | `{ "blocked": true }` | `USER_NOT_FOUND` (404) |
| `GET /api/v1/moderation/queue` | Moderator | 60 / min | `?status=open&reason_code=...&community_slug=...&cursor=...` | `CursorPage<ModerationQueueItemResponse>` | `FORBIDDEN_ROLE` (403) |
| `POST /api/v1/moderation/actions` | Moderator | 60 / min | `{ "target_type": "post", "target_id": "...", "action_type": "remove_content", "reason_code": "doxxing_pii", "internal_note": "...", "public_explanation": "..." }` | `ModerationActionResponse` | `FORBIDDEN_ROLE` (403) |
| `POST /api/v1/moderation/appeals` | User | 3 / day | `{ "moderation_action_id": "...", "appeal_statement": "..." }` | `AppealResponse` (`201`) | `APPEAL_ALREADY_EXISTS` (409) |

## 3. Core Request & Response Schema Contracts

### 3.1 `CreatePostRequest`
```json
{
  "community_slug": "workplace-rants",
  "post_type": "rant",
  "identity_mode": "anonymous",
  "title": "Asked to train my replacement before my bonus vests",
  "body": "Management announced a reorganization today...",
  "content_language": "en",
  "tags": ["reorg", "bonus", "burnout"],
  "meme_asset_id": null,
  "poll": null,
  "exit_story": null,
  "acknowledge_pii_warning": false
}
```

### 3.2 `PublicPostResponse` (Illustrating Strict Anonymous Isolation)
Notice that `author` contains **no `user_id`, no `handle`, and no `profile_id`** when `identity_mode` is `"anonymous"`, while `viewer_context.is_author` tells the authenticated author's browser that they own the post:

```json
{
  "id": "0192d4e8-7a1b-7000-8123-456789abcdef",
  "community": {
    "slug": "workplace-rants",
    "name": "Workplace Rants"
  },
  "post_type": "rant",
  "identity_mode": "anonymous",
  "author": {
    "display_name": "Anonymous Member",
    "handle": null,
    "avatar_url": null,
    "professional_badge": null
  },
  "title": "Asked to train my replacement before my bonus vests",
  "body": "Management announced a reorganization today...",
  "content_language": "en",
  "tags": ["reorg", "bonus", "burnout"],
  "meme_asset": null,
  "poll": null,
  "exit_story": null,
  "stats": {
    "score": 148,
    "upvote_count": 152,
    "downvote_count": 4,
    "comment_count": 37,
    "reaction_counts": {
      "relatable": 64,
      "support": 29,
      "oof": 18
    }
  },
  "viewer_context": {
    "is_author": true,
    "viewer_vote": 1,
    "viewer_reactions": ["relatable"],
    "is_saved": false
  },
  "created_at": "2026-10-28T16:45:00Z",
  "updated_at": "2026-10-28T16:45:00Z"
}
```


### 2.6 Phase 11 Workplace Experiences, Resignation Stories & Privacy-Safe Aggregated Insights

| Method & Path | Auth | Rate Limit | Request Body / Params | Response (`200`/`201`) | Error Codes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET /api/v1/workplace/experiences` | Optional | 120 / min | `?category=...&experience_band=...&industry_category=...&content_language=...&sort=latest\|popular&cursor=...` | `CursorPostListResponse` (includes `workplace_detail`) | `VALIDATION_ERROR` (422) |
| `GET /api/v1/workplace/resignation-stories` | Optional | 120 / min | `?resignation_reason=...&experience_band=...&industry_category=...&content_language=...&sort=latest\|popular&cursor=...` | `CursorPostListResponse` (includes `workplace_detail`) | `VALIDATION_ERROR` (422) |
| `POST /api/v1/workplace/contributions` | User + CSRF | 10 / hr | `CreateWorkplaceContributionRequest` (`aggregation_consent: true`, optional context & `1..5` ratings) | `PrivateContributionResponse` (`201 Created`) | `CONSENT_REQUIRED` (422), `CONTRIBUTION_ALREADY_EXISTS` (409) |
| `GET /api/v1/workplace/contributions/mine` | User | 60 / min | None | `PrivateContributionResponse \| null` | `UNAUTHORIZED` (401) |
| `PATCH /api/v1/workplace/contributions/{id}` | Owner + CSRF | 20 / min | `UpdateWorkplaceContributionRequest` (supports `aggregation_consent: false` withdrawal) | `PrivateContributionResponse` | `FORBIDDEN_NOT_OWNER` (403), `CONTRIBUTION_NOT_FOUND` (404) |
| `DELETE /api/v1/workplace/contributions/{id}` | Owner + CSRF | 20 / min | None | `{ "status": "deleted", "id": "..." }` | `FORBIDDEN_NOT_OWNER` (403), `CONTRIBUTION_NOT_FOUND` (404) |
| `GET /api/v1/workplace/insights` | Optional | 30 / min | Up to 2 broad filters (`industry_category`, `role_family`, `experience_band`, `company_size_band`, `broad_region`, `work_arrangement`) | `WorkplaceInsightsResponse` (k-anonymity `n >= 10` general, `n >= 20` sensitive, complementary bucket suppression `n < 3`) | `TOO_MANY_INSIGHT_FILTERS` (422), `RATE_LIMITED` (429) |
