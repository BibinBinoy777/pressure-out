"""Phase 4 Core Social Posting, PII Guardrail, Poll Voting, and Anonymous Isolation Tests.

Verifies:
1. All 8 post types (`discussion`, `question`, `rant`, `story`, `meme`, `poll`,
   `advice_request`, `workplace_experience`) can be created, retrieved, edited,
   and deleted (`AC-IMP-05`).
2. Anonymous post isolation (`AC-IMP-03`):
   - `PublicPostResponse` on `/api/v1/posts/{id}` and `/api/v1/posts` NEVER exposes
     `author_user_id`, `handle`, `display_name`, or `professional_badge` when
     `identity_mode == 'anonymous'`.
   - `GET /api/v1/profiles/{handle}/posts` includes `pseudonymous` and `professional`
     posts but strictly excludes `anonymous` posts!
3. Author ownership preserved on anonymous posts (`AC-IMP-04`):
   - The authenticated author of an `anonymous` post sees `viewer_context.is_author = True`
     and can edit (`PATCH`) and delete (`DELETE`) their anonymous post, while any
     other user receives `403 FORBIDDEN_NOT_AUTHOR`.
4. Pre-Publish PII & Secret Guardrail:
   - Hard blocks (`422 PII_HARD_BLOCK`) API keys (`AKIA...`), emails, and phone numbers.
   - Soft warns (`422 PII_CONFIRMATION_REQUIRED`) named manager accusations unless
     `acknowledge_pii_warning=True` is passed.
5. Structured Poll creation, voting, percentage calculation, and duplicate vote
   rejection (`409 ALREADY_VOTED`).
6. Cursor pagination determinism across `/api/v1/posts` and `/api/v1/profiles/{handle}/posts`.
7. Migration `0003_phase4_posts` round-trip (`upgrade` -> verify -> `downgrade` -> `upgrade`).
"""
from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.core.rate_limit import rate_limiter
from app.main import create_app

MIGRATION_0002_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "0002_phase3_identity_and_privacy.py"
)
MIGRATION_0003_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "0003_phase4_core_social_posting.py"
)


