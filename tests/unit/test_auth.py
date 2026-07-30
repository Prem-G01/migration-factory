"""Tests for X-API-Key authentication (migration_factory.api.auth).

Uses its own TestClient scope for the verify_api_key dependency. Unlike
test_api.py -- which overrides verify_api_key away entirely to test
business logic in isolation -- these tests exercise the real auth path, so
they explicitly save/restore whatever override another test module may
already have set on the shared `app` singleton (dependency_overrides is a
plain dict on a module-level object; pytest collection order isn't
guaranteed across files).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from migration_factory.api.auth import verify_api_key
from migration_factory.api.database import Base, get_session
from migration_factory.api.main import app

_test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
)
_test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False)


async def _create_tables() -> None:
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


asyncio.run(_create_tables())


async def _override_get_session() -> AsyncGenerator[AsyncSession]:
    async with _test_session_factory() as session:
        yield session


@pytest.fixture
def real_auth_client() -> Iterator[TestClient]:
    """A client that exercises the real verify_api_key path (test_api.py's
    module-level override doesn't apply here -- this file is runnable on its
    own), backed by its own hermetic in-memory DB so a valid-key request can
    reach a real endpoint without needing Postgres.
    """
    previous_auth = app.dependency_overrides.pop(verify_api_key, None)
    previous_session = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = _override_get_session
    try:
        yield TestClient(app)
    finally:
        if previous_auth is not None:
            app.dependency_overrides[verify_api_key] = previous_auth
        if previous_session is not None:
            app.dependency_overrides[get_session] = previous_session
        else:
            app.dependency_overrides.pop(get_session, None)


def test_auth_not_configured_returns_503(
    real_auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("API_KEYS", raising=False)
    response = real_auth_client.get("/api/v1/runs", headers={"X-API-Key": "anything"})
    assert response.status_code == 503


def test_auth_missing_api_key_returns_403(
    real_auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("API_KEYS", "valid-key-1,valid-key-2")
    response = real_auth_client.get("/api/v1/runs")
    assert response.status_code == 403


def test_auth_invalid_api_key_returns_401(
    real_auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("API_KEYS", "valid-key-1,valid-key-2")
    response = real_auth_client.get("/api/v1/runs", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401


def test_auth_valid_api_key_succeeds(
    real_auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("API_KEYS", "valid-key-1,valid-key-2")
    response = real_auth_client.get("/api/v1/runs", headers={"X-API-Key": "valid-key-2"})
    assert response.status_code == 200


def test_auth_protects_analyze_endpoint(
    real_auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("API_KEYS", "valid-key-1")
    response = real_auth_client.post(
        "/api/v1/analyze",
        files={"file": ("x.tfstate", b"{}", "application/json")},
        data={"target": "gcp"},
    )
    assert response.status_code == 403


def test_health_endpoints_do_not_require_auth(
    real_auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("API_KEYS", raising=False)
    assert real_auth_client.get("/api/v1/health").status_code == 200
    assert real_auth_client.get("/", follow_redirects=False).status_code == 307
    assert real_auth_client.get("/health", follow_redirects=False).status_code == 307
