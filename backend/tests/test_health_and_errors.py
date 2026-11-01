"""API smoke tests for `/api/v1/health`, correlation IDs, and the safe error envelope."""
from __future__ import annotations

import unittest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.config import Settings
from app.core.errors import AppError
from app.main import create_app


class SamplePayload(BaseModel):
    count: int


def _create_test_client() -> TestClient:
    test_settings = Settings(
        app_env="test",
        database_url="sqlite:///:memory:",
        log_level="CRITICAL",
    )
    app = create_app(settings=test_settings)

    test_router = APIRouter(prefix="/api/v1/test-only")

    @test_router.get("/boom")
    async def trigger_unhandled_error() -> dict[str, str]:
        raise RuntimeError(
            "FATAL SQL error near postgresql+asyncpg://po_user:super_secret_pw@db:5432/prod "
            "at /etc/secret/path/config.py"
        )

    @test_router.get("/domain-error")
    async def trigger_domain_error() -> dict[str, str]:
        raise AppError(
            code="FEATURE_NOT_ENABLED",
            message="This feature is not enabled in Phase 2.",
            status_code=403,
        )

    @test_router.post("/validate")
    async def trigger_validation(payload: SamplePayload) -> dict[str, int]:
        return {"count": payload.count}

    app.include_router(test_router)
    return TestClient(app, raise_server_exceptions=False)


class HealthAndErrorHandlingTests(unittest.TestCase):
    """Verifies GET /api/v1/health, correlation IDs, and error isolation."""

    def setUp(self) -> None:
        self.client = _create_test_client()

    def test_health_endpoint_returns_expected_contract(self) -> None:
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            data,
            {
                "status": "ok",
                "service": "pressure-out-api",
                "api_version": "v1",
            },
        )
        self.assertIn("x-correlation-id", {k.lower() for k in response.headers.keys()})
        cid = response.headers.get("X-Correlation-ID") or response.headers.get("x-correlation-id")
        self.assertIsNotNone(cid)
        self.assertTrue(str(cid).startswith("req_"))

        raw_text = response.text.lower()
        for forbidden in ("postgresql", "sqlite", "password", "secret", "/working_dir", "env"):
            self.assertNotIn(forbidden, raw_text)

    def test_correlation_id_propagates_when_valid_and_regenerates_when_unsafe(self) -> None:
        custom_cid = "req_custom_trace_12345"
        res_valid = self.client.get(
            "/api/v1/health", headers={"X-Correlation-ID": custom_cid}
        )
        self.assertEqual(res_valid.headers.get("X-Correlation-ID"), custom_cid)

        res_unsafe = self.client.get(
            "/api/v1/health", headers={"X-Correlation-ID": "bad<script>header!"}
        )
        assigned = res_unsafe.headers.get("X-Correlation-ID", "")
        self.assertNotEqual(assigned, "bad<script>header!")
        self.assertTrue(assigned.startswith("req_"))

    def test_not_found_returns_standard_error_envelope(self) -> None:
        response = self.client.get("/api/v1/non-existent-route")
        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertIn("error", body)
        self.assertEqual(body["error"]["code"], "RESOURCE_NOT_FOUND")
        self.assertIn("correlation_id", body["error"])

    def test_domain_app_error_returns_standard_envelope(self) -> None:
        response = self.client.get("/api/v1/test-only/domain-error")
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertEqual(body["error"]["code"], "FEATURE_NOT_ENABLED")
        self.assertEqual(body["error"]["message"], "This feature is not enabled in Phase 2.")

    def test_validation_error_returns_422_envelope(self) -> None:
        response = self.client.post("/api/v1/test-only/validate", json={"count": "not-an-int"})
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("details", body["error"])

    def test_unhandled_exception_never_leaks_stack_trace_sql_or_credentials(self) -> None:
        response = self.client.get(
            "/api/v1/test-only/boom", headers={"X-Correlation-ID": "req_crash_check_01"}
        )
        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertEqual(body["error"]["code"], "INTERNAL_SERVER_ERROR")
        self.assertEqual(body["error"]["correlation_id"], "req_crash_check_01")

        raw = response.text
        for leaked_secret in (
            "super_secret_pw",
            "postgresql+asyncpg",
            "/etc/secret/path",
            "RuntimeError",
            "Traceback",
        ):
            self.assertNotIn(leaked_secret, raw)


if __name__ == "__main__":
    unittest.main()
