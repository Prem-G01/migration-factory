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
