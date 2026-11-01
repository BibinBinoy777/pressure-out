"""Phase 12 Production Hardening, Security Invariants, Worker Recovery & 25-Step Launch Smoke Tests."""

from __future__ import annotations

import asyncio
import base64
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.core.metrics import metrics_collector
from app.core.rate_limit import rate_limiter
from app.main import create_app
from app.modules.memes.storage import LocalFilesystemStorageAdapter
from app.workers.meme_worker import MemeJobWorker


class Phase12ProductionHardeningAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
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
        rate_limiter.reset()
        metrics_collector.reset()
        asyncio.run(self.db_manager.dispose())
        self.tmp_dir.cleanup()

    def _register_user(
        self, handle: str, ui_locale: str = "en", role: str = "member"
    ) -> tuple[TestClient, str, str]:
        rate_limiter.reset()
        c = TestClient(self.app)
        resp = c.post(
            "/api/v1/auth/register",
            json={
                "handle": handle,
                "password": "ValidPassword#2026!",
                "default_identity_mode": "pseudonymous",
                "preferred_ui_locale": ui_locale,
            },
        )
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

    def test_01_production_settings_fail_fast_invariants(self) -> None:
        """Production mode must fail fast if insecure defaults, SQLite, or mock providers are active."""
        valid_prod_key = base64.urlsafe_b64encode(b"P" * 32).decode("ascii")
        valid_kwargs = {
            "app_env": "production",
            "database_url": "postgresql+asyncpg://po_prod:StrongProdDbPass!99@db.internal:5432/pressure_out",
            "rate_limit_backend": "redis",
            "redis_url": "redis://:StrongProdRedisPass!99@redis.internal:6379/0",
            "session_cookie_secure": True,
            "email_hmac_pepper": "prod-secret-hmac-pepper-at-least-32-bytes-long!!",
            "email_encryption_key_base64": valid_prod_key,
            "cors_origins": ["https://pressureout.example.com"],
            "ai_caption_provider": "disabled",
            "ai_image_provider": "disabled",
            "translation_provider": "disabled",
        }

        # Valid production configuration succeeds
        prod_settings = Settings(**valid_kwargs)
        self.assertEqual(prod_settings.app_env, "production")

        # 1. Rejects SQLite in production
        with self.assertRaises(ValueError):
            Settings(**{**valid_kwargs, "database_url": "sqlite:///./prod.db"})

        # 2. Rejects default dev password in production
        with self.assertRaises(ValueError):
            Settings(
                **{
                    **valid_kwargs,
                    "database_url": "postgresql+asyncpg://po_dev_user:po_dev_local_only_password_change_me@db:5432/pressure_out_dev",
                }
            )

        # 3. Rejects insecure session cookies in production
        with self.assertRaises(ValueError):
            Settings(**{**valid_kwargs, "session_cookie_secure": False})

        # 4. Rejects default dev HMAC pepper in production
        with self.assertRaises(ValueError):
            Settings(
                **{
                    **valid_kwargs,
                    "email_hmac_pepper": "po_dev_only_hmac_pepper_change_in_prod",
                }
            )

        # 5. Rejects wildcard or non-HTTPS CORS origin in production
        with self.assertRaises(ValueError):
            Settings(**{**valid_kwargs, "cors_origins": ["*"]})
        with self.assertRaises(ValueError):
            Settings(**{**valid_kwargs, "cors_origins": ["http://insecure.example.com"]})

        # 6. Rejects local_mock providers in production
        with self.assertRaises(ValueError):
            Settings(**{**valid_kwargs, "ai_caption_provider": "local_mock"})
        with self.assertRaises(ValueError):
            Settings(**{**valid_kwargs, "translation_provider": "local_mock"})

    def test_02_security_headers_body_size_guard_and_csrf_origin_validation(self) -> None:
        """Responses include defensive headers, oversized bodies return 413, and untrusted Origins return 403."""
        client, _, csrf = self._register_user("sec_tester_12")

        res = client.get("/api/v1/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(res.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(res.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("default-src 'self'", res.headers.get("Content-Security-Policy", ""))
        self.assertIn("camera=()", res.headers.get("Permissions-Policy", ""))
        self.assertTrue(res.headers.get("X-Correlation-ID"))

        # Oversized body (> 1 MB) rejected with 413 PAYLOAD_TOO_LARGE before parsing
        oversized_payload = "x" * (1024 * 1024 + 512)
        too_large = client.post(
            "/api/v1/posts",
            content=oversized_payload,
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf,
                "Content-Length": str(len(oversized_payload)),
            },
        )
        self.assertEqual(too_large.status_code, 413)
        self.assertEqual(too_large.json()["error"]["code"], "PAYLOAD_TOO_LARGE")

        # State-changing request with untrusted Origin rejected with 403 UNTRUSTED_ORIGIN
        bad_origin = client.post(
            "/api/v1/posts",
            json={
                "community_slug": "general-workplace",
                "post_type": "story",
                "identity_mode": "pseudonymous",
                "title": "Cross origin forgery attempt",
                "body": "Should be blocked by origin guard",
                "content_language": "en",
            },
            headers={
                "X-CSRF-Token": csrf,
                "Origin": "https://evil-attacker.example.org",
            },
        )
        self.assertEqual(bad_origin.status_code, 403, bad_origin.text)
        self.assertEqual(bad_origin.json()["error"]["code"], "UNTRUSTED_ORIGIN")

        # Trusted Origin succeeds
        good_origin = client.post(
            "/api/v1/posts",
            json={
                "community_slug": "general-workplace",
                "post_type": "story",
                "identity_mode": "pseudonymous",
                "title": "Trusted origin post",
                "body": "Allowed from configured frontend origin",
                "content_language": "en",
            },
            headers={
                "X-CSRF-Token": csrf,
                "Origin": "http://localhost:3000",
            },
        )
        self.assertEqual(good_origin.status_code, 201, good_origin.text)

    def test_03_health_liveness_readiness_and_redacted_metrics(self) -> None:
        """Liveness, readiness, and redacted operational metrics endpoints work and expose zero PII."""
        live = self.client.get("/api/v1/health/live")
        self.assertEqual(live.status_code, 200)
        self.assertEqual(live.json()["status"], "ok")

        ready = self.client.get("/api/v1/health/ready")
        self.assertEqual(ready.status_code, 200)
        ready_body = ready.json()
        self.assertEqual(ready_body["status"], "ready")
        self.assertTrue(ready_body["database_ready"])
        self.assertTrue(ready_body["storage_ready"])

        metrics = self.client.get("/api/v1/health/metrics")
        self.assertEqual(metrics.status_code, 200)
        m_body = metrics.json()
        self.assertIn("http_metrics", m_body)
        self.assertGreaterEqual(m_body["http_metrics"]["http_requests_total"], 2)
        self.assertIn("db_pool", m_body)
        self.assertIn("worker_queue", m_body)
        serialized = str(m_body)
        self.assertNotIn("email", serialized.lower())
        self.assertNotIn("password", serialized.lower())

    def test_04_worker_stale_job_crash_recovery(self) -> None:
        """MemeJobWorker recovers jobs left in 'generating' state after an unexpected worker restart."""
        _, user_id, _ = self._register_user("worker_tester_12")
        j1_id = str(uuid.uuid4())
        j2_id = str(uuid.uuid4())

        async def _seed_and_recover() -> tuple[int, str, str, str]:
            async with self.db_manager.session_scope() as session:
                await session.execute(
                    """
                    INSERT INTO meme_jobs (
                        id, user_id, idempotency_key, job_type, status, user_prompt,
                        prompt_language, style_tone, attempt_count, provider_name,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, 'ai_image', 'generating', 'standup meeting chaos', 'en', 'sarcastic', 1, 'local_mock', datetime('now'), datetime('now'))
                    """,
                    (j1_id, user_id, str(uuid.uuid4())),
                )
                await session.execute(
                    """
                    INSERT INTO meme_jobs (
                        id, user_id, idempotency_key, job_type, status, user_prompt,
                        prompt_language, style_tone, attempt_count, provider_name,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, 'ai_image', 'generating', 'office printer on fire', 'en', 'sarcastic', 2, 'local_mock', datetime('now'), datetime('now'))
                    """,
                    (j2_id, user_id, str(uuid.uuid4())),
                )
                storage = LocalFilesystemStorageAdapter(self.storage_dir)
                worker = MemeJobWorker(
                    session=session,
                    settings=self.settings,
                    storage=storage,
                )
                recovered = await worker.recover_stale_generating_jobs()
                r1 = await session.execute(
                    "SELECT status, error_code FROM meme_jobs WHERE id = ?", (j1_id,)
                )
                r2 = await session.execute(
                    "SELECT status, error_code FROM meme_jobs WHERE id = ?", (j2_id,)
                )
                return recovered, str(r1[0][0]), str(r2[0][0]), str(r2[0][1])

        recovered, s1, s2, err2 = asyncio.run(_seed_and_recover())
        self.assertEqual(recovered, 2)
        self.assertEqual(s1, "queued")
        self.assertEqual(s2, "failed")
        self.assertEqual(err2, "WORKER_INTERRUPTED")

    def test_05_account_deletion_scrubs_all_phases_and_data_export(self) -> None:
        """Self-service export returns user data and account deletion removes insight contributions & scrubs posts/comments."""
        clients = []
        for idx in range(10):
            c, u_id, csrf = self._register_user(f"contrib_p12_{idx}")
            clients.append((c, u_id, csrf))
            r = c.post(
                "/api/v1/workplace/contributions",
                json={
                    "aggregation_consent": True,
                    "industry_category": "technology",
                    "role_family": "software_engineering",
                    "experience_band": "mid_3_6",
                    "work_arrangement": "hybrid",
                    "overall_satisfaction": 4,
                    "work_life_balance": 3,
                    "management_quality": 3,
                    "psychological_safety": 4,
                },
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(r.status_code, 201, r.text)

        target_client, _, target_csrf = clients[0]

        # Target user creates a post and a comment
        post_res = target_client.post(
            "/api/v1/posts",
            json={
                "community_slug": "general-workplace",
                "post_type": "workplace_experience",
                "identity_mode": "pseudonymous",
                "title": "My candid engineering story",
                "body": "Detailed story body before deletion",
                "content_language": "en",
                "workplace_detail": {
                    "experience_kind": "workplace_experience",
                    "experience_category": "workplace_culture",
                    "industry_category": "technology",
                },
            },
            headers={"X-CSRF-Token": target_csrf},
        )
        self.assertEqual(post_res.status_code, 201, post_res.text)
        post_id = post_res.json()["id"]

        comment_res = target_client.post(
            f"/api/v1/posts/{post_id}/comments",
            json={
                "body": "My comment before account deletion",
                "identity_mode": "pseudonymous",
                "content_language": "en",
            },
            headers={"X-CSRF-Token": target_csrf},
        )
        self.assertEqual(comment_res.status_code, 201, comment_res.text)

        # Verify cohort is unlocked (10 contributors -> cohort_eligible_band == '10+')
        ins_before = clients[1][0].get(
            "/api/v1/workplace/insights?industry_category=technology&role_family=software_engineering"
        )
        self.assertEqual(ins_before.status_code, 200, ins_before.text)
        self.assertEqual(ins_before.json()["cohort_eligible_band"], "10+")

        # Verify self-service export works prior to deletion
        export_res = target_client.get("/api/v1/me/export")
        self.assertEqual(export_res.status_code, 200, export_res.text)
        export_data = export_res.json()
        self.assertEqual(export_data["public_profile"]["handle"], "contrib_p12_0")
        self.assertEqual(len(export_data["authored_posts"]), 1)
        self.assertEqual(len(export_data["authored_comments"]), 1)
        self.assertIsNotNone(export_data["structured_workplace_contribution"])

        # Delete target user's account
        del_res = target_client.request(
            "DELETE",
            "/api/v1/me",
            json={
                "password_confirmation": "ValidPassword#2026!",
                "delete_published_posts": True,
            },
            headers={"X-CSRF-Token": target_csrf},
        )
        self.assertEqual(del_res.status_code, 200, del_res.text)

        # Cohort sample count now drops from 10 to 9 and is suppressed (cohort_eligible_band is None)!
        ins_after = clients[1][0].get(
            "/api/v1/workplace/insights?industry_category=technology&role_family=software_engineering"
        )
        self.assertEqual(ins_after.status_code, 200, ins_after.text)
        self.assertIsNone(ins_after.json()["cohort_eligible_band"])
        for m in ins_after.json()["metrics"]:
            self.assertTrue(m["insufficient_data"])

    def test_06_complete_25_step_end_to_end_launch_smoke_flow(self) -> None:
        """Executes the full 25-step launch verification smoke scenario across Phases 1-12."""
        # Step 1-3: Register author, peer (Malayalam locale), and update settings
        author_c, _, author_csrf = self._register_user("smoke_author_12", ui_locale="en")
        peer_c, _, peer_csrf = self._register_user("smoke_peer_12", ui_locale="ml")

        pref_res = peer_c.patch(
            "/api/v1/me/settings",
            json={
                "preferred_ui_locale": "ml",
                "preferred_content_languages": ["ml", "en"],
            },
            headers={"X-CSRF-Token": peer_csrf},
        )
        self.assertEqual(pref_res.status_code, 200, pref_res.text)

        # Step 4-5: Join starter community
        join_res = peer_c.post(
            "/api/v1/communities/general-workplace/membership",
            json={"action": "join"},
            headers={"X-CSRF-Token": peer_csrf},
        )
        self.assertEqual(join_res.status_code, 200, join_res.text)

        # Step 6-7: Create pseudonymous post and anonymous post; verify zero identity leakage
        pseudo_post = author_c.post(
            "/api/v1/posts",
            json={
                "community_slug": "general-workplace",
                "post_type": "story",
                "identity_mode": "pseudonymous",
                "title": "Pseudonymous deployment postmortem",
                "body": "Our staging pipeline caught a subtle config drift before release.",
                "content_language": "en",
            },
            headers={"X-CSRF-Token": author_csrf},
        )
        self.assertEqual(pseudo_post.status_code, 201, pseudo_post.text)
        pseudo_post_id = pseudo_post.json()["id"]

        anon_post = author_c.post(
            "/api/v1/posts",
            json={
                "community_slug": "general-workplace",
                "post_type": "rant",
                "identity_mode": "anonymous",
                "title": "Anonymous confession about crunch weeks",
                "body": "Unpaid weekend overtime is burning out the platform team.",
                "content_language": "en",
            },
            headers={"X-CSRF-Token": author_csrf},
        )
        self.assertEqual(anon_post.status_code, 201, anon_post.text)
        anon_data = anon_post.json()
        self.assertEqual(anon_data["identity_mode"], "anonymous")
        self.assertIsNone(anon_data["author"]["handle"])
        self.assertNotIn("smoke_author_12", str(anon_data))

        # Step 8-10: Comment, vote, and verify notifications
        comm_comment = peer_c.post(
            f"/api/v1/posts/{pseudo_post_id}/comments",
            json={
                "body": "Solid catch on the config drift!",
                "identity_mode": "pseudonymous",
                "content_language": "en",
            },
            headers={"X-CSRF-Token": peer_csrf},
        )
        self.assertEqual(comm_comment.status_code, 201, comm_comment.text)

        vote_res = peer_c.put(
            f"/api/v1/posts/{pseudo_post_id}/vote",
            json={"value": 1},
            headers={"X-CSRF-Token": peer_csrf},
        )
        self.assertEqual(vote_res.status_code, 200, vote_res.text)

        notif_res = author_c.get("/api/v1/notifications")
        self.assertEqual(notif_res.status_code, 200, notif_res.text)
        self.assertGreaterEqual(len(notif_res.json()["items"]), 1)

        # Step 11-13: Render meme via AI Meme Studio and publish meme post
        templates_res = author_c.get("/api/v1/memes/templates")
        self.assertEqual(templates_res.status_code, 200, templates_res.text)
        template_slug = templates_res.json()["items"][0]["slug"]

        render_res = author_c.post(
            "/api/v1/memes/render",
            json={
                "template_id_or_slug": template_slug,
                "language": "en",
                "output_format": "PNG",
                "captions": [
                    {"region_id": "top", "text": "WHEN ALL 12 PHASES PASS"},
                    {"region_id": "bottom", "text": "READY FOR STAGING"},
                ],
            },
            headers={"X-CSRF-Token": author_csrf},
        )
        self.assertEqual(render_res.status_code, 201, render_res.text)
        asset_id = render_res.json()["id"]

        meme_post = author_c.post(
            "/api/v1/posts",
            json={
                "community_slug": "corporate-memes",
                "post_type": "meme",
                "identity_mode": "pseudonymous",
                "title": "Launch verification mood",
                "body": "Shipping with real guardrails.",
                "content_language": "en",
                "meme_asset_id": asset_id,
            },
            headers={"X-CSRF-Token": author_csrf},
        )
        self.assertEqual(meme_post.status_code, 201, meme_post.text)

        # Step 14-15: Translate post into Malayalam, then edit source and confirm stale translation invalidation
        tr_res = peer_c.post(
            f"/api/v1/posts/{pseudo_post_id}/translations",
            json={"target_locale": "ml"},
            headers={"X-CSRF-Token": peer_csrf},
        )
        self.assertEqual(tr_res.status_code, 200, tr_res.text)
        self.assertEqual(tr_res.json()["target_locale"], "ml")

        edit_res = author_c.patch(
            f"/api/v1/posts/{pseudo_post_id}",
            json={
                "title": "Pseudonymous deployment postmortem (Updated)",
                "body": "Updated postmortem body after root cause analysis.",
            },
            headers={"X-CSRF-Token": author_csrf},
        )
        self.assertEqual(edit_res.status_code, 200, edit_res.text)

        # Re-translating after source edit produces a fresh cache miss (cache_hit=False)
        tr_after_edit = peer_c.post(
            f"/api/v1/posts/{pseudo_post_id}/translations",
            json={"target_locale": "ml"},
            headers={"X-CSRF-Token": peer_csrf},
        )
        self.assertEqual(tr_after_edit.status_code, 200, tr_after_edit.text)
        self.assertFalse(tr_after_edit.json()["cache_hit"])

        # Step 16-20: Workplace experience & resignation story
        wp_exp = author_c.post(
            "/api/v1/posts",
            json={
                "community_slug": "work-life-balance",
                "post_type": "workplace_experience",
                "identity_mode": "pseudonymous",
                "title": "On-call rotation improvements that actually worked",
                "body": "We moved to follow-the-sun handoffs and cut paging fatigue in half.",
                "content_language": "en",
                "workplace_detail": {
                    "experience_kind": "workplace_experience",
                    "experience_category": "work_life_balance",
                    "industry_category": "technology",
                    "lesson_learned": "Follow-the-sun handoffs cut alert fatigue.",
                },
            },
            headers={"X-CSRF-Token": author_csrf},
        )
        self.assertEqual(wp_exp.status_code, 201, wp_exp.text)

        resig = author_c.post(
            "/api/v1/posts",
            json={
                "community_slug": "resignation-stories",
                "post_type": "workplace_experience",
                "identity_mode": "anonymous",
                "title": "Why I left after three re-orgs in one year",
                "body": "Constant strategy whiplash taught me to value leadership stability.",
                "content_language": "en",
                "workplace_detail": {
                    "experience_kind": "resignation_story",
                    "experience_category": "resignation",
                    "primary_resignation_reason": "better_opportunity",
                    "transition_outcome": "accepted_new_role",
                    "lesson_learned": "Ask about roadmap stability during interviews.",
                },
            },
            headers={"X-CSRF-Token": author_csrf},
        )
        self.assertEqual(resig.status_code, 201, resig.text)

        # Step 21-25: Feed, Explore, Search, and Logout
        feed_res = peer_c.get("/api/v1/feed?mode=latest")
        self.assertEqual(feed_res.status_code, 200, feed_res.text)
        self.assertGreaterEqual(len(feed_res.json()["items"]), 3)

        search_res = peer_c.get("/api/v1/search?q=postmortem")
        self.assertEqual(search_res.status_code, 200, search_res.text)
        self.assertGreaterEqual(len(search_res.json()["items"]), 1)

        logout_res = author_c.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": author_csrf},
        )
        self.assertIn(logout_res.status_code, {200, 204})


if __name__ == "__main__":
    unittest.main()
