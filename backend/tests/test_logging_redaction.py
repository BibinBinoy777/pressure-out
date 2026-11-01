"""Tests for structured JSON logging and sensitive-data redaction policy."""
from __future__ import annotations

import json
import logging
import unittest

from app.config import Settings, mask_dsn
from app.logging_config import StructuredJsonFormatter, redact_sensitive_data


class LoggingRedactionTests(unittest.TestCase):
    """Ensures passwords, cookies, tokens, DSNs, AI keys, emails, and post bodies are redacted."""

    def setUp(self) -> None:
        self.formatter = StructuredJsonFormatter()

    def test_redact_sensitive_dictionary_keys_recursively(self) -> None:
        sensitive_payload = {
            "username": "pseudonym_user",
            "password": "MyPlaintextPassword123!",
            "password_confirmation": "MyPlaintextPassword123!",
            "headers": {
                "cookie": "po_session=secret_session_cookie_val",
                "x-csrf-token": "csrf_secret_token_999",
                "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            },
            "config": {
                "database_url": "postgresql+asyncpg://po_user:db_secret_pass@localhost:5432/po",
                "openai_api_key": "sk-live-1234567890abcdef",
                "ai_provider_key": "ai-secret-key-xyz",
            },
            "recovery": {
                "recovery_email": "private.employee@company.com",
                "recovery_code": "REC-9988-7766",
            },
            "content": {
                "post_body": "My manager is terrible and here is my private vent",
                "user_prompt": "Generate meme about confidential project X",
            },
        }

        redacted = redact_sensitive_data(sensitive_payload)
        serialized = json.dumps(redacted)

        self.assertEqual(redacted["username"], "pseudonym_user")
        for forbidden_secret in (
            "MyPlaintextPassword123!",
            "secret_session_cookie_val",
            "csrf_secret_token_999",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "db_secret_pass",
            "sk-live-1234567890abcdef",
            "ai-secret-key-xyz",
            "private.employee@company.com",
            "REC-9988-7766",
            "My manager is terrible",
            "confidential project X",
        ):
            self.assertNotIn(forbidden_secret, serialized)

    def test_structured_json_formatter_redacts_inline_message_secrets(self) -> None:
        record = logging.LogRecord(
            name="pressure_out.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=42,
            msg=(
                "Connection failed for postgresql+asyncpg://admin:TopSecretDBPass@db:5432/po "
                "with Cookie po_session=tok_abc123 and api_key=sk_999888 "
                "for user alice.smith@example.org"
            ),
            args=(),
            exc_info=None,
        )
        formatted = self.formatter.format(record)
        parsed = json.loads(formatted)

        self.assertEqual(parsed["level"], "ERROR")
        self.assertIn("correlation_id", parsed)
        for secret in ("TopSecretDBPass", "tok_abc123", "sk_999888", "alice.smith@example.org"):
            self.assertNotIn(secret, formatted)

    def test_settings_safe_summary_masks_database_password(self) -> None:
        settings = Settings(
            database_url="postgresql+asyncpg://po_user:MySuperSecretPass99@localhost:5432/po_dev"
        )
        summary = settings.safe_summary()
        self.assertNotIn("MySuperSecretPass99", json.dumps(summary))
        self.assertIn("[REDACTED]", str(summary["database_url"]))
        self.assertEqual(
            mask_dsn("postgresql+asyncpg://u:sec@host:5432/db"),
            "postgresql+asyncpg://u:[REDACTED]@host:5432/db",
        )


if __name__ == "__main__":
    unittest.main()
