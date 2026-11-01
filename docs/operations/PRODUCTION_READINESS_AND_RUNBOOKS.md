# Pressure Out — Production Readiness, Pre-Staging Hardening & Operational Runbooks (Phase 12 & 12.1)

## 1. Purpose & Launch Readiness Status

This runbook documents the production architecture, startup configuration invariants, shared Redis rate limiting, separated JSON vs. multipart upload policies, full 24-table account export and deletion lifecycle, process-aware metrics semantics, S3/R2 object storage adapter, 16-step PostgreSQL 16 staging qualification procedure, hardened backup/restore drills, and incident response playbooks for **Pressure Out**.

* **Current Assessment:** `READY FOR NETWORKED STAGING QUALIFICATION`
* **Why Ready for Networked Staging Qualification:** All code-level multi-worker and infrastructure blockers identified in Phase 12 have been resolved in Phase 12.1:
  1. Multi-worker shared Redis rate limiting (`RedisRateLimitStore` with atomic Lua `EVAL`, SHA-256 hashed keys, and fail-closed `503 RATE_LIMIT_BACKEND_UNAVAILABLE` policy) + internal `redis:7-alpine` service in `docker-compose.prod.yml`.
  2. Separated request-size policies (`1 MB` JSON limit vs. `6 MB` multipart envelope / `5 MB` image asset limit on `POST /api/v1/memes/upload`) with stream byte counting that prevents missing or falsified `Content-Length` bypasses.
  3. Complete 24-table account deletion and personal data export (`GET /api/v1/me/export` & `DELETE /api/v1/me`) including underlying media file deletion, cached translation purging, community member count recalculation, k-anonymity cohort recalculation, and append-only `audit_events` preservation.
  4. Process-aware operational telemetry (`collection_scope: "process_local"`, `is_cluster_wide`, `worker_pid`, `configured_web_concurrency`) paired with database-global `worker_queue` telemetry.
  5. Provider-neutral `S3CompatibleStorageAdapter` (supporting AWS S3 and Cloudflare R2 via AWS Signature Version 4 `AWS4-HMAC-SHA256`, private ACLs, bounded timeouts, and presigned GET URLs) alongside `LocalFilesystemStorageAdapter`.
  6. Reproducible 16-step PostgreSQL 16 staging qualification script (`scripts/qualify_postgres_staging.py`) and hardened backup/restore script (`scripts/backup_restore_postgres.sh`).

## 2. Rate-Limiting Backend Selection, Redis Configuration & Worker Constraints

* **Configuration Variables:**
  * `WEB_CONCURRENCY`: Number of Uvicorn worker processes (`1` in local dev/test, `2` by default in production).
  * `RATE_LIMIT_BACKEND`: `memory` (local dev/test only, requires `WEB_CONCURRENCY=1`) or `redis` (required whenever `WEB_CONCURRENCY > 1` or `APP_ENV=production`).
  * `REDIS_URL`: `redis://:password@redis:6379/0` or `rediss://:password@host:6379/0`.
  * `REDIS_SOCKET_TIMEOUT_SECONDS`: Bounded TCP/TLS socket timeout (default `2.0` seconds).
  * `RATE_LIMIT_FAIL_CLOSED`: `true` (default and mandatory in production).
* **Startup Fail-Fast Rules:**
  * Setting `WEB_CONCURRENCY > 1` with `RATE_LIMIT_BACKEND=memory` aborts startup immediately (`MULTI_WORKER_CONFIG_ERROR`).
  * Setting `APP_ENV=production` with `RATE_LIMIT_BACKEND=memory`, an empty/invalid `REDIS_URL`, the default dev Redis password, or `RATE_LIMIT_FAIL_CLOSED=false` aborts startup immediately (`PRODUCTION_CONFIG_ERROR`).
* **Failure Behavior & Availability Trade-Off:**
  * When `RATE_LIMIT_FAIL_CLOSED=true` and Redis is unreachable, rate-limited endpoints return `503 RATE_LIMIT_BACKEND_UNAVAILABLE` rather than silently falling back to process-local memory or allowing unlimited brute-force/spam requests, and `GET /api/v1/health/ready` returns `503 Service Unavailable` (`status: "degraded"`, `rate_limit_ready: false`).

