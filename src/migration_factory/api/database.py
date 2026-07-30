"""Async PostgreSQL persistence for API run results (SQLAlchemy 2.0 + asyncpg).

Replaces the old in-memory `_RUNS` dict: run metadata, the full JSON report,
the pre-rendered HTML report, and the generated Terraform zip (when present)
are all persisted here, so runs survive an API process restart. Schema
changes go through Alembic (`alembic/`), never `Base.metadata.create_all()`
in application code.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, LargeBinary, String, Text, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from migration_factory.core.config import get_settings


class Base(DeclarativeBase):
    pass


class MigrationRun(Base):
    __tablename__ = "migration_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    direction: Mapped[str] = mapped_column(String(64))
    source_file: Mapped[str] = mapped_column(String(255))
    target: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    report_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    # Not in the originally requested column list, but GET /report/{id}/html
    # (an endpoint that already existed) needs somewhere to read rendered
    # HTML from — regenerating it per-request would mean re-hydrating every
    # nested Pydantic report from report_json. Cheaper and simpler to store
    # the render once, at analyze time.
    html_report: Mapped[str] = mapped_column(Text)
    terraform_zip_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class CloudConnection(Base):
    """A cross-account IAM role trust relationship a user has (or is being
    asked to) set up in their own AWS account, granting this platform's
    fixed identity permission to assume it. Deliberately holds no secret
    material -- only a role ARN and an external ID, both safe to store in
    plaintext. See PHASE_1_CLOUD_ACCESS design notes in the engine module
    docstring for why this replaces storing long-lived user credentials.

    Single-tenant for now (no user_id) -- this app has no account/auth
    model beyond a shared API key today; add user_id once one exists
    rather than guessing at its shape now.
    """

    __tablename__ = "cloud_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider: Mapped[str] = mapped_column(String(16))
    role_arn: Mapped[str] = mapped_column(String(255))
    external_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending, verified, failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database.url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency: yields a session scoped to one request."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def save_run(session: AsyncSession, run: MigrationRun) -> None:
    session.add(run)
    await session.commit()


async def get_run(session: AsyncSession, run_id: str) -> MigrationRun | None:
    return await session.get(MigrationRun, run_id)


async def list_runs(session: AsyncSession) -> list[MigrationRun]:
    result = await session.execute(select(MigrationRun).order_by(MigrationRun.created_at.desc()))
    return list(result.scalars().all())


async def delete_run(session: AsyncSession, run_id: str) -> bool:
    run = await session.get(MigrationRun, run_id)
    if run is None:
        return False
    await session.delete(run)
    await session.commit()
    return True


async def save_cloud_connection(session: AsyncSession, connection: CloudConnection) -> None:
    session.add(connection)
    await session.commit()


async def get_cloud_connection(session: AsyncSession, connection_id: str) -> CloudConnection | None:
    return await session.get(CloudConnection, connection_id)
