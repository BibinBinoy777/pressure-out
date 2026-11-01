"""Phase 11 Workplace Experiences, Resignation Stories, Structured Contributions &
Privacy-Safe k-Anonymity Aggregation Engine Test Suite.
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


class Phase11WorkplaceExperiencesAndInsightsTests(unittest.TestCase):
    def setUp(self) -> None:
        rate_limiter.reset()
        self.settings = Settings(
            app_env="test",
            database_url="sqlite:///:memory:",
            insights_min_cohort_size=10,
            insights_sensitive_min_cohort_size=20,
            insights_min_category_bucket_count=3,
        )
        self.app = create_app(settings=self.settings)
        self.db_manager = self.app.state.db_manager
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        rate_limiter.reset()
        asyncio.run(self.db_manager.dispose())

    def _register_user(self, handle: str) -> tuple[TestClient, str, str]:
        rate_limiter.reset()
        c = TestClient(self.app)
        resp = c.post(
            "/api/v1/auth/register",
            json={
                "handle": handle,
                "password": "ValidPassword#2026!",
                "default_identity_mode": "pseudonymous",
                "preferred_ui_locale": "en",
            },
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        data = resp.json()
        return c, data["user_id"], data["csrf_token"]

    def test_01_workplace_experiences_and_resignation_stories_privacy_and_filters(self) -> None:
        c1, u1_id, csrf1 = self._register_user("worker_kerala_1")
        c2, u2_id, csrf2 = self._register_user("worker_chennai_2")

        # 1. Create a Workplace Experience post (pseudonymous)
        exp_resp = c1.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": csrf1},
            json={
                "community_slug": "work-life-balance",
                "post_type": "workplace_experience",
                "identity_mode": "pseudonymous",
                "title": "Switching to an async-first remote engineering culture",
                "body": "Cutting daily status meetings in half gave everyone 10 hours of deep focus back.",
                "content_language": "en",
                "tags": ["remote-work", "async"],
                "workplace_detail": {
                    "experience_kind": "workplace_experience",
                    "experience_category": "remote_work",
                    "experience_band": "senior_6_10",
                    "industry_category": "technology",
                    "lesson_learned": "Written async updates beat 45-minute status calls.",
                },
            },
        )
        self.assertEqual(exp_resp.status_code, 201, exp_resp.text)
        exp_post = exp_resp.json()
        self.assertIsNotNone(exp_post["workplace_detail"])
        self.assertEqual(exp_post["workplace_detail"]["experience_category"], "remote_work")
        self.assertTrue(exp_post["workplace_detail"]["is_self_reported"])

        # 2. Create an ANONYMOUS Resignation Story in Malayalam
        resign_resp = c2.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": csrf2},
            json={
                "community_slug": "resignation-stories",
                "post_type": "workplace_experience",
                "identity_mode": "anonymous",
                "title": "മികച്ച അവസരത്തിനായി ജോലി രാജിവെച്ച അനുഭവം",
                "body": "മൂന്ന് വർഷത്തെ കാത്തിരിപ്പിന് ശേഷം പുതിയൊരു കമ്പനിയിലേക്ക് മാറി.",
                "content_language": "ml",
                "tags": ["resignation", "career-growth"],
                "workplace_detail": {
                    "experience_kind": "resignation_story",
                    "experience_category": "resignation",
                    "primary_resignation_reason": "better_opportunity",
                    "secondary_resignation_reason": "compensation",
                    "experience_band": "mid_3_6",
                    "industry_category": "technology",
                    "transition_outcome": "accepted_new_role",
                    "lesson_learned": "Never feel guilty about prioritizing your own career growth.",
                },
            },
        )
        self.assertEqual(resign_resp.status_code, 201, resign_resp.text)
        resign_post = resign_resp.json()

        # Verify strict anonymous isolation (AC-IMP-03)
        raw_resign_json = json.dumps(resign_post)
        self.assertNotIn(u2_id, raw_resign_json)
        self.assertNotIn("worker_chennai_2", raw_resign_json)
        self.assertEqual(resign_post["author"]["display_name"], "Anonymous Member")
        self.assertIsNone(resign_post["author"]["handle"])

        # Verify GET /api/v1/workplace/experiences and GET /api/v1/workplace/resignation-stories filters
        wx_list = self.client.get(
            "/api/v1/workplace/experiences?category=remote_work&industry_category=technology"
        ).json()["items"]
        self.assertEqual(len(wx_list), 1)
        self.assertEqual(wx_list[0]["id"], exp_post["id"])

        rs_list = self.client.get(
            "/api/v1/workplace/resignation-stories?resignation_reason=better_opportunity&content_language=ml"
        ).json()["items"]
        self.assertEqual(len(rs_list), 1)
        self.assertEqual(rs_list[0]["id"], resign_post["id"])

        # Verify editing and deleting a workplace experience post works and updates discovery feeds
        edit_wx = c1.patch(
            f"/api/v1/posts/{exp_post['id']}",
            headers={"X-CSRF-Token": csrf1},
            json={"title": "Updated: Async-first remote engineering culture"},
        )
        self.assertEqual(edit_wx.status_code, 200)
        self.assertEqual(
            edit_wx.json()["title"],
            "Updated: Async-first remote engineering culture",
        )

        del_wx = c1.delete(
            f"/api/v1/posts/{exp_post['id']}",
            headers={"X-CSRF-Token": csrf1},
        )
        self.assertEqual(del_wx.status_code, 200)
        wx_after_del = self.client.get(
            "/api/v1/workplace/experiences?category=remote_work"
        ).json()["items"]
        self.assertEqual(len(wx_after_del), 0)

        # CRITICAL: Verify public narrative posts & resignation stories NEVER feed into aggregated insights!
        insights_empty = self.client.get("/api/v1/workplace/insights").json()
        self.assertIsNone(insights_empty["cohort_eligible_band"])
        for m in insights_empty["metrics"]:
            self.assertTrue(m["insufficient_data"])
            self.assertIsNone(m["average_rating"])

    def test_02_structured_contribution_consent_uniqueness_ownership_and_privacy(self) -> None:
        c1, _, csrf1 = self._register_user("contrib_owner")
        c2, _, csrf2 = self._register_user("contrib_other")

        # 1. Explicit consent == False is rejected (422 CONSENT_REQUIRED)
        no_consent = c1.post(
            "/api/v1/workplace/contributions",
            headers={"X-CSRF-Token": csrf1},
            json={
                "aggregation_consent": False,
                "industry_category": "technology",
                "overall_satisfaction": 4,
            },
        )
        self.assertEqual(no_consent.status_code, 422)
        self.assertEqual(no_consent.json()["error"]["code"], "CONSENT_REQUIRED")

        # 2. Out-of-range rating is rejected (422 INVALID_RATING_VALUE)
        bad_rating = c1.post(
            "/api/v1/workplace/contributions",
            headers={"X-CSRF-Token": csrf1},
            json={
                "aggregation_consent": True,
                "overall_satisfaction": 6,
            },
        )
        self.assertEqual(bad_rating.status_code, 422)
        self.assertEqual(bad_rating.json()["error"]["code"], "INVALID_RATING_VALUE")

        # 3. Valid contribution succeeds (201 Created)
        ok_resp = c1.post(
            "/api/v1/workplace/contributions",
            headers={"X-CSRF-Token": csrf1},
            json={
                "aggregation_consent": True,
                "industry_category": "technology",
                "role_family": "software_engineering",
                "experience_band": "mid_3_6",
                "company_size_band": "midsize_51_500",
                "broad_region": "south_asia",
                "work_arrangement": "hybrid",
                "overall_satisfaction": 4,
                "work_life_balance": 3,
                "resignation_reason": "compensation",
            },
        )
        self.assertEqual(ok_resp.status_code, 201, ok_resp.text)
        contrib_id = ok_resp.json()["id"]

        # 4. Duplicate POST from same user is rejected (409 CONTRIBUTION_ALREADY_EXISTS)
        dup_resp = c1.post(
            "/api/v1/workplace/contributions",
            headers={"X-CSRF-Token": csrf1},
            json={
                "aggregation_consent": True,
                "overall_satisfaction": 5,
            },
        )
        self.assertEqual(dup_resp.status_code, 409)
        self.assertEqual(dup_resp.json()["error"]["code"], "CONTRIBUTION_ALREADY_EXISTS")

        # 5. Owner can fetch /api/v1/workplace/contributions/mine; other user sees null
        mine = c1.get("/api/v1/workplace/contributions/mine")
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(mine.json()["id"], contrib_id)
        self.assertIsNone(c2.get("/api/v1/workplace/contributions/mine").json())

        # 6. Other user cannot PATCH or DELETE owner's contribution (403 FORBIDDEN_NOT_OWNER)
        forbid_patch = c2.patch(
            f"/api/v1/workplace/contributions/{contrib_id}",
            headers={"X-CSRF-Token": csrf2},
            json={"overall_satisfaction": 1},
        )
        self.assertEqual(forbid_patch.status_code, 403)
        self.assertEqual(forbid_patch.json()["error"]["code"], "FORBIDDEN_NOT_OWNER")

        forbid_del = c2.delete(
            f"/api/v1/workplace/contributions/{contrib_id}",
            headers={"X-CSRF-Token": csrf2},
        )
        self.assertEqual(forbid_del.status_code, 403)

    def test_03_privacy_safe_aggregation_thresholds_sensitive_metrics_and_complementary_suppression(self) -> None:
        clients_and_contrib_ids: list[tuple[TestClient, str, str]] = []

        # Create 9 distinct contributors -> BELOW general threshold (10) and sensitive threshold (20)
        for i in range(1, 10):
            c, _, csrf = self._register_user(f"insight_user_{i}")
            r = c.post(
                "/api/v1/workplace/contributions",
                headers={"X-CSRF-Token": csrf},
                json={
                    "aggregation_consent": True,
                    "industry_category": "technology",
                    "work_arrangement": "remote",
                    "overall_satisfaction": 4,
                    "work_life_balance": 5,
                    "compensation_satisfaction": 3,
                    "resignation_reason": "compensation",
                },
            )
            self.assertEqual(r.status_code, 201)
            clients_and_contrib_ids.append((c, csrf, r.json()["id"]))

        # At n = 9: ALL metrics must be suppressed (`insufficient_data = True`, `sample_size_band = None`)
        ins_9 = self.client.get("/api/v1/workplace/insights").json()
        self.assertIsNone(ins_9["cohort_eligible_band"])
        for m in ins_9["metrics"]:
            self.assertTrue(m["insufficient_data"])
            self.assertIsNone(m["average_rating"])
            self.assertIsNone(m["sample_size_band"])
        self.assertTrue(ins_9["resignation_reasons"]["insufficient_data"])

        # Add 10th distinct contributor -> General metrics (threshold 10) unlock, while Sensitive metrics (threshold 20) stay suppressed!
        c10, _, csrf10 = self._register_user("insight_user_10")
        r10 = c10.post(
            "/api/v1/workplace/contributions",
            headers={"X-CSRF-Token": csrf10},
            json={
                "aggregation_consent": True,
                "industry_category": "technology",
                "work_arrangement": "remote",
                "overall_satisfaction": 4,
                "work_life_balance": 5,
                "compensation_satisfaction": 3,
                "resignation_reason": "compensation",
            },
        )
        clients_and_contrib_ids.append((c10, csrf10, r10.json()["id"]))

        ins_10 = self.client.get("/api/v1/workplace/insights").json()
        self.assertEqual(ins_10["cohort_eligible_band"], "10+")
        metrics_by_key = {m["metric_key"]: m for m in ins_10["metrics"]}
        self.assertFalse(metrics_by_key["overall_satisfaction"]["insufficient_data"])
        self.assertEqual(metrics_by_key["overall_satisfaction"]["average_rating"], 4.0)
        self.assertEqual(metrics_by_key["overall_satisfaction"]["sample_size_band"], "10+")

        # Sensitive compensation_satisfaction and resignation_reasons STILL suppressed at n = 10!
        self.assertTrue(metrics_by_key["compensation_satisfaction"]["insufficient_data"])
        self.assertIsNone(metrics_by_key["compensation_satisfaction"]["average_rating"])
        self.assertTrue(ins_10["resignation_reasons"]["insufficient_data"])

        # Test consent withdrawal and deletion recalculation at n = 10 -> n = 9:
        # User 10 withdraws consent -> cohort drops back to 9 -> general metrics suppressed again!
        c10.patch(
            f"/api/v1/workplace/contributions/{r10.json()['id']}",
            headers={"X-CSRF-Token": csrf10},
            json={"aggregation_consent": False},
        )
        ins_withdrawn = self.client.get("/api/v1/workplace/insights").json()
        self.assertIsNone(ins_withdrawn["cohort_eligible_band"])

        # User 10 re-enables consent -> back to 10+
        c10.patch(
            f"/api/v1/workplace/contributions/{r10.json()['id']}",
            headers={"X-CSRF-Token": csrf10},
            json={"aggregation_consent": True},
        )
        self.assertEqual(
            self.client.get("/api/v1/workplace/insights").json()["cohort_eligible_band"],
            "10+",
        )

        # Also verify DELETE /api/v1/workplace/contributions/{id} removes contribution and recalculates aggregate
        del_c10 = c10.delete(
            f"/api/v1/workplace/contributions/{r10.json()['id']}",
            headers={"X-CSRF-Token": csrf10},
        )
        self.assertEqual(del_c10.status_code, 200)
        self.assertIsNone(
            self.client.get("/api/v1/workplace/insights").json()["cohort_eligible_band"]
        )
        # Re-create User 10's contribution before adding 11..20
        r10 = c10.post(
            "/api/v1/workplace/contributions",
            headers={"X-CSRF-Token": csrf10},
            json={
                "aggregation_consent": True,
                "industry_category": "technology",
                "work_arrangement": "remote",
                "overall_satisfaction": 4,
                "work_life_balance": 5,
                "compensation_satisfaction": 3,
                "resignation_reason": "compensation",
            },
        )
        self.assertEqual(r10.status_code, 201)

        # Now add Contributors 11..20 so total n = 20 (unlocking sensitive metrics & testing complementary bucket suppression):
        # Users 1..16 have 'compensation' (16), Users 17..19 have 'workload' (3), User 20 has 'relocation' (1)
        for i in range(11, 21):
            c_i, _, csrf_i = self._register_user(f"insight_user_{i}")
            reason = (
                "compensation"
                if i <= 16
                else ("workload" if i <= 19 else "relocation")
            )
            c_i.post(
                "/api/v1/workplace/contributions",
                headers={"X-CSRF-Token": csrf_i},
                json={
                    "aggregation_consent": True,
                    "industry_category": "technology",
                    "work_arrangement": "remote",
                    "overall_satisfaction": 4,
                    "compensation_satisfaction": 3,
                    "resignation_reason": reason,
                },
            )

        ins_20 = self.client.get("/api/v1/workplace/insights").json()
        self.assertEqual(ins_20["cohort_eligible_band"], "20+")
        m20 = {m["metric_key"]: m for m in ins_20["metrics"]}
        self.assertFalse(m20["compensation_satisfaction"]["insufficient_data"])
        self.assertEqual(m20["compensation_satisfaction"]["average_rating"], 3.0)
        self.assertEqual(m20["compensation_satisfaction"]["sample_size_band"], "20+")

        # Verify complementary suppression on resignation_reasons:
        # 'relocation' (1 < 3) is suppressed, AND because 1 < 3, the next smallest bucket 'workload' (3)
        # is ALSO suppressed into `suppressed_other_percentage` (4 / 20 = 20%), leaving only 'compensation' (80%) visible!
        rb = ins_20["resignation_reasons"]
        self.assertFalse(rb["insufficient_data"])
        self.assertEqual(len(rb["buckets"]), 1)
        self.assertEqual(rb["buckets"][0]["reason_code"], "compensation")
        self.assertEqual(rb["buckets"][0]["percentage"], 80)
        self.assertEqual(rb["suppressed_other_percentage"], 20)

        # Verify filter dimension cap: <= 2 filters allowed, 3 filters rejected with 422 TOO_MANY_INSIGHT_FILTERS
        ok_2_filters = self.client.get(
            "/api/v1/workplace/insights?industry_category=technology&work_arrangement=remote"
        )
        self.assertEqual(ok_2_filters.status_code, 200)

        too_many_filters = self.client.get(
            "/api/v1/workplace/insights?industry_category=technology&work_arrangement=remote&broad_region=south_asia"
        )
        self.assertEqual(too_many_filters.status_code, 422)
        self.assertEqual(
            too_many_filters.json()["error"]["code"], "TOO_MANY_INSIGHT_FILTERS"
        )

    def test_04_migration_0010_upgrade_downgrade_roundtrip(self) -> None:
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
            "0010_phase11_workplace_experiences.py",
        ):
            _load_migration(fname).upgrade(conn)

        mig10 = _load_migration("0010_phase11_workplace_experiences.py")
        mig10.downgrade(conn)
        tables_down = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        self.assertNotIn("workplace_experience_details", tables_down)
        self.assertNotIn("workplace_insight_contributions", tables_down)

        mig10.upgrade(conn)
        tables_up = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        self.assertIn("workplace_experience_details", tables_up)
        self.assertIn("workplace_insight_contributions", tables_up)
        conn.close()


if __name__ == "__main__":
    unittest.main()
