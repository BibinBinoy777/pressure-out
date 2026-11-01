"""Correlation/Request ID middleware for request tracing and safe error reporting."""
from __future__ import annotations

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import correlation_id_ctx

_SAFE_CORRELATION_ID_RE = re.compile(r"^[A-Za-z0-9_\-.]{4,64}$")


def generate_correlation_id() -> str:
    """Generate a new unique request correlation identifier."""
    return f"req_{uuid.uuid4().hex[:24]}"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Assigns a validated correlation ID to every incoming request and outgoing response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("X-Correlation-ID", "").strip()
        if incoming and _SAFE_CORRELATION_ID_RE.match(incoming):
            cid = incoming
        else:
            cid = generate_correlation_id()

        request.state.correlation_id = cid
        token = correlation_id_ctx.set(cid)
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = cid
            return response
        finally:
            correlation_id_ctx.reset(token)
