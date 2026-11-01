"""Phase 8 AI Meme Studio, TemplateRenderer, Quotas, Worker & Privacy Test Suite."""
from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.core.errors import AppError
from app.core.rate_limit import rate_limiter
from app.database.session import DatabaseManager, _load_migration
from app.main import create_app
from app.modules.memes.adapters.base import ImageGenRequest, ImageGenResult
from app.modules.memes.storage import LocalFilesystemStorageAdapter
from app.modules.memes.template_renderer import (
    RenderCaptionInput,
    TemplateRenderer,
    TextRegionSpec,
)
from app.workers.meme_worker import MemeJobWorker


class FlakyImageAdapter:
    """Fails on attempt 1 with a transient 503 error, succeeds on attempt 2."""

    def __init__(self, fallback_bytes: bytes) -> None:
        self.calls = 0
        self.fallback_bytes = fallback_bytes

    async def generate_image(self, req: ImageGenRequest) -> ImageGenResult:
        self.calls += 1
        if self.calls == 1:
            raise AppError(
                code="PROVIDER_TIMEOUT",
                message="Upstream provider timed out.",
                status_code=504,
            )
        return ImageGenResult(
            image_bytes=self.fallback_bytes,
            mime_type="image/png",
            provider_name="local_mock",
            model_name="flaky-retry-test",
            is_mock=True,
            estimated_cost_micros=10000,
        )


