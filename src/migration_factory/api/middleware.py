"""Audit logging for the REST API.

Runs as ASGI middleware (not a FastAPI dependency) so it can see the
response status code, which dependencies -- resolved before the route
handler runs -- can't. Only /api/v1/* traffic is logged; /docs, /openapi.json,
and the root/health redirects are excluded to keep this signal instead of
noise.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from migration_factory.core.logging import get_logger

logger = get_logger(__name__)

_AUDITED_PREFIX = "/api/v1/"


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith(_AUDITED_PREFIX) or request.url.path.endswith("/health"):
            return await call_next(request)

        api_key = request.headers.get("x-api-key")
        key_fingerprint = api_key[:8] if api_key else "none"
        started_at = time.perf_counter()

        response = await call_next(request)

        logger.info(
            "api_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            key_fingerprint=key_fingerprint,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 1),
        )
        return response
