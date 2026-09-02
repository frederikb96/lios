"""Database connection management: async engine, session factory, lifecycle."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

if TYPE_CHECKING:
    from lios_relay.config import DatabaseConfig

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Manages the async engine and session factory for one database URL."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        """The async engine, raising if :meth:`init` has not run yet."""
        if self._engine is None:
            raise RuntimeError("Database not initialized. Call init() first.")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """The session factory, raising if :meth:`init` has not run yet."""
        if self._session_factory is None:
            raise RuntimeError("Database not initialized. Call init() first.")
        return self._session_factory

    async def init(self) -> None:
        """Create the engine and session factory."""
        self._engine = create_async_engine(
            self._config.url,
            echo=False,
            pool_size=self._config.pool_size,
            max_overflow=self._config.max_overflow,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        url_safe = self._config.url.split("@")[-1] if "@" in self._config.url else "***"
        logger.info("Database initialized", extra={"url": url_safe})

    async def close(self) -> None:
        """Dispose of the connection pool."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database connection closed")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """An async session context manager: commits on success, rolls back on exception."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def health_check(self) -> bool:
        """Whether the database is currently reachable."""
        try:
            async with self.session() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.warning("Database health check failed", extra={"error": str(e)})
            return False


_db_connection: DatabaseConnection | None = None


def get_db_connection() -> DatabaseConnection:
    """The global database connection.

    Raises:
        RuntimeError: :func:`init_database` has not run yet.
    """
    if _db_connection is None:
        raise RuntimeError("Database not initialized")
    return _db_connection


async def init_database(config: DatabaseConfig) -> DatabaseConnection:
    """Initialize the global database connection."""
    global _db_connection
    _db_connection = DatabaseConnection(config)
    await _db_connection.init()
    return _db_connection


async def close_database() -> None:
    """Close the global database connection."""
    global _db_connection
    if _db_connection:
        await _db_connection.close()
        _db_connection = None