## 3. Request-Body and Multipart Media-Upload Policies

* **JSON & Standard Requests (`MAX_JSON_REQUEST_BYTES = 1,048,576` / 1 MB):** Enforced on all non-multipart requests (`413 PAYLOAD_TOO_LARGE`).
* **Multipart Media Uploads (`MAX_MULTIPART_UPLOAD_BYTES = 6,291,456` / 6 MB envelope; `MAX_ASSET_BYTES = 5,242,880` / 5 MB image binary):** Enforced on `POST /api/v1/memes/upload` (`413 UPLOAD_TOO_LARGE` if multipart envelope exceeds 6 MB; `422 IMAGE_TOO_LARGE` if inner image exceeds 5 MB).
* **Anti-Bypass Streamed Body Guard:** `SecurityHeadersAndSizeLimitMiddleware` wraps the ASGI `receive` channel to count incoming body chunk bytes incrementally without unbounded memory buffering, rejecting requests with `413` the instant streamed bytes exceed the applicable limit even when `Content-Length` is omitted or falsified.

## 4. Account Export & Deletion Data-Category Policy (All 24 Tables)

| Database Table / Asset | `GET /api/v1/me/export` Policy | `DELETE /api/v1/me` Policy |
|---|---|---|
| `users` | Exports `user_id`, decrypted `recovery_email`, `account_status`, `role`, `default_identity_mode`, `preferred_ui_locale`, `preferred_content_locales`, `created_at` (never hashes/secrets) | Scrubs `email_hash=NULL`, `email_encrypted=NULL`, `recovery_code_hash=NULL`, `password_hash='DELETED_ACCOUNT'`, `account_status='deleted'`, `deleted_at=now` |
| `public_profiles` & `avatar_storage_key` | Exports `handle`, `display_name`, `bio`, `show_karma` | Deletes row and deletes underlying avatar file via `StorageAdapter.delete_object` |
| `professional_profiles` | Exports `role_title`, `industry`, `experience_band`, `region_label`, `is_enabled` | Deletes row |
| `user_sessions` & `password_recovery_tokens` | Excluded (authentication credentials/tokens are never exported) | Deletes all rows for `user_id` |
| `posts` & `workplace_experience_details` | Exports all non-deleted authored posts + attached `workplace_detail` | If `delete_published_posts=true`: deletes `workplace_experience_details`, scrubs post to `[deleted]`/`[deleted by author]`, sets `author_user_id=NULL, meme_asset_id=NULL`. If `false`: anonymizes (`author_user_id=NULL, identity_mode='anonymous'`). |
| `polls`, `poll_options`, `poll_votes` | Exports user's own `poll_votes` | Deletes user's `poll_votes` (and deletes poll/options if authored post is deleted) |
| `comments` | Exports all non-deleted authored comments | Scrubs `body='[deleted by author]'`, `author_user_id=NULL`, `identity_mode='anonymous'`, `deleted_at=now` to preserve reply tree structure |
| `votes`, `reactions`, `saved_posts` | Exports user's own `votes`, `reactions`, and `saved_bookmarks` | Deletes all rows for `user_id` |
| `communities`, `community_rules`, `community_memberships` | Exports user's `community_memberships` | Decrements `communities.member_count` for active memberships, deletes `community_memberships`, sets `communities.created_by_user_id=NULL` |
| `user_topic_preferences` & `user_blocks` | Exports user's `topic_preferences` and `blocks_and_mutes` (by target public `handle` only) | Deletes all rows where user is owner, blocker, or blocked |
| `notifications` | Exports user's `notifications` | Deletes all rows for `recipient_user_id` |
| `meme_assets` & underlying storage objects | Exports user's `meme_assets` metadata | Deletes underlying image files from `StorageAdapter` and deletes rows (for all assets if `delete_published_posts=true`, or unpublished assets if `false` while setting `owner_user_id=NULL` on published assets) |
| `meme_jobs` & `ai_provider_usage` | Exports user's `meme_jobs` | Deletes `meme_jobs`; sets `ai_provider_usage.user_id=NULL` to preserve aggregate spend accounting without user attribution |
| `content_translations` | Derived cache (not personal data) | Deletes cached translations for user's comments and deleted posts |
| `workplace_insight_contributions` | Exports user's full 16-field `structured_workplace_contribution` | Deletes row so future k-anonymity cohorts immediately recalculate without the deleted user |
| `reports`, `moderation_actions`, `moderation_appeals` | Exports user's own `submitted_reports` and `moderation_appeals` (excluding moderator `internal_note` and other users' identities) | Deletes user's `reports` and `moderation_appeals`; sets `moderation_actions.affected_user_id=NULL` and `moderation_appeals.reviewed_by_user_id=NULL` |
| `audit_events` | Excluded (admin-only security ledger) | Preserved intact (enforced by append-only DB triggers); inserts a redacted `account_self_deleted` event with a one-way SHA-256 subject prefix |

