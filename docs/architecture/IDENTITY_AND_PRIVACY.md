# Identity, Authentication & Privacy Architecture

**Document ID:** ARCH-PO-006  
**Version:** 2.0.0  
**Related Diagram:** [IDENTITY_FLOW.md](../diagrams/IDENTITY_FLOW.md)

## 1. The Five-Layer Identity Model

To uphold the defining product principle—*people must be able to express themselves without being required to reveal their real-world identity*—Pressure Out separates identity into five distinct architectural concepts:

| Layer | Database Representation | Visibility Scope | Purpose |
| :--- | :--- | :--- | :--- |
| **1. Private Account** | `users` (`id`, `password_hash`, `email_hash`, `email_encrypted`, `account_status`) | Strictly Private (Owner & Automated Auth Service Only) | Authentication, session ownership, account recovery, quota accounting, and anti-abuse enforcement. |
| **2. Public Pseudonymous Profile** | `public_profiles` (`handle`, `display_name`, `bio`, `avatar_storage_key`) | Public (`GET /api/v1/profiles/{handle}`) | Allows a user to build community reputation and continuity under a chosen handle without using their legal name. |
| **3. Optional Professional Profile** | `professional_profiles` (`role_title`, `industry`, `experience_band`, `region_label`) | Public Only When Selected (`identity_mode = 'professional'`) | Voluntary self-declared career context for lending weight to career advice or salary discussions. No employment verification documents required. |
| **4. Per-Post / Per-Comment Display Identity** | `posts.identity_mode`, `comments.identity_mode` (`pseudonymous`, `anonymous`, `professional`) | Public on Individual Content Item | Determines how the author block is serialized in API responses for that specific post or comment. |
| **5. Private Content Ownership Association** | `posts.author_user_id`, `comments.author_user_id` | Strictly Internal | Allows the author to edit or delete their own anonymous posts, receive reply notifications, and enables Sticky `Anonymous OP` replies. |

## 2. Registration, Authentication & Recovery Security

1. **Zero Real-Name / Zero Employer Requirement:** Registration requires only a unique pseudonymous `handle` (3–32 alphanumeric/underscore characters) and a password (minimum 10 characters, checked against common breached password lists).
2. **Password & Email Cryptography:**
   * Passwords are hashed using **Argon2id** (`memory_cost=65536`, `time_cost=3`, `parallelism=4`).
   * Providing a recovery email is **optional**. When provided, the email is normalized, hashed with **HMAC-SHA256** (`email_hash`) for uniqueness/lookup, and encrypted with **AES-256-GCM** (`email_encrypted`) using a server-side key so database dumps cannot leak plaintext emails.
   * Users who decline to provide a recovery email receive a one-time printable **Account Recovery Code** at signup (stored as an Argon2id hash).
3. **Server-Managed Session Security:**
   * Sessions are stored in `user_sessions` and delivered via an `HttpOnly`, `Secure` (in HTTPS environments), `SameSite=Lax` cookie named `po_session`.
   * Every state-changing request (`POST`, `PUT`, `PATCH`, `DELETE`) must supply an `X-CSRF-Token` header matching the session's `csrf_secret`.
   * Password changes and account deletion immediately revoke all active sessions for that `user_id`.

## 3. Per-Post & Per-Comment Anonymity Rules

### 3.1 How Anonymous Posts Are Protected Against Re-Identification
When a post or comment has `identity_mode = 'anonymous'`:
1. **Serializer Stripping:** `PublicPostSerializer` and `PublicCommentSerializer` never emit `author_user_id`, `handle`, `display_name`, `avatar_url`, or `professional_badge`.
2. **Profile Exclusion:** The query powering `GET /api/v1/profiles/{handle}` includes a hard SQL predicate `WHERE posts.identity_mode != 'anonymous'`, ensuring anonymous posts never appear on a user's public profile history.
3. **Search & Timing Correlation Mitigation:** Public search cannot query by `author_user_id` on anonymous posts. Public timestamps on anonymous posts can optionally be rounded to the nearest minute in public payloads to reduce automated cross-platform timing correlation.
4. **Thread-Scoped Comment Labels:** Within a single post's comment section:
   * If the post's original author replies in `anonymous` mode, they are labeled **`Anonymous OP`** (`is_anonymous_op = TRUE`).
   * Other anonymous commenters in that thread receive a deterministic, thread-salted short label (`HMAC(post_id || user_id)[:4]`, e.g., `Anonymous • 7B2F`) so readers can follow a back-and-forth conversation inside that single thread without being able to correlate `7B2F` across different posts.

### 3.2 Sticky Anonymous OP Guardrail (Comment Interaction Rule)
A common failure mode on anonymous forums occurs when an author publishes an anonymous post and later replies to a comment while their default profile mode is still `pseudonymous`, inadvertently revealing their handle as the OP.
* **Architectural Rule:** Whenever `current_user.id == post.author_user_id` and `post.identity_mode == 'anonymous'`:
  * The frontend `CommentComposer` automatically initializes in `anonymous` (`Anonymous OP`) mode.
  * The backend endpoint `POST /api/v1/posts/{id}/comments` rejects any comment from the post author with `identity_mode != 'anonymous'` (`409 Conflict: OP_ANONYMITY_MISMATCH`) unless the request explicitly sets `"confirm_op_identity_reveal": true`.

## 4. Honest Anonymity Disclaimers & Threat Model

Pressure Out explicitly documents that **Anonymous-to-community is not cryptographic untraceability**:
* **Self-Disclosure Risk:** If a user writes highly specific details (*"When I was fired from the 4-person design team in Kochi last Tuesday..."*), coworkers may deduce who they are from the text alone. The composer displays a clear reminder and runs a pre-publish PII/name heuristic check.
* **Internal Moderator Isolation:** Community moderators and global moderators **cannot** view `author_user_id`, `@handle`, email, or IP hashes on anonymous posts in the Moderation Queue. Moderation actions (`remove_content`, `user_cooldown`) execute against the `post_id` or `report_id`, and the backend resolves the underlying `author_user_id` internally without exposing it to the moderator's screen.
* **Break-Glass Legal Escalation:** Only a designated System Administrator role with MFA can trigger a legal preservation hold, and doing so requires a mandatory legal ticket reference and writes an immutable, high-severity alert to `audit_events`.
