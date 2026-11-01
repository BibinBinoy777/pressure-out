"""Phase 6 Comments, Sticky Anonymous OP Replies, Voting, Reactions, Bookmarks, and Notifications Tests."""
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

MIGRATION_0002_PATH = Path(__file__).resolve().parent.parent / "alembic/versions/0002_phase3_identity_and_privacy.py"
MIGRATION_0003_PATH = Path(__file__).resolve().parent.parent / "alembic/versions/0003_phase4_core_social_posting.py"
MIGRATION_0004_PATH = Path(__file__).resolve().parent.parent / "alembic/versions/0004_phase5_communities.py"
MIGRATION_0005_PATH = Path(__file__).resolve().parent.parent / "alembic/versions/0005_phase6_comments_engagement_notifications.py"


class Phase6CommentsEngagementNotificationsTests(unittest.TestCase):
    """Verifies threaded comments, Sticky Anonymous OP protection, voting, reactions, saves, and notifications."""

    def setUp(self) -> None:
        rate_limiter.reset()
        self.settings = Settings(
            app_env="test",
            database_url="sqlite:///:memory:",
            log_level="CRITICAL",
            session_cookie_secure=False,
        )
        self.app = create_app(settings=self.settings)
        self.client_op = TestClient(self.app, raise_server_exceptions=False)
        self.client_peer = TestClient(self.app, raise_server_exceptions=False)

        # Register Original Poster (OP)
        reg_op = self.client_op.post(
            "/api/v1/auth/register",
            json={"handle": "op_devika", "password": "SafePassword!Devika2026"},
        )
        self.assertEqual(reg_op.status_code, 201)
        self.op_id = reg_op.json()["user_id"]
        self.csrf_op = reg_op.json()["csrf_token"]

        # Register Peer commenter
        reg_peer = self.client_peer.post(
            "/api/v1/auth/register",
            json={"handle": "peer_prashanth", "password": "SafePassword!Prashanth2026"},
        )
        self.assertEqual(reg_peer.status_code, 201)
        self.peer_id = reg_peer.json()["user_id"]
        self.csrf_peer = reg_peer.json()["csrf_token"]

    def tearDown(self) -> None:
        rate_limiter.reset()

    def test_sticky_anonymous_op_guardrail_and_thread_scoped_labels_ac_imp_06(self) -> None:
        # 1. OP creates an ANONYMOUS post P1
        p1_res = self.client_op.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_op},
            json={
                "community_slug": "workplace-rants",
                "post_type": "rant",
                "identity_mode": "anonymous",
                "title": "Anonymous rant about weekend on-call rotations",
                "body": "Three weekends in a row without comp-off.",
            },
        )
        self.assertEqual(p1_res.status_code, 201)
        p1_id = p1_res.json()["id"]

        # 2. OP comments on P1 WITHOUT specifying `identity_mode`.
        # Even though OP's account default_identity_mode is 'pseudonymous', Sticky OP rule
        # MUST auto-lock the comment to 'anonymous' ('Anonymous OP')!
        c_op_auto = self.client_op.post(
            f"/api/v1/posts/{p1_id}/comments",
            headers={"X-CSRF-Token": self.csrf_op},
            json={"body": "Adding context: we are a 4-person backend team."},
        )
        self.assertEqual(c_op_auto.status_code, 201, c_op_auto.text)
        c_op_data = c_op_auto.json()
        self.assertEqual(c_op_data["identity_mode"], "anonymous")
        self.assertEqual(c_op_data["author"]["display_name"], "Anonymous OP")
        self.assertTrue(c_op_data["author"]["is_anonymous_op"])
        self.assertIsNone(c_op_data["author"]["handle"])
        self.assertNotIn("op_devika", c_op_auto.text)

        # 3. OP tries to comment with `identity_mode='pseudonymous'` without `confirm_op_identity_reveal=True`
        # -> MUST be blocked with 409 OP_ANONYMITY_MISMATCH!
        c_op_mismatch = self.client_op.post(
            f"/api/v1/posts/{p1_id}/comments",
            headers={"X-CSRF-Token": self.csrf_op},
            json={
                "body": "Accidental reply with my handle",
                "identity_mode": "pseudonymous",
                "confirm_op_identity_reveal": False,
            },
        )
        self.assertEqual(c_op_mismatch.status_code, 409)
        self.assertEqual(c_op_mismatch.json()["error"]["code"], "OP_ANONYMITY_MISMATCH")

        # 4. Peer comments anonymously twice on P1 -> gets consistent thread-scoped label `Anonymous • XXXX`
        c_peer_1 = self.client_peer.post(
            f"/api/v1/posts/{p1_id}/comments",
            headers={"X-CSRF-Token": self.csrf_peer},
            json={"body": "First anonymous reply from peer", "identity_mode": "anonymous"},
        ).json()
        c_peer_2 = self.client_peer.post(
            f"/api/v1/posts/{p1_id}/comments",
            headers={"X-CSRF-Token": self.csrf_peer},
            json={"body": "Second anonymous reply from peer", "identity_mode": "anonymous"},
        ).json()

        label_p1 = c_peer_1["author"]["display_name"]
        self.assertTrue(label_p1.startswith("Anonymous • "))
        self.assertEqual(label_p1, c_peer_2["author"]["display_name"])
        self.assertFalse(c_peer_1["author"]["is_anonymous_op"])

        # 5. On a different Post P2, Peer's anonymous label MUST be different to prevent cross-post tracking
        p2_id = self.client_op.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_op},
            json={
                "community_slug": "salary-talk",
                "post_type": "question",
                "identity_mode": "pseudonymous",
                "title": "Second distinct post",
                "body": "Comparing bonus structures.",
            },
        ).json()["id"]

        c_peer_p2 = self.client_peer.post(
            f"/api/v1/posts/{p2_id}/comments",
            headers={"X-CSRF-Token": self.csrf_peer},
            json={"body": "Anonymous reply on P2", "identity_mode": "anonymous"},
        ).json()
        label_p2 = c_peer_p2["author"]["display_name"]
        self.assertNotEqual(label_p1, label_p2)

    def test_nested_comment_threads_subtree_pagination_and_soft_deletion(self) -> None:
        post_id = self.client_op.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_op},
            json={
                "community_slug": "it-software",
                "post_type": "discussion",
                "title": "Code review culture in 2026",
                "body": "How fast does your team review PRs?",
            },
        ).json()["id"]

        # Root comment (depth 0)
        root_c = self.client_peer.post(
            f"/api/v1/posts/{post_id}/comments",
            headers={"X-CSRF-Token": self.csrf_peer},
            json={"body": "Usually within 4 hours — വേഗത്തിൽ നോക്കും!"},
        ).json()
        self.assertEqual(root_c["depth"], 0)

        # Child reply (depth 1)
        child_c = self.client_op.post(
            f"/api/v1/posts/{post_id}/comments",
            headers={"X-CSRF-Token": self.csrf_op},
            json={
                "parent_comment_id": root_c["id"],
                "body": "That's awesome! Ours take 3 days.",
            },
        ).json()
        self.assertEqual(child_c["depth"], 1)
        self.assertTrue(child_c["path"].startswith(root_c["path"] + "."))

        # Subtree query `?parent_id=root_c["id"]` returns only the child reply
        subtree = self.client_op.get(
            f"/api/v1/posts/{post_id}/comments?parent_id={root_c['id']}"
        ).json()
        self.assertEqual([c["id"] for c in subtree["items"]], [child_c["id"]])

        # Soft-deleting root comment scrubs body & handle while preserving child reply tree
        del_res = self.client_peer.delete(
            f"/api/v1/comments/{root_c['id']}",
            headers={"X-CSRF-Token": self.csrf_peer},
        )
        self.assertEqual(del_res.status_code, 200)

        all_comments = self.client_op.get(f"/api/v1/posts/{post_id}/comments").json()["items"]
        self.assertEqual(len(all_comments), 2)
        self.assertTrue(all_comments[0]["is_deleted"])
        self.assertEqual(all_comments[0]["body"], "[deleted by author]")
        self.assertIsNone(all_comments[0]["author"]["handle"])
        self.assertEqual(all_comments[1]["id"], child_c["id"])

    def test_vote_idempotency_reactions_and_saved_bookmarks_ac_imp_07(self) -> None:
        post_id = self.client_op.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_op},
            json={
                "community_slug": "corporate-memes",
                "post_type": "story",
                "title": "Accidentally replied-all to a 10,000-employee mailing list",
                "body": "Please remove me from this distribution list.",
            },
        ).json()["id"]

        # Upvote twice from same user -> idempotent (score = 1, upvote_count = 1)
        v1 = self.client_peer.put(
            f"/api/v1/posts/{post_id}/vote",
            headers={"X-CSRF-Token": self.csrf_peer},
            json={"value": 1},
        ).json()
        v2 = self.client_peer.put(
            f"/api/v1/posts/{post_id}/vote",
            headers={"X-CSRF-Token": self.csrf_peer},
            json={"value": 1},
        ).json()
        self.assertEqual(v1["score"], 1)
        self.assertEqual(v2["score"], 1)
        self.assertEqual(v2["upvote_count"], 1)

        # Switch to downvote (-1) -> score = -1, upvote_count = 0, downvote_count = 1
        v_down = self.client_peer.put(
            f"/api/v1/posts/{post_id}/vote",
            headers={"X-CSRF-Token": self.csrf_peer},
            json={"value": -1},
        ).json()
        self.assertEqual(v_down["score"], -1)
        self.assertEqual(v_down["upvote_count"], 0)
        self.assertEqual(v_down["downvote_count"], 1)

        # Toggle reactions (`relatable` and `oof`)
        r1 = self.client_peer.put(
            f"/api/v1/posts/{post_id}/reactions/relatable",
            headers={"X-CSRF-Token": self.csrf_peer},
            json={"active": True},
        ).json()
        self.assertEqual(r1["reaction_counts"]["relatable"], 1)
        self.assertIn("relatable", r1["viewer_reactions"])

        # Bookmark post and fetch `/api/v1/me/saved`
        save_res = self.client_peer.post(
            f"/api/v1/posts/{post_id}/save",
            headers={"X-CSRF-Token": self.csrf_peer},
            json={"saved": True},
        )
        self.assertEqual(save_res.status_code, 200)
        self.assertTrue(save_res.json()["saved"])

        saved_list = self.client_peer.get("/api/v1/me/saved").json()
        self.assertEqual([p["id"] for p in saved_list["items"]], [post_id])

    def test_privacy_safe_notifications_and_mark_read(self) -> None:
        post_id = self.client_op.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": self.csrf_op},
            json={
                "community_slug": "workplace-rants",
                "post_type": "discussion",
                "title": "Notification test post",
                "body": "Waiting for replies.",
            },
        ).json()["id"]

        # Peer replies ANONYMOUSLY -> OP receives notification that does NOT leak peer's handle
        self.client_peer.post(
            f"/api/v1/posts/{post_id}/comments",
            headers={"X-CSRF-Token": self.csrf_peer},
            json={
                "body": "Supportive anonymous reply!",
                "identity_mode": "anonymous",
            },
        )

        notifs_res = self.client_op.get("/api/v1/notifications")
        self.assertEqual(notifs_res.status_code, 200)
        notifs_data = notifs_res.json()
        self.assertEqual(notifs_data["unread_count"], 1)
        self.assertEqual(len(notifs_data["items"]), 1)
        self.assertIn("Anonymous Member", notifs_data["items"][0]["title"])
        self.assertNotIn("peer_prashanth", notifs_res.text)

        # Mark all read
        mark_res = self.client_op.patch(
            "/api/v1/notifications/read",
            headers={"X-CSRF-Token": self.csrf_op},
            json={"mark_all": True},
        )
        self.assertEqual(mark_res.status_code, 200)

        after_read = self.client_op.get("/api/v1/notifications").json()
        self.assertEqual(after_read["unread_count"], 0)

    def test_migration_0005_upgrade_downgrade_roundtrip(self) -> None:
        specs = [
            importlib.util.spec_from_file_location(f"m_{i}", p)
            for i, p in enumerate(
                [MIGRATION_0002_PATH, MIGRATION_0003_PATH, MIGRATION_0004_PATH, MIGRATION_0005_PATH],
                start=2,
            )
        ]
        mods = []
        for s in specs:
            assert s and s.loader
            m = importlib.util.module_from_spec(s)
            s.loader.exec_module(m)
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
                for t in mods[-1].PHASE6_TABLES:
                    self.assertIn(t, tables_up)

                mods[-1].downgrade(conn)
                conn.commit()
                tables_down = {
                    r[0]
                    for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                for t in mods[-1].PHASE6_TABLES:
                    self.assertNotIn(t, tables_down)

                mods[-1].upgrade(conn)
                conn.commit()
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