class Phase8AIMemeStudioTests(unittest.TestCase):
    def setUp(self) -> None:
        rate_limiter.reset()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.storage_dir = Path(self.tmp_dir.name) / "media"
        self.settings = Settings(
            app_env="test",
            database_url="sqlite:///:memory:",
            local_storage_path=str(self.storage_dir),
            ai_caption_provider="local_mock",
            ai_image_provider="local_mock",
            meme_caption_daily_limit=3,
            meme_image_daily_limit=2,
            meme_max_concurrent_jobs=1,
            meme_job_max_retries=1,
            ai_daily_spend_cap_usd=1.0,
        )
        self.app = create_app(settings=self.settings)
        self.db_manager = self.app.state.db_manager
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        asyncio.run(self.db_manager.dispose())
        self.tmp_dir.cleanup()

    def _register_and_get_csrf(self, handle: str, password: str = "ValidPass#2026!") -> tuple[TestClient, str]:
        c = TestClient(self.app)
        resp = c.post(
            "/api/v1/auth/register",
            json={
                "handle": handle,
                "password": password,
                "default_identity_mode": "pseudonymous",
                "preferred_ui_locale": "en",
            },
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        csrf = resp.json()["csrf_token"]
        return c, csrf

    def test_01_template_listing_and_preview_rendering(self) -> None:
        resp = self.client.get("/api/v1/memes/templates")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertGreaterEqual(len(data["items"]), 6)
        self.assertTrue(data["ai_caption_enabled"])
        self.assertTrue(data["ai_image_enabled"])
        self.assertTrue(data["is_mock_provider"])

        first = data["items"][0]
        self.assertEqual(first["slug"], "friday-455pm-deploy")
        self.assertGreaterEqual(len(first["text_regions"]), 2)
        self.assertIn("CC0", first["license_info"])

        # Category filter
        eng_resp = self.client.get("/api/v1/memes/templates?category=engineering")
        self.assertEqual(eng_resp.status_code, 200)
        self.assertEqual(len(eng_resp.json()["items"]), 1)

        # Preview image endpoint
        prev = self.client.get(f"/api/v1/memes/templates/{first['slug']}/preview")
        self.assertEqual(prev.status_code, 200)
        self.assertEqual(prev.headers["content-type"], "image/png")
        self.assertEqual(prev.headers["x-content-type-options"], "nosniff")
        self.assertTrue(prev.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_02_multilingual_unicode_template_rendering_png_and_webp(self) -> None:
        c, csrf = self._register_and_get_csrf("meme_creator_ml")
        multilingual_cases = [
            ("en", "When the sprint review is in 5 minutes", "And staging just caught fire 🔥"),
            ("ml", "വെള്ളിയാഴ്ച വൈകുന്നേരം 4:55 PM", "മാനേജർ: ഒരു ചെറിയ പണി കൂടിയുണ്ട്!"),
            ("hi", "उम्मीद: आज जल्दी लॉग-ऑफ करूँगा", "हकीकत: शाम 5 बजे अर्जेंट मीटिंग"),
            ("ta", "வெள்ளிக்கிழமை மாலை ஓய்வு", "திடீர் மீட்டிங் அழைப்பு!"),
            ("mul", "Deploy on Friday? നമസ്കാരം नमस्ते வணக்கம் 🚀", "What could possibly go wrong 😅"),
        ]
        for lang, top_txt, bot_txt in multilingual_cases:
            fmt = "WEBP" if lang == "ml" else "PNG"
            r = c.post(
                "/api/v1/memes/render",
                headers={"X-CSRF-Token": csrf},
                json={
                    "template_id_or_slug": "friday-455pm-deploy",
                    "captions": [
                        {"region_id": "top", "text": top_txt},
                        {"region_id": "bottom", "text": bot_txt},
                    ],
                    "language": lang,
                    "output_format": fmt,
                },
            )
            self.assertEqual(r.status_code, 201, r.text)
            asset = r.json()
            self.assertEqual(asset["caption_language"], lang)
            self.assertEqual(
                asset["mime_type"], "image/webp" if fmt == "WEBP" else "image/png"
            )
            self.assertGreater(asset["file_size_bytes"], 1000)
            self.assertNotIn("owner_user_id", asset)

            dl = c.get(asset["download_url"])
            self.assertEqual(dl.status_code, 200)
            self.assertEqual(dl.headers["x-content-type-options"], "nosniff")
            if fmt == "WEBP":
                self.assertEqual(dl.content[:4], b"RIFF")
            else:
                self.assertTrue(dl.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_03_template_rendering_works_when_ai_providers_disabled(self) -> None:
        disabled_settings = Settings(
            app_env="test",
            database_url="sqlite:///:memory:",
            local_storage_path=str(self.storage_dir),
            ai_caption_provider="disabled",
            ai_image_provider="disabled",
        )
        app_disabled = create_app(settings=disabled_settings)
        db_mgr = app_disabled.state.db_manager
        c = TestClient(app_disabled)

        reg = c.post(
            "/api/v1/auth/register",
            json={"handle": "offline_creator", "password": "ValidPass#2026!"},
        )
        csrf = reg.json()["csrf_token"]

        # AI caption returns 503 when disabled
        cap_resp = c.post(
            "/api/v1/memes/captions",
            headers={"X-CSRF-Token": csrf},
            json={"prompt": "Friday deploy chaos", "tone": "sarcastic", "language": "en"},
        )
        self.assertEqual(cap_resp.status_code, 503)
        self.assertEqual(cap_resp.json()["error"]["code"], "AI_PROVIDER_UNAVAILABLE")

        # Template rendering STILL succeeds 100% locally!
        render_resp = c.post(
            "/api/v1/memes/render-template",
            headers={"X-CSRF-Token": csrf},
            json={
                "template_id_or_slug": "could-have-been-an-email",
                "captions": [
                    {"region_id": "top", "text": "60 minute calendar invite"},
                    {"region_id": "bottom", "text": "For a two-sentence status update"},
                ],
                "language": "en",
            },
        )
        self.assertEqual(render_resp.status_code, 201, render_resp.text)
        asyncio.run(db_mgr.dispose())

    def test_04_caption_assistant_pii_sanitization_safety_and_daily_quota(self) -> None:
        c, csrf = self._register_and_get_csrf("caption_tester")

        # Unsafe violent/doxxing prompt is blocked with 422 UNSAFE_PROMPT without consuming quota
        unsafe = c.post(
            "/api/v1/memes/captions",
            headers={"X-CSRF-Token": csrf},
            json={
                "prompt": "Let us post the home address and social security number of our manager",
                "tone": "sarcastic",
                "language": "en",
            },
        )
        self.assertEqual(unsafe.status_code, 422)
        self.assertEqual(unsafe.json()["error"]["code"], "UNSAFE_PROMPT")

        # Accidental email/phone/handle in prompt is automatically redacted before provider call
        r1 = c.post(
            "/api/v1/memes/captions",
            headers={"X-CSRF-Token": csrf},
            json={
                "prompt": "My manager boss@corp.example or @ toxic_lead called 987-654-3210 at 4:55pm",
                "tone": "sarcastic",
                "language": "en",
            },
        )
        self.assertEqual(r1.status_code, 200, r1.text)
        body1 = r1.json()
        self.assertIn("email_redacted", body1["pii_redactions"])
        self.assertIn("phone_redacted", body1["pii_redactions"])
        self.assertNotIn("boss@corp.example", body1["sanitized_prompt"])
        self.assertTrue(body1["is_mock_provider"])
        self.assertEqual(body1["quota_remaining"], 2)

        # Request 2 (Malayalam) and Request 3 (Hindi)
        r2 = c.post(
            "/api/v1/memes/captions/suggest",
            headers={"X-CSRF-Token": csrf},
            json={"prompt": "വെള്ളിയാഴ്ച മീറ്റിംഗ്", "tone": "humorous" if False else "absurd", "language": "ml"},
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["quota_remaining"], 1)

        r3 = c.post(
            "/api/v1/memes/captions",
            headers={"X-CSRF-Token": csrf},
            json={"prompt": "शाम 5 बजे मीटिंग", "tone": "deadpan", "language": "hi"},
        )
        self.assertEqual(r3.status_code, 200)
        self.assertEqual(r3.json()["quota_remaining"], 0)

        # Request 4 exceeds daily limit (3) -> 429 MEME_QUOTA_EXCEEDED
        r4 = c.post(
            "/api/v1/memes/captions",
            headers={"X-CSRF-Token": csrf},
            json={"prompt": "One more request over daily quota", "tone": "sarcastic", "language": "en"},
        )
        self.assertEqual(r4.status_code, 429)
        self.assertEqual(r4.json()["error"]["code"], "MEME_QUOTA_EXCEEDED")

    def test_05_async_image_job_lifecycle_idempotency_concurrency_cancel_and_worker(self) -> None:
        c1, csrf1 = self._register_and_get_csrf("job_owner_one")
        c2, csrf2 = self._register_and_get_csrf("other_viewer_two")

        # 1. Submit job with Idempotency-Key -> 202 Accepted
        j1 = c1.post(
            "/api/v1/memes/jobs",
            headers={"X-CSRF-Token": csrf1, "Idempotency-Key": "idem-key-001"},
            json={
                "job_type": "ai_image",
                "prompt": "A developer surrounded by 47 unread Slack notifications on Friday afternoon",
                "style_tone": "absurd",
                "language": "en",
                "captions": [
                    {"region_id": "top", "text": "JUST ONE QUICK QUESTION"},
                    {"region_id": "bottom", "text": "47 THREAD REPLIES LATER"},
                ],
            },
        )
        self.assertEqual(j1.status_code, 202, j1.text)
        job_data = j1.json()
        job_id = job_data["id"]
        self.assertEqual(job_data["status"], "queued")

        # 2. Repeating with same Idempotency-Key returns the exact same job without error
        j1_dup = c1.post(
            "/api/v1/memes/jobs",
            headers={"X-CSRF-Token": csrf1, "Idempotency-Key": "idem-key-001"},
            json={
                "job_type": "ai_image",
                "prompt": "A developer surrounded by 47 unread Slack notifications on Friday afternoon",
                "style_tone": "absurd",
                "language": "en",
            },
        )
        self.assertEqual(j1_dup.status_code, 202)
        self.assertEqual(j1_dup.json()["id"], job_id)

        # 3. Submitting a second concurrent job while job 1 is still queued -> 429 CONCURRENT_JOB_LIMIT_EXCEEDED
        j_concurrent = c1.post(
            "/api/v1/memes/jobs",
            headers={"X-CSRF-Token": csrf1, "Idempotency-Key": "idem-key-002"},
            json={
                "job_type": "ai_image",
                "prompt": "Another concurrent job attempt",
                "style_tone": "sarcastic",
                "language": "en",
            },
        )
        self.assertEqual(j_concurrent.status_code, 429)
        self.assertEqual(j_concurrent.json()["error"]["code"], "CONCURRENT_JOB_LIMIT_EXCEEDED")

        # 4. Another user CANNOT inspect or cancel user 1's job (403 FORBIDDEN_JOB_ACCESS)
        forbidden_get = c2.get(f"/api/v1/memes/jobs/{job_id}")
        self.assertEqual(forbidden_get.status_code, 403)
        self.assertEqual(forbidden_get.json()["error"]["code"], "FORBIDDEN_JOB_ACCESS")

        # 5. Cancel job 1 while queued -> transitions to 'cancelled' and frees concurrency & daily quota
        cancel_resp = c1.post(
            f"/api/v1/memes/jobs/{job_id}/cancel",
            headers={"X-CSRF-Token": csrf1},
        )
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertEqual(cancel_resp.json()["status"], "cancelled")

        # 6. Now create Job 2 and run background worker to completion
        j2 = c1.post(
            "/api/v1/memes/jobs",
            headers={"X-CSRF-Token": csrf1, "Idempotency-Key": "idem-key-003"},
            json={
                "job_type": "ai_image",
                "prompt": "Coffee machine broken during sprint planning",
                "style_tone": "dramatic",
                "language": "en",
                "captions": [
                    {"region_id": "top", "text": "COFFEE MACHINE OFFLINE"},
                    {"region_id": "bottom", "text": "SPRINT VELOCITY ZERO"},
                ],
            },
        )
        self.assertEqual(j2.status_code, 202)
        job2_id = j2.json()["id"]

        async def _run_worker() -> None:
            async with self.db_manager.session_scope() as session:
                worker = MemeJobWorker(session=session, settings=self.settings)
                await worker.process_single_job(job2_id)

        asyncio.run(_run_worker())

        # Poll job 2 -> status is 'ready' with validated result_asset
        polled = c1.get(f"/api/v1/memes/jobs/{job2_id}")
        self.assertEqual(polled.status_code, 200)
        ready_job = polled.json()
        self.assertEqual(ready_job["status"], "ready")
        self.assertTrue(ready_job["is_mock_provider"])
        self.assertIsNotNone(ready_job["result_asset"])
        asset_id = ready_job["result_asset"]["id"]

        # Cancelling an already-ready job returns 409 JOB_NOT_CANCELLABLE
        cannot_cancel = c1.post(
            f"/api/v1/memes/jobs/{job2_id}/cancel",
            headers={"X-CSRF-Token": csrf1},
        )
        self.assertEqual(cannot_cancel.status_code, 409)
        self.assertEqual(cannot_cancel.json()["error"]["code"], "JOB_NOT_CANCELLABLE")

        # Verify another user cannot publish user 1's meme asset (403 FORBIDDEN_MEME_ASSET)
        hijack_resp = c2.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": csrf2},
            json={
                "community_slug": "corporate-memes",
                "post_type": "meme",
                "identity_mode": "pseudonymous",
                "title": "Trying to attach someone else's meme asset",
                "body": "Should be rejected with 403.",
                "content_language": "en",
                "meme_asset_id": asset_id,
            },
        )
        self.assertEqual(hijack_resp.status_code, 403)
        self.assertEqual(hijack_resp.json()["error"]["code"], "FORBIDDEN_MEME_ASSET")

        # Verify publishing a meme post without meme_asset_id returns 422 MEME_ASSET_REQUIRED
        missing_asset = c1.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": csrf1},
            json={
                "community_slug": "corporate-memes",
                "post_type": "meme",
                "identity_mode": "pseudonymous",
                "title": "Meme post missing meme_asset_id",
                "body": "Should fail with 422.",
                "content_language": "en",
            },
        )
        self.assertEqual(missing_asset.status_code, 422)
        self.assertEqual(missing_asset.json()["error"]["code"], "MEME_ASSET_REQUIRED")

        # 7. Publish the generated meme asset anonymously to c/corporate-memes!
        pub_resp = c1.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": csrf1},
            json={
                "community_slug": "corporate-memes",
                "post_type": "meme",
                "identity_mode": "anonymous",
                "title": "When the office espresso machine gives up before we do",
                "body": "Generated in AI Meme Studio during retro.",
                "content_language": "en",
                "meme_asset_id": asset_id,
                "tags": ["coffee", "sprint-planning"],
            },
        )
        self.assertEqual(pub_resp.status_code, 201, pub_resp.text)
        post_data = pub_resp.json()
        self.assertEqual(post_data["post_type"], "meme")
        self.assertEqual(post_data["identity_mode"], "anonymous")
        self.assertEqual(post_data["author"]["display_name"], "Anonymous Member")
        self.assertIsNone(post_data["author"]["handle"])
        self.assertNotIn("author_user_id", post_data)
        self.assertEqual(post_data["meme_asset"]["id"], asset_id)
        self.assertNotIn("owner_user_id", post_data["meme_asset"])

        # Verify anonymous meme post NEVER appears on author's public profile (AC-IMP-03)
        prof_posts = self.client.get("/api/v1/profiles/job_owner_one/posts")
        self.assertEqual(prof_posts.status_code, 200)
        self.assertEqual(len(prof_posts.json()["items"]), 0)

    def test_06_worker_bounded_retry_and_expired_asset_cleanup(self) -> None:
        c, csrf = self._register_and_get_csrf("retry_tester")
        j_resp = c.post(
            "/api/v1/memes/jobs",
            headers={"X-CSRF-Token": csrf},
            json={
                "job_type": "ai_image",
                "prompt": "Testing bounded worker retry on transient 504",
                "style_tone": "sarcastic",
                "language": "en",
            },
        )
        self.assertEqual(j_resp.status_code, 202)
        jid = j_resp.json()["id"]

        renderer = TemplateRenderer()
        sample_png = renderer.render_meme(
            template_slug="friday-455pm-deploy",
            width=800,
            height=800,
            regions=[
                TextRegionSpec("top", "Top", 40, 36, 720, 160),
                TextRegionSpec("bottom", "Bottom", 40, 580, 720, 160),
            ],
            captions=[RenderCaptionInput("top", "Retry Test")],
        ).image_bytes
        flaky_adapter = FlakyImageAdapter(sample_png)

        async def _attempt_1_and_2() -> tuple[str, str, int]:
            async with self.db_manager.session_scope() as session:
                worker = MemeJobWorker(
                    session=session,
                    settings=self.settings,
                    image_adapter=flaky_adapter,
                )
                after_1 = await worker.process_single_job(jid)
                assert after_1 is not None
                status_1 = str(after_1["status"])
                after_2 = await worker.process_single_job(jid)
                assert after_2 is not None
                status_2 = str(after_2["status"])
                return status_1, status_2, int(after_2["attempt_count"])

        s1, s2, attempts = asyncio.run(_attempt_1_and_2())
        self.assertEqual(s1, "queued")   # Re-queued after 1st transient failure
        self.assertEqual(s2, "ready")    # Succeeded on 2nd attempt
        self.assertEqual(attempts, 2)

        # Verify global daily spend circuit breaker (AI_DAILY_SPEND_CAP_USD)
        low_cap_settings = Settings(
            app_env="test",
            database_url="sqlite:///:memory:",
            local_storage_path=str(self.storage_dir),
            ai_caption_provider="local_mock",
            ai_image_provider="local_mock",
            ai_daily_spend_cap_usd=0.0001,  # 100 micros cap (first caption costs 500 micros)
        )
        low_app = create_app(settings=low_cap_settings)
        lc = TestClient(low_app)
        reg = lc.post("/api/v1/auth/register", json={"handle": "spend_cap_user", "password": "ValidPass#2026!"})
        l_csrf = reg.json()["csrf_token"]
        first_cap = lc.post(
            "/api/v1/memes/captions",
            headers={"X-CSRF-Token": l_csrf},
            json={"prompt": "First request before cap trips", "tone": "sarcastic", "language": "en"},
        )
        self.assertEqual(first_cap.status_code, 200)
        second_cap = lc.post(
            "/api/v1/memes/captions",
            headers={"X-CSRF-Token": l_csrf},
            json={"prompt": "Second request after cap reached", "tone": "sarcastic", "language": "en"},
        )
        self.assertEqual(second_cap.status_code, 503)
        self.assertEqual(second_cap.json()["error"]["code"], "AI_DAILY_SPEND_CAP_REACHED")
        asyncio.run(low_app.state.db_manager.dispose())


    def test_07_storage_validation_rejects_corrupt_and_path_traversal(self) -> None:
        adapter = LocalFilesystemStorageAdapter(self.storage_dir)
        with self.assertRaises(AppError) as ctx_magic:
            adapter.validate_and_store(
                raw_bytes=b"not-an-image-at-all-1234567890",
                expected_mime_type="image/png",
                asset_id="bad-1",
            )
        self.assertEqual(ctx_magic.exception.code, "UNSUPPORTED_IMAGE_FORMAT")

        with self.assertRaises(AppError) as ctx_path:
            adapter.read_bytes("../../etc/passwd")
        self.assertEqual(ctx_path.exception.code, "INVALID_STORAGE_KEY")

    def test_08_migration_0007_upgrade_downgrade_roundtrip(self) -> None:
        conn = sqlite3.connect(":memory:")
        for fname in (
            "0002_phase3_identity_and_privacy.py",
            "0003_phase4_core_social_posting.py",
            "0004_phase5_communities.py",
            "0005_phase6_comments_engagement_notifications.py",
            "0006_phase7_feed_search_discovery.py",
            "0007_phase8_ai_meme_studio.py",
        ):
            mod = _load_migration(fname)
            mod.upgrade(conn)

        mig7 = _load_migration("0007_phase8_ai_meme_studio.py")
        mig7.downgrade(conn)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertNotIn("meme_templates", tables)
        self.assertNotIn("meme_jobs", tables)

        mig7.upgrade(conn)
        tables_after = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("meme_templates", tables_after)
        self.assertIn("meme_assets", tables_after)
        self.assertIn("meme_jobs", tables_after)
        self.assertIn("ai_provider_usage", tables_after)
        conn.close()


if __name__ == "__main__":
    unittest.main()
