"""AapdaNetra-X Database Session Layer — Phase 6.5A

Async SQLAlchemy 2.x engine and session management for PostgreSQL + PostGIS.

Architecture:
  DatabaseManager is a singleton that owns the engine lifecycle.
  It is initialized at FastAPI startup and disposed at shutdown.

  No ORM models are defined here — that is Phase 6.5B.
  No Alembic migrations are configured — that is Phase 6.5B.
  No PostGIS CREATE EXTENSION is issued — migrations will handle that.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger("aapdanetra.db")


class DatabaseManager:
    """Manages the async SQLAlchemy engine and session factory.

    Lifecycle:
        1. initialize()  — creates engine, verifies connectivity
        2. get_session()  — returns an async session (context manager)
        3. dispose()      — cleanly shuts down pool and engine
    """

    def __init__(self) -> None:
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._available: bool = False
        self._initialization_error: Optional[str] = None

    # ── Public Properties ─────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """Whether the database connection was successfully established."""
        return self._available

    @property
    def initialization_error(self) -> Optional[str]:
        """Sanitized error message if initialization failed, else None."""
        return self._initialization_error

    @property
    def engine(self) -> Optional[AsyncEngine]:
        """The underlying async engine, or None if not initialized."""
        return self._engine

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def initialize(
        self,
        database_url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 1800,
        pool_pre_ping: bool = True,
        connect_timeout: int = 10,
        command_timeout: int = 30,
        echo: bool = False,
    ) -> bool:
        """Create the async engine and verify connectivity.

        Args:
            database_url: Async-compatible PostgreSQL connection string.
            pool_size: Number of persistent connections in the pool.
            max_overflow: Maximum overflow connections beyond pool_size.
            pool_timeout: Seconds to wait before timing out on getting a connection.
            pool_recycle: Seconds after which to recycle connections.
            pool_pre_ping: Whether to check connection health before checkout.
            connect_timeout: Driver connection timeout in seconds.
            command_timeout: Driver query command execution timeout in seconds.
            echo: Whether to log all SQL statements (debug only).

        Returns:
            True if the database is reachable, False otherwise.
        """
        try:
            self._engine = create_async_engine(
                database_url,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=pool_timeout,
                pool_recycle=pool_recycle,
                pool_pre_ping=pool_pre_ping,
                connect_args={
                    "timeout": connect_timeout,
                    "command_timeout": command_timeout,
                },
                echo=echo,
            )

            self._session_factory = async_sessionmaker(
                bind=self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            # Lightweight connectivity check
            async with self._engine.connect() as conn:
                await conn.execute(
                    __import__("sqlalchemy").text("SELECT 1")
                )

            self._available = True
            self._initialization_error = None
            logger.info("Database connection established successfully")
            return True

        except Exception as exc:
            self._available = False
            # Sanitize: never include credentials in the error message
            self._initialization_error = _sanitize_db_error(str(exc))
            logger.error(
                "Database initialization failed: %s",
                self._initialization_error,
            )
            # Clean up partial engine if created
            if self._engine is not None:
                try:
                    await self._engine.dispose()
                except Exception:
                    pass
                self._engine = None
                self._session_factory = None
            return False

    async def dispose(self) -> None:
        """Dispose the engine and release all pooled connections."""
        if self._engine is not None:
            await self._engine.dispose()
            logger.info("Database engine disposed")
        self._engine = None
        self._session_factory = None
        self._available = False

    # ── Session Access ────────────────────────────────────────────────

    def get_session(self) -> AsyncSession:
        """Create a new async session.

        Raises:
            RuntimeError: If the database is not initialized or unavailable.
        """
        if self._session_factory is None:
            raise RuntimeError(
                "Database session requested but database is not initialized. "
                "Check PERSISTENCE_MODE and database connectivity."
            )
        return self._session_factory()

    # ── Health Metadata ───────────────────────────────────────────────

    def get_health_metadata(self, persistence_mode: str) -> dict:
        """Return non-sensitive persistence metadata for /health.

        Never exposes credentials, URLs, or connection strings.
        """
        configured = persistence_mode.lower() != "disabled"
        return {
            "mode": persistence_mode,
            "configured": configured,
            "available": self._available if configured else False,
            "backend": "postgresql" if configured else None,
            "error": self._initialization_error if (configured and not self._available) else None,
        }

    async def check_health(self, persistence_mode: str) -> dict:
        """Perform active DB connectivity check, measure latency, verify PostGIS, and return sanitized health info."""
        base_meta = self.get_health_metadata(persistence_mode)
        mode = persistence_mode.lower()

        if mode == "disabled" or self._engine is None or not self._available:
            base_meta["database"] = {
                "status": "disabled" if mode == "disabled" else "unreachable",
                "reachable": False,
                "latency_ms": None,
            }
            base_meta["postgis"] = {
                "status": "disabled" if mode == "disabled" else "unavailable",
                "version": None,
            }
            return base_meta

        import time
        from sqlalchemy import text

        try:
            start_time = time.perf_counter()
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

                postgis_ver = None
                try:
                    res = await conn.execute(text("SELECT PostGIS_Full_Version()"))
                    postgis_ver = res.scalar()
                except Exception:
                    pass

            base_meta["database"] = {
                "status": "healthy",
                "reachable": True,
                "latency_ms": latency_ms,
            }
            base_meta["postgis"] = {
                "status": "available" if postgis_ver else "unavailable",
                "version": postgis_ver,
            }
            return base_meta

        except Exception as exc:
            sanitized_err = _sanitize_db_error(str(exc))
            base_meta["available"] = False
            base_meta["error"] = sanitized_err
            base_meta["database"] = {
                "status": "unreachable",
                "reachable": False,
                "latency_ms": None,
            }
            base_meta["postgis"] = {
                "status": "unavailable",
                "version": None,
            }
            return base_meta


# ── Module-level singleton ────────────────────────────────────────────

_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Return the module-level DatabaseManager singleton.

    The singleton is created lazily on first access.
    Initialization (engine creation) happens separately via initialize().
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


async def get_db():
    """FastAPI dependency yielding an AsyncSession."""
    manager = get_db_manager()
    session = manager.get_session()
    try:
        yield session
    finally:
        await session.close()


def _reset_db_manager() -> None:
    """Reset the singleton — used only in tests."""
    global _db_manager
    _db_manager = None


# ── Helpers ───────────────────────────────────────────────────────────

def _sanitize_db_error(error_message: str) -> str:
    """Remove potential credentials from database error messages.

    Strips anything that looks like a connection string or password.
    """
    import re

    # Remove full connection URIs
    sanitized = re.sub(
        r"postgresql(\+\w+)?://[^\s]+",
        "postgresql://***",
        error_message,
    )
    # Remove password= parameters
    sanitized = re.sub(
        r"password=[^\s&]+",
        "password=***",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized
