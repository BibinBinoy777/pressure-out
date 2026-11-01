"""Structured JSON logging and sensitive-data redaction policy for Pressure Out.

Redaction Policy (Phase 2 & Phase 12.2 Requirement):
The logging subsystem MUST NEVER record:
1. Passwords (`password`, `password_hash`, `new_password`, `password_confirmation`)
2. Session cookies (`cookie`, `set-cookie`, `po_session`, `session_id`)
3. Authentication tokens (`authorization`, `access_token`, `refresh_token`, `bearer`)
4. CSRF tokens (`x-csrf-token`, `csrf_token`, `csrf_secret`)
5. Database & Redis credentials (`database_url`, `redis_url`, `dsn`, embedded DSN passwords)
6. AI & Object Storage credentials (`api_key`, `s3_access_key_id`, `s3_secret_access_key`, `x-amz-signature`, `x-amz-credential`)
7. Private recovery information (`recovery_email`, `email`, `email_encrypted`, `recovery_code`)
8. Unnecessary sensitive post/prompt contents (`post_body`, `comment_body`, `user_prompt`, `raw_prompt`)
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Mapping

correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="req_unassigned"
)

REDACTED_PLACEHOLDER = "[REDACTED]"

SENSITIVE_KEY_NAMES: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "password_hash",
        "password_confirmation",
        "current_password",
        "new_password",
        "cookie",
        "cookies",
        "set-cookie",
        "po_session",
        "session_id",
        "session_token",
        "authorization",
        "access_token",
        "refresh_token",
        "api_key",
        "openai_api_key",
        "ai_provider_key",
        "provider_api_key",
        "secret",
        "secret_key",
        "client_secret",
        "s3_access_key_id",
        "s3_secret_access_key",
        "x_amz_signature",
        "x_amz_credential",
        "x_amz_security_token",
        "x-csrf-token",
        "csrf_token",
        "csrf_secret",
        "database_url",
        "test_database_url",
        "redis_url",
        "dsn",
        "db_password",
        "postgres_password",
        "redis_password",
        "email",
        "recovery_email",
        "email_encrypted",
        "recovery_code",
        "recovery_token",
        "post_body",
        "comment_body",
        "user_prompt",
        "raw_prompt",
    }
)

_VALUE_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"((?:postgresql(?:\+[a-z0-9]+)?|rediss?)://[^:/?#\s]*:)([^@/?#\s]+)(@)", re.I), r"\1[REDACTED]\3"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.I), r"\1[REDACTED]"),
    (re.compile(r"(po_session=)[^;\s]+", re.I), r"\1[REDACTED]"),
    (re.compile(r"(X-Amz-(?:Signature|Credential|Security-Token)=)[^&\s\"']+", re.I), r"\1[REDACTED]"),
    (
        re.compile(
            r"((?:password|passwd|secret|api_key|csrf_token|recovery_email|access_token|s3_secret_access_key)\s*[=:]\s*)([^\s,;\"']+)",
            re.I,
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
)


def redact_sensitive_string(value: str) -> str:
    """Scrub sensitive patterns from a string value."""
    result = value
    for pattern, replacement in _VALUE_REDACTION_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_sensitive_data(data: Any) -> Any:
    """Recursively redact sensitive keys and patterns from dicts, lists, and strings."""
    if isinstance(data, Mapping):
        redacted_dict: dict[str, Any] = {}
        for k, v in data.items():
            key_norm = str(k).strip().lower().replace("-", "_")
            if key_norm in SENSITIVE_KEY_NAMES or str(k).strip().lower() in SENSITIVE_KEY_NAMES:
                redacted_dict[str(k)] = REDACTED_PLACEHOLDER
            else:
                redacted_dict[str(k)] = redact_sensitive_data(v)
        return redacted_dict
    if isinstance(data, (list, tuple)):
        return [redact_sensitive_data(item) for item in data]
    if isinstance(data, str):
        return redact_sensitive_string(data)
    return data


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON with mandatory sensitive-data redaction."""

    def format(self, record: logging.LogRecord) -> str:
        raw_message = record.getMessage()
        safe_message = redact_sensitive_string(raw_message)

        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": safe_message,
            "correlation_id": getattr(record, "correlation_id", None) or correlation_id_ctx.get(),
        }

        extra_context = getattr(record, "context", None)
        if extra_context is not None:
            payload["context"] = redact_sensitive_data(extra_context)

        if isinstance(record.args, Mapping):
            payload["args"] = redact_sensitive_data(record.args)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure root/application structured JSON logger."""
    logger = logging.getLogger("pressure_out")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    handler = logging.StreamHandler()
    handler.setFormatter(StructuredJsonFormatter())
    logger.addHandler(handler)
    return logger
