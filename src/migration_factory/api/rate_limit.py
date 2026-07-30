"""Rate limiting for the REST API.

In-memory storage: this deployment runs a single instance (Render's free
tier has no horizontal scaling), so a shared store like Redis buys nothing
here and would be one more paid service to provision for zero benefit. If
this ever runs multiple instances, point RATE_LIMIT_STORAGE_URL at a real
store (e.g. Redis) -- the limiter setup below doesn't otherwise change.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from migration_factory.core.logging import get_logger

logger = get_logger(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.environ.get("RATE_LIMIT_STORAGE_URL", "memory://"),
    default_limits=["1000/hour"],
)

# Tiered by cost: analyze runs the full pipeline; discover shells out to a
# cloud CLI (slow, and the most attractive endpoint to hammer); everything
# else is comparatively cheap.
ANALYZE_LIMIT = "20/minute"
DISCOVER_LIMIT = "10/minute"
WRITE_LIMIT = "30/minute"
READ_LIMIT = "120/minute"


async def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RateLimitExceeded)
    logger.warning("rate_limit_exceeded", path=request.url.path, client=get_remote_address(request))
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limit_exceeded", "detail": str(exc.detail)},
        headers={"Retry-After": "60"},
    )


def setup_rate_limiting(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
