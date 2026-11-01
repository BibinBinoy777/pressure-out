"""Adversarial Identity-Privacy Isolation Test Suite (Phase 3 Acceptance Gate AC-IMP-03)."""
from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.config import Settings
from app.core.rate_limit import rate_limiter
from app.main import create_app


class Phase3PrivacyIsolationTests(unittest.TestCase):
    """Adversarial tests guaranteeing zero private identity leakage across public serializers."""

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

    def test_strict_public_profile_and_per_post_identity_mode_isolation(self) -> None:
        reg_res = self.client.post(
            "/api/v1/auth/register",
            json={
                "handle": "secret_architect",
                "password": "UltraSecretPassword!2026",
                "recovery_email": "real.name.confidential@megacorp.com",
            },
        )
        self.assertEqual(reg_res.status_code, 201)
        priv_data = reg_res.json()
        user_id = priv_data["user_id"]
        csrf_token = priv_data["csrf_token"]
        recovery_code = priv_data["one_time_recovery_code"]

        prof_res = self.client.patch(
            "/api/v1/me/profile",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "display_name": "Arun Architect",
                "bio": "Building distributed systems.",
                "professional_profile": {
                    "role_title": "Principal Systems Architect",
                    "industry": "Enterprise SaaS",
                    "experience_band": "lead_10_plus",
                    "region_label": "South India",
                    "is_enabled": True,
                },
            },
        )
        self.assertEqual(prof_res.status_code, 200)

        pub_res = self.client.get("/api/v1/profiles/secret_architect")
        self.assertEqual(pub_res.status_code, 200)
        pub_raw = pub_res.text
        pub_json = pub_res.json()

        self.assertEqual(pub_json["handle"], "secret_architect")
        self.assertEqual(pub_json["display_name"], "Arun Architect")
        self.assertFalse(pub_json["professional_badge"]["is_verified"])

        for forbidden_substring in (
            user_id,
            "real.name.confidential@megacorp.com",
            "r***l@megacorp.com",
            csrf_token,
            recovery_code,
            "user_id",
            "email",
            "csrf_token",
            "default_identity_mode",
            "account_status",
        ):
            self.assertNotIn(forbidden_substring, pub_raw)

        for is_op, expected_label in ((False, "Anonymous Member"), (True, "Anonymous OP")):
            anon_res = self.client.post(
                "/api/v1/identity/preview-display",
                headers={"X-CSRF-Token": csrf_token},
                json={"identity_mode": "anonymous", "is_anonymous_op": is_op},
            )
            self.assertEqual(anon_res.status_code, 200)
            anon_raw = anon_res.text
            anon_json = anon_res.json()

            self.assertEqual(anon_json["identity_mode"], "anonymous")
            self.assertEqual(anon_json["display_name"], expected_label)
            self.assertIsNone(anon_json["handle"])
            self.assertIsNone(anon_json["professional_badge"])

            for forbidden in (
                user_id,
                "secret_architect",
                "Arun Architect",
                "Principal Systems Architect",
                "Enterprise SaaS",
                "South India",
                "real.name.confidential",
            ):
                self.assertNotIn(forbidden, anon_raw)

        pseudo_res = self.client.post(
            "/api/v1/identity/preview-display",
            headers={"X-CSRF-Token": csrf_token},
            json={"identity_mode": "pseudonymous"},
        )
        self.assertEqual(pseudo_res.status_code, 200)
        pseudo_json = pseudo_res.json()
        self.assertEqual(pseudo_json["handle"], "secret_architect")
        self.assertIsNone(pseudo_json["professional_badge"])
        self.assertNotIn("Principal Systems Architect", pseudo_res.text)
        self.assertNotIn(user_id, pseudo_res.text)

        prof_mode_res = self.client.post(
            "/api/v1/identity/preview-display",
            headers={"X-CSRF-Token": csrf_token},
            json={"identity_mode": "professional"},
        )
        self.assertEqual(prof_mode_res.status_code, 200)
        prof_mode_json = prof_mode_res.json()
        self.assertEqual(
            prof_mode_json["professional_badge"]["role_title"],
            "Principal Systems Architect",
        )
        self.assertFalse(prof_mode_json["professional_badge"]["is_verified"])
        self.assertNotIn(user_id, prof_mode_res.text)

        self.client.patch(
            "/api/v1/me/profile",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "professional_profile": {
                    "role_title": "Principal Systems Architect",
                    "industry": "Enterprise SaaS",
                    "experience_band": "lead_10_plus",
                    "region_label": "South India",
                    "is_enabled": False,
                }
            },
        )
        pub_disabled = self.client.get("/api/v1/profiles/secret_architect").json()
        self.assertIsNone(pub_disabled["professional_badge"])

        prof_blocked = self.client.post(
            "/api/v1/identity/preview-display",
            headers={"X-CSRF-Token": csrf_token},
            json={"identity_mode": "professional"},
        )
        self.assertEqual(prof_blocked.status_code, 422)
        self.assertEqual(prof_blocked.json()["error"]["code"], "PROFESSIONAL_PROFILE_REQUIRED")

    def test_database_stores_encrypted_email_and_hashed_password_never_plaintext(self) -> None:
        raw_email = "top.secret.engineer@company.io"
        raw_pwd = "MyPlaintextPassphrase!9000"
        reg_res = self.client.post(
            "/api/v1/auth/register",
            json={
                "handle": "crypto_check_user",
                "password": raw_pwd,
                "recovery_email": raw_email,
            },
        )
        self.assertEqual(reg_res.status_code, 201)

        conn = self.app.state.db_manager._shared_memory_conn
        assert conn is not None
        row = conn.execute(
            "SELECT email_hash, email_encrypted, password_hash FROM users"
        ).fetchone()
        self.assertIsNotNone(row)
        email_hash, email_encrypted, password_hash = row

        self.assertNotIn(raw_email, str(email_hash))
        self.assertNotIn(raw_email.encode("utf-8"), bytes(email_encrypted))
        self.assertNotIn(raw_pwd, str(password_hash))
        self.assertTrue(str(password_hash).startswith("scrypt$"))


if __name__ == "__main__":
    unittest.main()
