"""Phase 5 Communities, Memberships, Rules, Feeds, and Community Moderation Tests."""
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
MIGRATION_0004_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "0004_phase5_communities.py"
)


class Phase5CommunitiesTests(unittest.TestCase):
    """Verifies starter communities, join/leave, community feeds, and moderation controls."""

    def setUp(self) -> None:
        rate_limiter.reset()
        self.settings = Settings(
            app_env="test",
            database_url="sqlite:///:memory:",
            log_level="CRITICAL",
            session_cookie_secure=False,
        )
        self.app = create_app(settings=self.settings)
        self.client_member = TestClient(self.app, raise_server_exceptions=False)
        self.client_admin = TestClient(self.app, raise_server_exceptions=False)

        # Register regular member
        reg_m = self.client_member.post(
            "/api/v1/auth/register",
            json={"handle": "member_meera", "password": "SafePassword!Meera2026"},
        )
        self.assertEqual(reg_m.status_code, 201)
        self.member_id = reg_m.json()["user_id"]
        self.csrf_member = reg_m.json()["csrf_token"]

        # Register admin user and elevate role in DB
        reg_a = self.client_admin.post(
            "/api/v1/auth/register",
            json={"handle": "admin_arjun", "password": "SafePassword!Arjun2026"},
        )
        self.assertEqual(reg_a.status_code, 201)
        self.admin_id = reg_a.json()["user_id"]
        self.csrf_admin = reg_a.json()["csrf_token"]

        conn = self.app.state.db_manager._shared_memory_conn
        assert conn is not None
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (self.admin_id,))
        conn.commit()

    def tearDown(self) -> None:
        rate_limiter.reset()

    def test_starter_communities_seeded_searchable_and_rules_returned(self) -> None:
        res = self.client_member.get("/api/v1/communities")
        self.assertEqual(res.status_code, 200)
        communities = res.json()
        slugs = {c["slug"] for c in communities}

        expected_starter_slugs = {
            "workplace-rants",
            "corporate-memes",
            "career-advice",
            "it-software",
            "salary-talk",
            "job-hunting",
            "freshers-corner",
            "work-life-balance",
            "startup-life",
            "office-humour",
            "resignation-stories",
            "general-workplace",
        }
        self.assertTrue(expected_starter_slugs.issubset(slugs))

        # Search filter `?q=salary`
        search_res = self.client_member.get("/api/v1/communities?q=salary")
        self.assertEqual(search_res.status_code, 200)
        self.assertEqual(len(search_res.json()), 1)
        self.assertEqual(search_res.json()[0]["slug"], "salary-talk")

        # Individual community detail includes rules
        detail_res = self.client_member.get("/api/v1/communities/workplace-rants")
        self.assertEqual(detail_res.status_code, 200)
        detail = detail_res.json()
        self.assertEqual(detail["name"], "Workplace Rants")
        self.assertEqual(len(detail["rules"]), 4)
        self.assertEqual(detail["rules"][0]["rule_number"], 1)

    def test_join_leave_membership_idempotency_and_joined_filter(self) -> None:
        # Join c/corporate-memes
        join1 = self.client_member.post(
            "/api/v1/communities/corporate-memes/membership",
            headers={"X-CSRF-Token": self.csrf_member},
            json={"action": "join"},
        )
        self.assertEqual(join1.status_code, 200)
        self.assertTrue(join1.json()["is_member"])
        self.assertEqual(join1.json()["member_count"], 1)

        # Joining again is idempotent (member_count stays 1)
        join2 = self.client_member.post(
            "/api/v1/communities/corporate-memes/membership",
            headers={"X-CSRF-Token": self.csrf_member},
            json={"action": "join"},
        )
        self.assertEqual(join2.status_code, 200)
        self.assertEqual(join2.json()["member_count"], 1)

        # `?joined_only=true` returns only c/corporate-memes
        joined_list = self.client_member.get("/api/v1/communities?joined_only=true").json()
        self.assertEqual([c["slug"] for c in joined_list], ["corporate-memes"])

        # Leave c/corporate-memes
        leave = self.client_member.post(
            "/api/v1/communities/corporate-memes/membership",
            headers={"X-CSRF-Token": self.csrf_member},
            json={"action": "leave"},
        )
        self.assertEqual(leave.status_code, 200)
        self.assertFalse(leave.json()["is_member"])
        self.assertEqual(leave.json()["member_count"], 0)

    def test_community_feed_post_counts_and_anonymous_isolation(self) -> None:
        # Create an anonymous post in c/freshers-corner
        post_res = self.client_member.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_member},
            json={
                "community_slug": "freshers-corner",
                "post_type": "question",
                "identity_mode": "anonymous",
                "title": "First week onboarding anxiety — is this normal?",
                "body": "Just graduated and joined a 500-person team.",
            },
        )
        self.assertEqual(post_res.status_code, 201)
        post_id = post_res.json()["id"]

        # Community post_count incremented to 1
        comm_detail = self.client_admin.get("/api/v1/communities/freshers-corner").json()
        self.assertEqual(comm_detail["post_count"], 1)

        # Fetch community feed (`GET /api/v1/communities/freshers-corner/posts`) as another user
        feed_res = self.client_admin.get("/api/v1/communities/freshers-corner/posts")
        self.assertEqual(feed_res.status_code, 200)
        items = feed_res.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], post_id)
        self.assertEqual(items[0]["author"]["display_name"], "Anonymous Member")
        self.assertIsNone(items[0]["author"]["handle"])
        self.assertNotIn("member_meera", feed_res.text)
        self.assertNotIn(self.member_id, feed_res.text)

        # Delete post -> community post_count decrements back to 0
        self.client_member.delete(
            f"/api/v1/posts/{post_id}",
            headers={"X-CSRF-Token": self.csrf_member},
        )
        comm_after = self.client_admin.get("/api/v1/communities/freshers-corner").json()
        self.assertEqual(comm_after["post_count"], 0)

    def test_admin_controlled_community_creation_and_member_moderation(self) -> None:
        # Regular member cannot create a new community (403 FORBIDDEN_ROLE)
        forbidden_create = self.client_member.post(
            "/api/v1/communities",
            headers={"X-CSRF-Token": self.csrf_member},
            json={
                "slug": "design-systems",
                "name": "Design Systems",
                "description": "For UI/UX designers.",
            },
        )
        self.assertEqual(forbidden_create.status_code, 403)
        self.assertEqual(forbidden_create.json()["error"]["code"], "FORBIDDEN_ROLE")

        # Admin can create a new community with custom rules
        admin_create = self.client_admin.post(
            "/api/v1/communities",
            headers={"X-CSRF-Token": self.csrf_admin},
            json={
                "slug": "kerala-techies",
                "name": "Kerala Techies — കേരള ടെക്കികൾ",
                "description": "Technopark, Infopark, Cyberpark, and remote tech workers.",
                "primary_language": "ml",
                "rules": [
                    {
                        "rule_number": 1,
                        "title": "Be Supportive",
                        "description": "Help fellow developers and freshers.",
                    }
                ],
            },
        )
        self.assertEqual(admin_create.status_code, 201, admin_create.text)
        created_data = admin_create.json()
        self.assertEqual(created_data["slug"], "kerala-techies")
        self.assertEqual(created_data["viewer_context"]["role"], "moderator")
        self.assertTrue(created_data["viewer_context"]["can_moderate"])

        # Moderator bans `member_meera` from `c/kerala-techies`
        ban_res = self.client_admin.patch(
            "/api/v1/communities/kerala-techies/members/member_meera",
            headers={"X-CSRF-Token": self.csrf_admin},
            json={"status": "banned"},
        )
        self.assertEqual(ban_res.status_code, 200)

        # Banned member cannot join or post in `c/kerala-techies` (403 COMMUNITY_BANNED)
        join_banned = self.client_member.post(
            "/api/v1/communities/kerala-techies/membership",
            headers={"X-CSRF-Token": self.csrf_member},
            json={"action": "join"},
        )
        self.assertEqual(join_banned.status_code, 403)
        self.assertEqual(join_banned.json()["error"]["code"], "COMMUNITY_BANNED")

        post_banned = self.client_member.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_member},
            json={
                "community_slug": "kerala-techies",
                "post_type": "discussion",
                "title": "Trying to post while banned",
                "body": "Should be rejected.",
            },
        )
        self.assertEqual(post_banned.status_code, 403)
        self.assertEqual(post_banned.json()["error"]["code"], "COMMUNITY_BANNED")

        # Restricting a community blocks regular members from posting while allowing moderators
        restrict_res = self.client_admin.patch(
            "/api/v1/communities/startup-life/status",
            headers={"X-CSRF-Token": self.csrf_admin},
            json={"status": "restricted"},
        )
        self.assertEqual(restrict_res.status_code, 200)

        member_post_restricted = self.client_member.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_member},
            json={
                "community_slug": "startup-life",
                "post_type": "discussion",
                "title": "Regular member post in restricted community",
                "body": "Should fail with 403 COMMUNITY_RESTRICTED.",
            },
        )
        self.assertEqual(member_post_restricted.status_code, 403)
        self.assertEqual(member_post_restricted.json()["error"]["code"], "COMMUNITY_RESTRICTED")

        admin_post_restricted = self.client_admin.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_admin},
            json={
                "community_slug": "startup-life",
                "post_type": "discussion",
                "title": "Moderator announcement in restricted community",
                "body": "Moderators can still post announcements.",
            },
        )
        self.assertEqual(admin_post_restricted.status_code, 201)

    def test_migration_0004_upgrade_downgrade_roundtrip(self) -> None:
        for path in (MIGRATION_0002_PATH, MIGRATION_0003_PATH, MIGRATION_0004_PATH):
            self.assertTrue(path.is_file())

        spec2 = importlib.util.spec_from_file_location("mig2", MIGRATION_0002_PATH)
        spec3 = importlib.util.spec_from_file_location("mig3", MIGRATION_0003_PATH)
        spec4 = importlib.util.spec_from_file_location("mig4", MIGRATION_0004_PATH)
        assert spec2 and spec2.loader and spec3 and spec3.loader and spec4 and spec4.loader
        m2 = importlib.util.module_from_spec(spec2)
        m3 = importlib.util.module_from_spec(spec3)
        m4 = importlib.util.module_from_spec(spec4)
        spec2.loader.exec_module(m2)
        spec3.loader.exec_module(m3)
        spec4.loader.exec_module(m4)

        with tempfile.NamedTemporaryFile(suffix=".sqlite3") as tmp:
            conn = sqlite3.connect(tmp.name)
            try:
                m2.upgrade(conn)
                m3.upgrade(conn)
                m4.upgrade(conn)
                conn.commit()

                seeded_count = conn.execute("SELECT COUNT(*) FROM communities").fetchone()[0]
                self.assertGreaterEqual(seeded_count, 11)

                m4.downgrade(conn)
                conn.commit()
                tables_after_down = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                for t in m4.PHASE5_TABLES:
                    self.assertNotIn(t, tables_after_down)

                m4.upgrade(conn)
                conn.commit()
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