## 5. Process-Aware Operational Metrics Semantics

* `GET /api/v1/health/metrics` returns:
  * `http_metrics`: Explicitly labeled with `collection_scope: "process_local"`, `is_cluster_wide: (configured_web_concurrency == 1)`, `worker_pid`, and `configured_web_concurrency`. Latency percentiles (`latency_p50_ms`, `latency_p95_ms`) are computed over a bounded sliding window of up to `2,000` recent requests per worker process.
  * `worker_queue`: Explicitly labeled with `collection_scope: "database_global"`, querying shared `meme_jobs` status counts directly from the database.
  * `infrastructure`: Reports `rate_limit_backend`, `rate_limit_healthy`, `storage_backend`, and `configured_web_concurrency`.

## 6. Media Storage Backends (Local Filesystem vs. S3 / Cloudflare R2)

* **Local Filesystem (`STORAGE_BACKEND=local`):** Uses `LocalFilesystemStorageAdapter(LOCAL_STORAGE_PATH)` with atomic `.tmp` rename writes. Suitable for local development and single-node staging (`pressure_out_prod_media` volume).
* **S3-Compatible / Cloudflare R2 (`STORAGE_BACKEND=s3` or `r2`):** Uses `S3CompatibleStorageAdapter` with AWS Signature Version 4 (`AWS4-HMAC-SHA256`), private object ACL (`x-amz-acl: private`), bounded timeouts (`S3_TIMEOUT_SECONDS`), and time-limited presigned GET URLs (`generate_presigned_get_url`). Required for multi-node horizontal deployments.

## 7. 16-Step PostgreSQL 16 Staging Qualification & Backup/Restore Commands

Execute the following command sequence on the networked staging host:

```bash
# 1. Verify the 16-step qualification plan
python3 scripts/qualify_postgres_staging.py --verify-plan

# 2. Bring up PostgreSQL 16, Redis 7, Backend (2 workers), Worker, and Frontend
docker compose -f docker-compose.prod.yml up -d --build

# 3. Execute live 16-step PostgreSQL 16 qualification
python3 scripts/qualify_postgres_staging.py --database-url "$DATABASE_URL"

# 4. Run full backend test suite (16 modules, 79 tests) against PostgreSQL 16
cd backend && TEST_DATABASE_URL="$DATABASE_URL" PYTHONPATH=. python3 -m unittest discover -s tests -p "test_*.py" -v && cd ..

# 5. Execute hardened PostgreSQL backup, checksum verification, and disposable restore drill
./scripts/backup_restore_postgres.sh validate-config /backups/po_staging.dump pressure_out_restore_drill_2026103001
./scripts/backup_restore_postgres.sh backup "$DATABASE_URL" /backups/po_staging.dump
./scripts/backup_restore_postgres.sh verify /backups/po_staging.dump
./scripts/backup_restore_postgres.sh drill "$POSTGRES_ADMIN_URL" /backups/po_staging.dump pressure_out_restore_drill_2026103001
```
