"""FastAPI application factory for Pressure Out."""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.rate_limit import rate_limiter
from app.database.session import DatabaseManager
from app.logging_config import configure_logging
from app.middleware.correlation import CorrelationIdMiddleware
from app.middleware.security_headers import SecurityHeadersAndSizeLimitMiddleware


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    resolved_settings = settings or get_settings()
    logger = configure_logging(resolved_settings.log_level)

    rate_limiter.configure_from_settings(resolved_settings)

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        docs_url="/api/v1/docs" if resolved_settings.app_env != "production" else None,
        redoc_url="/api/v1/redoc" if resolved_settings.app_env != "production" else None,
        openapi_url="/api/v1/openapi.json" if resolved_settings.app_env != "production" else None,
    )

    db_manager = DatabaseManager(resolved_settings)
    if not resolved_settings.database_url.startswith("postgresql"):
        db_manager.apply_migrations_sync()

    application.state.settings = resolved_settings
    application.state.db_manager = db_manager

    # Register Correlation ID middleware first (outermost) so all responses & logs carry X-Correlation-ID
    application.add_middleware(
        SecurityHeadersAndSizeLimitMiddleware,
        is_production=(resolved_settings.app_env == "production"),
        max_body_bytes=resolved_settings.max_json_request_bytes,
        max_multipart_bytes=resolved_settings.max_multipart_upload_bytes,
    )
    application.add_middleware(CorrelationIdMiddleware)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Correlation-ID", "Idempotency-Key"],
        expose_headers=["X-Correlation-ID"],
    )

    register_exception_handlers(application)
    application.include_router(api_v1_router)

    logger.info(
        "Initialized Pressure Out FastAPI application",
        extra={"context": resolved_settings.safe_summary()},
    )
    return application


app = create_app()
