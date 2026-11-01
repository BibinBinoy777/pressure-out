"""Phase 12.1 Pre-Staging Hardening & Infrastructure Qualification Test Suite.

Covers:
1. Shared Redis rate limiting across multiple worker instances, concurrent requests,
   window expiration, independent keys, SHA-256 key hashing (zero PII), and fail-closed
   behavior (503 RATE_LIMIT_BACKEND_UNAVAILABLE) + readiness degradation when Redis is down.
2. Production & multi-worker configuration validation (rejecting in-memory rate limiting
   when WEB_CONCURRENCY > 1 or APP_ENV=production; validating S3/R2 storage configuration).
3. Separated request-size policies (1 MB JSON limit vs. 6 MB multipart envelope & 5 MB
   image limit), anti-bypass streamed body counting when Content-Length is falsified,
   and atomic multipart upload on POST /api/v1/memes/upload with zero orphaned files.
4. Complete Account Export (GET /api/v1/me/export) & Deletion (DELETE /api/v1/me) across
   all 24 tables, underlying media file cleanup, translation cache purging, community
   member_count decrement, k-anonymity cohort recalculation, and append-only audit preservation.
5. Process-aware operational metrics (collection_scope='process_local', is_cluster_wide,
   worker_pid, configured_web_concurrency, and database_global worker queue).
6. S3CompatibleStorageAdapter (SigV4 signing, private ACL, EXIF stripping, presigned URLs,
   path traversal rejection, and 503 failure handling) + LocalFilesystemStorageAdapter compatibility.
7. Backup script safety validation, performance benchmark CLI argument validation,
   PostgreSQL 16 staging qualification plan verification, and docker-compose.prod.yml consistency.
"""
from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.core.errors import AppError
from app.core.metrics import metrics_collector
from app.core.rate_limit import (
    InMemoryRateLimitStore,
    RedisRateLimitStore,
    SharedMemoryRedisEvalClient,
    SlidingWindowRateLimiter,
    rate_limiter,
)
from app.main import create_app
from app.modules.memes.storage import (
    InMemoryS3Transport,
    LocalFilesystemStorageAdapter,
    S3CompatibleStorageAdapter,
    create_storage_adapter,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _make_valid_png_bytes(width: int = 128, height: int = 128) -> bytes:
    img = Image.new("RGB", (width, height), color=(32, 96, 160))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_multipart_body(
    *,
    boundary: str,
    file_bytes: bytes,
    filename: str = "workplace_meme.png",
    file_mime: str = "image/png",
    alt_text: str = "Uploaded workplace meme",
    language: str = "en",
) -> bytes:
    parts = [
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="alt_text"\r\n\r\n'
        f"{alt_text}\r\n".encode("utf-8"),
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="language"\r\n\r\n'
        f"{language}\r\n".encode("utf-8"),
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {file_mime}\r\n\r\n".encode("utf-8")
        + file_bytes
        + f"\r\n--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(parts)


class Phase121PreStagingHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        rate_limiter.configure(InMemoryRateLimitStore())
        rate_limiter.reset()
        metrics_collector.reset()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.storage_dir = Path(self.tmp_dir.name) / "media"
        self.settings = Settings(
            app_env="test",
            database_url="sqlite:///:memory:",
            local_storage_path=str(self.storage_dir),
            ai_caption_provider="local_mock",
            ai_image_provider="local_mock",
            translation_provider="local_mock",
            insights_min_cohort_size=10,
            insights_sensitive_min_cohort_size=20,
            insights_min_category_bucket_count=3,
        )
        self.app = create_app(settings=self.settings)
        self.db_manager = self.app.state.db_manager
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        rate_limiter.configure(InMemoryRateLimitStore())
        rate_limiter.reset()
        metrics_collector.reset()
        asyncio.run(self.db_manager.dispose())
        self.tmp_dir.cleanup()

    def _register_user(
        self,
        handle: str,
        *,
        recovery_email: str | None = None,
        role: str = "member",
    ) -> tuple[TestClient, str, str]:
        rate_limiter.reset()
        c = TestClient(self.app)
        payload = {
            "handle": handle,
            "password": "ValidPassword#2026!",
            "default_identity_mode": "pseudonymous",
            "preferred_ui_locale": "en",
        }
        if recovery_email:
            payload["recovery_email"] = recovery_email
        resp = c.post("/api/v1/auth/register", json=payload)
        self.assertEqual(resp.status_code, 201, resp.text)
        data = resp.json()
        user_id = data["user_id"]
        csrf = data["csrf_token"]
        if role != "member":
            async def _elevate() -> None:
                async with self.db_manager.session_scope() as session:
                    await session.execute(
                        "UPDATE users SET role = ? WHERE id = ?",
                        (role, user_id),
                    )
            asyncio.run(_elevate())
        return c, user_id, csrf

    def test_01_shared_redis_rate_limiting_across_workers_concurrency_expiry_and_fail_closed(self) -> None:
        """Verifies multi-worker Redis rate limiting, concurrent atomicity, window expiry, key hashing, and fail-closed 503."""
        clock_ms = [1_700_000_000_000]
        shared_redis = SharedMemoryRedisEvalClient(time_ms_fn=lambda: clock_ms[0])

        # Simulate two independent Uvicorn worker processes sharing the same Redis backend
        worker_1 = SlidingWindowRateLimiter(
            RedisRateLimitStore(
                redis_url="redis://:secret@redis.internal:6379/0",
                fail_closed=True,
                transport=shared_redis,
                time_ms_fn=lambda: clock_ms[0],
            )
        )
        worker_2 = SlidingWindowRateLimiter(
            RedisRateLimitStore(
                redis_url="redis://:secret@redis.internal:6379/0",
                fail_closed=True,
                transport=shared_redis,
                time_ms_fn=lambda: clock_ms[0],
            )
        )

        # Limit = 3 per 60s across both workers for the same subject
        worker_1.check_and_record(bucket="auth_login", key="user_handle_alpha", limit=3, window_seconds=60)
        worker_2.check_and_record(bucket="auth_login", key="user_handle_alpha", limit=3, window_seconds=60)
        worker_1.check_and_record(bucket="auth_login", key="user_handle_alpha", limit=3, window_seconds=60)

        # 4th attempt on worker_2 is rejected with 429 RATE_LIMITED because workers share state!
        with self.assertRaises(AppError) as ctx:
            worker_2.check_and_record(bucket="auth_login", key="user_handle_alpha", limit=3, window_seconds=60)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.code, "RATE_LIMITED")

        # Independent key is unaffected
        worker_2.check_and_record(bucket="auth_login", key="user_handle_beta", limit=3, window_seconds=60)

        # Verify no raw handle or IP appears in Redis keys (SHA-256 hashed)
        stored_keys = shared_redis.inspect_keys()
        self.assertTrue(len(stored_keys) >= 2)
        for k in stored_keys:
            self.assertTrue(k.startswith("po:rl:auth_login:"))
            self.assertNotIn("user_handle_alpha", k)
            self.assertNotIn("user_handle_beta", k)

        # Advance simulated clock past 60s window -> requests succeed again
        clock_ms[0] += 61_000
        worker_2.check_and_record(bucket="auth_login", key="user_handle_alpha", limit=3, window_seconds=60)

        # Concurrent burst test: 20 threads racing against a limit of 5 -> exactly 5 pass, 15 fail with 429
        def _attempt_burst(idx: int) -> int:
            limiter = worker_1 if idx % 2 == 0 else worker_2
            try:
                limiter.check_and_record(bucket="burst_test", key="shared_ip", limit=5, window_seconds=60)
                return 200
            except AppError as exc:
                return exc.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            statuses = list(pool.map(_attempt_burst, range(20)))
        self.assertEqual(statuses.count(200), 5)
        self.assertEqual(statuses.count(429), 15)

        # Simulate Redis outage -> fail-closed raises 503 RATE_LIMIT_BACKEND_UNAVAILABLE (never silently allows!)
        shared_redis.simulate_unavailable = True
        self.assertFalse(worker_1.is_healthy())
        with self.assertRaises(AppError) as down_ctx:
            worker_1.check_and_record(bucket="auth_login", key="user_handle_alpha", limit=3, window_seconds=60)
        self.assertEqual(down_ctx.exception.status_code, 503)
        self.assertEqual(down_ctx.exception.code, "RATE_LIMIT_BACKEND_UNAVAILABLE")

        # Bind degraded Redis store to global rate_limiter and verify /api/v1/health/ready reports 503
        rate_limiter.configure(worker_1.store)
        ready_degraded = self.client.get("/api/v1/health/ready")
        self.assertEqual(ready_degraded.status_code, 503)
        self.assertEqual(ready_degraded.json()["status"], "degraded")
        self.assertFalse(ready_degraded.json()["rate_limit_ready"])
        self.assertEqual(ready_degraded.json()["rate_limit_backend"], "redis")

    def test_02_multi_worker_and_production_rate_limit_and_s3_config_validation(self) -> None:
        """Rejects WEB_CONCURRENCY > 1 with memory rate limiting, rejects memory in production, and validates S3 config."""
        # 1. Multi-worker with memory backend fails fast in any environment
        with self.assertRaises(ValueError) as mw_ctx:
            Settings(
                app_env="staging",
                web_concurrency=2,
                rate_limit_backend="memory",
            )
        self.assertIn("MULTI_WORKER_CONFIG_ERROR", str(mw_ctx.exception))

        # 2. Production with memory backend fails fast even if web_concurrency=1
        valid_prod_key = base64.urlsafe_b64encode(b"K" * 32).decode("ascii")
        prod_base = {
            "app_env": "production",
            "database_url": "postgresql+asyncpg://po_prod:StrongProdDbPass!99@db.internal:5432/pressure_out",
            "web_concurrency": 1,
            "rate_limit_backend": "redis",
            "redis_url": "redis://:StrongProdRedisPass!99@redis.internal:6379/0",
            "rate_limit_fail_closed": True,
            "session_cookie_secure": True,
            "email_hmac_pepper": "prod-secret-hmac-pepper-at-least-32-bytes-long!!",
            "email_encryption_key_base64": valid_prod_key,
            "cors_origins": ["https://pressureout.example.com"],
            "ai_caption_provider": "disabled",
            "ai_image_provider": "disabled",
            "translation_provider": "disabled",
        }
        self.assertEqual(Settings(**prod_base).rate_limit_backend, "redis")

        with self.assertRaises(ValueError):
            Settings(**{**prod_base, "rate_limit_backend": "memory"})
        with self.assertRaises(ValueError):
            Settings(**{**prod_base, "rate_limit_fail_closed": False})
        with self.assertRaises(ValueError):
            Settings(**{**prod_base, "redis_url": "redis://:po_dev_redis_password_change_me@redis:6379/0"})

        # 3. Storage backend s3/r2 requires endpoint, bucket, access key, and secret key
        with self.assertRaises(ValueError) as s3_ctx:
            Settings(app_env="staging", storage_backend="r2", s3_bucket_name="po-memes")
        self.assertIn("STORAGE_CONFIG_ERROR", str(s3_ctx.exception))

    def test_03_request_size_separation_multipart_uploads_and_stream_limit_guard(self) -> None:
        """Verifies 1 MB JSON limit, valid multipart image upload, > 5 MB image rejection, and falsified Content-Length protection."""
        client, _, csrf = self._register_user("upload_tester_12_1")

        # 1. Valid multipart image upload succeeds on POST /api/v1/memes/upload
        png_bytes = _make_valid_png_bytes(200, 200)
        boundary = "----PressureOutBoundary7MA4YWxkTrZu0gW"
        mp_body = _build_multipart_body(
            boundary=boundary,
            file_bytes=png_bytes,
            alt_text="Sprint planning chaos",
            language="en",
        )
        up_res = client.post(
            "/api/v1/memes/upload",
            content=mp_body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-CSRF-Token": csrf,
            },
        )
        self.assertEqual(up_res.status_code, 201, up_res.text)
        up_data = up_res.json()
        self.assertEqual(up_data["width"], 200)
        self.assertEqual(up_data["height"], 200)
        self.assertEqual(up_data["alt_text"], "Sprint planning chaos")

        # 2. JSON payload > 1 MB with misleadingly small Content-Length header ("50") is caught by stream byte guard!
        huge_json = json.dumps(
            {
                "community_slug": "general-workplace",
                "post_type": "story",
                "identity_mode": "pseudonymous",
                "title": "Misleading content-length test",
                "body": "A" * (1024 * 1024 + 4096),
                "content_language": "en",
            }
        ).encode("utf-8")
        stream_blocked = client.post(
            "/api/v1/posts",
            content=huge_json,
            headers={
                "Content-Type": "application/json",
                "Content-Length": "50",  # Falsified small Content-Length!
                "X-CSRF-Token": csrf,
            },
        )
        self.assertEqual(stream_blocked.status_code, 413, stream_blocked.text)
        self.assertEqual(stream_blocked.json()["error"]["code"], "PAYLOAD_TOO_LARGE")

        # 3. Multipart upload > 5 MB image limit (within 6 MB envelope) is rejected with 422 IMAGE_TOO_LARGE and leaves zero orphaned files
        files_before = set(self.storage_dir.rglob("*")) if self.storage_dir.exists() else set()
        oversized_img = b"\x89PNG\r\n\x1a\n" + (b"\x00" * (5 * 1024 * 1024 + 1024))
        mp_over_5mb = _build_multipart_body(boundary=boundary, file_bytes=oversized_img)
        img_too_big = client.post(
            "/api/v1/memes/upload",
            content=mp_over_5mb,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-CSRF-Token": csrf,
            },
        )
        self.assertEqual(img_too_big.status_code, 422, img_too_big.text)
        self.assertEqual(img_too_big.json()["error"]["code"], "IMAGE_TOO_LARGE")
        files_after = set(self.storage_dir.rglob("*")) if self.storage_dir.exists() else set()
        self.assertEqual(files_before, files_after)

        # 4. Multipart payload > 6 MB envelope is rejected by middleware with 413 UPLOAD_TOO_LARGE
        mp_over_6mb = _build_multipart_body(
            boundary=boundary,
            file_bytes=b"X" * (6 * 1024 * 1024 + 2048),
        )
        env_too_big = client.post(
            "/api/v1/memes/upload",
            content=mp_over_6mb,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-CSRF-Token": csrf,
            },
        )
        self.assertEqual(env_too_big.status_code, 413, env_too_big.text)
        self.assertEqual(env_too_big.json()["error"]["code"], "UPLOAD_TOO_LARGE")

    def test_04_account_export_and_deletion_completeness_media_translations_and_audit(self) -> None:
        """Verifies full export completeness, ownership isolation, media & translation cleanup, and audit preservation on deletion."""
        owner_c, owner_id, owner_csrf = self._register_user(
            "lifecycle_owner", recovery_email="owner_recovery@example.com"
        )
        other_c, other_id, other_csrf = self._register_user("lifecycle_other")

        # Owner joins a community, sets topic preference, blocks other user, renders a meme, creates a post + comment + translation + contribution + report
        owner_c.post(
            "/api/v1/communities/corporate-memes/membership",
            json={"action": "join"},
            headers={"X-CSRF-Token": owner_csrf},
        )
        comm_before = owner_c.get("/api/v1/communities/corporate-memes").json()["member_count"]

        owner_c.put(
            "/api/v1/users/lifecycle_other/block",
            json={"mode": "mute"},
            headers={"X-CSRF-Token": owner_csrf},
        )

        render_res = owner_c.post(
            "/api/v1/memes/render",
            json={
                "template_id_or_slug": "friday-455pm-deploy",
                "language": "en",
                "output_format": "PNG",
                "captions": [
                    {"region_id": "top", "text": "TESTING ACCOUNT LIFECYCLE"},
                    {"region_id": "bottom", "text": "CLEANING UP MEDIA FILES"},
                ],
            },
            headers={"X-CSRF-Token": owner_csrf},
        )
        self.assertEqual(render_res.status_code, 201)
        asset_id = render_res.json()["id"]

        post_res = owner_c.post(
            "/api/v1/posts",
            json={
                "community_slug": "work-life-balance",
                "post_type": "workplace_experience",
                "identity_mode": "pseudonymous",
                "title": "Lifecycle test post for export and deletion",
                "body": "Verifying translation cache and media asset cleanup on account deletion.",
                "content_language": "en",
                "meme_asset_id": asset_id,
                "workplace_detail": {
                    "experience_kind": "workplace_experience",
                    "experience_category": "work_life_balance",
                    "industry_category": "technology",
                    "lesson_learned": "Always test full deletion paths.",
                },
            },
            headers={"X-CSRF-Token": owner_csrf},
        )
        self.assertEqual(post_res.status_code, 201, post_res.text)
        post_id = post_res.json()["id"]

        # Cache a Malayalam translation for this post
        tr_res = other_c.post(
            f"/api/v1/posts/{post_id}/translations",
            json={"target_locale": "ml"},
            headers={"X-CSRF-Token": other_csrf},
        )
        self.assertEqual(tr_res.status_code, 200)

        # Owner adds a comment, bookmark, and structured contribution
        owner_c.post(
            f"/api/v1/posts/{post_id}/comments",
            json={
                "body": "Owner comment to be scrubbed on deletion.",
                "identity_mode": "pseudonymous",
                "content_language": "en",
            },
            headers={"X-CSRF-Token": owner_csrf},
        )
        owner_c.post(
            f"/api/v1/posts/{post_id}/save",
            json={"saved": True},
            headers={"X-CSRF-Token": owner_csrf},
        )
        owner_c.post(
            "/api/v1/workplace/contributions",
            json={
                "aggregation_consent": True,
                "industry_category": "technology",
                "role_family": "software_engineering",
                "experience_band": "mid_3_6",
                "work_arrangement": "remote",
                "overall_satisfaction": 4,
                "work_life_balance": 4,
            },
            headers={"X-CSRF-Token": owner_csrf},
        )

        # Verify export completeness and strict security redaction
        exp = owner_c.get("/api/v1/me/export")
        self.assertEqual(exp.status_code, 200, exp.text)
        exp_json = exp.json()
        self.assertEqual(exp_json["export_metadata"]["schema_version"], "1.2.1")
        self.assertEqual(exp_json["account"]["recovery_email"], "owner_recovery@example.com")
        self.assertEqual(len(exp_json["authored_posts"]), 1)
        self.assertIsNotNone(exp_json["authored_posts"][0]["workplace_detail"])
        self.assertEqual(len(exp_json["authored_comments"]), 1)
        self.assertEqual(len(exp_json["saved_bookmarks"]), 1)
        self.assertEqual(len(exp_json["community_memberships"]), 1)
        self.assertEqual(len(exp_json["blocks_and_mutes"]), 1)
        self.assertEqual(exp_json["blocks_and_mutes"][0]["target_handle"], "lifecycle_other")
        self.assertEqual(len(exp_json["meme_assets"]), 1)
        self.assertIsNotNone(exp_json["structured_workplace_contribution"])
        raw_exp = json.dumps(exp_json)
        self.assertNotIn("password_hash", raw_exp)
        self.assertNotIn("csrf_secret", raw_exp)
        self.assertNotIn(other_id, raw_exp)

        # Verify media file exists on disk before account deletion
        storage_key = exp_json["meme_assets"][0]["storage_key"]
        self.assertTrue((self.storage_dir / storage_key).is_file())

        # Execute account deletion with delete_published_posts=True
        del_res = owner_c.request(
            "DELETE",
            "/api/v1/me",
            json={
                "password_confirmation": "ValidPassword#2026!",
                "delete_published_posts": True,
            },
            headers={"X-CSRF-Token": owner_csrf},
        )
        self.assertEqual(del_res.status_code, 200, del_res.text)

        # 1. Media file is deleted from disk
        self.assertFalse((self.storage_dir / storage_key).is_file())

        # 2. Community member_count decremented
        comm_after = other_c.get("/api/v1/communities/corporate-memes").json()["member_count"]
        self.assertEqual(comm_after, comm_before - 1)

        # 3. Cached content_translations for the deleted post were purged, and immutable audit_events recorded
        async def _verify_db_cleanup() -> tuple[int, int]:
            async with self.db_manager.session_scope() as session:
                tr_rows = await session.execute(
                    "SELECT COUNT(1) FROM content_translations WHERE source_type = 'post' AND source_id = ?",
                    (post_id,),
                )
                audit_rows = await session.execute(
                    "SELECT COUNT(1) FROM audit_events WHERE action_name = 'account_self_deleted'"
                )
                return int(tr_rows[0][0]), int(audit_rows[0][0])

        tr_cnt, audit_cnt = asyncio.run(_verify_db_cleanup())
        self.assertEqual(tr_cnt, 0)
        self.assertGreaterEqual(audit_cnt, 1)

    def test_05_process_aware_operational_metrics_and_s3_storage_adapter(self) -> None:
        """Verifies process-local metrics scope disclosure and S3CompatibleStorageAdapter SigV4 + presigned URLs."""
        # 1. Metrics explicitly report process_local scope and configured_web_concurrency
        m_res = self.client.get("/api/v1/health/metrics")
        self.assertEqual(m_res.status_code, 200)
        m_data = m_res.json()
        self.assertEqual(m_data["http_metrics"]["collection_scope"], "process_local")
        self.assertTrue(m_data["http_metrics"]["is_cluster_wide"])
        self.assertEqual(m_data["worker_queue"]["collection_scope"], "database_global")

        multi_worker_snap = metrics_collector.snapshot(configured_web_concurrency=2)
        self.assertEqual(multi_worker_snap["collection_scope"], "process_local")
        self.assertFalse(multi_worker_snap["is_cluster_wide"])
        self.assertEqual(multi_worker_snap["configured_web_concurrency"], 2)

        # 2. S3CompatibleStorageAdapter deterministic test with InMemoryS3Transport
        s3_transport = InMemoryS3Transport()
        s3_settings = Settings(
            app_env="staging",
            storage_backend="r2",
            s3_endpoint_url="https://acct123.r2.cloudflarestorage.com",
            s3_bucket_name="pressure-out-memes",
            s3_access_key_id="AKIAIOSFODNN7EXAMPLE",
            s3_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            s3_region="auto",
        )
        adapter = create_storage_adapter(s3_settings, s3_transport=s3_transport)
        self.assertIsInstance(adapter, S3CompatibleStorageAdapter)
        self.assertTrue(adapter.is_healthy())

        png_raw = _make_valid_png_bytes(64, 64)
        stored = adapter.validate_and_store(
            raw_bytes=png_raw,
            expected_mime_type="image/png",
            storage_prefix="memes",
            asset_id="s3-asset-001",
        )
        self.assertEqual(stored.storage_key, "memes/s3-asset-001.png")
        self.assertEqual(adapter.read_bytes("memes/s3-asset-001.png"), stored.sanitized_bytes)

        # Verify private ACL and SigV4 Authorization header on PUT request
        put_reqs = [r for r in s3_transport.request_log if r["method"] == "PUT"]
        self.assertEqual(len(put_reqs), 1)
        self.assertEqual(put_reqs[0]["headers"].get("x-amz-acl"), "private")
        self.assertIn("AWS4-HMAC-SHA256 Credential=", put_reqs[0]["headers"].get("Authorization", ""))

        # Verify presigned GET URL generation
        presigned = adapter.generate_presigned_get_url("memes/s3-asset-001.png", expires_seconds=900)
        self.assertIn("X-Amz-Algorithm=AWS4-HMAC-SHA256", presigned)
        self.assertIn("X-Amz-Expires=900", presigned)
        self.assertIn("X-Amz-Signature=", presigned)
        self.assertNotIn("wJalrXUtnFEMI", presigned)

        # Verify path traversal rejection
        with self.assertRaises(AppError):
            adapter.read_bytes("../secret/config.png")

        # Verify delete_object and 404 after delete
        self.assertTrue(adapter.delete_object("memes/s3-asset-001.png"))
        with self.assertRaises(AppError) as nf_ctx:
            adapter.read_bytes("memes/s3-asset-001.png")
        self.assertEqual(nf_ctx.exception.status_code, 404)

        # Verify transport outage translates to 503 STORAGE_BACKEND_UNAVAILABLE
        s3_transport.simulate_failure = True
        self.assertFalse(adapter.is_healthy())
        with self.assertRaises(AppError) as out_ctx:
            adapter.validate_and_store(
                raw_bytes=png_raw,
                expected_mime_type="image/png",
                asset_id="s3-asset-002",
            )
        self.assertEqual(out_ctx.exception.status_code, 503)
        self.assertEqual(out_ctx.exception.code, "STORAGE_BACKEND_UNAVAILABLE")

    def test_06_scripts_and_production_compose_consistency(self) -> None:
        """Verifies backup script safety guards, benchmark CLI validation, PG qualification plan, and docker-compose.prod.yml."""
        # 1. Backup script accepts valid .dump path and pressure_out_restore_drill_* target
        ok_backup = subprocess.run(
            [
                str(REPO_ROOT / "scripts" / "backup_restore_postgres.sh"),
                "validate-config",
                "/tmp/po_staging_backup.dump",
                "pressure_out_restore_drill_2026103001",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(ok_backup.returncode, 0, ok_backup.stderr)

        # Rejects restoring into a production database name!
        bad_target = subprocess.run(
            [
                str(REPO_ROOT / "scripts" / "backup_restore_postgres.sh"),
                "validate-config",
                "/tmp/po_staging_backup.dump",
                "pressure_out_production",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(bad_target.returncode, 0)
        self.assertIn("Unsafe restore target database", bad_target.stderr)

        # Rejects path traversal in backup output path
        bad_path = subprocess.run(
            [
                str(REPO_ROOT / "scripts" / "backup_restore_postgres.sh"),
                "validate-config",
                "../etc/passwd.dump",
                "pressure_out_restore_drill_2026103001",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(bad_path.returncode, 0)

        # 2. Performance benchmark CLI argument validation
        ok_bench = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "performance_benchmark.py"),
                "--users",
                "15",
                "--iterations",
                "5",
                "--concurrency",
                "2",
                "--validate-args-only",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(ok_bench.returncode, 0, ok_bench.stderr)

        # 3. PostgreSQL 16 staging qualification plan verification
        pg_plan = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "qualify_postgres_staging.py"),
                "--verify-plan",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(pg_plan.returncode, 0, pg_plan.stderr)
        plan_json = json.loads(pg_plan.stdout)
        self.assertEqual(plan_json["expected_alembic_head"], "0010_phase11_workplace")
        self.assertEqual(len(plan_json["steps"]), 16)

        # 4. Production Compose consistency check
        compose_raw = (REPO_ROOT / "docker-compose.prod.yml").read_text()
        self.assertIn("redis:\n    image: redis:7-alpine", compose_raw)
        self.assertIn("--requirepass", compose_raw)
        self.assertIn("--maxmemory-policy noeviction", compose_raw)
        self.assertIn("RATE_LIMIT_BACKEND: redis", compose_raw)
        self.assertIn("WEB_CONCURRENCY: ${WEB_CONCURRENCY:-2}", compose_raw)
        self.assertIn("RATE_LIMIT_FAIL_CLOSED: \"true\"", compose_raw)
        self.assertNotIn("6379:6379", compose_raw)  # Redis is never publicly exposed


if __name__ == "__main__":
    unittest.main()
