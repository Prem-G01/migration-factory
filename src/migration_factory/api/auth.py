"""X-API-Key authentication for the REST API.

Fail-closed: if API_KEYS isn't configured, every protected request is
rejected rather than silently running open (production-hardening
requirement -- a misconfigured deployment should be loudly broken, not
quietly unauthenticated). Keys are read from the environment on every
call rather than cached at import time, so rotating API_KEYS doesn't
require a process restart.

Tests bypass this via `app.dependency_overrides[verify_api_key]`, the same
pattern already used for the DB session dependency in test_api.py -- not a
pytest-detection env check, since a dependency override is the idiomatic
FastAPI way to swap this out and keeps this module free of test-only
branches.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from migration_factory.core.logging import get_logger

logger = get_logger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _load_valid_keys() -> set[str]:
    raw = os.environ.get("API_KEYS", "")
    return {key.strip() for key in raw.split(",") if key.strip()}


async def verify_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    valid_keys = _load_valid_keys()
    if not valid_keys:
        logger.warning("api_auth_misconfigured", detail="API_KEYS is not set; rejecting all requests")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured",
        )

    if not api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing X-API-Key header")

    if api_key not in valid_keys:
        logger.warning("api_auth_invalid_key", key_fingerprint=api_key[:8])
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    return api_key
