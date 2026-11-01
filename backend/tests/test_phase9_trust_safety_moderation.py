"""Phase 9 Trust, Safety, Reporting, Velocity Auto-Hold, Privacy-Blind Moderation,
Appeals (Separation of Duties), Blocking/Muting & Immutable Audit Trail Tests.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.config import Settings
from app.core.rate_limit import rate_limiter
from app.database.session import _load_migration
from app.main import create_app


class Phase9TrustSafetyModerationTests(unittest.TestCase):
    def setUp(self) -> None:
        rate_limiter.reset()
        self.settings = Settings(
            app_env="test",
            database_url="sqlite:///:memory:",
        )
        self.app = create_app(settings=self.settings)
        self.db_manager = self.app.state.db_manager
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        rate_limiter.reset()
        asyncio.run(self.db_manager.dispose())

    def _register_user(
        self, handle: str, role: str = "member", community_mod_slug: str | None = None
    ) -> tuple[TestClient, str, str]:
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
        user_id = data["user_id"]
        csrf = data["csrf_token"]

        if role != "member" or community_mod_slug:
            async def _elevate() -> None:
                async with self.db_manager.session_scope() as session:
                    if role != "member":
                        await session.execute(
                            "UPDATE users SET role = ? WHERE id = ?",
                            (role, user_id),
                        )
                    if community_mod_slug:
                        comm_rows = await session.execute(
                            "SELECT id FROM communities WHERE slug = ?",
                            (community_mod_slug,),
                        )
                        comm_id = str(comm_rows[0][0])
                        await session.execute(
                            """
                            INSERT OR REPLACE INTO community_memberships
                            (user_id, community_id, role, status, joined_at)
                            VALUES (?, ?, 'moderator', 'active', ?)
                            """,
                            (user_id, comm_id, datetime.now(timezone.utc).isoformat()),
                        )

            asyncio.run(_elevate())
        return c, user_id, csrf

    def test_01_reporting_validation_duplicate_rate_limit_and_privacy(self) -> None:
        author_c, author_id, author_csrf = self._register_user("author_r1")
        rep_c, rep_id, rep_csrf = self._register_user("reporter_r1")
        other_c, _, other_csrf = self._register_user("other_viewer_r1")

        post_resp = author_c.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": author_csrf},
            json={
                "community_slug": "workplace-rants",
                "post_type": "rant",
                "identity_mode": "anonymous",
                "title": "Unpaid weekend overtime expectations",
                "body": "Management expects us online every Sunday without comp-off.",
                "content_language": "en",
            },
        )
        self.assertEqual(post_resp.status_code, 201)
        post_id = post_resp.json()["id"]

        # Unauthenticated report fails with 401
        unauth = self.client.post(
            "/api/v1/reports",
            json={"target_type": "post", "target_id": post_id, "reason_code": "spam"},
        )
        self.assertEqual(unauth.status_code, 401)

        # Invalid reason code fails with 422 INVALID_REPORT_REASON
        bad_reason = rep_c.post(
            "/api/v1/reports",
            headers={"X-CSRF-Token": rep_csrf},
            json={"target_type": "post", "target_id": post_id, "reason_code": "i_disagree"},
        )
        self.assertEqual(bad_reason.status_code, 422)
        self.assertEqual(bad_reason.json()["error"]["code"], "INVALID_REPORT_REASON")

        # Unknown target fails with 404 TARGET_NOT_FOUND
        bad_target = rep_c.post(
            "/api/v1/reports",
            headers={"X-CSRF-Token": rep_csrf},
            json={"target_type": "post", "target_id": "nonexistent-post-999", "reason_code": "spam"},
        )
        self.assertEqual(bad_target.status_code, 404)
        self.assertEqual(bad_target.json()["error"]["code"], "TARGET_NOT_FOUND")

        # Valid report submission succeeds with 201
        valid_rep = rep_c.post(
            "/api/v1/reports",
            headers={"X-CSRF-Token": rep_csrf},
            json={
                "target_type": "post",
                "target_id": post_id,
                "reason_code": "harassment",
                "details": "Checking moderator review workflow.",
            },
        )
        self.assertEqual(valid_rep.status_code, 201, valid_rep.text)
        rep_body = valid_rep.json()
        self.assertEqual(rep_body["priority_score"], 5)
        self.assertEqual(rep_body["status"], "open")
        self.assertFalse(rep_body["protective_hold_triggered"])

        # Duplicate report from same account returns 409 DUPLICATE_REPORT
        dup_rep = rep_c.post(
            "/api/v1/reports",
            headers={"X-CSRF-Token": rep_csrf},
            json={"target_type": "post", "target_id": post_id, "reason_code": "doxxing_pii"},
        )
        self.assertEqual(dup_rep.status_code, 409)
        self.assertEqual(dup_rep.json()["error"]["code"], "DUPLICATE_REPORT")

        # Reporter can see their own report in /api/v1/reports/mine, while other users see 0
        mine = rep_c.get("/api/v1/reports/mine")
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(len(mine.json()["items"]), 1)
        other_mine = other_c.get("/api/v1/reports/mine")
        self.assertEqual(len(other_mine.json()["items"]), 0)

        # Author deletes post -> reporting deleted post returns 410 TARGET_NO_LONGER_ELIGIBLE
        del_resp = author_c.delete(f"/api/v1/posts/{post_id}", headers={"X-CSRF-Token": author_csrf})
        self.assertEqual(del_resp.status_code, 200)
        rep_deleted = other_c.post(
            "/api/v1/reports",
            headers={"X-CSRF-Token": other_csrf},
            json={"target_type": "post", "target_id": post_id, "reason_code": "spam"},
        )
        self.assertEqual(rep_deleted.status_code, 410)
        self.assertEqual(rep_deleted.json()["error"]["code"], "TARGET_NO_LONGER_ELIGIBLE")

    def test_02_high_severity_velocity_protective_hold_and_window(self) -> None:
        author_c, author_id, author_csrf = self._register_user("author_vel")
        r1_c, r1_id, r1_csrf = self._register_user("rep_vel_1")
        r2_c, r2_id, r2_csrf = self._register_user("rep_vel_2")
        r3_c, r3_id, r3_csrf = self._register_user("rep_vel_3")
        r4_c, r4_id, r4_csrf = self._register_user("rep_vel_4")

        # Create 2 posts: Post A (low-severity reports) and Post B (high-severity velocity reports)
        pa = author_c.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": author_csrf},
            json={
                "community_slug": "workplace-rants",
                "post_type": "rant",
                "identity_mode": "anonymous",
                "title": "Legitimate criticism of return-to-office policy",
                "body": "Forcing a 2-hour commute to sit on Zoom calls all day is unproductive.",
                "content_language": "en",
            },
        ).json()
        pb = author_c.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": author_csrf},
            json={
                "community_slug": "workplace-rants",
                "post_type": "rant",
                "identity_mode": "anonymous",
                "title": "Post reported for potential doxxing exposure",
                "body": "Contains details flagged by multiple community members.",
                "content_language": "en",
            },
        ).json()

        # 3 distinct low-severity ('misleading_allegation' / 'spam') reports on Post A do NOT trigger auto-hold!
        for rc, r_csrf in [(r1_c, r1_csrf), (r2_c, r2_csrf), (r3_c, r3_csrf)]:
            res = rc.post(
                "/api/v1/reports",
                headers={"X-CSRF-Token": r_csrf},
                json={"target_type": "post", "target_id": pa["id"], "reason_code": "misleading_allegation"},
            )
            self.assertEqual(res.status_code, 201)
            self.assertFalse(res.json()["protective_hold_triggered"])

        # Post A remains publicly visible in feed
        feed_a = self.client.get("/api/v1/feed?mode=latest").json()["items"]
        self.assertTrue(any(item["id"] == pa["id"] for item in feed_a))

        # Now test Post B with an expired report outside the 30-minute window:
        # Reporter 1 submits 'doxxing_pii', then we backdate Reporter 1's report to 45 minutes ago
        res_b1 = r1_c.post(
            "/api/v1/reports",
            headers={"X-CSRF-Token": r1_csrf},
            json={"target_type": "post", "target_id": pb["id"], "reason_code": "doxxing_pii"},
        )
        self.assertEqual(res_b1.status_code, 201)
        self.assertEqual(res_b1.json()["priority_score"], 10)
        self.assertFalse(res_b1.json()["protective_hold_triggered"])
        rep1_id = res_b1.json()["id"]

        async def _backdate_report_1() -> None:
            old_ts = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
            async with self.db_manager.session_scope() as session:
                await session.execute(
                    "UPDATE reports SET created_at = ? WHERE id = ?",
                    (old_ts, rep1_id),
                )

        asyncio.run(_backdate_report_1())

        # Reporter 2 and Reporter 3 submit within the 30-min window -> only 2 in window (since R1 is 45m old) -> NO hold yet!
        res_b2 = r2_c.post(
            "/api/v1/reports",
            headers={"X-CSRF-Token": r2_csrf},
            json={"target_type": "post", "target_id": pb["id"], "reason_code": "threat"},
        )
        self.assertFalse(res_b2.json()["protective_hold_triggered"])

        res_b3 = r3_c.post(
            "/api/v1/reports",
            headers={"X-CSRF-Token": r3_csrf},
            json={"target_type": "post", "target_id": pb["id"], "reason_code": "doxxing_pii"},
        )
        self.assertFalse(res_b3.json()["protective_hold_triggered"])

        # Reporter 4 submits within the 30-min window -> 3 distinct reporters in 30m window -> AUTO-HOLD TRIGGERED!
        res_b4 = r4_c.post(
            "/api/v1/reports",
            headers={"X-CSRF-Token": r4_csrf},
            json={"target_type": "post", "target_id": pb["id"], "reason_code": "doxxing_pii"},
        )
        self.assertEqual(res_b4.status_code, 201)
        self.assertTrue(res_b4.json()["protective_hold_triggered"])
        self.assertEqual(res_b4.json()["status"], "in_review")

        # Post B is now hidden from public feeds and search while in 'awaiting_review'
        feed_after = self.client.get("/api/v1/feed?mode=latest").json()["items"]
        self.assertFalse(any(item["id"] == pb["id"] for item in feed_after))
        search_after = self.client.get("/api/v1/search?q=doxxing").json()["items"]
        self.assertFalse(any(item["id"] == pb["id"] for item in search_after))

        # Author was NOT automatically suspended and received a privacy-safe notification
        notifs = author_c.get("/api/v1/notifications").json()["items"]
        self.assertTrue(any("Temporary Protective Hold" in n["title"] for n in notifs))
        for n in notifs:
            self.assertNotIn("rep_vel", json.dumps(n))

    def test_03_moderator_rbac_privacy_blind_queue_and_multilingual_escalation(self) -> None:
        author_c, author_id, author_csrf = self._register_user("secret_anon_author")
        rep_c, rep_id, rep_csrf = self._register_user("queue_reporter")
        member_c, _, _ = self._register_user("regular_member")
        comm_mod_c, _, comm_mod_csrf = self._register_user(
            "rants_comm_mod", role="member", community_mod_slug="workplace-rants"
        )
        global_mod_c, _, global_mod_csrf = self._register_user(
            "global_mod_one", role="global_moderator"
        )

        # Author publishes an ANONYMOUS Malayalam post in c/workplace-rants
        anon_post = author_c.post(
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

        rep_c.post(
            "/api/v1/reports",
            headers={"X-CSRF-Token": rep_csrf},
            json={
                "target_type": "post",
                "target_id": anon_post["id"],
                "reason_code": "harassment",
                "details": "Reported Malayalam post for review.",
            },
        )

        # 1. Regular member is blocked from moderator queue (403 FORBIDDEN_ROLE)
        self.assertEqual(member_c.get("/api/v1/moderation/queue").status_code, 403)

        # 2. Community moderator of c/workplace-rants CAN view queue for c/workplace-rants
        q_resp = comm_mod_c.get("/api/v1/moderation/queue?content_language=ml")
        self.assertEqual(q_resp.status_code, 200, q_resp.text)
        q_items = q_resp.json()["items"]
        self.assertEqual(len(q_items), 1)

        # CRITICAL PRIVACY-BLIND CHECK:
        # Ensure author_id, 'secret_anon_author', rep_id, and 'queue_reporter' NEVER appear anywhere in queue payload!
        raw_queue_json = json.dumps(q_resp.json())
        self.assertNotIn(author_id, raw_queue_json)
        self.assertNotIn("secret_anon_author", raw_queue_json)
        self.assertNotIn(rep_id, raw_queue_json)
        self.assertNotIn("queue_reporter", raw_queue_json)
        self.assertEqual(
            q_items[0]["target_preview"]["public_author"]["display_name"],
            "Anonymous Member",
        )
        self.assertIsNone(q_items[0]["target_preview"]["public_author"]["handle"])

        # 3. Community moderator cannot view queue for a different community (c/salary-talk -> 403)
        other_comm_q = comm_mod_c.get("/api/v1/moderation/queue?community_slug=salary-talk")
        self.assertEqual(other_comm_q.status_code, 403)
        self.assertEqual(other_comm_q.json()["error"]["code"], "FORBIDDEN_MODERATION_SCOPE")

        # 4. Community moderator cannot issue platform-wide user_cooldown (403 FORBIDDEN_MODERATION_SCOPE)
        forbid_cooldown = comm_mod_c.post(
            "/api/v1/moderation/actions",
            headers={"X-CSRF-Token": comm_mod_csrf},
            json={
                "target_type": "user",
                "target_id": "regular_member",
                "action_type": "user_cooldown",
                "reason_code": "harassment",
                "internal_note": "Trying platform cooldown as community mod",
                "public_explanation": "Cooldown notice",
            },
        )
        self.assertEqual(forbid_cooldown.status_code, 403)
        self.assertEqual(forbid_cooldown.json()["error"]["code"], "FORBIDDEN_MODERATION_SCOPE")

        # 5. Community moderator does not read Malayalam -> clicks "Escalate — Language Specialist Needed"
        esc_resp = comm_mod_c.post(
            "/api/v1/moderation/actions",
            headers={"X-CSRF-Token": comm_mod_csrf},
            json={
                "target_type": "post",
                "target_id": anon_post["id"],
                "action_type": "escalate_language_specialist",
                "reason_code": "language_specialist_needed",
                "internal_note": "Escalating Malayalam post to Malayalam-fluent moderator.",
                "public_explanation": "Escalated for native-language review.",
            },
        )
        self.assertEqual(esc_resp.status_code, 201, esc_resp.text)

        # Verify report is now in 'escalated_language_specialist' status while post remains 'published'
        esc_q = global_mod_c.get("/api/v1/moderation/queue?status=escalated_language_specialist")
        self.assertEqual(len(esc_q.json()["items"]), 1)

    def test_04_appeals_separation_of_duties_restoration_and_independent_restrictions(self) -> None:
        author_c, author_id, author_csrf = self._register_user("appellant_user")
        bystander_c, _, bystander_csrf = self._register_user("bystander_user")
        mod1_c, mod1_id, mod1_csrf = self._register_user("mod_actor_1", role="global_moderator")
        mod2_c, mod2_id, mod2_csrf = self._register_user("mod_reviewer_2", role="global_moderator")

        post = author_c.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": author_csrf},
            json={
                "community_slug": "salary-talk",
                "post_type": "discussion",
                "identity_mode": "pseudonymous",
                "title": "Compensation band comparison for Senior Backend Engineers",
                "body": "Sharing anonymized base and bonus ranges across Bengaluru and Kochi.",
                "content_language": "en",
            },
        ).json()

        # Global Mod 1 removes the post erroneously
        act_resp = mod1_c.post(
            "/api/v1/moderation/actions",
            headers={"X-CSRF-Token": mod1_csrf},
            json={
                "target_type": "post",
                "target_id": post["id"],
                "action_type": "remove_content",
                "reason_code": "confidential_ip",
                "internal_note": "Flagged salary bands as confidential IP.",
                "public_explanation": "Removed under confidential information policy.",
            },
        )
        self.assertEqual(act_resp.status_code, 201)
        action_id = act_resp.json()["id"]

        # Post is no longer in public feed
        self.assertEqual(len(self.client.get("/api/v1/feed").json()["items"]), 0)

        # Bystander cannot appeal someone else's moderation action (403 FORBIDDEN_NOT_AFFECTED_USER)
        bad_appeal = bystander_c.post(
            "/api/v1/moderation/appeals",
            headers={"X-CSRF-Token": bystander_csrf},
            json={
                "moderation_action_id": action_id,
                "appeal_statement": "I am not the author but I want to appeal this.",
            },
        )
        self.assertEqual(bad_appeal.status_code, 403)
        self.assertEqual(bad_appeal.json()["error"]["code"], "FORBIDDEN_NOT_AFFECTED_USER")

        # Author checks /api/v1/moderation/my-actions and submits a valid appeal
        my_actions = author_c.get("/api/v1/moderation/my-actions").json()["items"]
        self.assertEqual(len(my_actions), 1)
        self.assertEqual(my_actions[0]["id"], action_id)

        ap_resp = author_c.post(
            "/api/v1/moderation/appeals",
            headers={"X-CSRF-Token": author_csrf},
            json={
                "moderation_action_id": action_id,
                "appeal_statement": "Discussing general salary bands is protected workplace expression and contains no proprietary IP.",
            },
        )
        self.assertEqual(ap_resp.status_code, 201, ap_resp.text)
        appeal_id = ap_resp.json()["id"]

        # Duplicate appeal on the same action returns 409 APPEAL_ALREADY_EXISTS
        dup_ap = author_c.post(
            "/api/v1/moderation/appeals",
            headers={"X-CSRF-Token": author_csrf},
            json={
                "moderation_action_id": action_id,
                "appeal_statement": "Second appeal attempt on same action.",
            },
        )
        self.assertEqual(dup_ap.status_code, 409)
        self.assertEqual(dup_ap.json()["error"]["code"], "APPEAL_ALREADY_EXISTS")

        # SEPARATION OF DUTIES: Mod 1 (original decision-maker) CANNOT decide their own appeal!
        self_review = mod1_c.post(
            f"/api/v1/moderation/appeals/{appeal_id}/decision",
            headers={"X-CSRF-Token": mod1_csrf},
            json={
                "decision": "rejected",
                "decision_reason_code": "confidential_ip",
                "review_decision_note": "I stand by my own decision.",
            },
        )
        self.assertEqual(self_review.status_code, 403)
        self.assertEqual(self_review.json()["error"]["code"], "SEPARATION_OF_DUTIES_VIOLATION")

        # Independent Mod 2 reviews and accepts the appeal -> restores post to 'published'!
        decide_ok = mod2_c.post(
            f"/api/v1/moderation/appeals/{appeal_id}/decision",
            headers={"X-CSRF-Token": mod2_csrf},
            json={
                "decision": "accepted",
                "decision_reason_code": "appeal_overturned",
                "review_decision_note": "Salary discussions are explicitly protected on Pressure Out. Restoring post.",
            },
        )
        self.assertEqual(decide_ok.status_code, 200, decide_ok.text)
        self.assertEqual(decide_ok.json()["status"], "accepted")

        # Post is back in public feed!
        self.assertEqual(len(self.client.get("/api/v1/feed").json()["items"]), 1)

        # Verify independent account restrictions are preserved when only one appeal is accepted:
        # Mod 1 applies user_cooldown AND user_suspend to bystander_user
        act_cool = mod1_c.post(
            "/api/v1/moderation/actions",
            headers={"X-CSRF-Token": mod1_csrf},
            json={
                "target_type": "user",
                "target_id": "bystander_user",
                "action_type": "user_cooldown",
                "reason_code": "spam",
                "internal_note": "Cooldown 1",
                "public_explanation": "Cooldown for spam",
            },
        ).json()
        ap_cool = bystander_c.post(
            "/api/v1/moderation/appeals",
            headers={"X-CSRF-Token": bystander_csrf},
            json={
                "moderation_action_id": act_cool["id"],
                "appeal_statement": "Appealing the cooldown decision.",
            },
        ).json()
        # Separate suspension applied by Mod 1 (note: user_suspend revokes sessions, so we submit appeal before or check account status after)
        mod1_c.post(
            "/api/v1/moderation/actions",
            headers={"X-CSRF-Token": mod1_csrf},
            json={
                "target_type": "user",
                "target_id": "bystander_user",
                "action_type": "user_suspend",
                "reason_code": "threat",
                "internal_note": "Separate suspension for threats",
                "public_explanation": "Suspended for threat policy violation",
            },
        )
        # Mod 2 overturns ONLY the cooldown appeal -> account must remain 'suspended' because the separate suspension was NOT overturned!
        mod2_c.post(
            f"/api/v1/moderation/appeals/{ap_cool['id']}/decision",
            headers={"X-CSRF-Token": mod2_csrf},
            json={
                "decision": "accepted",
                "decision_reason_code": "appeal_overturned",
                "review_decision_note": "Overturning spam cooldown only.",
            },
        )

        async def _get_bystander_status() -> str:
            async with self.db_manager.session_scope() as session:
                rows = await session.execute(
                    """
                    SELECT u.account_status FROM users u
                    JOIN public_profiles pp ON pp.user_id = u.id
                    WHERE pp.handle_normalized = 'bystander_user'
                    """
                )
                return str(rows[0][0])

        self.assertEqual(asyncio.run(_get_bystander_status()), "suspended")

    def test_05_blocking_and_muting_interactions_feed_filtering_and_anonymous_privacy(self) -> None:
        ua_c, _, ua_csrf = self._register_user("alice_worker")
        ub_c, _, ub_csrf = self._register_user("bob_coworker")
        uc_c, _, _ = self._register_user("charlie_reader")

        # Self-block is rejected with 422 CANNOT_BLOCK_SELF
        self_blk = ua_c.put(
            "/api/v1/users/alice_worker/block",
            headers={"X-CSRF-Token": ua_csrf},
            json={"active": True, "mode": "block"},
        )
        self.assertEqual(self_blk.status_code, 422)
        self.assertEqual(self_blk.json()["error"]["code"], "CANNOT_BLOCK_SELF")

        # Bob creates 1 pseudonymous post and 1 anonymous post; Alice creates 1 post
        pa = ua_c.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": ua_csrf},
            json={
                "community_slug": "general-workplace",
                "post_type": "discussion",
                "identity_mode": "pseudonymous",
                "title": "Alice's workplace thread",
                "body": "Open for respectful discussion.",
                "content_language": "en",
            },
        ).json()
        pb_pseudo = ub_c.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": ub_csrf},
            json={
                "community_slug": "general-workplace",
                "post_type": "discussion",
                "identity_mode": "pseudonymous",
                "title": "Bob's pseudonymous post",
                "body": "Visible to everyone unless muted/blocked.",
                "content_language": "en",
            },
        ).json()
        pb_anon = ub_c.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": ub_csrf},
            json={
                "community_slug": "general-workplace",
                "post_type": "rant",
                "identity_mode": "anonymous",
                "title": "Bob's anonymous rant",
                "body": "Published anonymously.",
                "content_language": "en",
            },
        ).json()

        # 1. Alice MUTES Bob -> Bob's posts are hidden from Alice's feed, but Charlie still sees all 3 posts!
        mute_res = ua_c.put(
            "/api/v1/users/bob_coworker/block",
            headers={"X-CSRF-Token": ua_csrf},
            json={"active": True, "mode": "mute"},
        )
        self.assertEqual(mute_res.status_code, 200)
        self.assertEqual(mute_res.json()["mode"], "mute")

        alice_feed_ids = [p["id"] for p in ua_c.get("/api/v1/feed").json()["items"]]
        self.assertIn(pa["id"], alice_feed_ids)
        self.assertNotIn(pb_pseudo["id"], alice_feed_ids)
        self.assertNotIn(pb_anon["id"], alice_feed_ids)

        charlie_feed_ids = [p["id"] for p in uc_c.get("/api/v1/feed").json()["items"]]
        self.assertEqual(len(charlie_feed_ids), 3)

        # 2. Alice upgrades to BLOCK on Bob -> Bob cannot comment, vote, or react on Alice's post!
        blk_res = ua_c.put(
            "/api/v1/users/bob_coworker/block",
            headers={"X-CSRF-Token": ua_csrf},
            json={"active": True, "mode": "block"},
        )
        self.assertEqual(blk_res.status_code, 200)
        self.assertEqual(blk_res.json()["mode"], "block")

        bob_comment = ub_c.post(
            f"/api/v1/posts/{pa['id']}/comments",
            headers={"X-CSRF-Token": ub_csrf},
            json={"body": "Trying to comment while blocked", "content_language": "en"},
        )
        self.assertEqual(bob_comment.status_code, 403)
        self.assertEqual(bob_comment.json()["error"]["code"], "INTERACTION_BLOCKED")

        bob_vote = ub_c.put(
            f"/api/v1/posts/{pa['id']}/vote",
            headers={"X-CSRF-Token": ub_csrf},
            json={"value": 1},
        )
        self.assertEqual(bob_vote.status_code, 403)
        self.assertEqual(bob_vote.json()["error"]["code"], "INTERACTION_BLOCKED")

        # Alice can inspect her block list in /api/v1/me/blocks
        blocks_list = ua_c.get("/api/v1/me/blocks").json()["items"]
        self.assertEqual(len(blocks_list), 1)
        self.assertEqual(blocks_list[0]["handle"], "bob_coworker")

        # 3. Alice unblocks Bob -> Bob's posts reappear in Alice's feed and Bob can vote/comment again!
        unblk = ua_c.put(
            "/api/v1/users/bob_coworker/block",
            headers={"X-CSRF-Token": ua_csrf},
            json={"active": False, "mode": "block"},
        )
        self.assertEqual(unblk.status_code, 200)
        self.assertFalse(unblk.json()["active"])

        alice_feed_restored = [p["id"] for p in ua_c.get("/api/v1/feed").json()["items"]]
        self.assertIn(pb_pseudo["id"], alice_feed_restored)

        bob_vote_ok = ub_c.put(
            f"/api/v1/posts/{pa['id']}/vote",
            headers={"X-CSRF-Token": ub_csrf},
            json={"value": 1},
        )
        self.assertEqual(bob_vote_ok.status_code, 200)

    def test_06_audit_trail_admin_only_redaction_and_append_only_immutability(self) -> None:
        author_c, author_id, author_csrf = self._register_user("anon_audit_author")
        mod_c, _, mod_csrf = self._register_user("global_mod_audit", role="global_moderator")
        admin_c, _, _ = self._register_user("platform_admin", role="admin")

        anon_post = author_c.post(
            "/api/v1/posts",
            headers={"X-CSRF-Token": author_csrf},
            json={
                "community_slug": "workplace-rants",
                "post_type": "rant",
                "identity_mode": "anonymous",
                "title": "Anonymous post moderated and audited",
                "body": "My manager John Smith scheduled an 11 PM call.",
                "content_language": "en",
                "acknowledge_pii_warning": True,
            },
        ).json()

        mod_c.post(
            "/api/v1/moderation/actions",
            headers={"X-CSRF-Token": mod_csrf},
            json={
                "target_type": "post",
                "target_id": anon_post["id"],
                "action_type": "restrict_visibility",
                "reason_code": "doxxing_pii",
                "internal_note": "Restricting visibility for PII check",
                "public_explanation": "Restricted under privacy guidelines.",
            },
        )

        # Global moderator and regular users CANNOT access /api/v1/moderation/audit (403 FORBIDDEN_ROLE)
        self.assertEqual(author_c.get("/api/v1/moderation/audit").status_code, 403)
        self.assertEqual(mod_c.get("/api/v1/moderation/audit").status_code, 403)

        # Admin CAN query /api/v1/moderation/audit and filter by action_name / reason_code
        audit_resp = admin_c.get(
            "/api/v1/moderation/audit?event_category=moderation&action_name=restrict_visibility"
        )
        self.assertEqual(audit_resp.status_code, 200, audit_resp.text)
        audit_items = audit_resp.json()["items"]
        self.assertEqual(len(audit_items), 1)

        # Verify anonymous author's user_id NEVER appears in the audit log response!
        self.assertNotIn(author_id, json.dumps(audit_resp.json()))

        # Verify database-level append-only triggers reject UPDATE and DELETE on audit_events
        async def _attempt_audit_tampering() -> None:
            async with self.db_manager.session_scope() as session:
                with self.assertRaises(sqlite3.IntegrityError):
                    await session.execute("UPDATE audit_events SET action_name = 'tampered'")
                with self.assertRaises(sqlite3.IntegrityError):
                    await session.execute("DELETE FROM audit_events")

        asyncio.run(_attempt_audit_tampering())

        # Verify migration 0008 upgrade/downgrade round-trip
        conn = sqlite3.connect(":memory:")
        for fname in (
            "0002_phase3_identity_and_privacy.py",
            "0003_phase4_core_social_posting.py",
            "0004_phase5_communities.py",
            "0005_phase6_comments_engagement_notifications.py",
            "0006_phase7_feed_search_discovery.py",
            "0007_phase8_ai_meme_studio.py",
            "0008_phase9_trust_safety_moderation.py",
        ):
            _load_migration(fname).upgrade(conn)

        mig8 = _load_migration("0008_phase9_trust_safety_moderation.py")
        mig8.downgrade(conn)
        tables_after_down = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        self.assertNotIn("reports", tables_after_down)
        self.assertNotIn("audit_events", tables_after_down)

        mig8.upgrade(conn)
        tables_after_up = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for tbl in ("reports", "moderation_actions", "moderation_appeals", "user_blocks", "audit_events"):
            self.assertIn(tbl, tables_after_up)
        conn.close()


if __name__ == "__main__":
    unittest.main()
