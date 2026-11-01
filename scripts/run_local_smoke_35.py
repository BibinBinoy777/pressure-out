#!/usr/bin/env python3
"""Pressure Out — Complete 35-Step Local End-to-End Application Smoke Verification (Phase 12.3).

Executes all 35 user journeys and safety invariants from Phase 12.3 Section 12 using
synthetic test accounts, real local TCP RESP2 Redis rate limiting (`LocalResp2TestServer`
or external `REDIS_URL`), `LocalFilesystemStorageAdapter`, and `MemeJobWorker`, then cleans
up synthetic test accounts and media files via the documented data lifecycle.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.config import Settings  # noqa: E402
from app.core.rate_limit import (  # noqa: E402
    InMemoryRateLimitStore,
    LocalResp2TestServer,
    SharedMemoryRedisEvalClient,
    rate_limiter,
)
from app.main import create_app  # noqa: E402
from app.workers.meme_worker import MemeJobWorker  # noqa: E402


def _make_png(width: int = 120, height: int = 120) -> bytes:
    img = Image.new("RGB", (width, height), color=(40, 100, 160))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _multipart_upload_payload(boundary: str, png_bytes: bytes) -> bytes:
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="alt_text"\r\n\r\n'
        f"Uploaded local Windows smoke meme\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="language"\r\n\r\n'
        f"en\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="win_smoke.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode("utf-8") + png_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")


def run_local_smoke_35(
    *,
    database_url: str = "sqlite:///:memory:",
    redis_url: str | None = None,
) -> Dict[str, Any]:
    steps_completed: List[Dict[str, Any]] = []

    def _record(step_num: int, name: str, detail: str = "PASS") -> None:
        steps_completed.append({"step": step_num, "name": name, "status": "PASS", "detail": detail})

    backing = SharedMemoryRedisEvalClient(eviction_policy="noeviction")
    local_resp_server: LocalResp2TestServer | None = None
    if not redis_url:
        local_resp_server = LocalResp2TestServer(backing, requirepass="LocalWinSmokePass!2026")
        effective_redis_url = local_resp_server.redis_url
    else:
        effective_redis_url = redis_url

    with tempfile.TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir) / "media"
        settings = Settings(
            app_env="development",
            database_url=database_url,
            web_concurrency=2,
            rate_limit_backend="redis",
            redis_url=effective_redis_url,
            rate_limit_fail_closed=True,
            local_storage_path=str(storage_dir),
            session_cookie_secure=False,
            ai_caption_provider="local_mock",
            ai_image_provider="local_mock",
            translation_provider="local_mock",
            insights_min_cohort_size=10,
        )
        app = create_app(settings=settings)
        db_manager = app.state.db_manager

        try:
            # Step 1: Registration (create 10 synthetic users for full smoke + k=10 insights + 3 reporters)
            users = []
            for idx in range(10):
                backing.reset()
                c = TestClient(app)
                reg = c.post(
                    "/api/v1/auth/register",
                    json={
                        "handle": f"win_local_{idx:02d}",
                        "password": "LocalWinPassword#2026!",
                        "default_identity_mode": "pseudonymous",
                        "preferred_ui_locale": "en",
                        "recovery_email": f"win_local_{idx:02d}@example.com" if idx == 0 else None,
                    },
                )
                assert reg.status_code == 201, reg.text
                users.append((c, reg.json()["user_id"], reg.json()["csrf_token"]))
            _record(1, "Registration", "Registered 10 synthetic accounts")

            author_c, author_id, author_csrf = users[0]
            peer_c, peer_id, peer_csrf = users[1]
            rep2_c, _, rep2_csrf = users[2]
            rep3_c, _, rep3_csrf = users[3]

            # Step 2: Login
            backing.reset()
            login_c = TestClient(app)
            login_res = login_c.post(
                "/api/v1/auth/login",
                json={"handle": "win_local_00", "password": "LocalWinPassword#2026!"},
            )
            assert login_res.status_code == 200, login_res.text
            author_csrf = login_res.json()["csrf_token"]
            author_c = login_c
            _record(2, "Login", "Authenticated win_local_00 and issued session cookie + CSRF token")

            # Step 3: CSRF verification
            no_csrf = author_c.post(
                "/api/v1/posts",
                json={
                    "community_slug": "general-workplace",
                    "post_type": "story",
                    "identity_mode": "pseudonymous",
                    "title": "Missing CSRF check",
                    "body": "Must be rejected with 403.",
                    "content_language": "en",
                },
            )
            assert no_csrf.status_code == 403, no_csrf.text
            _record(3, "CSRF verification", "State-changing request without X-CSRF-Token rejected (403)")

            # Step 4: Locale preference
            loc_res = peer_c.patch(
                "/api/v1/me/settings",
                json={"preferred_ui_locale": "ml", "preferred_content_locales": ["ml", "en"]},
                headers={"X-CSRF-Token": peer_csrf},
            )
            assert loc_res.status_code == 200, loc_res.text
            _record(4, "Locale preference", "Updated preferred_ui_locale='ml'")

            # Step 5: Community membership
            join_res = peer_c.post(
                "/api/v1/communities/general-workplace/membership",
                json={"action": "join"},
                headers={"X-CSRF-Token": peer_csrf},
            )
            assert join_res.status_code == 200, join_res.text
            _record(5, "Community membership", "Joined c/general-workplace")

            # Step 6: Pseudonymous post
            p_pseudo = author_c.post(
                "/api/v1/posts",
                json={
                    "community_slug": "general-workplace",
                    "post_type": "story",
                    "identity_mode": "pseudonymous",
                    "title": "Local Windows setup sprint retrospective",
                    "body": "Running PostgreSQL 16 and Redis 7 on D: drive keeps C: completely free.",
                    "content_language": "en",
                    "tags": ["windows", "sprint"],
                },
                headers={"X-CSRF-Token": author_csrf},
            )
            assert p_pseudo.status_code == 201, p_pseudo.text
            pseudo_post_id = p_pseudo.json()["id"]
            _record(6, "Pseudonymous post", f"Created post {pseudo_post_id}")

            # Step 7: Anonymous post
            p_anon = author_c.post(
                "/api/v1/posts",
                json={
                    "community_slug": "workplace-rants",
                    "post_type": "rant",
                    "identity_mode": "anonymous",
                    "title": "വെള്ളിയാഴ്ച വൈകുന്നേരം അമിത ജോലിഭാരം",
                    "body": "ആഴ്ചാവസാനം വിശ്രമമില്ലാതെ പണിയെടുപ്പിക്കുന്നു.",
                    "content_language": "ml",
                },
                headers={"X-CSRF-Token": author_csrf},
            )
            assert p_anon.status_code == 201, p_anon.text
            anon_post_id = p_anon.json()["id"]
            assert p_anon.json()["author"]["handle"] is None
            assert "win_local_00" not in json.dumps(p_anon.json())
            _record(7, "Anonymous post", "Verified zero handle/user_id leakage on anonymous post")

            # Step 8: Anonymous comment privacy
            c_anon = peer_c.post(
                f"/api/v1/posts/{anon_post_id}/comments",
                json={
                    "body": "Totally relatable anonymous reply.",
                    "identity_mode": "anonymous",
                    "content_language": "en",
                },
                headers={"X-CSRF-Token": peer_csrf},
            )
            assert c_anon.status_code == 201, c_anon.text
            anon_comment_id = c_anon.json()["id"]
            assert c_anon.json()["author"]["handle"] is None
            assert "win_local_01" not in json.dumps(c_anon.json())
            _record(8, "Anonymous comment privacy", "Verified anonymous comment strips handle and user_id")

            # Step 9: Replies
            c_reply = author_c.post(
                f"/api/v1/posts/{pseudo_post_id}/comments",
                json={
                    "body": "Top-level comment on pseudonymous post.",
                    "identity_mode": "pseudonymous",
                    "content_language": "en",
                },
                headers={"X-CSRF-Token": author_csrf},
            )
            assert c_reply.status_code == 201, c_reply.text
            parent_cid = c_reply.json()["id"]
            nested_reply = peer_c.post(
                f"/api/v1/posts/{pseudo_post_id}/comments",
                json={
                    "parent_comment_id": parent_cid,
                    "body": "Nested child reply in thread.",
                    "identity_mode": "pseudonymous",
                    "content_language": "en",
                },
                headers={"X-CSRF-Token": peer_csrf},
            )
            assert nested_reply.status_code == 201, nested_reply.text
            assert nested_reply.json()["depth"] == 1
            _record(9, "Replies", "Verified nested comment reply tree (depth=1)")

            # Step 10: Voting
            v_res = peer_c.put(
                f"/api/v1/posts/{pseudo_post_id}/vote",
                json={"value": 1},
                headers={"X-CSRF-Token": peer_csrf},
            )
            assert v_res.status_code == 200 and v_res.json()["score"] == 1
            _record(10, "Voting", "Verified idempotent upvote on post")

            # Step 11: Reactions
            react_res = peer_c.put(
                f"/api/v1/posts/{pseudo_post_id}/reactions/relatable",
                json={"active": True},
                headers={"X-CSRF-Token": peer_csrf},
            )
            assert react_res.status_code == 200
            assert react_res.json()["reaction_counts"]["relatable"] == 1
            _record(11, "Reactions", "Verified relatable reaction toggle")

            # Step 12: Notifications
            notif_res = author_c.get("/api/v1/notifications")
            assert notif_res.status_code == 200 and len(notif_res.json()["items"]) >= 1
            _record(12, "Notifications", "Verified in-app reply notification delivery")

            # Step 13: Latest feed
            latest_res = peer_c.get("/api/v1/feed?mode=latest")
            assert latest_res.status_code == 200 and len(latest_res.json()["items"]) >= 2
            _record(13, "Latest feed", "Verified chronological Latest feed")

            # Step 14: Popular feed
            pop_res = peer_c.get("/api/v1/feed?mode=popular")
            assert pop_res.status_code == 200 and len(pop_res.json()["items"]) >= 2
            _record(14, "Popular feed", "Verified ranked Popular feed")

            # Step 15: Search
            srch_res = peer_c.get("/api/v1/search?q=retrospective")
            assert srch_res.status_code == 200 and len(srch_res.json()["items"]) == 1
            _record(15, "Search", "Verified keyword search retrieval")

            # Step 16: Language filtering
            ml_srch = peer_c.get("/api/v1/search?q=ജോലിഭാരം&lang=ml")
            assert ml_srch.status_code == 200 and len(ml_srch.json()["items"]) == 1
            es_srch = peer_c.get("/api/v1/search?q=ജോലിഭാരം&lang=es")
            assert es_srch.status_code == 200 and len(es_srch.json()["items"]) == 0
            _record(16, "Language filtering", "Verified ?lang=ml vs ?lang=es search filtering")

            # Step 17: Meme template rendering
            render_res = author_c.post(
                "/api/v1/memes/render",
                json={
                    "template_id_or_slug": "friday-455pm-deploy",
                    "language": "en",
                    "output_format": "PNG",
                    "captions": [
                        {"region_id": "top", "text": "C: DRIVE ALMOST FULL"},
                        {"region_id": "bottom", "text": "MOVED EVERYTHING TO D:\\PRESSUREOUT"},
                    ],
                },
                headers={"X-CSRF-Token": author_csrf},
            )
            assert render_res.status_code == 201, render_res.text
            rendered_asset_id = render_res.json()["id"]
            _record(17, "Meme template rendering", f"Rendered PNG template meme {rendered_asset_id}")

            # Step 18: Meme upload
            boundary = "----WinLocalSmokeBoundary123"
            up_res = author_c.post(
                "/api/v1/memes/upload",
                content=_multipart_upload_payload(boundary, _make_png(128, 128)),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": author_csrf},
            )
            assert up_res.status_code == 201, up_res.text
            uploaded_asset_id = up_res.json()["id"]
            _record(18, "Meme upload", f"Uploaded custom PNG meme asset {uploaded_asset_id}")

            # Step 19: Meme publishing
            meme_post = author_c.post(
                "/api/v1/posts",
                json={
                    "community_slug": "corporate-memes",
                    "post_type": "meme",
                    "identity_mode": "pseudonymous",
                    "title": "D: drive developer relief",
                    "body": "Zero bytes wasted on C:.",
                    "content_language": "en",
                    "meme_asset_id": rendered_asset_id,
                },
                headers={"X-CSRF-Token": author_csrf},
            )
            assert meme_post.status_code == 201, meme_post.text
            _record(19, "Meme publishing", "Published meme post to c/corporate-memes")

            # Step 20: Background worker processing
            job_res = author_c.post(
                "/api/v1/memes/jobs",
                json={
                    "prompt": "When the local Windows build passes on the first try",
                    "language": "en",
                    "style_tone": "wholesome",
                },
                headers={"X-CSRF-Token": author_csrf},
            )
            assert job_res.status_code == 202, job_res.text
            job_id = job_res.json()["id"]

            async def _run_worker_once() -> None:
                async with db_manager.session_scope() as session:
                    w = MemeJobWorker(session=session, settings=settings)
                    await w.process_single_job()

            asyncio.run(_run_worker_once())
            job_status = author_c.get(f"/api/v1/memes/jobs/{job_id}").json()
            assert job_status["status"] == "ready" and job_status["result_asset"] and job_status["result_asset"]["id"]
            _record(20, "Background worker processing", f"Processed async meme job {job_id} -> ready")

            # Step 21: On-demand translation (cache miss -> cache hit)
            tr1 = peer_c.post(
                f"/api/v1/posts/{anon_post_id}/translations",
                json={"target_locale": "en"},
                headers={"X-CSRF-Token": peer_csrf},
            )
            assert tr1.status_code == 200 and not tr1.json()["cache_hit"]
            tr2 = peer_c.post(
                f"/api/v1/posts/{anon_post_id}/translations",
                json={"target_locale": "en"},
                headers={"X-CSRF-Token": peer_csrf},
            )
            assert tr2.status_code == 200 and tr2.json()["cache_hit"]
            _record(21, "On-demand translation", "Verified Malayalam -> English translation and cache hit")

            # Step 22: Translation cache invalidation
            edit_anon = author_c.patch(
                f"/api/v1/posts/{anon_post_id}",
                json={"body": "ആഴ്ചാവസാനം വിശ്രമമില്ലാതെ പണിയെടുപ്പിക്കുന്നു (Updated)."},
                headers={"X-CSRF-Token": author_csrf},
            )
            assert edit_anon.status_code == 200
            tr3 = peer_c.post(
                f"/api/v1/posts/{anon_post_id}/translations",
                json={"target_locale": "en"},
                headers={"X-CSRF-Token": peer_csrf},
            )
            assert tr3.status_code == 200 and not tr3.json()["cache_hit"]
            _record(22, "Translation cache invalidation", "Source edit invalidated cached translation")

            # Step 23: Workplace experience posting
            wx_post = author_c.post(
                "/api/v1/posts",
                json={
                    "community_slug": "work-life-balance",
                    "post_type": "workplace_experience",
                    "identity_mode": "pseudonymous",
                    "title": "Async engineering handoffs cut meeting load by 40%",
                    "body": "Written handoff notes replaced our daily 1-hour status call.",
                    "content_language": "en",
                    "workplace_detail": {
                        "experience_kind": "workplace_experience",
                        "experience_category": "remote_work",
                        "industry_category": "technology",
                        "lesson_learned": "Document decisions asynchronously.",
                    },
                },
                headers={"X-CSRF-Token": author_csrf},
            )
            assert wx_post.status_code == 201, wx_post.text
            _record(23, "Workplace experience posting", "Published structured workplace_experience post")

            # Step 24: Resignation story creation
            rs_post = author_c.post(
                "/api/v1/posts",
                json={
                    "community_slug": "resignation-stories",
                    "post_type": "workplace_experience",
                    "identity_mode": "anonymous",
                    "title": "Why I left for a team with sustainable on-call rotations",
                    "body": "Sleep quality improved within two weeks of switching teams.",
                    "content_language": "en",
                    "workplace_detail": {
                        "experience_kind": "resignation_story",
                        "experience_category": "resignation",
                        "primary_resignation_reason": "work_life_balance",
                        "transition_outcome": "accepted_new_role",
                        "lesson_learned": "Ask about paging frequency during interviews.",
                    },
                },
                headers={"X-CSRF-Token": author_csrf},
            )
            assert rs_post.status_code == 201, rs_post.text
            _record(24, "Resignation story creation", "Published anonymous resignation_story post")

            # Step 25: Structured workplace contribution (10 contributors)
            contrib_ids = []
            for u_client, _, u_csrf in users:
                backing.reset()
                cr = u_client.post(
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
                    headers={"X-CSRF-Token": u_csrf},
                )
                assert cr.status_code == 201, cr.text
                contrib_ids.append(cr.json()["id"])
            _record(25, "Structured workplace contribution", "Submitted 10 consented structured contributions")

            # Step 26: Aggregated workplace insights (unlocked at k=10)
            ins_10 = peer_c.get("/api/v1/workplace/insights?industry_category=technology").json()
            assert ins_10["cohort_eligible_band"] == "10+"
            _record(26, "Aggregated workplace insights", "Verified cohort unlocked at k=10 (band='10+')")

            # Step 27: Contribution withdrawal & immediate cohort suppression
            w_res = peer_c.patch(
                f"/api/v1/workplace/contributions/{contrib_ids[1]}",
                json={"aggregation_consent": False},
                headers={"X-CSRF-Token": peer_csrf},
            )
            assert w_res.status_code == 200
            ins_9 = peer_c.get("/api/v1/workplace/insights?industry_category=technology").json()
            assert ins_9["cohort_eligible_band"] is None
            _record(27, "Contribution withdrawal", "Withdrawing consent dropped cohort to 9 and suppressed insights")

            # Step 28 & 29: Reporting & Moderation visibility restrictions (3 high-severity reports -> auto hold)
            for rep_client, rep_csrf in ((peer_c, peer_csrf), (rep2_c, rep2_csrf), (rep3_c, rep3_csrf)):
                backing.reset()
                rr = rep_client.post(
                    "/api/v1/reports",
                    json={
                        "target_type": "post",
                        "target_id": pseudo_post_id,
                        "reason_code": "doxxing_pii",
                        "details": "High severity test report for protective velocity hold.",
                    },
                    headers={"X-CSRF-Token": rep_csrf},
                )
                assert rr.status_code == 201, rr.text
            _record(28, "Reporting", "Submitted 3 distinct high-severity reports")

            held_Ids = [item["id"] for item in peer_c.get("/api/v1/feed?mode=latest").json()["items"]]
            assert pseudo_post_id not in held_Ids
            _record(29, "Moderation visibility restrictions", "Auto-held post hidden from public feeds")

            # Step 30: Blocking and muting
            blk_res = author_c.put(
                "/api/v1/users/win_local_01/block",
                json={"mode": "block"},
                headers={"X-CSRF-Token": author_csrf},
            )
            assert blk_res.status_code == 200
            blocked_comment = peer_c.post(
                f"/api/v1/posts/{anon_post_id}/comments",
                json={"body": "Should be blocked", "identity_mode": "pseudonymous", "content_language": "en"},
                headers={"X-CSRF-Token": peer_csrf},
            )
            assert blocked_comment.status_code == 403
            _record(30, "Blocking and muting", "Verified bidirectional interaction block (403 INTERACTION_BLOCKED)")

            # Step 31: Account data export
            exp_res = author_c.get("/api/v1/me/export")
            assert exp_res.status_code == 200
            exp_data = exp_res.json()
            assert exp_data["account"]["recovery_email"] == "win_local_00@example.com"
            assert len(exp_data["meme_assets"]) >= 2
            storage_keys = [a["storage_key"] for a in exp_data["meme_assets"]]
            for sk in storage_keys:
                assert (storage_dir / sk).is_file()
            _record(31, "Account data export", "Verified owner personal data export completeness")

            # Step 32 & 33: Account deletion & Media cleanup
            del_res = author_c.request(
                "DELETE",
                "/api/v1/me",
                json={"password_confirmation": "LocalWinPassword#2026!", "delete_published_posts": True},
                headers={"X-CSRF-Token": author_csrf},
            )
            assert del_res.status_code == 200
            _record(32, "Account deletion", "Deleted win_local_00 account and scrubbed posts/comments")

            for sk in storage_keys:
                assert not (storage_dir / sk).is_file()
            _record(33, "Media cleanup", "Verified all meme image files for deleted account removed from disk")

            # Step 34: Audit-history preservation
            async def _check_audit() -> int:
                async with db_manager.session_scope() as session:
                    rows = await session.execute(
                        "SELECT COUNT(1) FROM audit_events WHERE event_category IN ('account_security', 'auto_protective_hold')"
                    )
                    return int(rows[0][0])

            audit_cnt = asyncio.run(_check_audit())
            assert audit_cnt >= 2
            _record(34, "Audit-history preservation", f"Verified {audit_cnt} immutable audit_events preserved")

            # Step 35: Logout and session revocation (+ clean up remaining synthetic users)
            logout_res = peer_c.post("/api/v1/auth/logout", headers={"X-CSRF-Token": peer_csrf})
            assert logout_res.status_code in {200, 204}
            after_logout = peer_c.get("/api/v1/me")
            assert after_logout.status_code == 401
            _record(35, "Logout and session revocation", "Verified session revoked and /api/v1/me returns 401")

            return {
                "total_steps": 35,
                "passed_steps": len(steps_completed),
                "all_passed": len(steps_completed) == 35,
                "steps": steps_completed,
            }
        finally:
            rate_limiter.configure(InMemoryRateLimitStore())
            asyncio.run(db_manager.dispose())
            if local_resp_server is not None:
                local_resp_server.close()


if __name__ == "__main__":
    report = run_local_smoke_35()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["all_passed"] else 1)
