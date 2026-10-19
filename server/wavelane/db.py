"""Async SQLAlchemy engine, session factory and FastAPI dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    """SQLite needs WAL + foreign keys turned on explicitly, per connection."""
    module = type(dbapi_connection).__module__
    if "sqlite" not in module:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


def build_engine(settings: Settings | None = None) -> AsyncEngine:
    settings = settings or get_settings()
    kwargs: dict[str, Any] = {"echo": False, "future": True}
    if settings.is_sqlite:
        # A single file cannot take concurrent writers; pooling is pointless.
        kwargs["connect_args"] = {"timeout": 30}
    else:
        kwargs |= {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}
    return create_async_engine(settings.database_url, **kwargs)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, autoflush=False
        )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session that commits on success."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_models() -> None:
    """Create tables that do not exist yet (development convenience)."""
    from .models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(connection) -> None:
    """Add columns that newer code expects to a database made by an older version.

    create_all only creates missing tables, so a column added later would never appear
    in an existing file. Each entry is (table, column, SQL type).
    """
    from sqlalchemy import inspect, text

    wanted = [("tracks", "cover_path", "VARCHAR(500)")]
    inspector = inspect(connection)
    for table, column, sql_type in wanted:
        if column not in {c["name"] for c in inspector.get_columns(table)}:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
