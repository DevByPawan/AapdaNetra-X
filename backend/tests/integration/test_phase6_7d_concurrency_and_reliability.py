"""AapdaNetra-X — Phase 6.7D Real PostgreSQL Concurrency & Reliability Integration Suite

Executes real PostgreSQL/PostGIS concurrency, health check, failure mode, transaction isolation,
and connection lifecycle tests against the dedicated test database 'aapdanetra_test'.
"""

import asyncio
from datetime import datetime, timezone
import uuid
import pytest
from geoalchemy2 import WKTElement
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings
from app.db.models import Incident, TelemetryObservation, RiskPrediction
from app.db.session import DatabaseManager
from app.services.timeline_service import TimelineService
from app.services.persistence_service import PersistenceService

pytestmark = pytest.mark.postgis


# ── TEST 1: EXTENDED HEALTH CHECK & LATENCY ─────────────────────────────────

@pytest.mark.anyio
async def test_01_database_pool_and_health_check_extended_metadata(test_engine):
    """Verify check_health measures database latency (ms) and queries PostGIS version without exposing secrets."""
    db_mgr = DatabaseManager()
    db_mgr._engine = test_engine
    db_mgr._available = True

    health = await db_mgr.check_health(persistence_mode="required")

    assert health["mode"] == "required"
    assert health["configured"] is True
    assert health["available"] is True
    assert health["backend"] == "postgresql"
    assert health["error"] is None

    # Extended database health metadata
    assert "database" in health
    db_meta = health["database"]
    assert db_meta["status"] == "healthy"
    assert db_meta["reachable"] is True
    assert isinstance(db_meta["latency_ms"], float)
    assert db_meta["latency_ms"] > 0.0

    # Extended PostGIS health metadata
    assert "postgis" in health
    gis_meta = health["postgis"]
    assert gis_meta["status"] == "available"
    assert isinstance(gis_meta["version"], str)
    assert "POSTGIS" in gis_meta["version"]


# ── TEST 2: FAILURE MODE & SANITIZED ERROR HANDLING ──────────────────────────

@pytest.mark.anyio
async def test_02_connection_failure_modes_and_sanitized_errors():
    """Verify DatabaseManager handles connection failures gracefully and sanitizes error output."""
    db_mgr = DatabaseManager()

    # Invalid connection string with password secret
    bad_url = "postgresql+asyncpg://bad_user:secret_password_123@127.0.0.1:59999/nonexistent_db"

    success = await db_mgr.initialize(
        database_url=bad_url,
        pool_size=1,
        max_overflow=0,
        connect_timeout=1,
    )

    assert success is False
    assert db_mgr.is_available is False
    assert db_mgr.initialization_error is not None

    # CRITICAL: Must not leak secret password or raw connection URI
    assert "secret_password_123" not in db_mgr.initialization_error
    assert "bad_user:secret_password_123" not in db_mgr.initialization_error

    # Verify health metadata output under failure
    health = db_mgr.get_health_metadata(persistence_mode="required")
    assert health["available"] is False
    assert health["error"] is not None
    assert "secret_password_123" not in health["error"]


# ── TEST 3: CONCURRENT MULTI-INCIDENT WRITING ────────────────────────────────

@pytest.mark.anyio
async def test_03_concurrent_multi_incident_writing(test_engine):
    """Smoke test: 5 independent tasks writing different incidents concurrently to PostgreSQL."""
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async def write_incident(idx: int):
        now = datetime.now(timezone.utc)
        inc_id = f"INC-CONCUR-{idx}-{uuid.uuid4().hex[:4]}"
        async with session_factory() as session:
            inc = Incident(
                id=inc_id, incident_type="flood", status="active", started_at=now,
                sector=f"Sector-{idx}", severity="MEDIUM", location_name=f"Loc {idx}",
                latitude=28.6 + idx * 0.01, longitude=77.2 + idx * 0.01,
                geom=WKTElement(f"POINT({77.2 + idx * 0.01} {28.6 + idx * 0.01})", srid=4326)
            )
            session.add(inc)
            await session.commit()
            return inc_id

    inc_ids = await asyncio.gather(*[write_incident(i) for i in range(5)])

    assert len(inc_ids) == 5
    assert len(set(inc_ids)) == 5

    # Verify all 5 incidents exist in PostgreSQL
    async with session_factory() as session:
        res = await session.execute(select(Incident).where(Incident.id.in_(inc_ids)))
        fetched = res.scalars().all()
        assert len(fetched) == 5


# ── TEST 4: CONCURRENT TELEMETRY WRITES FOR SAME INCIDENT ─────────────────────

