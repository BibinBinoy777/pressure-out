"""Phase 7 Feed Modes (Latest, Popular, Following, Explore), Anti-Outrage Ranking, Topic Muting, and Multilingual Search Tests."""
from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.core.rate_limit import rate_limiter
from app.main import create_app
from app.modules.feed.ranking import compute_hot_rank_score

MIGRATIONS = [
    Path(__file__).resolve().parent.parent / f"alembic/versions/{fname}"
    for fname in (
        "0002_phase3_identity_and_privacy.py",
        "0003_phase4_core_social_posting.py",
        "0004_phase5_communities.py",
        "0005_phase6_comments_engagement_notifications.py",
        "0006_phase7_feed_search_discovery.py",
    )
]


class Phase7FeedRankingDiscoveryTests(unittest.TestCase):
    """Verifies explainable ranking, anti-outrage dampening, feed modes, topic muting, and search."""

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

        reg_a = self.client_a.post(
            "/api/v1/auth/register",
            json={"handle": "creator_kiran", "password": "SafePassword!Kiran2026"},
        )
        self.assertEqual(reg_a.status_code, 201)
        self.user_a_id = reg_a.json()["user_id"]
        self.csrf_a = reg_a.json()["csrf_token"]

        reg_b = self.client_b.post(
            "/api/v1/auth/register",
            json={"handle": "reader_lekshmi", "password": "SafePassword!Lekshmi2026"},
        )
        self.assertEqual(reg_b.status_code, 201)
        self.user_b_id = reg_b.json()["user_id"]
        self.csrf_b = reg_b.json()["csrf_token"]

    def tearDown(self) -> None:
        rate_limiter.reset()

    def test_explainable_hot_rank_formula_and_anti_outrage_dampener(self) -> None:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        older_iso = (now - timedelta(hours=24)).isoformat()

        # 1. Constructive story with 10 upvotes, 0 downvotes, 4 reactions, 3 comments
        constructive_score = compute_hot_rank_score(
            upvote_count=10,
            downvote_count=0,
            reaction_counts={"support": 2, "relatable": 2},
            comment_count=3,
            post_type="story",
            created_at_iso=now_iso,
            reference_time=now,
        )

        # 2. Polarized / brigaded outrage rant with 10 upvotes and 8 downvotes (balance_ratio = 0.8 >= 0.65)
        polarized_score = compute_hot_rank_score(
            upvote_count=10,
            downvote_count=8,
            reaction_counts={},
            comment_count=25,
            post_type="rant",
            created_at_iso=now_iso,
            reference_time=now,
        )
        self.assertGreater(constructive_score, polarized_score)

        # 3. Ratioed outrage post (0 upvotes, 30 comments) is dampened compared to endorsed post
        ratioed_score = compute_hot_rank_score(
            upvote_count=0,
            downvote_count=0,
            reaction_counts={},
            comment_count=30,
            post_type="rant",
            created_at_iso=now_iso,
            reference_time=now,
        )
        self.assertGreater(constructive_score, ratioed_score)

        # 4. Age decay reduces score of 24h-old post compared to fresh post with identical stats
        older_score = compute_hot_rank_score(
            upvote_count=10,
            downvote_count=0,
            reaction_counts={"support": 2, "relatable": 2},
            comment_count=3,
            post_type="story",
            created_at_iso=older_iso,
            reference_time=now,
        )
        self.assertGreater(constructive_score, older_score)

    def test_latest_popular_following_feeds_and_topic_muting(self) -> None:
        # Creator A publishes Post 1 in `c/salary-talk` with tag `appraisal`
        p1 = self.client_a.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_a},
            json={
                "community_slug": "salary-talk",
                "post_type": "discussion",
                "title": "2026 Appraisal hike percentages across IT companies",
                "body": "Share your band and percentage.",
                "tags": ["appraisal", "compensation"],
            },
        ).json()

        # Creator A publishes Post 2 in `c/corporate-memes` with tag `standup`
        p2 = self.client_a.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_a},
            json={
                "community_slug": "corporate-memes",
                "post_type": "meme",
                "title": "When a 15-minute standup turns into a 90-minute architecture debate",
                "body": "Every single Tuesday.",
                "tags": ["standup", "memes"],
                "meme_asset_id": "asset_standup_1",
            },
        ).json()

        # Reader B upvotes and reacts to Post 1 so Post 1 has higher hot_rank_score than Post 2
        self.client_b.put(
            f"/api/v1/posts/{p1['id']}/vote",
            headers={"X-CSRF-Token": self.csrf_b},
            json={"value": 1},
        )
        self.client_b.put(
            f"/api/v1/posts/{p1['id']}/reactions/relatable",
            headers={"X-CSRF-Token": self.csrf_b},
            json={"active": True},
        )

        # Popular feed orders Post 1 before Post 2
        pop_items = self.client_b.get("/api/v1/feed?mode=popular").json()["items"]
        self.assertEqual(pop_items[0]["id"], p1["id"])

        # Latest feed orders Post 2 (newest) before Post 1
        latest_items = self.client_b.get("/api/v1/feed?mode=latest").json()["items"]
        self.assertEqual(latest_items[0]["id"], p2["id"])

        # Reader B follows tag `standup` -> Following feed returns Post 2
        fol_res = self.client_b.put(
            "/api/v1/feed/topics/standup",
            headers={"X-CSRF-Token": self.csrf_b},
            json={"preference": "follow"},
        )
        self.assertEqual(fol_res.status_code, 200)

        following_items = self.client_b.get("/api/v1/feed?mode=following").json()["items"]
        self.assertEqual([item["id"] for item in following_items], [p2["id"]])

        # Reader B mutes tag `appraisal` -> Post 1 is excluded from Reader B's Popular & Latest feeds!
        mute_res = self.client_b.put(
            "/api/v1/feed/topics/appraisal",
            headers={"X-CSRF-Token": self.csrf_b},
            json={"preference": "mute"},
        )
        self.assertEqual(mute_res.status_code, 200)

        pop_after_mute = self.client_b.get("/api/v1/feed?mode=popular").json()["items"]
        self.assertNotIn(p1["id"], [item["id"] for item in pop_after_mute])

    def test_explore_discovery_and_multilingual_search_with_anonymous_isolation(self) -> None:
        # Creator A publishes an anonymous Malayalam/English post in `c/freshers-corner`
        anon_post = self.client_a.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_a},
            json={
                "community_slug": "freshers-corner",
                "post_type": "question",
                "identity_mode": "anonymous",
                "title": "ആദ്യത്തെ പ്രോജക്ട് — Onboarding guide for freshers",
                "body": "How do you ask senior engineers for help without feeling awkward?",
                "content_language": "ml",
                "tags": ["onboarding", "freshers"],
            },
        ).json()

        # 1. Explore endpoint includes trending tags, featured communities, and fresh_community_posts
        explore_res = self.client_b.get("/api/v1/explore")
        self.assertEqual(explore_res.status_code, 200)
        explore_data = explore_res.json()
        self.assertTrue(len(explore_data["trending_tags"]) >= 1)
        self.assertTrue(len(explore_data["featured_communities"]) >= 4)
        fresh_ids = [p["id"] for p in explore_data["fresh_community_posts"]]
        self.assertIn(anon_post["id"], fresh_ids)

        # 2. Search by Malayalam keyword (`പ്രോജക്ട്`), English keyword (`Onboarding`), or tag (`freshers`)
        for query_str in ("പ്രോജക്ട്", "Onboarding", "freshers"):
            s_res = self.client_b.get(f"/api/v1/search?q={query_str}")
            self.assertEqual(s_res.status_code, 200)
            s_items = s_res.json()["items"]
            self.assertEqual(len(s_items), 1)
            self.assertEqual(s_items[0]["id"], anon_post["id"])
            # Verify anonymous isolation in search results
            self.assertEqual(s_items[0]["author"]["display_name"], "Anonymous Member")
            self.assertIsNone(s_items[0]["author"]["handle"])
            self.assertNotIn("creator_kiran", s_res.text)
            self.assertNotIn(self.user_a_id, s_res.text)

        # 3. Search respects language filter `?lang=ml` vs `?lang=es`
        self.assertEqual(
            len(self.client_b.get("/api/v1/search?q=Onboarding&lang=ml").json()["items"]),
            1,
        )
        self.assertEqual(
            len(self.client_b.get("/api/v1/search?q=Onboarding&lang=es").json()["items"]),
            0,
        )

    def test_migration_0006_upgrade_downgrade_roundtrip(self) -> None:
        mods = []
        for idx, path in enumerate(MIGRATIONS, start=2):
            spec = importlib.util.spec_from_file_location(f"m_{idx}", path)
            assert spec and spec.loader
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            mods.append(m)

        with tempfile.NamedTemporaryFile(suffix=".sqlite3") as tmp:
            conn = sqlite3.connect(tmp.name)
            try:
                for m in mods:
                    m.upgrade(conn)
                conn.commit()

                tables_up = {
                    r[0]
                    for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                for t in mods[-1].PHASE7_TABLES:
                    self.assertIn(t, tables_up)

                mods[-1].downgrade(conn)
                conn.commit()
                tables_down = {
                    r[0]
                    for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                for t in mods[-1].PHASE7_TABLES:
                    self.assertNotIn(t, tables_down)

                mods[-1].upgrade(conn)
                conn.commit()
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
