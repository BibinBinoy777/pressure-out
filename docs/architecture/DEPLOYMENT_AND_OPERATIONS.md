# Deployment, Observability & Operations Architecture

**Document ID:** ARCH-PO-010  
**Version:** 2.0.0  
**Related Diagram:** [SYSTEM_COMPONENTS.md](../diagrams/SYSTEM_COMPONENTS.md)

## 1. Local Development Architecture (Phase 2 Target)

Local development is designed to be 100% repeatable with zero paid cloud credentials required.

### 1.1 Local Runtime Components (`docker-compose.yml`)
1. **`db` (PostgreSQL 16-alpine):** Runs on port `5432`, initializes extensions (`pgcrypto`, `citext`, `ltree`, `pg_trgm`), and persists data to a local named Docker volume (`po_pgdata`).
2. **`backend` (FastAPI API):** Runs `uvicorn app.main:app --reload` on port `8000`, connected to `db` and a local bind-mounted storage directory (`./storage/media`).
3. **`worker` (Background Job Runner):** Runs `python -m app.workers.runner` using the same backend image and codebase, polling `meme_jobs` via `SKIP LOCKED`. Uses `LocalMockAIProvider` by default so developers can test the entire Meme Studio flow offline at $0 cost.
4. **`frontend` (Next.js App):** Runs on port `3000`, communicating with `http://localhost:8000/api/v1`.

### 1.2 Environment Configuration & Secret Management
Configuration is validated at startup via `pydantic-settings` (`backend/app/core/config.py`). Secrets are **never** committed to Git; only `.env.example` with placeholder documentation is tracked.

```ini
# .env.example (Non-Secret Template — NEVER commit real credentials)
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://po_user:po_dev_password@localhost:5432/pressure_out
SESSION_COOKIE_SECURE=false
EMAIL_ENCRYPTION_KEY_BASE64=generate_32_byte_base64_key_for_local_dev_only
EMAIL_HMAC_PEPPER=local_dev_hmac_pepper_change_in_prod

# Storage Adapter ("local" | "s3")
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=./storage/media

# AI Meme Studio Providers ("mock" | "http")
AI_CAPTION_PROVIDER=mock
AI_IMAGE_PROVIDER=mock
AI_DAILY_SPEND_CAP_USD=25.00
MEME_CAPTION_DAILY_LIMIT=15
MEME_IMAGE_DAILY_LIMIT=5
```

## 2. Production Readiness & Target Topology

> **Phase 1 Honesty Statement:** Pressure Out is currently in Phase 1 (Architecture & Specification). The platform is **not** production-ready until Phases 2–12 and all launch-readiness gates in Section 22 are implemented and verified.

When moving from local development to Staging and Production:
* **HTTPS & Edge Protection:** All public traffic terminates TLS 1.3 at a CDN/WAF edge (e.g., Cloudflare) enforcing HSTS, bot throttling, and IP rate limits.
* **Network Isolation:** PostgreSQL runs in a private VPC subnet with zero public IP address. The application connects using a least-privilege database role (`po_app_role`) that cannot drop tables or bypass audit constraints; schema migrations run as a separate CI/CD release step using a migration role (`po_migrator_role`).
* **Database Migration Protocol:** Every Alembic migration must be tested for both `upgrade head` and `downgrade -1` in Staging before production deployment. Destructive column drops follow an expand-and-contract pattern across two releases.
* **Backups & Recovery Targets (RPO / RTO):**
  * **Automated Backups:** Daily full encrypted snapshots + continuous WAL archiving to isolated offsite storage, retained for 30 days.
  * **RPO (Recovery Point Objective):** ≤ 15 minutes of data loss in worst-case storage failure.
  * **RTO (Recovery Time Objective):** ≤ 2 hours to provision a replacement instance and restore from backup.
  * **Restore Testing:** Automated monthly restore drill into an isolated staging database to verify backup integrity.

## 3. Observability, Monitoring & Incident Response

### 3.1 Structured Redacted Logging
All backend and worker logs emit structured JSON containing `timestamp`, `level`, `correlation_id`, `module`, `event`, and `duration_ms`.
* **Mandatory Log Redaction Filter:** A logging filter automatically scrubs `password`, `po_session`, `X-CSRF-Token`, `email`, raw IP addresses, and `author_user_id` on anonymous post events so application logs cannot be used to deanonymize users.

### 3.2 Key Operational Metrics & Alerts

| Metric | Warning Threshold | Critical Alert & Automated Action |
| :--- | :--- | :--- |
| **API 5xx Error Rate** | > 1.0% over 5 mins | > 3.0% over 5 mins -> Page on-call & trigger deployment rollback review. |
| **API p95 Latency (`/api/v1/feed`)** | > 350ms | > 800ms -> Inspect slow queries (`pg_stat_statements`) & connection pool. |
| **AI Daily Spend (`ai_provider_usage`)** | 80% of `AI_DAILY_SPEND_CAP_USD` | 100% of cap -> Circuit breaker automatically trips to Template-Only mode. |
| **`meme_jobs` Queue Depth / Age** | Oldest `queued` job > 60s | Oldest `queued` job > 180s -> Scale worker replicas or trip provider breaker. |
| **High-Priority Moderation Backlog** | Unreviewed `doxxing_pii` / `threat` report > 1h | > 4h -> Escalate alert to Global Moderators. |

### 3.3 Incident Response Runbook Summary
1. **Triage & Containment:** Identify whether the incident is an availability outage, runaway AI cost spike, or privacy/security breach. Trip feature flags (`ENABLE_AI_IMAGE_GEN=false` or `READ_ONLY_MODE=true`) immediately to contain blast radius.
2. **Evidence Preservation:** Snapshot relevant `audit_events` and redacted application logs.
3. **Remediation & Verification:** Deploy hotfix or rollback, run privacy-leakage and smoke test suites, and verify metrics return to baseline.
4. **Post-Incident Review:** Document root cause, timeline, and preventative database/code constraints within 48 hours.