@pytest.mark.anyio
async def test_04_concurrent_telemetry_writes_for_same_incident(test_engine, test_db_session: AsyncSession):
    """Smoke test: 10 concurrent telemetry writes targeting the same parent incident."""
    now = datetime.now(timezone.utc)
    inc_id = f"INC-TEL-CONCUR-{uuid.uuid4().hex[:6]}"

    inc = Incident(
        id=inc_id, incident_type="flood", status="active", started_at=now,
        sector="Sector-1", severity="HIGH", location_name="Hub", latitude=28.6, longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326)
    )
    test_db_session.add(inc)
    await test_db_session.commit()

    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async def write_telemetry(idx: int):
        async with session_factory() as session:
            obs = TelemetryObservation(
                id=uuid.uuid4(), incident_id=inc_id, data_mode="live", fallback_used=False,
                rainfall_intensity=10.0 + idx, rainfall_trend=0.0, water_level=2.0, water_level_trend=0.0,
                road_congestion=0.1, population_exposure=100.0, infrastructure_vulnerability=0.1,
                provenance={"worker_id": idx}, observed_at=now
            )
            session.add(obs)
            await session.commit()
            return obs.id

    obs_ids = await asyncio.gather(*[write_telemetry(i) for i in range(10)])

    assert len(obs_ids) == 10
    assert len(set(obs_ids)) == 10

    # Verify all 10 observations persisted under the parent incident
    async with session_factory() as session:
        res = await session.execute(select(TelemetryObservation).where(TelemetryObservation.incident_id == inc_id))
        fetched = res.scalars().all()
        assert len(fetched) == 10


# ── TEST 5: CONCURRENT RISK PREDICTION WRITES ────────────────────────────────

@pytest.mark.anyio
async def test_05_concurrent_risk_prediction_writes_for_same_incident(test_engine, test_db_session: AsyncSession):
    """Smoke test: 5 concurrent risk prediction writes for the same incident across horizons."""
    now = datetime.now(timezone.utc)
    inc_id = f"INC-RISK-CONCUR-{uuid.uuid4().hex[:6]}"

    inc = Incident(
        id=inc_id, incident_type="flood", status="active", started_at=now,
        sector="Sector-1", severity="HIGH", location_name="Hub", latitude=28.6, longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326)
    )
    test_db_session.add(inc)
    await test_db_session.commit()

    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async def write_risk(horizon: int):
        async with session_factory() as session:
            pred = RiskPrediction(
                id=uuid.uuid4(), incident_id=inc_id, horizon=horizon, horizon_label=f"+{horizon}h",
                current_risk=0.5, predicted_risk=0.5 + (horizon * 0.05), risk_category="MEDIUM",
                confidence=0.9, prediction_reliability=0.9, affected_population=500, critical_population=50,
                critical_assets_count=1, affected_assets_count=0, trend="STABLE", map_status_text="OK",
                prediction_note="Concur test", input_features={}, heatmap_zones=[], created_at=now
            )
            session.add(pred)
            await session.commit()
            return pred.id

    pred_ids = await asyncio.gather(*[write_risk(h) for h in range(5)])

    assert len(pred_ids) == 5
    assert len(set(pred_ids)) == 5

    async with session_factory() as session:
        res = await session.execute(select(RiskPrediction).where(RiskPrediction.incident_id == inc_id))
        fetched = res.scalars().all()
        assert len(fetched) == 5


# ── TEST 6: CONCURRENT HISTORICAL READS DURING INSERTS ───────────────────────

@pytest.mark.anyio
async def test_06_concurrent_historical_reads_during_inserts(test_engine, test_db_session: AsyncSession):
    """Smoke test: Reads timeline concurrently while background inserts execute on the same incident."""
    now = datetime.now(timezone.utc)
    inc_id = f"INC-READ-WRITE-{uuid.uuid4().hex[:6]}"

    inc = Incident(
        id=inc_id, incident_type="flood", status="active", started_at=now,
        sector="Sector-1", severity="HIGH", location_name="Hub", latitude=28.6, longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326)
    )
    test_db_session.add(inc)
    await test_db_session.commit()

    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async def writer_task(idx: int):
        async with session_factory() as session:
            obs = TelemetryObservation(
                id=uuid.uuid4(), incident_id=inc_id, data_mode="live", fallback_used=False,
                rainfall_intensity=20.0 + idx, rainfall_trend=0.0, water_level=2.5, water_level_trend=0.0,
                road_congestion=0.2, population_exposure=200.0, infrastructure_vulnerability=0.2,
                provenance={}, observed_at=now
            )
            session.add(obs)
            await session.commit()

    async def reader_task():
        async with session_factory() as session:
            svc = TimelineService(session)
            res = await svc.get_incident_timeline(inc_id)
            return len(res.items)

    # Run 5 writers and 5 readers concurrently
    writers = [writer_task(i) for i in range(5)]
    readers = [reader_task() for _ in range(5)]

    results = await asyncio.gather(*writers, *readers)
    read_counts = results[5:]

    for count in read_counts:
        assert isinstance(count, int)
        assert count >= 0


# ── TEST 7: SESSION LIFECYCLE & CONNECTION RELEASE ────────────────────────────

@pytest.mark.anyio
async def test_07_session_lifecycle_and_connection_release(test_engine):
    """Verify session pool cleanly reclaims connections after rapid sequential and concurrent session usage."""
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    # Acquire and release 20 sessions sequentially
    for _ in range(20):
        async with session_factory() as session:
            res = await session.execute(text("SELECT 1"))
            assert res.scalar() == 1

    # Acquire and release 10 sessions concurrently
    async def session_worker():
        async with session_factory() as session:
            res = await session.execute(text("SELECT 1"))
            return res.scalar()

    results = await asyncio.gather(*[session_worker() for _ in range(10)])
    assert results == [1] * 10
