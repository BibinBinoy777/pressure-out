"""Phase 3 authentication, session security, CSRF guard, recovery, and account deletion tests."""
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


class Phase3AuthAndAccountTests(unittest.TestCase):
    """Verifies registration, login, session cookies, CSRF, recovery, and account deletion."""

    def setUp(self) -> None:
        rate_limiter.reset()
        self.settings = Settings(
            app_env="test",
            database_url="sqlite:///:memory:",
            log_level="CRITICAL",
            session_cookie_secure=False,
        )
        self.app = create_app(settings=self.settings)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def tearDown(self) -> None:
        rate_limiter.reset()

    def test_zero_real_name_registration_and_case_insensitive_handle_uniqueness(self) -> None:
        res = self.client.post(
            "/api/v1/auth/register",
            json={
                "handle": "Vennikulam_Dev",
                "password": "StrongPassphrase!2026",
            },
        )
        self.assertEqual(res.status_code, 201, res.text)
        data = res.json()
        self.assertEqual(data["handle"], "Vennikulam_Dev")
        self.assertEqual(data["default_identity_mode"], "pseudonymous")
        self.assertFalse(data["has_recovery_email"])
        self.assertIsNotNone(data["csrf_token"])
        self.assertTrue(str(data["one_time_recovery_code"]).startswith("PO-"))

        set_cookie = res.headers.get("set-cookie", "")
        self.assertIn("po_session=", set_cookie)
        self.assertIn("httponly", set_cookie.lower())
        self.assertIn("samesite=lax", set_cookie.lower())

        res_dup = self.client.post(
            "/api/v1/auth/register",
            json={
                "handle": "vennikulam_dev",
                "password": "AnotherStrongPassword!2026",
            },
        )
        self.assertEqual(res_dup.status_code, 409)
        self.assertEqual(res_dup.json()["error"]["code"], "HANDLE_TAKEN")

    def test_weak_and_breached_passwords_rejected(self) -> None:
        res_short = self.client.post(
            "/api/v1/auth/register",
            json={"handle": "short_pwd_user", "password": "short"},
        )
        self.assertEqual(res_short.status_code, 422)
        self.assertEqual(res_short.json()["error"]["code"], "WEAK_PASSWORD")

        res_breached = self.client.post(
            "/api/v1/auth/register",
            json={"handle": "breached_user", "password": "password1234"},
        )
        self.assertEqual(res_breached.status_code, 422)
        self.assertEqual(res_breached.json()["error"]["code"], "WEAK_PASSWORD")

    def test_csrf_protection_enforced_on_state_changing_endpoints(self) -> None:
        reg = self.client.post(
            "/api/v1/auth/register",
            json={"handle": "csrf_tester", "password": "SafePassphrase#9876"},
        )
        self.assertEqual(reg.status_code, 201)
        csrf_token = reg.json()["csrf_token"]

        res_no_csrf = self.client.patch(
            "/api/v1/me/profile",
            json={"display_name": "Should Fail"},
        )
        self.assertEqual(res_no_csrf.status_code, 403)
        self.assertEqual(res_no_csrf.json()["error"]["code"], "CSRF_VALIDATION_FAILED")

        res_ok = self.client.patch(
            "/api/v1/me/profile",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "display_name": "മലയാളം ടെക്കി • हिन्दी • தமிழ் 🚀",
                "bio": "Unfiltered workplace thoughts.",
                "professional_profile": {
                    "role_title": "Staff Backend Engineer",
                    "industry": "FinTech",
                    "experience_band": "senior_6_10",
                    "region_label": "Kerala, India",
                    "is_enabled": True,
                },
            },
        )
        self.assertEqual(res_ok.status_code, 200, res_ok.text)
        updated = res_ok.json()
        self.assertEqual(updated["display_name"], "മലയാളം ടെക്കി • हिन्दी • தமிழ் 🚀")
        self.assertEqual(updated["professional_profile"]["role_title"], "Staff Backend Engineer")
        self.assertFalse(updated["professional_profile"]["is_verified"])

    def test_password_recovery_with_backup_code_revokes_sessions_and_prevents_replay(self) -> None:
        reg = self.client.post(
            "/api/v1/auth/register",
            json={
                "handle": "recovery_user",
                "password": "InitialPassword!2026",
                "recovery_email": "worker.recover@example.com",
            },
        )
        self.assertEqual(reg.status_code, 201)
        recovery_code = reg.json()["one_time_recovery_code"]

        reset_res = self.client.post(
            "/api/v1/auth/recovery/reset",
            json={
                "handle": "recovery_user",
                "recovery_code_or_token": recovery_code,
                "new_password": "BrandNewRotatedPassword!2026",
            },
        )
        self.assertEqual(reset_res.status_code, 200, reset_res.text)

        me_res = self.client.get("/api/v1/me")
        self.assertEqual(me_res.status_code, 401)

        replay_res = self.client.post(
            "/api/v1/auth/recovery/reset",
            json={
                "handle": "recovery_user",
                "recovery_code_or_token": recovery_code,
                "new_password": "AnotherPasswordAttempt!2026",
            },
        )
        self.assertEqual(replay_res.status_code, 400)
        self.assertEqual(replay_res.json()["error"]["code"], "INVALID_RECOVERY_CODE")

        login_res = self.client.post(
            "/api/v1/auth/login",
            json={
                "handle": "RECOVERY_USER",
                "password": "BrandNewRotatedPassword!2026",
            },
        )
        self.assertEqual(login_res.status_code, 200)
        self.assertEqual(login_res.json()["masked_recovery_email"], "w***r@example.com")

    def test_account_deletion_revokes_sessions_and_purges_public_profile(self) -> None:
        reg = self.client.post(
            "/api/v1/auth/register",
            json={"handle": "ephemeral_worker", "password": "DeleteMeSafely!2026"},
        )
        self.assertEqual(reg.status_code, 201)
        csrf_token = reg.json()["csrf_token"]

        pub_before = self.client.get("/api/v1/profiles/ephemeral_worker")
        self.assertEqual(pub_before.status_code, 200)

        del_res = self.client.request(
            "DELETE",
            "/api/v1/me",
            headers={"X-CSRF-Token": csrf_token},
            json={"password_confirmation": "DeleteMeSafely!2026", "delete_published_posts": True},
        )
        self.assertEqual(del_res.status_code, 200, del_res.text)
        self.assertEqual(del_res.json()["status"], "account_deleted")

        pub_after = self.client.get("/api/v1/profiles/ephemeral_worker")
        self.assertEqual(pub_after.status_code, 404)

        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)

    def test_rate_limiting_blocks_brute_force_registration(self) -> None:
        for i in range(5):
            r = self.client.post(
                "/api/v1/auth/register",
                json={"handle": f"rate_user_{i}", "password": "ValidPassword!1234"},
            )
            self.assertEqual(r.status_code, 201)

        r6 = self.client.post(
            "/api/v1/auth/register",
            json={"handle": "rate_user_6", "password": "ValidPassword!1234"},
        )
        self.assertEqual(r6.status_code, 429)
        self.assertEqual(r6.json()["error"]["code"], "RATE_LIMITED")

    def test_migration_0002_upgrade_downgrade_roundtrip(self) -> None:
        spec = importlib.util.spec_from_file_location("mig_0002", MIGRATION_0002_PATH)
        assert spec is not None and spec.loader is not None
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)

        with tempfile.NamedTemporaryFile(suffix=".sqlite3") as tmp:
            conn = sqlite3.connect(tmp.name)
            try:
                mig.upgrade(conn)
                conn.commit()
                tables_up = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                for expected in mig.PHASE3_TABLES:
                    self.assertIn(expected, tables_up)

                mig.downgrade(conn)
                conn.commit()
                tables_down = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                for dropped in mig.PHASE3_TABLES:
                    self.assertNotIn(dropped, tables_down)

                mig.upgrade(conn)
                conn.commit()
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
