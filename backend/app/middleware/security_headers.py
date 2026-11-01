"""Browser security headers, separated JSON vs. multipart body size guards, and latency telemetry middleware."""
from __future__ import annotations

import time
from typing import Any, Callable
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.metrics import metrics_collector

MAX_JSON_REQUEST_BYTES = 1 * 1024 * 1024  # 1 MB limit for JSON API payloads
MAX_MULTIPART_UPLOAD_BYTES = 6 * 1024 * 1024  # 6 MB envelope limit for multipart media uploads (inner image limit = 5 MB)

MULTIPART_UPLOAD_PATHS = {
    "/api/v1/memes/upload",
}

CSP_POLICY = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class _PayloadTooLargeStreamError(Exception):
    """Raised when streamed request body bytes exceed the policy limit."""

    def __init__(self, limit_bytes: int, policy_kind: str) -> None:
        super().__init__(f"{policy_kind} exceeded {limit_bytes} bytes")
        self.limit_bytes = limit_bytes
        self.policy_kind = policy_kind


def _attach_security_headers(response: Response, *, is_production: bool, scheme: str) -> None:
    response.headers.setdefault("Content-Security-Policy", CSP_POLICY)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    )
    if is_production or scheme == "https":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=63072000; includeSubDomains; preload",
        )


class SecurityHeadersAndSizeLimitMiddleware(BaseHTTPMiddleware):
    """Enforces separated JSON (1 MB) and multipart upload (6 MB) request limits,
    prevents missing/falsified Content-Length bypasses via stream byte counting,
    attaches browser security headers, and records process-aware latency metrics.
    """

    def __init__(
        self,
        app: Any,
        *,
        is_production: bool = False,
        max_body_bytes: int = MAX_JSON_REQUEST_BYTES,
        max_multipart_bytes: int = MAX_MULTIPART_UPLOAD_BYTES,
    ) -> None:
        super().__init__(app)
        self.is_production = is_production
        self.max_body_bytes = max_body_bytes
        self.max_multipart_bytes = max_multipart_bytes

    def _resolve_limit_for_request(self, request: Request) -> tuple[int, str]:
        content_type = (request.headers.get("content-type") or "").lower()
        path = request.url.path.rstrip("/") or "/"
        if content_type.startswith("multipart/form-data") and path in MULTIPART_UPLOAD_PATHS:
            return self.max_multipart_bytes, "multipart_upload"
        return self.max_body_bytes, "json_or_standard"

    def _build_413_response(
        self,
        request: Request,
        *,
        limit_bytes: int,
        policy_kind: str,
        duration_ms: float,
    ) -> JSONResponse:
        cid = getattr(request.state, "correlation_id", "req_oversized")
        metrics_collector.record_request(413, duration_ms)
        code = "UPLOAD_TOO_LARGE" if policy_kind == "multipart_upload" else "PAYLOAD_TOO_LARGE"
        resp = JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": code,
                    "message": f"Request payload exceeds the maximum allowed {policy_kind} size of {limit_bytes} bytes.",
                    "correlation_id": cid,
                    "details": {
                        "policy": policy_kind,
                        "max_bytes": limit_bytes,
                    },
                }
            },
        )
        _attach_security_headers(
            resp, is_production=self.is_production, scheme=request.url.scheme
        )
        return resp

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_ts = time.perf_counter()
        limit_bytes, policy_kind = self._resolve_limit_for_request(request)

        # 1. Fast reject on declared Content-Length header when valid and > limit_bytes
        content_len_str = request.headers.get("content-length", "").strip()
        if content_len_str:
            try:
                declared_len = int(content_len_str)
                if declared_len < 0 or declared_len > limit_bytes:
                    return self._build_413_response(
                        request,
                        limit_bytes=limit_bytes,
                        policy_kind=policy_kind,
                        duration_ms=(time.perf_counter() - start_ts) * 1000.0,
                    )
            except ValueError:
                pass

        # 2. Wrap ASGI receive channel so missing or falsified Content-Length headers
        #    cannot bypass the byte limit and streams are never buffered without bounds.
        original_receive: Callable[[], Any] = request._receive
        bytes_seen = 0

        stream_exceeded = False

        async def _bounded_receive() -> dict[str, Any]:
            nonlocal bytes_seen, stream_exceeded
            message = await original_receive()
            if message.get("type") == "http.request":
                chunk = message.get("body", b"") or b""
                bytes_seen += len(chunk)
                if bytes_seen > limit_bytes:
                    stream_exceeded = True
                    raise _PayloadTooLargeStreamError(limit_bytes, policy_kind)
            return message

        request._receive = _bounded_receive  # type: ignore[attr-defined]

        try:
            response = await call_next(request)
        except Exception:
            if stream_exceeded:
                return self._build_413_response(
                    request,
                    limit_bytes=limit_bytes,
                    policy_kind=policy_kind,
                    duration_ms=(time.perf_counter() - start_ts) * 1000.0,
                )
            raise

        if stream_exceeded:
            return self._build_413_response(
                request,
                limit_bytes=limit_bytes,
                policy_kind=policy_kind,
                duration_ms=(time.perf_counter() - start_ts) * 1000.0,
            )

        duration_ms = (time.perf_counter() - start_ts) * 1000.0
        metrics_collector.record_request(response.status_code, duration_ms)
        _attach_security_headers(
            response, is_production=self.is_production, scheme=request.url.scheme
        )
        return response
