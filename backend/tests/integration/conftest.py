"""Phase 6.7C — Real PostgreSQL/PostGIS Integration Test Fixtures

Provides async engine and session management targeting exclusively the dedicated 'aapdanetra_test' database.
"""

import os
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

TEST_DB_NAME = "aapdanetra_test"
TEST_DB_URL = f"postgresql+asyncpg://pawanagrahari@localhost:5432/{TEST_DB_NAME}"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def test_engine():
    """Session-scoped AsyncEngine connecting exclusively to aapdanetra_test."""
    engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)
    
    # Safety Check: Fail fast if connected to wrong database
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT current_database();"))
        active_db = res.scalar()
        if active_db != TEST_DB_NAME:
            raise RuntimeError(
                f"SAFETY FATAL: Integration test attempted to connect to '{active_db}' "
                f"instead of dedicated test database '{TEST_DB_NAME}'!"
            )
            
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
async def init_db_manager(test_engine):
    from app.config import settings
    from app.db.session import get_db_manager
    orig_mode = settings.persistence_mode
    orig_url = settings.database_url
    settings.persistence_mode = "required"
    settings.database_url = TEST_DB_URL
    db_mgr = get_db_manager()
    await db_mgr.initialize(TEST_DB_URL)
    yield db_mgr
    await db_mgr.dispose()
    settings.persistence_mode = orig_mode
    settings.database_url = orig_url


@pytest.fixture
async def test_db_session(test_engine):
    """Function-scoped AsyncSession with clean table truncation post-test."""
    session_factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    # Post-test cleanup: truncate domain tables in dependency order without dropping schema
    async with test_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE decisions, audit_events, alerts, simulations, evacuation_routes, "
"shap_records, risk_predictions, telemetry_observations, critical_assets, "
"incidents CASCADE;"
            )
        )
