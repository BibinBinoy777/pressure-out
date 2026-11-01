"""Consistent, safe API error envelope and exception handlers for Pressure Out.

Guarantees that all HTTP 4xx and 5xx responses return:
{
  "error": {
    "code": "MACHINE_READABLE_CODE",
    "message": "Safe human-readable message",
    "correlation_id": "req_..."
  }
}
Unexpected exceptions are logged with correlation_id and never leak stack traces,
SQL queries, database credentials, filesystem paths, or environment variables.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_config import correlation_id_ctx

logger = logging.getLogger("pressure_out.errors")


class ErrorPayload(BaseModel):
    code: str
    message: str
    correlation_id: str
    details: Optional[dict[str, Any]] = None


class ErrorEnvelope(BaseModel):
    error: ErrorPayload


class AppError(Exception):
    """Domain/application error with an explicit HTTP status and safe error code."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def _get_request_correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", None) or correlation_id_ctx.get()


def build_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    correlation_id: str,
    details: Optional[dict[str, Any]] = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": correlation_id,
        }
    }
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(
        status_code=status_code,
        content=body,
        headers={"X-Correlation-ID": correlation_id},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register uniform exception handlers on the FastAPI instance."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        cid = _get_request_correlation_id(request)
        return build_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            correlation_id=cid,
            details=exc.details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        cid = _get_request_correlation_id(request)
        status_code_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "RESOURCE_NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMITED",
            503: "SERVICE_UNAVAILABLE",
        }
        code = status_code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        safe_message = (
            exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
        )
        return build_error_response(
            status_code=exc.status_code,
            code=code,
            message=safe_message,
            correlation_id=cid,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        cid = _get_request_correlation_id(request)
        sanitized_fields = [
            {
                "loc": [str(part) for part in err.get("loc", [])],
                "msg": str(err.get("msg", "Invalid value")),
                "type": str(err.get("type", "value_error")),
            }
            for err in exc.errors()
        ]
        return build_error_response(
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request payload validation failed.",
            correlation_id=cid,
            details={"fields": sanitized_fields},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        cid = _get_request_correlation_id(request)
        # Log internally with redaction filter; NEVER leak exc message/traceback to client
        logger.error(
            "Unhandled internal exception during request processing",
            extra={
                "correlation_id": cid,
                "context": {
                    "path": request.url.path,
                    "method": request.method,
                    "exception_type": type(exc).__name__,
                },
            },
        )
        return build_error_response(
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected internal error occurred. Please reference the correlation ID if reporting this issue.",
            correlation_id=cid,
        )
