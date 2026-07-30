"""Tests for rate limiting (migration_factory.api.rate_limit).

Uses a minimal isolated app wired with the real limiter/handler/middleware,
not the real endpoints -- tripping the real endpoints' much higher limits
(20-120/minute) would mean dozens to hundreds of requests per test, and
discover/aws in particular shells out to the real AWS CLI (confirmed
available on this machine), which is exactly the kind of external
dependency the rest of this test suite avoids.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from migration_factory.api.rate_limit import limiter, setup_rate_limiting


@pytest.fixture
def limited_client() -> Iterator[TestClient]:
    app = FastAPI()
    setup_rate_limiting(app)

    @app.get("/ping")
    @limiter.limit("3/minute")
    def ping(request: Request) -> dict[str, bool]:
        return {"ok": True}

    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        limiter.reset()


def test_requests_under_the_limit_succeed(limited_client: TestClient) -> None:
    for _ in range(3):
        assert limited_client.get("/ping").status_code == 200


def test_request_over_the_limit_is_rejected(limited_client: TestClient) -> None:
    for _ in range(3):
        limited_client.get("/ping")
    response = limited_client.get("/ping")
    assert response.status_code == 429
    assert response.json()["error"] == "rate_limit_exceeded"
    assert "Retry-After" in response.headers


def test_rate_limit_resets(limited_client: TestClient) -> None:
    for _ in range(3):
        limited_client.get("/ping")
    assert limited_client.get("/ping").status_code == 429
    limiter.reset()
    assert limited_client.get("/ping").status_code == 200
