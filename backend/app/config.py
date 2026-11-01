"""Environment-driven application configuration for Pressure Out.

Loads configuration from environment variables (and `.env` if present), validates
settings, and provides safe redaction helpers so sensitive connection strings or
credentials are never printed in diagnostic output.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

_DSN_PASSWORD_RE = re.compile(r"(://[^:/?#\s]*:)([^@/?#\s]+)(@)")


def mask_dsn(dsn: str) -> str:
    """Mask the password component inside a database or Redis URL."""
    if not dsn:
        return ""
    return _DSN_PASSWORD_RE.sub(r"\1[REDACTED]\3", dsn)


def _derive_default_dev_aes_key() -> str:
    raw = hashlib.sha256(b"pressure-out-local-dev-only-aes-256-gcm-key").digest()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _default_storage_path() -> str:
    repo_root = Path(__file__).resolve().parent.parent.parent
    return str(repo_root / "storage" / "media")


def _parse_bool(val: Optional[bool], env_key: str, default: bool) -> bool:
    if val is not None:
        return bool(val)
    raw = os.getenv(env_key, "").strip().lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    return default


class Settings:
    """Validated runtime settings for the FastAPI backend."""

    def __init__(
        self,
        *,
        app_env: Optional[str] = None,
        app_name: Optional[str] = None,
        app_version: Optional[str] = None,
        log_level: Optional[str] = None,
        cors_origins: Optional[List[str]] = None,
        database_url: Optional[str] = None,
        test_database_url: Optional[str] = None,
        db_pool_size: Optional[int] = None,
        db_max_overflow: Optional[int] = None,
        db_pool_timeout_seconds: Optional[int] = None,
        web_concurrency: Optional[int] = None,
        rate_limit_backend: Optional[str] = None,
        redis_url: Optional[str] = None,
        redis_socket_timeout_seconds: Optional[float] = None,
        rate_limit_fail_closed: Optional[bool] = None,
        max_json_request_bytes: Optional[int] = None,
        max_multipart_upload_bytes: Optional[int] = None,
        storage_backend: Optional[str] = None,
        local_storage_path: Optional[str] = None,
        s3_endpoint_url: Optional[str] = None,
        s3_region: Optional[str] = None,
        s3_bucket_name: Optional[str] = None,
        s3_access_key_id: Optional[str] = None,
        s3_secret_access_key: Optional[str] = None,
        s3_key_prefix: Optional[str] = None,
        s3_timeout_seconds: Optional[float] = None,
        s3_presigned_url_ttl_seconds: Optional[int] = None,
        ai_caption_provider: Optional[str] = None,
        ai_image_provider: Optional[str] = None,
        translation_provider: Optional[str] = None,
        session_cookie_name: Optional[str] = None,
        session_cookie_secure: Optional[bool] = None,
        session_ttl_hours: Optional[int] = None,
        email_hmac_pepper: Optional[str] = None,
        email_encryption_key_base64: Optional[str] = None,
        meme_max_prompt_chars: Optional[int] = None,
        meme_caption_daily_limit: Optional[int] = None,
        meme_image_daily_limit: Optional[int] = None,
        meme_max_concurrent_jobs: Optional[int] = None,
        meme_job_max_retries: Optional[int] = None,
        meme_provider_timeout_sec: Optional[float] = None,
        ai_daily_spend_cap_usd: Optional[float] = None,
        translation_timeout_sec: Optional[float] = None,
        translation_hourly_limit: Optional[int] = None,
        insights_min_cohort_size: Optional[int] = None,
        insights_sensitive_min_cohort_size: Optional[int] = None,
        insights_min_category_bucket_count: Optional[int] = None,
    ) -> None:
        self.app_env: str = (app_env or os.getenv("APP_ENV", "development")).strip().lower()
        if self.app_env not in {"development", "test", "staging", "production"}:
            raise ValueError(f"Invalid APP_ENV: {self.app_env}")

        self.app_name: str = app_name or os.getenv("APP_NAME", "Pressure Out API")
        self.app_version: str = app_version or os.getenv("APP_VERSION", "0.8.1")
        self.log_level: str = (log_level or os.getenv("LOG_LEVEL", "INFO")).strip().upper()

        raw_cors = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
        self.cors_origins: List[str] = (
            cors_origins
            if cors_origins is not None
            else [origin.strip() for origin in raw_cors.split(",") if origin.strip()]
        )

        default_db = (
            "postgresql+asyncpg://po_dev_user:po_dev_local_only_password_change_me"
            "@localhost:5432/pressure_out_dev"
        )
        self.database_url: str = database_url or os.getenv("DATABASE_URL", default_db)
        self.test_database_url: str = test_database_url or os.getenv(
            "TEST_DATABASE_URL",
            "sqlite:///./test_pressure_out.sqlite3",
        )

        self.db_pool_size: int = int(db_pool_size or os.getenv("DB_POOL_SIZE", "5"))
        self.db_max_overflow: int = int(db_max_overflow or os.getenv("DB_MAX_OVERFLOW", "10"))
        self.db_pool_timeout_seconds: int = int(
            db_pool_timeout_seconds or os.getenv("DB_POOL_TIMEOUT_SECONDS", "30")
        )

        # Phase 12.1 Multi-Worker & Rate Limiting Configuration
        default_workers = "2" if self.app_env == "production" else "1"
        self.web_concurrency: int = int(
            web_concurrency
            if web_concurrency is not None
            else os.getenv("WEB_CONCURRENCY", default_workers)
        )
        default_rl_backend = "redis" if self.app_env == "production" else "memory"
        self.rate_limit_backend: str = (
            rate_limit_backend or os.getenv("RATE_LIMIT_BACKEND", default_rl_backend)
        ).strip().lower()
        if self.rate_limit_backend not in {"memory", "redis"}:
            raise ValueError(
                f"Invalid RATE_LIMIT_BACKEND '{self.rate_limit_backend}' (expected 'memory' or 'redis')."
            )
        default_redis_url = (
            ""
            if self.app_env == "production"
            else "redis://127.0.0.1:6379/0"
        )
        self.redis_url: str = (
            redis_url if redis_url is not None else os.getenv("REDIS_URL", default_redis_url)
        ).strip()
        self.redis_socket_timeout_seconds: float = float(
            redis_socket_timeout_seconds
            if redis_socket_timeout_seconds is not None
            else os.getenv("REDIS_SOCKET_TIMEOUT_SECONDS", "2.0")
        )
        self.rate_limit_fail_closed: bool = _parse_bool(
            rate_limit_fail_closed, "RATE_LIMIT_FAIL_CLOSED", True
        )

        # Phase 12.1 Separated Request Body & Multipart Upload Size Limits
        self.max_json_request_bytes: int = int(
            max_json_request_bytes
            if max_json_request_bytes is not None
            else os.getenv("MAX_JSON_REQUEST_BYTES", str(1 * 1024 * 1024))
        )
        self.max_multipart_upload_bytes: int = int(
            max_multipart_upload_bytes
            if max_multipart_upload_bytes is not None
            else os.getenv("MAX_MULTIPART_UPLOAD_BYTES", str(6 * 1024 * 1024))
        )

        # Phase 8 & 12.1 Media Storage Configuration (local | s3 | r2)
        self.storage_backend: str = (
            storage_backend or os.getenv("STORAGE_BACKEND", "local")
        ).strip().lower()
        if self.storage_backend not in {"local", "s3", "r2"}:
            raise ValueError(
                f"Invalid STORAGE_BACKEND '{self.storage_backend}' (expected 'local', 's3', or 'r2')."
            )
        self.local_storage_path: str = local_storage_path or os.getenv(
            "LOCAL_STORAGE_PATH", _default_storage_path()
        )
        self.s3_endpoint_url: str = (
            s3_endpoint_url
            if s3_endpoint_url is not None
            else os.getenv("S3_ENDPOINT_URL", "")
        ).strip()
        self.s3_region: str = (
            s3_region if s3_region is not None else os.getenv("S3_REGION", "auto")
        ).strip()
        self.s3_bucket_name: str = (
            s3_bucket_name if s3_bucket_name is not None else os.getenv("S3_BUCKET_NAME", "")
        ).strip()
        self.s3_access_key_id: str = (
            s3_access_key_id
            if s3_access_key_id is not None
            else os.getenv("S3_ACCESS_KEY_ID", "")
        ).strip()
        self.s3_secret_access_key: str = (
            s3_secret_access_key
            if s3_secret_access_key is not None
            else os.getenv("S3_SECRET_ACCESS_KEY", "")
        ).strip()
        self.s3_key_prefix: str = (
            s3_key_prefix if s3_key_prefix is not None else os.getenv("S3_KEY_PREFIX", "memes")
        ).strip()
        self.s3_timeout_seconds: float = float(
            s3_timeout_seconds
            if s3_timeout_seconds is not None
            else os.getenv("S3_TIMEOUT_SECONDS", "10.0")
        )
        self.s3_presigned_url_ttl_seconds: int = int(
            s3_presigned_url_ttl_seconds
            if s3_presigned_url_ttl_seconds is not None
            else os.getenv("S3_PRESIGNED_URL_TTL_SECONDS", "3600")
        )

        # Phase 8 AI Meme Studio Providers & Quotas
        self.ai_caption_provider: str = (
            ai_caption_provider or os.getenv("AI_CAPTION_PROVIDER", "local_mock")
        ).strip().lower()
        self.ai_image_provider: str = (
            ai_image_provider or os.getenv("AI_IMAGE_PROVIDER", "local_mock")
        ).strip().lower()
        self.translation_provider: str = (
            translation_provider or os.getenv("TRANSLATION_PROVIDER", "local_mock")
        ).strip().lower()

        self.meme_max_prompt_chars: int = int(
            meme_max_prompt_chars
            if meme_max_prompt_chars is not None
            else os.getenv("MEME_MAX_PROMPT_CHARS", "400")
        )
        self.meme_caption_daily_limit: int = int(
            meme_caption_daily_limit
            if meme_caption_daily_limit is not None
            else os.getenv("MEME_CAPTION_DAILY_LIMIT", "15")
        )
        self.meme_image_daily_limit: int = int(
            meme_image_daily_limit
            if meme_image_daily_limit is not None
            else os.getenv("MEME_IMAGE_DAILY_LIMIT", "5")
        )
        self.meme_max_concurrent_jobs: int = int(
            meme_max_concurrent_jobs
            if meme_max_concurrent_jobs is not None
            else os.getenv("MEME_MAX_CONCURRENT_JOBS", "1")
        )
        self.meme_job_max_retries: int = int(
            meme_job_max_retries
            if meme_job_max_retries is not None
            else os.getenv("MEME_JOB_MAX_RETRIES", "1")
        )
        self.meme_provider_timeout_sec: float = float(
            meme_provider_timeout_sec
            if meme_provider_timeout_sec is not None
            else os.getenv("MEME_PROVIDER_TIMEOUT_SEC", "15.0")
        )
        self.ai_daily_spend_cap_usd: float = float(
            ai_daily_spend_cap_usd
            if ai_daily_spend_cap_usd is not None
            else os.getenv("AI_DAILY_SPEND_CAP_USD", "25.0")
        )
        self.translation_timeout_sec: float = float(
            translation_timeout_sec
            if translation_timeout_sec is not None
            else os.getenv("TRANSLATION_TIMEOUT_SEC", "10.0")
        )
        self.translation_hourly_limit: int = int(
            translation_hourly_limit
            if translation_hourly_limit is not None
            else os.getenv("TRANSLATION_HOURLY_LIMIT", "30")
        )
        self.insights_min_cohort_size: int = int(
            insights_min_cohort_size
            if insights_min_cohort_size is not None
            else os.getenv("INSIGHTS_MIN_COHORT_SIZE", "10")
        )
        self.insights_sensitive_min_cohort_size: int = int(
            insights_sensitive_min_cohort_size
            if insights_sensitive_min_cohort_size is not None
            else os.getenv("INSIGHTS_SENSITIVE_MIN_COHORT_SIZE", "20")
        )
        self.insights_min_category_bucket_count: int = int(
            insights_min_category_bucket_count
            if insights_min_category_bucket_count is not None
            else os.getenv("INSIGHTS_MIN_CATEGORY_BUCKET_COUNT", "3")
        )

        # Phase 3 Identity & Session Security Settings
        self.session_cookie_name: str = session_cookie_name or os.getenv(
            "SESSION_COOKIE_NAME", "po_session"
        )
        self.session_cookie_secure: bool = _parse_bool(
            session_cookie_secure,
            "SESSION_COOKIE_SECURE",
            self.app_env in {"staging", "production"},
        )
        self.session_ttl_hours: int = int(
            session_ttl_hours or os.getenv("SESSION_TTL_HOURS", "168")
        )
        self.email_hmac_pepper: str = email_hmac_pepper or os.getenv(
            "EMAIL_HMAC_PEPPER", "po_dev_only_hmac_pepper_change_in_prod"
        )
        self.email_encryption_key_base64: str = email_encryption_key_base64 or os.getenv(
            "EMAIL_ENCRYPTION_KEY_BASE64", _derive_default_dev_aes_key()
        )

        self._validate_cross_environment_invariants()
        if self.app_env == "production":
            self._validate_production_invariants()

    def _validate_cross_environment_invariants(self) -> None:
        """Enforce invariants that apply in any environment (such as multi-worker rate limiting and S3 settings)."""
        if self.web_concurrency > 1 and self.rate_limit_backend != "redis":
            raise ValueError(
                "MULTI_WORKER_CONFIG_ERROR: WEB_CONCURRENCY > 1 requires RATE_LIMIT_BACKEND='redis' so rate-limit allowances are shared across workers."
            )
        if self.rate_limit_backend == "redis":
            if not self.redis_url or not self.redis_url.startswith(("redis://", "rediss://")):
                raise ValueError(
                    "REDIS_CONFIG_ERROR: RATE_LIMIT_BACKEND='redis' requires a valid REDIS_URL (redis:// or rediss://)."
                )
        if self.storage_backend in {"s3", "r2"}:
            missing = [
                name
                for name, val in (
                    ("S3_ENDPOINT_URL", self.s3_endpoint_url),
                    ("S3_BUCKET_NAME", self.s3_bucket_name),
                    ("S3_ACCESS_KEY_ID", self.s3_access_key_id),
                    ("S3_SECRET_ACCESS_KEY", self.s3_secret_access_key),
                )
                if not val
            ]
            if missing:
                raise ValueError(
                    f"STORAGE_CONFIG_ERROR: STORAGE_BACKEND='{self.storage_backend}' requires {', '.join(missing)}."
                )

    def _validate_production_invariants(self) -> None:
        """Fail startup immediately if unsafe development defaults or mock providers are active in production."""
        if not self.database_url.startswith("postgresql"):
            raise ValueError(
                "PRODUCTION_CONFIG_ERROR: DATABASE_URL must use PostgreSQL in production."
            )
        if "po_dev_local_only_password_change_me" in self.database_url:
            raise ValueError(
                "PRODUCTION_CONFIG_ERROR: Default development database password is forbidden in production."
            )
        if self.rate_limit_backend != "redis":
            raise ValueError(
                "PRODUCTION_CONFIG_ERROR: RATE_LIMIT_BACKEND must be 'redis' in production (process-local 'memory' rate limiting is forbidden)."
            )
        if "po_dev_redis_password_change_me" in self.redis_url:
            raise ValueError(
                "PRODUCTION_CONFIG_ERROR: Default development Redis password is forbidden in production."
            )
        if not self.rate_limit_fail_closed:
            raise ValueError(
                "PRODUCTION_CONFIG_ERROR: RATE_LIMIT_FAIL_CLOSED must be true in production."
            )
        if not self.session_cookie_secure:
            raise ValueError(
                "PRODUCTION_CONFIG_ERROR: SESSION_COOKIE_SECURE must be true in production."
            )
        if self.email_hmac_pepper == "po_dev_only_hmac_pepper_change_in_prod" or len(self.email_hmac_pepper) < 24:
            raise ValueError(
                "PRODUCTION_CONFIG_ERROR: A strong custom EMAIL_HMAC_PEPPER (>= 24 chars) is required in production."
            )
        if self.email_encryption_key_base64 == _derive_default_dev_aes_key():
            raise ValueError(
                "PRODUCTION_CONFIG_ERROR: Default development EMAIL_ENCRYPTION_KEY_BASE64 is forbidden in production."
            )
        if not self.cors_origins:
            raise ValueError(
                "PRODUCTION_CONFIG_ERROR: CORS_ORIGINS must be explicitly configured in production."
            )
        for origin in self.cors_origins:
            if origin == "*" or origin.startswith("http://"):
                raise ValueError(
                    f"PRODUCTION_CONFIG_ERROR: Wildcard or insecure HTTP CORS origin '{origin}' is forbidden in production."
                )
        for prov_name, prov_val in (
            ("AI_CAPTION_PROVIDER", self.ai_caption_provider),
            ("AI_IMAGE_PROVIDER", self.ai_image_provider),
            ("TRANSLATION_PROVIDER", self.translation_provider),
        ):
            if prov_val in {"local_mock", "mock"}:
                raise ValueError(
                    f"PRODUCTION_CONFIG_ERROR: {prov_name} cannot be set to '{prov_val}' in production (use 'disabled' or a verified provider)."
                )

    def safe_summary(self) -> dict[str, object]:
        """Return a redacted dictionary suitable for safe diagnostic inspection."""
        return {
            "app_env": self.app_env,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "log_level": self.log_level,
            "database_url": mask_dsn(self.database_url),
            "web_concurrency": self.web_concurrency,
            "rate_limit_backend": self.rate_limit_backend,
            "redis_url": mask_dsn(self.redis_url) if self.redis_url else None,
            "rate_limit_fail_closed": self.rate_limit_fail_closed,
            "storage_backend": self.storage_backend,
            "s3_bucket_name": self.s3_bucket_name or None,
            "session_cookie_name": self.session_cookie_name,
            "session_cookie_secure": self.session_cookie_secure,
            "ai_caption_provider": self.ai_caption_provider,
            "ai_image_provider": self.ai_image_provider,
            "translation_provider": self.translation_provider,
            "meme_caption_daily_limit": self.meme_caption_daily_limit,
            "meme_image_daily_limit": self.meme_image_daily_limit,
            "meme_max_concurrent_jobs": self.meme_max_concurrent_jobs,
            "ai_daily_spend_cap_usd": self.ai_daily_spend_cap_usd,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
