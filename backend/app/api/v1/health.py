"""Process liveness, dependency readiness, and process-aware operational metrics (`/api/v1/health`).

Never exposes secrets, environment variables, connection strings, filesystem paths,
or private user data.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.api.deps import get_db_session, get_request_db_manager, get_request_settings
from app.config import Settings
from app.core.metrics import metrics_collector
from app.core.rate_limit import rate_limiter
from app.database.session import DatabaseManager
from app.modules.memes.storage import create_storage_adapter

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    api_version: str


class ReadinessResponse(BaseModel):
    status: str
    database_ready: bool
    storage_ready: bool
    rate_limit_ready: bool
    rate_limit_backend: str
    storage_backend: str
    api_version: str


class OperationalMetricsResponse(BaseModel):
    service: str
    app_env: str
    http_metrics: Dict[str, Any]
    db_pool: Dict[str, int]
    worker_queue: Dict[str, Any]
    infrastructure: Dict[str, Any]


@router.get("/health", response_model=HealthResponse, summary="Check API process liveness")
@router.get("/health/live", response_model=HealthResponse, summary="Check API process liveness")
async def get_health() -> HealthResponse:
    """Return process liveness status under `/api/v1/health` and `/api/v1/health/live`."""
    return HealthResponse(
        status="ok",
        service="pressure-out-api",
        api_version="v1",
    )


@router.get("/health/ready", response_model=ReadinessResponse, summary="Check database, storage, and rate-limiter readiness")
async def get_readiness(
    response: Response,
    db_manager: DatabaseManager = Depends(get_request_db_manager),
    settings: Settings = Depends(get_request_settings),
) -> ReadinessResponse:
    """Verify database connectivity (`SELECT 1`), storage readiness, and shared rate-limiter health."""
    try:
        db_ok = await db_manager.verify_connectivity()
    except Exception:
        db_ok = False

    try:
        storage_adapter = create_storage_adapter(settings)
        storage_ok = storage_adapter.is_healthy()
    except Exception:
        storage_ok = False

    try:
        rl_ok = rate_limiter.is_healthy()
    except Exception:
        rl_ok = False

    overall_ready = db_ok and storage_ok and rl_ok
    if not overall_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if overall_ready else "degraded",
        database_ready=db_ok,
        storage_ready=storage_ok,
        rate_limit_ready=rl_ok,
        rate_limit_backend=rate_limiter.backend_name,
        storage_backend=settings.storage_backend,
        api_version="v1",
    )


@router.get("/health/metrics", response_model=OperationalMetricsResponse, summary="Retrieve process-aware operational metrics")
async def get_operational_metrics(
    session: Any = Depends(get_db_session),
    db_manager: DatabaseManager = Depends(get_request_db_manager),
    settings: Settings = Depends(get_request_settings),
) -> OperationalMetricsResponse:
    """Return process-scoped HTTP metrics, DB pool bounds, and shared DB-backed worker job queue state."""
    queue_counts: Dict[str, Any] = {
        "collection_scope": "database_global",
        "queued": 0,
        "generating": 0,
        "validating": 0,
        "ready": 0,
        "failed": 0,
        "cancelled": 0,
    }
    try:
        rows = await session.execute(
            "SELECT status, COUNT(1) FROM meme_jobs GROUP BY status"
        )
        for st, cnt in rows:
            queue_counts[str(st)] = int(cnt)
    except Exception:
        pass

    return OperationalMetricsResponse(
        service="pressure-out-api",
        app_env=settings.app_env,
        http_metrics=metrics_collector.snapshot(
            configured_web_concurrency=settings.web_concurrency
        ),
        db_pool=db_manager.pool_configuration,
        worker_queue=queue_counts,
        infrastructure={
            "rate_limit_backend": rate_limiter.backend_name,
            "rate_limit_healthy": rate_limiter.is_healthy(),
            "storage_backend": settings.storage_backend,
            "configured_web_concurrency": settings.web_concurrency,
        },
    )
