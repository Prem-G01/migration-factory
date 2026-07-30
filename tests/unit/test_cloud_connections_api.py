"""Tests for the /api/v1/cloud-connections/aws endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from migration_factory.api.auth import verify_api_key
from migration_factory.api.database import Base, get_session
from migration_factory.api.main import app
from migration_factory.cloud_access.aws import generate_trust_policy, platform_identity_arn

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


app.dependency_overrides[get_session] = _override_get_session
app.dependency_overrides[verify_api_key] = lambda: "test-key"

client = TestClient(app)


def test_create_connection_without_platform_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MF_AWS_PLATFORM_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("MF_AWS_PLATFORM_SECRET_ACCESS_KEY", raising=False)

    response = client.post("/api/v1/cloud-connections/aws")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert "error" in data
    assert "setup_instructions" not in data


@mock_aws
def test_full_connection_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MF_AWS_PLATFORM_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("MF_AWS_PLATFORM_SECRET_ACCESS_KEY", "testing")

    create_response = client.post("/api/v1/cloud-connections/aws")
    assert create_response.status_code == 200
    created = create_response.json()
    connection_id = created["connection_id"]
    external_id = created["external_id"]
    assert "setup_instructions" in created
    assert external_id in created["setup_instructions"]

    # Simulate the user having run those instructions in their own account.
    iam = boto3.client("iam", region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing")
    platform_arn = platform_identity_arn()
    assert platform_arn is not None
    role = iam.create_role(
        RoleName="test-connection-role",
        AssumeRolePolicyDocument=generate_trust_policy(platform_arn, external_id),
    )
    role_arn = role["Role"]["Arn"]

    set_arn_response = client.post(
        f"/api/v1/cloud-connections/aws/{connection_id}/role-arn", json={"role_arn": role_arn}
    )
    assert set_arn_response.status_code == 200
    assert set_arn_response.json()["role_arn"] == role_arn

    verify_response = client.get(f"/api/v1/cloud-connections/aws/{connection_id}/verify")
    assert verify_response.status_code == 200
    verify_data = verify_response.json()
    assert verify_data["status"] == "verified"
    assert "Verified access as" in verify_data["message"]

    get_response = client.get(f"/api/v1/cloud-connections/aws/{connection_id}")
    assert get_response.status_code == 200
    get_data = get_response.json()
    assert get_data["status"] == "verified"
    assert get_data["role_arn"] == role_arn
    assert get_data["verified_at"] is not None


def test_verify_unknown_connection_returns_404() -> None:
    response = client.get("/api/v1/cloud-connections/aws/does-not-exist/verify")
    assert response.status_code == 404


def test_verify_without_role_arn_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MF_AWS_PLATFORM_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("MF_AWS_PLATFORM_SECRET_ACCESS_KEY", raising=False)

    create_response = client.post("/api/v1/cloud-connections/aws")
    connection_id = create_response.json()["connection_id"]

    verify_response = client.get(f"/api/v1/cloud-connections/aws/{connection_id}/verify")
    assert verify_response.status_code == 400