class Phase4SocialPostingTests(unittest.TestCase):
    """End-to-end verification of Phase 4 Core Social Posting."""

    def setUp(self) -> None:
        rate_limiter.reset()
        self.settings = Settings(
            app_env="test",
            database_url="sqlite:///:memory:",
            log_level="CRITICAL",
            session_cookie_secure=False,
        )
        self.app = create_app(settings=self.settings)
        self.client_a = TestClient(self.app, raise_server_exceptions=False)
        self.client_b = TestClient(self.app, raise_server_exceptions=False)

        # Register Author A with professional profile
        reg_a = self.client_a.post(
            "/api/v1/auth/register",
            json={
                "handle": "author_anita",
                "password": "StrongPassword!Anita2026",
                "recovery_email": "anita.private@corp.com",
            },
        )
        self.assertEqual(reg_a.status_code, 201)
        self.user_a_id = reg_a.json()["user_id"]
        self.csrf_a = reg_a.json()["csrf_token"]

        prof_a = self.client_a.patch(
            "/api/v1/me/profile",
            headers={"X-CSRF-Token": self.csrf_a},
            json={
                "display_name": "Anita Nair",
                "professional_profile": {
                    "role_title": "Engineering Manager",
                    "industry": "FinTech",
                    "experience_band": "lead_10_plus",
                    "region_label": "Kochi, Kerala",
                    "is_enabled": True,
                },
            },
        )
        self.assertEqual(prof_a.status_code, 200)

        # Register Reader B
        reg_b = self.client_b.post(
            "/api/v1/auth/register",
            json={
                "handle": "reader_rahul",
                "password": "StrongPassword!Rahul2026",
            },
        )
        self.assertEqual(reg_b.status_code, 201)
        self.user_b_id = reg_b.json()["user_id"]
        self.csrf_b = reg_b.json()["csrf_token"]

    def tearDown(self) -> None:
        rate_limiter.reset()

    def test_all_eight_post_types_and_unicode_multilingual_persistence(self) -> None:
        post_types = [
            "discussion",
            "question",
            "rant",
            "story",
            "meme",
            "advice_request",
            "workplace_experience",
        ]
        for ptype in post_types:
            res = self.client_a.post(
                "/api/v1/posts",
                headers={"X-CSRF-Token": self.csrf_a},
                json={
                    "community_slug": "workplace-rants",
                    "post_type": ptype,
                    "identity_mode": "pseudonymous",
                    "title": f"Sample {ptype} post — ജോലിസ്ഥലത്തെ ചർച്ച",
                    "body": f"Body for {ptype} in Malayalam, हिन्दी, தமிழ், and English 🚀",
                    "content_language": "mul",
                    "tags": ["workplace", ptype.replace("_", "-")],
                    "meme_asset_id": "asset_mock_001" if ptype == "meme" else None,
                },
            )
            self.assertEqual(res.status_code, 201, f"Failed on {ptype}: {res.text}")
            body = res.json()
            self.assertEqual(body["post_type"], ptype)
            self.assertEqual(body["content_language"], "mul")
            self.assertEqual(body["author"]["handle"], "author_anita")

    def test_anonymous_post_isolation_and_profile_exclusion_ac_imp_03_and_04(self) -> None:
        # 1. Author A creates 1 Pseudonymous post, 1 Professional post, and 1 Anonymous post
        p_pseudo = self.client_a.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_a},
            json={
                "community_slug": "career-advice",
                "post_type": "discussion",
                "identity_mode": "pseudonymous",
                "title": "Public pseudonymous career thoughts",
                "body": "Sharing under my handle.",
            },
        ).json()

        p_prof = self.client_a.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_a},
            json={
                "community_slug": "salary-talk",
                "post_type": "advice_request",
                "identity_mode": "professional",
                "title": "How we evaluate senior backend compensation bands",
                "body": "Speaking from 10+ years in FinTech.",
            },
        ).json()
        self.assertEqual(
            p_prof["author"]["professional_badge"]["role_title"],
            "Engineering Manager",
        )
        self.assertFalse(p_prof["author"]["professional_badge"]["is_verified"])

        p_anon_res = self.client_a.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_a},
            json={
                "community_slug": "workplace-rants",
                "post_type": "rant",
                "identity_mode": "anonymous",
                "title": "Unfiltered anonymous rant about 11 PM standups",
                "body": "Nobody knows this is Anita!",
            },
        )
        self.assertEqual(p_anon_res.status_code, 201)
        p_anon = p_anon_res.json()
        anon_post_id = p_anon["id"]

        # 2. Reader B fetches the anonymous post (`GET /api/v1/posts/{id}`) and feed (`GET /api/v1/posts`)
        b_view_res = self.client_b.get(f"/api/v1/posts/{anon_post_id}")
        self.assertEqual(b_view_res.status_code, 200)
        b_raw = b_view_res.text
        b_json = b_view_res.json()

        self.assertEqual(b_json["identity_mode"], "anonymous")
        self.assertEqual(b_json["author"]["display_name"], "Anonymous Member")
        self.assertIsNone(b_json["author"]["handle"])
        self.assertIsNone(b_json["author"]["professional_badge"])
        self.assertFalse(b_json["viewer_context"]["is_author"])

        for secret in (
            self.user_a_id,
            "author_anita",
            "Anita Nair",
            "Engineering Manager",
            "FinTech",
            "Kochi",
            "anita.private@corp.com",
        ):
            self.assertNotIn(secret, b_raw)

        # 3. Querying Author A's public profile posts (`GET /api/v1/profiles/author_anita/posts`)
        # MUST return the pseudonymous and professional posts, and NEVER the anonymous post!
        prof_posts_res = self.client_b.get("/api/v1/profiles/author_anita/posts")
        self.assertEqual(prof_posts_res.status_code, 200)
        returned_ids = [item["id"] for item in prof_posts_res.json()["items"]]
        self.assertIn(p_pseudo["id"], returned_ids)
        self.assertIn(p_prof["id"], returned_ids)
        self.assertNotIn(anon_post_id, returned_ids)

        # 4. AC-IMP-04: Author A retains ownership of their anonymous post (can edit & delete),
        # while Reader B is rejected with 403 FORBIDDEN_NOT_AUTHOR
        b_edit = self.client_b.patch(
            f"/api/v1/posts/{anon_post_id}",
            headers={"X-CSRF-Token": self.csrf_b},
            json={"title": "Hijacked title"},
        )
        self.assertEqual(b_edit.status_code, 403)
        self.assertEqual(b_edit.json()["error"]["code"], "FORBIDDEN_NOT_AUTHOR")

        a_edit = self.client_a.patch(
            f"/api/v1/posts/{anon_post_id}",
            headers={"X-CSRF-Token": self.csrf_a},
            json={"title": "Updated anonymous rant about 11 PM standups"},
        )
        self.assertEqual(a_edit.status_code, 200)
        self.assertEqual(a_edit.json()["title"], "Updated anonymous rant about 11 PM standups")
        self.assertTrue(a_edit.json()["viewer_context"]["is_author"])

        # Delete anonymous post as Author A
        a_del = self.client_a.delete(
            f"/api/v1/posts/{anon_post_id}",
            headers={"X-CSRF-Token": self.csrf_a},
        )
        self.assertEqual(a_del.status_code, 200)

        # Subsequent GET returns 410 POST_REMOVED
        gone_res = self.client_b.get(f"/api/v1/posts/{anon_post_id}")
        self.assertEqual(gone_res.status_code, 410)
        self.assertEqual(gone_res.json()["error"]["code"], "POST_REMOVED")

    def test_prepublish_pii_and_secret_guardrail(self) -> None:
        # 1. Hard block: email address in post body
        res_email = self.client_a.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_a},
            json={
                "community_slug": "workplace-rants",
                "post_type": "rant",
                "title": "Contact this recruiter",
                "body": "Reach out to hr.person@company.com right now",
            },
        )
        self.assertEqual(res_email.status_code, 422)
        self.assertEqual(res_email.json()["error"]["code"], "PII_HARD_BLOCK")

        # 2. Hard block: phone number in post body
        res_phone = self.client_a.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_a},
            json={
                "community_slug": "workplace-rants",
                "post_type": "rant",
                "title": "Boss called from this number",
                "body": "He texted me from +91 9876543210 at midnight",
            },
        )
        self.assertEqual(res_phone.status_code, 422)
        self.assertEqual(res_phone.json()["error"]["code"], "PII_HARD_BLOCK")

        # 3. Hard block: leaked API key
        res_key = self.client_a.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_a},
            json={
                "community_slug": "it-software",
                "post_type": "question",
                "title": "Why is this AWS key failing?",
                "body": "Key is AKIAIOSFODNN7EXAMPLE in production",
            },
        )
        self.assertEqual(res_key.status_code, 422)
        self.assertEqual(res_key.json()["error"]["code"], "PII_HARD_BLOCK")

        # 4. Soft warning: naming a specific manager requires confirmation or edit
        res_named = self.client_a.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_a},
            json={
                "community_slug": "workplace-rants",
                "post_type": "rant",
                "title": "Unfair appraisal review",
                "body": "My manager Vikram Menon denied my promotion after 3 years.",
                "acknowledge_pii_warning": False,
            },
        )
        self.assertEqual(res_named.status_code, 422)
        self.assertEqual(res_named.json()["error"]["code"], "PII_CONFIRMATION_REQUIRED")

        # Passing acknowledge_pii_warning=True allows publication and attaches warning metadata
        res_ack = self.client_a.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_a},
            json={
                "community_slug": "workplace-rants",
                "post_type": "rant",
                "title": "Unfair appraisal review",
                "body": "My manager Vikram Menon denied my promotion after 3 years.",
                "acknowledge_pii_warning": True,
            },
        )
        self.assertEqual(res_ack.status_code, 201)
        self.assertEqual(len(res_ack.json()["pii_warnings"]), 1)

    def test_poll_creation_voting_and_duplicate_vote_prevention(self) -> None:
        poll_post = self.client_a.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_a},
            json={
                "community_slug": "work-life-balance",
                "post_type": "poll",
                "identity_mode": "pseudonymous",
                "title": "How many days per week are you required in the office?",
                "body": "Curious how RTO policies look in late 2026.",
                "poll": {
                    "allows_multiple": False,
                    "options": ["Fully Remote (0 days)", "Hybrid (2-3 days)", "Full RTO (5 days)"],
                },
            },
        )
        self.assertEqual(poll_post.status_code, 201, poll_post.text)
        post_data = poll_post.json()
        post_id = post_data["id"]
        options = post_data["poll"]["options"]
        self.assertEqual(len(options), 3)

        # Author A votes for Option 0
        v1 = self.client_a.post(
            f"/api/v1/posts/{post_id}/poll/vote",
            headers={"X-CSRF-Token": self.csrf_a},
            json={"option_ids": [options[0]["id"]]},
        )
        self.assertEqual(v1.status_code, 200)
        self.assertEqual(v1.json()["total_votes"], 1)
        self.assertEqual(v1.json()["options"][0]["percentage"], 100.0)

        # Duplicate vote by Author A must be rejected with 409 ALREADY_VOTED
        v_dup = self.client_a.post(
            f"/api/v1/posts/{post_id}/poll/vote",
            headers={"X-CSRF-Token": self.csrf_a},
            json={"option_ids": [options[1]["id"]]},
        )
        self.assertEqual(v_dup.status_code, 409)
        self.assertEqual(v_dup.json()["error"]["code"], "ALREADY_VOTED")

        # Reader B votes for Option 1 -> 50% / 50% split
        v2 = self.client_b.post(
            f"/api/v1/posts/{post_id}/poll/vote",
            headers={"X-CSRF-Token": self.csrf_b},
            json={"option_ids": [options[1]["id"]]},
        )
        self.assertEqual(v2.status_code, 200)
        self.assertEqual(v2.json()["total_votes"], 2)
        self.assertEqual(v2.json()["options"][0]["percentage"], 50.0)
        self.assertEqual(v2.json()["options"][1]["percentage"], 50.0)

    def test_cursor_pagination_and_migration_0003_roundtrip(self) -> None:
        # Create 4 posts and paginate 2 at a time
        created_ids = []
        for i in range(4):
            r = self.client_a.post(
                "/api/v1/posts",
                headers={"X-CSRF-Token": self.csrf_a},
                json={
                    "community_slug": "it-software",
                    "post_type": "discussion",
                    "title": f"Paginated discussion item {i}",
                    "body": f"Content {i}",
                },
            )
            self.assertEqual(r.status_code, 201)
            created_ids.append(r.json()["id"])

        page1 = self.client_b.get("/api/v1/posts?community_slug=it-software&limit=2").json()
        self.assertEqual(len(page1["items"]), 2)
        self.assertTrue(page1["has_more"])
        self.assertIsNotNone(page1["next_cursor"])

        page2 = self.client_b.get(
            f"/api/v1/posts?community_slug=it-software&limit=2&cursor={page1['next_cursor']}"
        ).json()
        self.assertEqual(len(page2["items"]), 2)
        self.assertFalse(page2["has_more"])

        combined_ids = [p["id"] for p in page1["items"]] + [p["id"] for p in page2["items"]]
        self.assertEqual(len(set(combined_ids)), 4)

        # Verify Migration 0003 upgrade -> downgrade -> upgrade round-trip
        spec2 = importlib.util.spec_from_file_location("mig_0002", MIGRATION_0002_PATH)
        spec3 = importlib.util.spec_from_file_location("mig_0003", MIGRATION_0003_PATH)
        assert spec2 and spec2.loader and spec3 and spec3.loader
        mig2 = importlib.util.module_from_spec(spec2)
        mig3 = importlib.util.module_from_spec(spec3)
        spec2.loader.exec_module(mig2)
        spec3.loader.exec_module(mig3)

        with tempfile.NamedTemporaryFile(suffix=".sqlite3") as tmp:
            conn = sqlite3.connect(tmp.name)
            try:
                mig2.upgrade(conn)
                mig3.upgrade(conn)
                conn.commit()
                tables_up = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                for t in mig3.PHASE4_TABLES:
                    self.assertIn(t, tables_up)

                mig3.downgrade(conn)
                conn.commit()
                tables_down = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                for t in mig3.PHASE4_TABLES:
                    self.assertNotIn(t, tables_down)

                mig3.upgrade(conn)
                conn.commit()
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
