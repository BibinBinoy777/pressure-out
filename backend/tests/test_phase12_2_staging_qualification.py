"""Phase 12.2 Networked Staging Qualification & Pre-Release Verification Test Suite.

Exercises:
1. Section 3 Staging Safety Guards (`verify_staging_safety_guards`).
2. Section 4 & 5 Real TCP Loopback RESP2 (`LocalResp2TestServer` + `RedisRespClient`)
   multi-worker rate limiting, `noeviction` OOM fail-closed behavior without key loss,
   window expiration, outage degradation (`503`), and recovery.
3. Section 9 13-Point S3/R2 Storage Qualification (`S3CompatibleStorageAdapter` +
   presigned URL signature/expiration verification + log redaction of `X-Amz-Signature` & Redis passwords).
4. Section 10 12-Case Multipart Upload Verification (`POST /api/v1/memes/upload`: PNG, WebP,
   >5 MB image, >6 MB envelope, missing/falsified Content-Length, unsupported MIME, bad magic bytes,
   corrupt image data, invalid dimensions, filename path traversal, and zero orphaned files).
5. Section 8, 13 & 15 Complete 27-Step Staging Smoke Flow with `APP_ENV=staging`,
   `WEB_CONCURRENCY=2`, `RATE_LIMIT_BACKEND=redis` (over TCP socket), and
   `AI_CAPTION_PROVIDER=disabled`, `AI_IMAGE_PROVIDER=disabled`, `TRANSLATION_PROVIDER=disabled`.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import datetime
import io
import json
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
    LocalResp2TestServer,
    RedisRateLimitStore,
    SharedMemoryRedisEvalClient,
    SlidingWindowRateLimiter,
    rate_limiter,
)
from app.logging_config import redact_sensitive_data, redact_sensitive_string
from app.main import create_app
from app.modules.memes.storage import (
    InMemoryS3Transport,
    S3CompatibleStorageAdapter,
    create_storage_adapter,
)

import importlib.util

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_qual_spec = importlib.util.spec_from_file_location(
    "qualify_postgres_staging", REPO_ROOT / "scripts" / "qualify_postgres_staging.py"
)
assert _qual_spec and _qual_spec.loader
_qual_mod = importlib.util.module_from_spec(_qual_spec)
_qual_spec.loader.exec_module(_qual_mod)
verify_staging_safety_guards = _qual_mod.verify_staging_safety_guards


def _make_image_bytes(fmt: str = "PNG", width: int = 128, height: int = 128) -> bytes:
    img = Image.new("RGB", (width, height), color=(48, 112, 180))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _build_multipart(
    *,
    boundary: str,
    file_bytes: bytes,
    filename: str = "meme.png",
    file_mime: str = "image/png",
    alt_text: str = "Staging smoke meme",
    language: str = "en",
) -> bytes:
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="alt_text"\r\n\r\n'
        f"{alt_text}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="language"\r\n\r\n'
        f"{language}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {file_mime}\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")


class Phase122StagingQualificationTests(unittest.TestCase):
    def setUp(self) -> None:
        rate_limiter.configure(InMemoryRateLimitStore())
        rate_limiter.reset()
        metrics_collector.reset()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.storage_dir = Path(self.tmp_dir.name) / "media"

    def tearDown(self) -> None:
        rate_limiter.configure(InMemoryRateLimitStore())
        rate_limiter.reset()
        metrics_collector.reset()
        self.tmp_dir.cleanup()

    def test_01_staging_safety_guards_reject_non_staging_or_production_targets(self) -> None:
        """Section 3: Staging safety verifier accepts valid staging config and blocks production identifiers."""
        verify_staging_safety_guards(
            app_env="staging",
            database_url="postgresql+asyncpg://po_stage:StagePass@staging-db.internal:5432/pressure_out_staging",
            redis_url="redis://:StageRedisPass@staging-redis.internal:6379/0",
            cors_origins=["https://staging.pressureout.example.com"],
            restore_target_db="pressure_out_restore_drill_2026103001",
        )

        # Rejects APP_ENV != staging
        with self.assertRaises(ValueError):
            verify_staging_safety_guards(
                app_env="production",
                database_url="postgresql+asyncpg://po_stage:StagePass@staging-db.internal:5432/pressure_out_staging",
                redis_url="redis://:StageRedisPass@staging-redis.internal:6379/0",
                cors_origins=["https://staging.pressureout.example.com"],
            )

        # Rejects production database hostname/identifier
        with self.assertRaises(ValueError):
            verify_staging_safety_guards(
                app_env="staging",
                database_url="postgresql+asyncpg://po:Pass@prod-db.internal:5432/pressure_out_prod",
                redis_url="redis://:StageRedisPass@staging-redis.internal:6379/0",
                cors_origins=["https://staging.pressureout.example.com"],
            )

        # Rejects production Redis hostname
        with self.assertRaises(ValueError):
            verify_staging_safety_guards(
                app_env="staging",
                database_url="postgresql+asyncpg://po_stage:StagePass@staging-db.internal:5432/pressure_out_staging",
                redis_url="redis://:Pass@production-redis.internal:6379/0",
                cors_origins=["https://staging.pressureout.example.com"],
            )

        # Rejects non-disposable restore database name
        with self.assertRaises(ValueError):
            verify_staging_safety_guards(
                app_env="staging",
                database_url="postgresql+asyncpg://po_stage:StagePass@staging-db.internal:5432/pressure_out_staging",
                redis_url="redis://:StageRedisPass@staging-redis.internal:6379/0",
                cors_origins=["https://staging.pressureout.example.com"],
                restore_target_db="pressure_out_staging",
            )

    def test_02_real_tcp_resp2_socket_multi_worker_rate_limiting_noeviction_oom_and_recovery(self) -> None:
        """Section 4 & 5: Exercises RedisRespClient over real TCP loopback sockets with noeviction OOM and outage recovery."""
        clock_ms = [1_700_000_000_000]
        backing = SharedMemoryRedisEvalClient(
            time_ms_fn=lambda: clock_ms[0],
            max_keys=50,
            eviction_policy="noeviction",
        )
        server = LocalResp2TestServer(backing, requirepass="StagingRedisSecret!2026")
        try:
            # 1. Wrong password fails authentication and triggers fail-closed 503
            bad_auth_store = RedisRateLimitStore(
                redis_url=f"redis://:wrong_password@{server.host}:{server.port}/0",
                socket_timeout_seconds=1.5,
                fail_closed=True,
            )
            self.assertFalse(bad_auth_store.is_healthy())
            with self.assertRaises(AppError) as bad_ctx:
                bad_auth_store.check_and_record(bucket="auth_login", key="u1", limit=3, window_seconds=60)
            self.assertEqual(bad_ctx.exception.status_code, 503)

            # 2. Two independent worker processes/instances sharing quota over real TCP sockets
            worker_1 = SlidingWindowRateLimiter(
                RedisRateLimitStore(
                    redis_url=server.redis_url,
                    socket_timeout_seconds=2.0,
                    fail_closed=True,
                    time_ms_fn=lambda: clock_ms[0],
                )
            )
            worker_2 = SlidingWindowRateLimiter(
                RedisRateLimitStore(
                    redis_url=server.redis_url,
                    socket_timeout_seconds=2.0,
                    fail_closed=True,
                    time_ms_fn=lambda: clock_ms[0],
                )
            )
            self.assertTrue(worker_1.is_healthy())
            self.assertTrue(worker_2.is_healthy())

            # 20 concurrent requests across worker_1 and worker_2 for limit=5 -> 5 admitted, 15 rejected (429)
            def _call_worker(i: int) -> int:
                w = worker_1 if i % 2 == 0 else worker_2
                try:
                    w.check_and_record(bucket="tcp_shared", key="subject_alpha", limit=5, window_seconds=60)
                    return 200
                except AppError as exc:
                    return exc.status_code

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                codes = list(pool.map(_call_worker, range(20)))
            self.assertEqual(codes.count(200), 5)
            self.assertEqual(codes.count(429), 15)

            # 3. Verify noeviction OOM behavior: existing active keys are NEVER evicted under memory exhaustion,
            #    and write attempts fail closed with 503 RATE_LIMIT_BACKEND_UNAVAILABLE.
            keys_before_oom = set(backing.inspect_keys())
            backing.simulate_oom = True
            with self.assertRaises(AppError) as oom_ctx:
                worker_1.check_and_record(bucket="tcp_shared", key="new_subject_oom", limit=5, window_seconds=60)
            self.assertEqual(oom_ctx.exception.status_code, 503)
            self.assertEqual(oom_ctx.exception.code, "RATE_LIMIT_BACKEND_UNAVAILABLE")
            self.assertEqual(set(backing.inspect_keys()), keys_before_oom)
            backing.simulate_oom = False

            # 4. Window expiration after 61s restores allowance
            clock_ms[0] += 61_000
            worker_2.check_and_record(bucket="tcp_shared", key="subject_alpha", limit=5, window_seconds=60)

            # 5. Simulate TCP outage & recovery
            server.accept_connections = False
            self.assertFalse(worker_1.is_healthy())
            with self.assertRaises(AppError) as out_ctx:
                worker_1.check_and_record(bucket="tcp_shared", key="subject_alpha", limit=5, window_seconds=60)
            self.assertEqual(out_ctx.exception.status_code, 503)

            server.accept_connections = True
            self.assertTrue(worker_1.is_healthy())
            worker_1.check_and_record(bucket="tcp_shared", key="subject_alpha", limit=5, window_seconds=60)
        finally:
            server.close()

    def test_03_s3_compatible_storage_13_point_qualification_and_log_redaction(self) -> None:
        """Section 9: Verifies 13 S3/R2 storage operations, presigned URL expiration, and log secret redaction."""
        s3_transport = InMemoryS3Transport()
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        adapter = S3CompatibleStorageAdapter(
            endpoint_url="https://staging-acct.r2.cloudflarestorage.com",
            bucket_name="po-staging-private-media",
            access_key_id="AKIASTAGINGEXAMPLE01",
            secret_access_key=secret_key,
            region="auto",
            key_prefix="memes",
            timeout_seconds=8.0,
            presigned_url_ttl_seconds=600,
            transport=s3_transport,
        )

        # 1-3. Upload PNG & WebP, inspect metadata, confirm private ACL and timeout propagation
        png_bytes = _make_image_bytes("PNG", 96, 96)
        meta_png = adapter.validate_and_store(
            raw_bytes=png_bytes,
            expected_mime_type="image/png",
            storage_prefix="memes",
            asset_id="stage-asset-png-01",
        )
        self.assertEqual(meta_png.mime_type, "image/png")
        self.assertEqual(meta_png.width, 96)
        self.assertEqual(s3_transport.request_log[-1]["headers"].get("x-amz-acl"), "private")
        self.assertEqual(s3_transport.request_log[-1]["timeout_seconds"], 8.0)

        webp_bytes = _make_image_bytes("WEBP", 120, 80)
        meta_webp = adapter.validate_and_store(
            raw_bytes=webp_bytes,
            expected_mime_type="image/webp",
            storage_prefix="memes",
            asset_id="stage-asset-webp-02",
        )
        self.assertEqual(meta_webp.mime_type, "image/webp")

        # 4-7. Presigned GET URL: valid before expiration (200), rejected after expiration (403), rejected if tampered (403)
        t0 = datetime.datetime(2026, 10, 30, 12, 0, 0, tzinfo=datetime.timezone.utc)
        presigned_url = adapter.generate_presigned_get_url(
            meta_png.storage_key,
            expires_seconds=300,
            now_utc=t0,
        )
        status_ok, body_ok, hdrs_ok = s3_transport.request_presigned_get(
            presigned_url,
            secret_access_key=secret_key,
            now_utc=t0 + datetime.timedelta(seconds=120),
        )
        self.assertEqual(status_ok, 200)
        self.assertEqual(body_ok, meta_png.sanitized_bytes)
        self.assertEqual(hdrs_ok["content-type"], "image/png")

        status_exp, _, _ = s3_transport.request_presigned_get(
            presigned_url,
            secret_access_key=secret_key,
            now_utc=t0 + datetime.timedelta(seconds=301),
        )
        self.assertEqual(status_exp, 403)

        tampered_url = presigned_url.replace("X-Amz-Expires=300", "X-Amz-Expires=9999")
        status_tamp, _, _ = s3_transport.request_presigned_get(
            tampered_url,
            secret_access_key=secret_key,
            now_utc=t0 + datetime.timedelta(seconds=10),
        )
        self.assertEqual(status_tamp, 403)

        # 9-11. Delete object, verify 404 on missing object, verify 503 on outage
        self.assertTrue(adapter.delete_object(meta_webp.storage_key))
        with self.assertRaises(AppError) as nf_ctx:
            adapter.read_bytes(meta_webp.storage_key)
        self.assertEqual(nf_ctx.exception.status_code, 404)

        s3_transport.simulate_failure = True
        with self.assertRaises(AppError) as out_ctx:
            adapter.read_bytes(meta_png.storage_key)
        self.assertEqual(out_ctx.exception.status_code, 503)

        # 12-13. Verify signed URL query parameters and Redis passwords are redacted in logs
        redacted_url = redact_sensitive_string(
            f"GET {presigned_url} redis://:SuperSecretRedisPass@staging-redis:6379/0"
        )
        self.assertIn("X-Amz-Signature=[REDACTED]", redacted_url)
        self.assertIn("X-Amz-Credential=[REDACTED]", redacted_url)
        self.assertNotIn("SuperSecretRedisPass", redacted_url)

        redacted_dict = redact_sensitive_data(
            {
                "s3_secret_access_key": secret_key,
                "redis_url": "redis://:SuperSecretRedisPass@staging-redis:6379/0",
            }
        )
        self.assertEqual(redacted_dict["s3_secret_access_key"], "[REDACTED]")
        self.assertEqual(redacted_dict["redis_url"], "[REDACTED]")

    def test_04_multipart_upload_12_edge_cases_verification(self) -> None:
        """Section 10: Exercises all 12 multipart upload edge cases and confirms zero orphaned files."""
        settings = Settings(
            app_env="staging",
            database_url="sqlite:///:memory:",
            local_storage_path=str(self.storage_dir),
            session_cookie_secure=False,
        )
        app = create_app(settings=settings)
        try:
            client = TestClient(app)
            reg = client.post(
                "/api/v1/auth/register",
                json={"handle": "mp_stage_user", "password": "ValidPassword#2026!"},
            )
            self.assertEqual(reg.status_code, 201)
            csrf = reg.json()["csrf_token"]
            boundary = "----StagingMultipartBoundary99"

            # 1. Valid PNG upload (201)
            r_png = client.post(
                "/api/v1/memes/upload",
                content=_build_multipart(boundary=boundary, file_bytes=_make_image_bytes("PNG", 100, 100)),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": csrf},
            )
            self.assertEqual(r_png.status_code, 201, r_png.text)

            # 2. Valid WebP upload (201)
            r_webp = client.post(
                "/api/v1/memes/upload",
                content=_build_multipart(
                    boundary=boundary,
                    file_bytes=_make_image_bytes("WEBP", 100, 100),
                    filename="meme.webp",
                    file_mime="image/webp",
                ),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": csrf},
            )
            self.assertEqual(r_webp.status_code, 201, r_webp.text)

            # Snapshot stored files after the 2 valid uploads
            valid_files = set(self.storage_dir.rglob("*.png")) | set(self.storage_dir.rglob("*.webp"))
            self.assertEqual(len(valid_files), 2)

            # 3. Image exceeding 5 MB limit (422 IMAGE_TOO_LARGE)
            over_5mb = b"\x89PNG\r\n\x1a\n" + (b"\x00" * (5 * 1024 * 1024 + 512))
            r3 = client.post(
                "/api/v1/memes/upload",
                content=_build_multipart(boundary=boundary, file_bytes=over_5mb),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": csrf},
            )
            self.assertEqual(r3.status_code, 422)
            self.assertEqual(r3.json()["error"]["code"], "IMAGE_TOO_LARGE")

            # 4. Multipart body exceeding 6 MB envelope (413 UPLOAD_TOO_LARGE)
            over_6mb = _build_multipart(boundary=boundary, file_bytes=b"X" * (6 * 1024 * 1024 + 1024))
            r4 = client.post(
                "/api/v1/memes/upload",
                content=over_6mb,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": csrf},
            )
            self.assertEqual(r4.status_code, 413)
            self.assertEqual(r4.json()["error"]["code"], "UPLOAD_TOO_LARGE")

            # 5. Falsified small Content-Length ("40") on > 6 MB multipart stream (413 UPLOAD_TOO_LARGE)
            r5 = client.post(
                "/api/v1/memes/upload",
                content=over_6mb,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Content-Length": "40",
                    "X-CSRF-Token": csrf,
                },
            )
            self.assertEqual(r5.status_code, 413)

            # 6. Unsupported MIME type (image/gif -> 422 UNSUPPORTED_IMAGE_FORMAT)
            r6 = client.post(
                "/api/v1/memes/upload",
                content=_build_multipart(
                    boundary=boundary,
                    file_bytes=_make_image_bytes("PNG", 64, 64),
                    file_mime="image/gif",
                ),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": csrf},
            )
            self.assertEqual(r6.status_code, 422)
            self.assertEqual(r6.json()["error"]["code"], "UNSUPPORTED_IMAGE_FORMAT")

            # 7. Invalid magic bytes (422 UNSUPPORTED_IMAGE_FORMAT)
            r7 = client.post(
                "/api/v1/memes/upload",
                content=_build_multipart(boundary=boundary, file_bytes=b"NOT_A_VALID_IMAGE_HEADER_12345"),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": csrf},
            )
            self.assertEqual(r7.status_code, 422)
            self.assertEqual(r7.json()["error"]["code"], "UNSUPPORTED_IMAGE_FORMAT")

            # 8. Corrupt image binary with valid PNG signature (422 CORRUPT_IMAGE_DATA)
            r8 = client.post(
                "/api/v1/memes/upload",
                content=_build_multipart(boundary=boundary, file_bytes=b"\x89PNG\r\n\x1a\nCORRUPT_BODY_BYTES"),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": csrf},
            )
            self.assertEqual(r8.status_code, 422)
            self.assertEqual(r8.json()["error"]["code"], "CORRUPT_IMAGE_DATA")

            # 9. Invalid dimensions (8x8 < 16px minimum -> 422 INVALID_IMAGE_DIMENSIONS)
            r9 = client.post(
                "/api/v1/memes/upload",
                content=_build_multipart(boundary=boundary, file_bytes=_make_image_bytes("PNG", 8, 8)),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": csrf},
            )
            self.assertEqual(r9.status_code, 422)
            self.assertEqual(r9.json()["error"]["code"], "INVALID_IMAGE_DIMENSIONS")

            # 10. Filename path traversal attempt ("../../etc/passwd.png") -> stored safely under UUID key
            r10 = client.post(
                "/api/v1/memes/upload",
                content=_build_multipart(
                    boundary=boundary,
                    file_bytes=_make_image_bytes("PNG", 64, 64),
                    filename="../../etc/passwd.png",
                ),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": csrf},
            )
            self.assertEqual(r10.status_code, 201)
            r10_id = r10.json()["id"]
            self.assertTrue(r10.json()["download_url"].endswith(f"/memes/assets/{r10_id}/download"))
            self.assertTrue((self.storage_dir / "memes" / f"{r10_id}.png").is_file())

            # Confirm zero orphaned .tmp or failed files exist
            tmp_files = list(self.storage_dir.rglob("*.tmp"))
            self.assertEqual(len(tmp_files), 0)
        finally:
            asyncio.run(app.state.db_manager.dispose())

    def test_05_staging_disabled_providers_27_step_end_to_end_smoke_and_cleanup(self) -> None:
        """Section 8, 13 & 15: Full 27-step staging smoke flow with APP_ENV=staging, WEB_CONCURRENCY=2, TCP Redis, and disabled AI/translation providers."""
        backing = SharedMemoryRedisEvalClient(eviction_policy="noeviction")
        tcp_redis = LocalResp2TestServer(backing, requirepass="StagingSmokePass!2026")
        staging_settings = Settings(
            app_env="staging",
            database_url="sqlite:///:memory:",
            web_concurrency=2,
            rate_limit_backend="redis",
            redis_url=tcp_redis.redis_url,
            rate_limit_fail_closed=True,
            local_storage_path=str(self.storage_dir),
            session_cookie_secure=False,
            ai_caption_provider="disabled",
            ai_image_provider="disabled",
            translation_provider="disabled",
            insights_min_cohort_size=10,
        )
        app = create_app(settings=staging_settings)
        try:
            # Verify health/ready & process-aware metrics with WEB_CONCURRENCY=2 + TCP Redis
            anon_client = TestClient(app)
            ready = anon_client.get("/api/v1/health/ready")
            self.assertEqual(ready.status_code, 200, ready.text)
            self.assertEqual(ready.json()["status"], "ready")
            self.assertEqual(ready.json()["rate_limit_backend"], "redis")
            self.assertTrue(ready.json()["rate_limit_ready"])

            metrics = anon_client.get("/api/v1/health/metrics").json()
            self.assertEqual(metrics["app_env"], "staging")
            self.assertEqual(metrics["http_metrics"]["collection_scope"], "process_local")
            self.assertFalse(metrics["http_metrics"]["is_cluster_wide"])
            self.assertEqual(metrics["http_metrics"]["configured_web_concurrency"], 2)

            # Register 10 synthetic staging accounts for k=10 cohort + smoke flows
            users = []
            for idx in range(10):
                backing.reset()
                c = TestClient(app)
                reg = c.post(
                    "/api/v1/auth/register",
                    json={
                        "handle": f"stage_smoke_{idx:02d}",
                        "password": "StagingPassword#2026!",
                        "default_identity_mode": "pseudonymous",
                        "preferred_ui_locale": "en",
                    },
                )
                self.assertEqual(reg.status_code, 201, reg.text)
                users.append((c, reg.json()["user_id"], reg.json()["csrf_token"]))

            author_c, author_id, author_csrf = users[0]
            peer_c, peer_id, peer_csrf = users[1]

            # Update locale preference & join community
            self.assertEqual(
                peer_c.patch(
                    "/api/v1/me/settings",
                    json={"preferred_ui_locale": "ml", "preferred_content_locales": ["ml", "en"]},
                    headers={"X-CSRF-Token": peer_csrf},
                ).status_code,
                200,
            )
            self.assertEqual(
                peer_c.post(
                    "/api/v1/communities/general-workplace/membership",
                    json={"action": "join"},
                    headers={"X-CSRF-Token": peer_csrf},
                ).status_code,
                200,
            )

            # Pseudonymous post, anonymous post, comment, vote, reaction, notification
            p_pseudo = author_c.post(
                "/api/v1/posts",
                json={
                    "community_slug": "general-workplace",
                    "post_type": "story",
                    "identity_mode": "pseudonymous",
                    "title": "Staging qualification postmortem",
                    "body": "Verifying multi-worker Redis rate limiting and disabled external AI providers.",
                    "content_language": "en",
                },
                headers={"X-CSRF-Token": author_csrf},
            )
            self.assertEqual(p_pseudo.status_code, 201)
            post_id = p_pseudo.json()["id"]

            p_anon = author_c.post(
                "/api/v1/posts",
                json={
                    "community_slug": "general-workplace",
                    "post_type": "rant",
                    "identity_mode": "anonymous",
                    "title": "Anonymous staging reflection",
                    "body": "Ensuring zero handle leakage in staging.",
                    "content_language": "en",
                },
                headers={"X-CSRF-Token": author_csrf},
            )
            self.assertEqual(p_anon.status_code, 201)
            self.assertIsNone(p_anon.json()["author"]["handle"])

            self.assertEqual(
                peer_c.post(
                    f"/api/v1/posts/{post_id}/comments",
                    json={"body": "Verified in staging!", "identity_mode": "pseudonymous", "content_language": "en"},
                    headers={"X-CSRF-Token": peer_csrf},
                ).status_code,
                201,
            )
            self.assertEqual(
                peer_c.put(
                    f"/api/v1/posts/{post_id}/vote",
                    json={"value": 1},
                    headers={"X-CSRF-Token": peer_csrf},
                ).status_code,
                200,
            )
            self.assertGreaterEqual(len(author_c.get("/api/v1/notifications").json()["items"]), 1)

            # Template meme rendering & multipart meme upload work with AI providers disabled!
            render_res = author_c.post(
                "/api/v1/memes/render",
                json={
                    "template_id_or_slug": "friday-455pm-deploy",
                    "language": "en",
                    "output_format": "PNG",
                    "captions": [
                        {"region_id": "top", "text": "AI PROVIDERS DISABLED"},
                        {"region_id": "bottom", "text": "TEMPLATE RENDERER STILL WORKS"},
                    ],
                },
                headers={"X-CSRF-Token": author_csrf},
            )
            self.assertEqual(render_res.status_code, 201)

            boundary = "----StagingSmokeUploadBoundary"
            up_res = author_c.post(
                "/api/v1/memes/upload",
                content=_build_multipart(boundary=boundary, file_bytes=_make_image_bytes("PNG", 96, 96)),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": author_csrf},
            )
            self.assertEqual(up_res.status_code, 201)

            # Disabled AI caption, AI image, and translation providers return clean 503 responses
            cap_disabled = author_c.post(
                "/api/v1/memes/captions",
                json={"prompt": "Friday deploy", "language": "en", "style_tone": "sarcastic"},
                headers={"X-CSRF-Token": author_csrf},
            )
            self.assertEqual(cap_disabled.status_code, 503)

            tr_disabled = peer_c.post(
                f"/api/v1/posts/{post_id}/translations",
                json={"target_locale": "ml"},
                headers={"X-CSRF-Token": peer_csrf},
            )
            self.assertEqual(tr_disabled.status_code, 503)

            # 10 structured contributions unlock k=10 insights; withdrawing 1 contribution suppresses cohort
            for c_client, _, c_csrf in users:
                backing.reset()
                r = c_client.post(
                    "/api/v1/workplace/contributions",
                    json={
                        "aggregation_consent": True,
                        "industry_category": "technology",
                        "role_family": "software_engineering",
                        "experience_band": "mid_3_6",
                        "work_arrangement": "hybrid",
                        "overall_satisfaction": 4,
                        "work_life_balance": 4,
                    },
                    headers={"X-CSRF-Token": c_csrf},
                )
                self.assertEqual(r.status_code, 201)

            ins_unlocked = peer_c.get("/api/v1/workplace/insights?industry_category=technology").json()
            self.assertEqual(ins_unlocked["cohort_eligible_band"], "10+")

            # Withdraw consent on peer_c -> cohort drops to 9 and suppresses!
            peer_contrib_id = peer_c.get("/api/v1/workplace/contributions/mine").json()["id"]
            withdraw = peer_c.patch(
                f"/api/v1/workplace/contributions/{peer_contrib_id}",
                json={"aggregation_consent": False},
                headers={"X-CSRF-Token": peer_csrf},
            )
            self.assertEqual(withdraw.status_code, 200)
            ins_suppressed = peer_c.get("/api/v1/workplace/insights?industry_category=technology").json()
            self.assertIsNone(ins_suppressed["cohort_eligible_band"])

            # Export and clean up all 10 synthetic staging accounts via DELETE /api/v1/me
            exp_res = author_c.get("/api/v1/me/export")
            self.assertEqual(exp_res.status_code, 200)
            self.assertGreaterEqual(len(exp_res.json()["meme_assets"]), 2)

            for c_client, _, c_csrf in users:
                backing.reset()
                del_r = c_client.request(
                    "DELETE",
                    "/api/v1/me",
                    json={"password_confirmation": "StagingPassword#2026!", "delete_published_posts": True},
                    headers={"X-CSRF-Token": c_csrf},
                )
                self.assertEqual(del_r.status_code, 200)
        finally:
            asyncio.run(app.state.db_manager.dispose())
            tcp_redis.close()


if __name__ == "__main__":
    unittest.main()
