"""Phase 10 Multilingual Experience, On-Demand Translation, Cache Invalidation,
RTL/Script Detection, Visibility & Privacy Isolation Test Suite.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import unittest

from fastapi.testclient import TestClient

from app.config import Settings
from app.core.rate_limit import rate_limiter
from app.database.session import _load_migration
from app.main import create_app
from app.modules.translations.matrix import detect_text_script_and_direction


class Phase10MultilingualTranslationsTests(unittest.TestCase):
    def setUp(self) -> None:
        rate_limiter.reset()
        self.settings = Settings(
            app_env="test",
            database_url="sqlite:///:memory:",
            translation_provider="local_mock",
            translation_hourly_limit=5,
        )
        self.app = create_app(settings=self.settings)
        self.db_manager = self.app.state.db_manager
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        rate_limiter.reset()
        asyncio.run(self.db_manager.dispose())

    def _register_user(self, handle: str, role: str = "member") -> tuple[TestClient, str, str]:
        rate_limiter.reset()
        c = TestClient(self.app)
        resp = c.post(
            "/api/v1/auth/register",
            json={
                "handle": handle,
                "password": "ValidPassword#2026!",
                "default_identity_mode": "pseudonymous",
                "preferred_ui_locale": "ml",
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

    def test_01_language_capabilities_and_post_comment_translation_with_cache(self) -> None:
        cap_resp = self.client.get("/api/v1/languages/capabilities")
        self.assertEqual(cap_resp.status_code, 200)
        cap_data = cap_resp.json()
        self.assertEqual(
            cap_data["supported_ui_locales"], ["en", "ml", "hi", "ta", "es"]
        )
        self.assertEqual(
            cap_data["supported_translation_targets"], ["en", "ml", "hi", "ta", "es"]
        )

        author_c, author_id, author_csrf = self._register_user("ml_author")
        reader_c, _, reader_csrf = self._register_user("en_reader")

        # Author creates a Malayalam post
        post = author_c.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": author_csrf},
            json={
                "community_slug": "workplace-rants",
                "post_type": "rant",
                "identity_mode": "anonymous",
                "title": "വെള്ളിയാഴ്ച വൈകുന്നേരം അമിത ജോലിഭാരം",
                "body": "ആഴ്ചാവസാനം വിശ്രമമില്ലാതെ പണിയെടുപ്പിക്കുന്നു.",
                "content_language": "ml",
            },
        ).json()

        # CSRF check on authenticated POST
        no_csrf = reader_c.post(
            f"/api/v1/posts/{post['id']}/translations",
            json={"target_locale": "en"},
        )
        self.assertEqual(no_csrf.status_code, 403)

        # Unsupported target locale -> 422 UNSUPPORTED_TRANSLATION_LANGUAGE
        bad_lang = reader_c.post(
            f"/api/v1/posts/{post['id']}/translations",
            headers={"X-CSRF-Token": reader_csrf},
            json={"target_locale": "de"},
        )
        self.assertEqual(bad_lang.status_code, 422)
        self.assertEqual(bad_lang.json()["error"]["code"], "UNSUPPORTED_TRANSLATION_LANGUAGE")

        # First valid translation request -> cache_hit is False
        t1 = reader_c.post(
            f"/api/v1/posts/{post['id']}/translations",
            headers={"X-CSRF-Token": reader_csrf},
            json={"target_locale": "en"},
        )
        self.assertEqual(t1.status_code, 200, t1.text)
        t1_data = t1.json()
        self.assertFalse(t1_data["cache_hit"])
        self.assertEqual(t1_data["source_language"], "ml")
        self.assertEqual(t1_data["target_locale"], "en")
        self.assertEqual(t1_data["translated_title"], "Excessive workload on Friday evening")
        self.assertEqual(
            t1_data["translated_body"],
            "Making us work through the weekend without rest.",
        )
        self.assertTrue(t1_data["is_mock_provider"])
        self.assertIn("Translated from Malayalam", t1_data["provenance_label"])

        # Privacy check: anonymous author's user_id and handle never appear in translation response
        raw_t1 = json.dumps(t1_data)
        self.assertNotIn(author_id, raw_t1)
        self.assertNotIn("ml_author", raw_t1)

        # Second identical request -> cache_hit is True and returns identical ID & hash
        t2 = reader_c.post(
            f"/api/v1/posts/{post['id']}/translations",
            headers={"X-CSRF-Token": reader_csrf},
            json={"target_locale": "en"},
        )
        self.assertEqual(t2.status_code, 200)
        self.assertTrue(t2.json()["cache_hit"])
        self.assertEqual(t2.json()["id"], t1_data["id"])
        self.assertEqual(t2.json()["source_version_hash"], t1_data["source_version_hash"])

        # Original post in GET /api/v1/posts/{id} remains 100% unmodified in Malayalam!
        orig_post = self.client.get(f"/api/v1/posts/{post['id']}").json()
        self.assertEqual(orig_post["title"], "വെള്ളിയാഴ്ച വൈകുന്നേരം അമിത ജോലിഭാരം")

        # Comment translation test
        comm = author_c.post(
            f"/api/v1/posts/{post['id']}/comments",
            headers={"X-CSRF-Token": author_csrf},
            json={
                "body": "उम्मीद: आज समय पर लॉग-ऑफ करूँगा",
                "content_language": "hi",
            },
        ).json()
        ct = reader_c.post(
            f"/api/v1/comments/{comm['id']}/translations",
            headers={"X-CSRF-Token": reader_csrf},
            json={"target_locale": "en"},
        )
        self.assertEqual(ct.status_code, 200, ct.text)
        self.assertEqual(
            ct.json()["translated_body"],
            "Expectation: I will log off on time today",
        )

    def test_02_source_edit_cache_invalidation_and_metadata_preservation(self) -> None:
        author_c, _, author_csrf = self._register_user("edit_author")
        post = author_c.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": author_csrf},
            json={
                "community_slug": "general-workplace",
                "post_type": "discussion",
                "identity_mode": "pseudonymous",
                "title": "Unpaid weekend overtime expectations",
                "body": "Original body before edit.",
                "content_language": "en",
                "tags": ["overtime"],
            },
        ).json()

        # Translate to Malayalam -> cache_hit False
        first_tr = author_c.post(
            f"/api/v1/posts/{post['id']}/translations",
            headers={"X-CSRF-Token": author_csrf},
            json={"target_locale": "ml"},
        ).json()
        self.assertFalse(first_tr["cache_hit"])
        hash_v1 = first_tr["source_version_hash"]

        # Unrelated metadata change (updating tags and upvoting) does NOT invalidate the text cache!
        author_c.patch(
            f"/api/v1/posts/{post['id']}",
            headers={"X-CSRF-Token": author_csrf},
            json={"tags": ["overtime", "burnout"]},
        )
        author_c.put(
            f"/api/v1/posts/{post['id']}/vote",
            headers={"X-CSRF-Token": author_csrf},
            json={"value": 1},
        )
        cached_tr = author_c.post(
            f"/api/v1/posts/{post['id']}/translations",
            headers={"X-CSRF-Token": author_csrf},
            json={"target_locale": "ml"},
        ).json()
        self.assertTrue(cached_tr["cache_hit"])
        self.assertEqual(cached_tr["source_version_hash"], hash_v1)

        # Editing the post body immediately invalidates the old translation and produces a new hash!
        author_c.patch(
            f"/api/v1/posts/{post['id']}",
            headers={"X-CSRF-Token": author_csrf},
            json={"body": "Updated body after team retrospective."},
        )
        after_edit_tr = author_c.post(
            f"/api/v1/posts/{post['id']}/translations",
            headers={"X-CSRF-Token": author_csrf},
            json={"target_locale": "ml"},
        ).json()
        self.assertFalse(after_edit_tr["cache_hit"])
        self.assertNotEqual(after_edit_tr["source_version_hash"], hash_v1)
        self.assertIn("Updated body after team retrospective.", after_edit_tr["translated_body"])

    def test_03_disabled_provider_and_rate_limiting(self) -> None:
        author_c, _, author_csrf = self._register_user("quota_author")
        post = author_c.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": author_csrf},
            json={
                "community_slug": "general-workplace",
                "post_type": "discussion",
                "title": "Rate limit test post",
                "body": "Testing translation rate limits.",
                "content_language": "en",
            },
        ).json()

        # Disabled provider returns 503 TRANSLATION_UNAVAILABLE without breaking original post
        disabled_settings = Settings(
            app_env="test",
            database_url="sqlite:///:memory:",
            translation_provider="disabled",
        )
        d_app = create_app(settings=disabled_settings)
        dc = TestClient(d_app)
        reg = dc.post(
            "/api/v1/auth/register",
            json={"handle": "disabled_user", "password": "ValidPassword#2026!"},
        ).json()
        d_post = dc.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": reg["csrf_token"]},
            json={
                "community_slug": "general-workplace",
                "post_type": "discussion",
                "title": "Original English Post",
                "body": "Remains available when translation is disabled.",
                "content_language": "en",
            },
        ).json()
        d_tr = dc.post(
            f"/api/v1/posts/{d_post['id']}/translations",
            headers={"X-CSRF-Token": reg["csrf_token"]},
            json={"target_locale": "es"},
        )
        self.assertEqual(d_tr.status_code, 503)
        self.assertEqual(d_tr.json()["error"]["code"], "TRANSLATION_UNAVAILABLE")
        asyncio.run(d_app.state.db_manager.dispose())

        # Rate limit enforcement (limit = 5 new translations/hour in test settings)
        for idx, lang in enumerate(["ml", "hi", "ta", "es"], start=1):
            r = author_c.post(
                f"/api/v1/posts/{post['id']}/translations",
                headers={"X-CSRF-Token": author_csrf},
                json={"target_locale": lang},
            )
            self.assertEqual(r.status_code, 200)

        # Edit post and translate 1 more time (5th provider call) -> 200
        author_c.patch(
            f"/api/v1/posts/{post['id']}",
            headers={"X-CSRF-Token": author_csrf},
            json={"body": "Edited body for 5th call."},
        )
        r5 = author_c.post(
            f"/api/v1/posts/{post['id']}/translations",
            headers={"X-CSRF-Token": author_csrf},
            json={"target_locale": "ml"},
        )
        self.assertEqual(r5.status_code, 200)

        # 6th uncached provider call exceeds hourly limit (5) -> 429 RATE_LIMITED
        r6 = author_c.post(
            f"/api/v1/posts/{post['id']}/translations",
            headers={"X-CSRF-Token": author_csrf},
            json={"target_locale": "hi"},
        )
        self.assertEqual(r6.status_code, 429)
        self.assertEqual(r6.json()["error"]["code"], "RATE_LIMITED")

    def test_04_visibility_blocks_moderation_holds_and_deleted_content(self) -> None:
        alice_c, _, alice_csrf = self._register_user("alice_trans")
        bob_c, _, bob_csrf = self._register_user("bob_trans")
        mod_c, _, mod_csrf = self._register_user("mod_trans", role="global_moderator")

        post = alice_c.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": alice_csrf},
            json={
                "community_slug": "general-workplace",
                "post_type": "discussion",
                "title": "Alice's post before block and moderation",
                "body": "Content that will be cached then restricted.",
                "content_language": "en",
            },
        ).json()

        # Bob translates Alice's post while public -> 200 OK (populates cache)
        ok_tr = bob_c.post(
            f"/api/v1/posts/{post['id']}/translations",
            headers={"X-CSRF-Token": bob_csrf},
            json={"target_locale": "es"},
        )
        self.assertEqual(ok_tr.status_code, 200)

        # Alice blocks Bob -> Bob is blocked from translating even though a cached translation exists!
        alice_c.put(
            "/api/v1/users/bob_trans/block",
            headers={"X-CSRF-Token": alice_csrf},
            json={"active": True, "mode": "block"},
        )
        blk_tr = bob_c.post(
            f"/api/v1/posts/{post['id']}/translations",
            headers={"X-CSRF-Token": bob_csrf},
            json={"target_locale": "es"},
        )
        self.assertEqual(blk_tr.status_code, 403)
        self.assertEqual(blk_tr.json()["error"]["code"], "INTERACTION_BLOCKED")

        # Alice unblocks Bob, then Moderator places post under review ('awaiting_review')
        alice_c.put(
            "/api/v1/users/bob_trans/block",
            headers={"X-CSRF-Token": alice_csrf},
            json={"active": False, "mode": "block"},
        )
        mod_c.post(
            "/api/v1/moderation/actions",
            headers={"X-CSRF-Token": mod_csrf},
            json={
                "target_type": "post",
                "target_id": post["id"],
                "action_type": "place_under_review",
                "reason_code": "doxxing_pii",
                "internal_note": "Placing under review",
                "public_explanation": "Under review",
            },
        )
        # Held post cannot be accessed via translation endpoint (410 POST_REMOVED)
        held_tr = bob_c.post(
            f"/api/v1/posts/{post['id']}/translations",
            headers={"X-CSRF-Token": bob_csrf},
            json={"target_locale": "es"},
        )
        self.assertEqual(held_tr.status_code, 410)

    def test_05_unicode_scripts_rtl_arabic_cjk_mixed_and_migration_0009_roundtrip(self) -> None:
        # Verify RTL Arabic, CJK, and Mixed script detection
        ar_lang, ar_dir, _ = detect_text_script_and_direction(
            "بيئة العمل تحتاج إلى توازن حقيقي", "ar"
        )
        self.assertEqual(ar_lang, "ar")
        self.assertEqual(ar_dir, "rtl")

        mul_lang, mul_dir, mul_uncertain = detect_text_script_and_direction(
            "Meeting കഴിഞ്ഞ് deploy ചെയ്യാം", "mul"
        )
        self.assertEqual(mul_dir, "ltr")
        self.assertTrue(mul_uncertain)

        c, _, csrf = self._register_user("polyglot_worker")
        mul_post = c.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": csrf},
            json={
                "community_slug": "general-workplace",
                "post_type": "discussion",
                "title": "Manglish + Arabic + CJK: ജോലി ضغط العمل 职场压力 🚀",
                "body": "Mixing scripts in one workplace post without losing any characters.",
                "content_language": "mul",
            },
        ).json()

        tr_mul = c.post(
            f"/api/v1/posts/{mul_post['id']}/translations",
            headers={"X-CSRF-Token": csrf},
            json={"target_locale": "en"},
        ).json()
        self.assertTrue(tr_mul["is_source_language_uncertain"])
        self.assertIn("Mixed / Undetermined Language", tr_mul["provenance_label"])

        # Verify migration 0009 upgrade/downgrade round-trip
        conn = sqlite3.connect(":memory:")
        for fname in (
            "0002_phase3_identity_and_privacy.py",
            "0003_phase4_core_social_posting.py",
            "0004_phase5_communities.py",
            "0005_phase6_comments_engagement_notifications.py",
            "0006_phase7_feed_search_discovery.py",
            "0007_phase8_ai_meme_studio.py",
            "0008_phase9_trust_safety_moderation.py",
            "0009_phase10_multilingual_translations.py",
        ):
            _load_migration(fname).upgrade(conn)

        mig9 = _load_migration("0009_phase10_multilingual_translations.py")
        mig9.downgrade(conn)
        tables_down = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        self.assertNotIn("content_translations", tables_down)

        mig9.upgrade(conn)
        tables_up = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        self.assertIn("content_translations", tables_up)
        conn.close()


if __name__ == "__main__":
    unittest.main()
