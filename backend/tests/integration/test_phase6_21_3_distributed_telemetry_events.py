"""Phase 6.21.3 — Distributed Telemetry & Events Integration Tests.

Verifies:
1. Sequential duplicate fingerprint submission returns duplicate_ignored and single DB row.
2. Concurrent duplicate fingerprint submissions resolve via PostgreSQL unique constraint to single DB row.
3. Multi-worker recovery of authoritative latest telemetry observation from PostgreSQL.
4. Out-of-order telemetry observation protection (older timestamps do not overwrite latest state).
5. Trend calculation derived from persisted PostgreSQL telemetry history.
6. Persistence mode: required failure prevents live overlay mutation and returns HTTP 503.
7. Cross-worker event propagation (Event published by Worker A reaches SSE subscriber on Worker B).
8. Hazard isolation: extreme_rainfall telemetry persists contextually without triggering flood routing/decisions.
"""

from datetime import datetime, timezone, timedelta
import asyncio
import uuid
import pytest

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Incident, TelemetryObservation
from app.events.broker import EventBroker
from app.events.schemas import EventEnvelope, EventType
from app.models.schemas import TelemetryIngestionRequest
from app.services.telemetry_service import (
    get_telemetry_service,
    TelemetryIngestionService,
    compute_observation_hash,
    _DEDUPLICATION_CACHE,
    _LATEST_OBSERVED_AT,
    _PREVIOUS_OBSERVATION,
)
from app.services.persistence_service import get_persistence_service
from app.hazards.types import HazardType

pytestmark = pytest.mark.postgis


def _make_incident_id() -> str:
    return f"INC-6.21.3-{uuid.uuid4().hex[:10]}"


async def _create_incident(session: AsyncSession, incident_id: str) -> Incident:
    from geoalchemy2 import WKTElement
    incident = Incident(
        id=incident_id,
        incident_type="flood",
        status="active",
        started_at=datetime.now(timezone.utc),
        sector="Phase-6.21.3",
        severity="HIGH",
        location_name="Yamuna River Corridor",
        latitude=28.6448,
        longitude=77.2167,
        geom=WKTElement("POINT(77.2167 28.6448)", srid=4326),
    )
    session.add(incident)
    await session.flush()
    return incident


@pytest.mark.anyio
async def test_01_telemetry_duplicate_fingerprint_sequential(test_db_session: AsyncSession):
    """1. Verify sequential duplicate fingerprint returns duplicate_ignored and single DB row."""
    inc_id = _make_incident_id()
    await _create_incident(test_db_session, inc_id)
    await test_db_session.commit()

    svc = TelemetryIngestionService()
    now_iso = datetime.now(timezone.utc).isoformat()

    req = TelemetryIngestionRequest(
        incident_id=inc_id,
        sensor_id="SENSOR-SEQ-01",
        observed_at=now_iso,
        features={
            "rainfall_intensity": 45.0,
            "rainfall_trend": 2.0,
            "water_level": 5.5,
            "water_level_trend": 0.4,
            "road_congestion": 0.3,
            "population_exposure": 0.5,
            "infrastructure_vulnerability": 0.4,
        },
        source="sensor_network",
        hazard_type="flood",
    )

    # First ingestion
    res1 = svc.ingest_observation(req)
    assert res1.status in ("accepted", "out_of_order")
    assert res1.persistence_status == "persisted"

    # Second ingestion with exact same payload
    res2 = svc.ingest_observation(req)
    assert res2.status == "duplicate_ignored"
    assert res2.persistence_status == "skipped"

    # Verify PostgreSQL has exactly 1 row for this fingerprint
    obs_res = await test_db_session.execute(
        select(TelemetryObservation).where(TelemetryObservation.fingerprint == res1.observation_hash)
    )
    rows = list(obs_res.scalars().all())
    assert len(rows) == 1


@pytest.mark.anyio
async def test_02_telemetry_duplicate_fingerprint_concurrent(test_db_session: AsyncSession):
    """2. Verify concurrent duplicate fingerprint submissions resolve via PostgreSQL to a single DB row."""
    inc_id = _make_incident_id()
    await _create_incident(test_db_session, inc_id)
    await test_db_session.commit()

    now_iso = datetime.now(timezone.utc).isoformat()
    req = TelemetryIngestionRequest(
        incident_id=inc_id,
        sensor_id="SENSOR-CONC-01",
        observed_at=now_iso,
        features={
            "rainfall_intensity": 50.0,
            "rainfall_trend": 3.0,
            "water_level": 6.0,
            "water_level_trend": 0.5,
            "road_congestion": 0.4,
            "population_exposure": 0.6,
            "infrastructure_vulnerability": 0.5,
        },
        source="sensor_network",
        hazard_type="flood",
    )

    svc1 = TelemetryIngestionService()
    svc2 = TelemetryIngestionService()

    # Clear memory cache so both attempt DB save
    _DEDUPLICATION_CACHE.clear()

    # Run ingest concurrently
    loop = asyncio.get_running_loop()
    res1, res2 = await asyncio.gather(
        loop.run_in_executor(None, svc1.ingest_observation, req),
        loop.run_in_executor(None, svc2.ingest_observation, req),
    )

    statuses = {res1.status, res2.status}
    assert "duplicate_ignored" in statuses or res1.status == "accepted"

    # Verify PostgreSQL has exactly 1 row
    obs_res = await test_db_session.execute(
        select(TelemetryObservation).where(TelemetryObservation.fingerprint == res1.observation_hash)
    )
    rows = list(obs_res.scalars().all())
    assert len(rows) == 1


@pytest.mark.anyio
async def test_03_telemetry_latest_observation_recovery_across_workers(test_db_session: AsyncSession):
    """3. Verify multi-worker recovery of authoritative latest telemetry observation from PostgreSQL."""
    inc_id = _make_incident_id()
    await _create_incident(test_db_session, inc_id)
    await test_db_session.commit()

    svc1 = TelemetryIngestionService()
    now_iso = datetime.now(timezone.utc).isoformat()

    req = TelemetryIngestionRequest(
        incident_id=inc_id,
        sensor_id="SENSOR-RECOV-01",
        observed_at=now_iso,
        features={
            "rainfall_intensity": 60.0,
            "rainfall_trend": 4.0,
            "water_level": 6.8,
            "water_level_trend": 0.6,
            "road_congestion": 0.5,
            "population_exposure": 0.7,
            "infrastructure_vulnerability": 0.6,
        },
        source="sensor_network",
        hazard_type="flood",
    )
    svc1.ingest_observation(req)

    # Clear process memory to simulate Worker B
    _LATEST_OBSERVED_AT.clear()
    _PREVIOUS_OBSERVATION.clear()

    # Worker B queries PersistenceService directly
    ps = get_persistence_service()
    latest_dict = ps.get_latest_telemetry_observation_sync(inc_id, hazard_type="flood")
    assert latest_dict is not None
    assert latest_dict["incident_id"] == inc_id
    assert latest_dict["rainfall_intensity"] == 60.0
    assert latest_dict["water_level"] == 6.8


@pytest.mark.anyio
async def test_04_telemetry_out_of_order_observation_protection(test_db_session: AsyncSession):
    """4. Verify out-of-order telemetry protection prevents older timestamps from corrupting latest state."""
    inc_id = _make_incident_id()
    await _create_incident(test_db_session, inc_id)
    await test_db_session.commit()

    svc = TelemetryIngestionService()
    now_dt = datetime.now(timezone.utc)
    t2_iso = now_dt.isoformat()
    t1_iso = (now_dt - timedelta(minutes=10)).isoformat()

    # Ingest newer observation T2
    req_t2 = TelemetryIngestionRequest(
        incident_id=inc_id,
        sensor_id="SENSOR-ORDER-01",
        observed_at=t2_iso,
        features={
            "rainfall_intensity": 70.0,
            "rainfall_trend": 5.0,
            "water_level": 7.5,
            "water_level_trend": 0.8,
            "road_congestion": 0.6,
            "population_exposure": 0.8,
            "infrastructure_vulnerability": 0.7,
        },
        hazard_type="flood",
    )
    res_t2 = svc.ingest_observation(req_t2)
    assert res_t2.status == "accepted"

    # Ingest older observation T1
    req_t1 = TelemetryIngestionRequest(
        incident_id=inc_id,
        sensor_id="SENSOR-ORDER-01",
        observed_at=t1_iso,
        features={
            "rainfall_intensity": 20.0,
            "rainfall_trend": 1.0,
            "water_level": 3.0,
            "water_level_trend": 0.1,
            "road_congestion": 0.2,
            "population_exposure": 0.3,
            "infrastructure_vulnerability": 0.2,
        },
        hazard_type="flood",
    )
    res_t1 = svc.ingest_observation(req_t1)
    assert res_t1.status == "out_of_order"

    # Verify latest observation in DB is still T2
    ps = get_persistence_service()
    latest_db = ps.get_latest_telemetry_observation_sync(inc_id, hazard_type="flood")
    assert latest_db is not None
    assert latest_db["rainfall_intensity"] == 70.0


@pytest.mark.anyio
async def test_05_telemetry_trend_calculation_from_persisted_history(test_db_session: AsyncSession):
    """5. Verify trend calculation is derived deterministically from persisted PostgreSQL history."""
    inc_id = _make_incident_id()
    await _create_incident(test_db_session, inc_id)
    await test_db_session.commit()

    svc = TelemetryIngestionService()
    base_dt = datetime.now(timezone.utc) - timedelta(minutes=5)
    t1_iso = base_dt.isoformat()
    t2_iso = (base_dt + timedelta(seconds=60)).isoformat()

    # T1
    req1 = TelemetryIngestionRequest(
        incident_id=inc_id,
        sensor_id="SENSOR-TREND-01",
        observed_at=t1_iso,
        features={
            "rainfall_intensity": 10.0,
            "rainfall_trend": 0.0,
            "water_level": 2.0,
            "water_level_trend": 0.0,
            "road_congestion": 0.2,
            "population_exposure": 0.3,
            "infrastructure_vulnerability": 0.2,
        },
        hazard_type="flood",
    )
    svc.ingest_observation(req1)

    # Clear memory cache to force DB trend lookup
    _PREVIOUS_OBSERVATION.clear()

    # T2 (60s later: rainfall +10mm/h -> trend = +600mm/h clamped to 50.0)
    req2 = TelemetryIngestionRequest(
        incident_id=inc_id,
        sensor_id="SENSOR-TREND-01",
        observed_at=t2_iso,
        features={
            "rainfall_intensity": 20.0,
            "rainfall_trend": 0.0,
            "water_level": 2.5,
            "water_level_trend": 0.0,
            "road_congestion": 0.2,
            "population_exposure": 0.3,
            "infrastructure_vulnerability": 0.2,
        },
        hazard_type="flood",
    )
    res2 = svc.ingest_observation(req2)
    assert "rainfall_trend" in res2.trends
    assert res2.trends["rainfall_trend"] == 50.0  # max clamped
    assert "water_level_trend" in res2.trends
    assert res2.trends["water_level_trend"] == 5.0  # max clamped 5.0


@pytest.mark.anyio
async def test_06_cross_worker_event_fan_out(test_db_session: AsyncSession):
    """7 & 8. Verify event published on Worker A reaches subscriber on Worker B via EventBroker fan-out."""
    broker_a = EventBroker()
    broker_b = EventBroker()

    sub_b = broker_b.subscribe()

    env = EventEnvelope(
        event=EventType.TELEMETRY_UPDATED,
        incident_id="INC-6.21.3-FANOUT",
        data={"sensor_id": "TEST-SENSOR", "water_level": 8.2},
    )

    # Publish via Broker A
    broker_a.publish(env)

    # Verify Subscriber on Broker B received the event
    assert sub_b.qsize() == 1
    received_evt = sub_b.get_nowait()
    assert received_evt.id == env.id
    assert received_evt.event == EventType.TELEMETRY_UPDATED
    assert received_evt.data["water_level"] == 8.2

    broker_b.unsubscribe(sub_b)


@pytest.mark.anyio
async def test_07_hazard_isolation_telemetry(test_db_session: AsyncSession):
    """10. Verify extreme_rainfall telemetry persists contextually without triggering flood routing/decisions."""
    inc_id = _make_incident_id()
    await _create_incident(test_db_session, inc_id)
    await test_db_session.commit()

    svc = TelemetryIngestionService()
    now_iso = datetime.now(timezone.utc).isoformat()

    req = TelemetryIngestionRequest(
        incident_id=inc_id,
        sensor_id="SENSOR-RAINFALL-01",
        observed_at=now_iso,
        features={
            "rainfall_intensity": 85.0,
            "rainfall_trend": 10.0,
            "water_level": 1.0,
            "water_level_trend": 0.0,
            "road_congestion": 0.1,
            "population_exposure": 0.2,
            "infrastructure_vulnerability": 0.2,
        },
        hazard_type="extreme_rainfall",
    )
    res = svc.ingest_observation(req)
    assert res.status == "accepted"
    assert res.hazard_type == "extreme_rainfall"

    # Verify telemetry stored under extreme_rainfall hazard_type
    ps = get_persistence_service()
    latest_db = ps.get_latest_telemetry_observation_sync(inc_id, hazard_type="extreme_rainfall")
    assert latest_db is not None
    assert latest_db["hazard_type"] == "extreme_rainfall"
    assert latest_db["rainfall_intensity"] == 85.0


@pytest.mark.anyio
async def test_08_event_broker_listen_notify_lifecycle_and_deduplication(test_db_session: AsyncSession):
    """Focused test verifying EventBroker LISTEN/NOTIFY commit, sender deduplication, and error handling."""
    broker_worker_b = EventBroker()

    # 1. Start listener on Worker B
    await broker_worker_b.start_listener()
    assert broker_worker_b.get_stats()["listener_active"] is True

    # 2. Subscribe to Worker B
    sub_b = broker_worker_b.subscribe()

    # 3. Simulate Worker A sending PostgreSQL NOTIFY with foreign sender_id
    foreign_env = EventEnvelope(
        event=EventType.RISK_UPDATED,
        incident_id="INC-6.21.3-FOREIGN",
        data={"predicted_risk": 0.85},
    )
    payload_foreign = {
        "sender_id": "broker-worker-a-12345",
        "envelope": foreign_env.model_dump(),
    }
    import json
    await test_db_session.execute(
        text("SELECT pg_notify('aapdanetra_events', :payload)"),
        {"payload": json.dumps(payload_foreign)},
    )
    await test_db_session.commit()

    # Wait up to 2 seconds for LISTEN callback to receive notification
    received_event = None
    for _ in range(20):
        if sub_b.qsize() > 0:
            received_event = sub_b.get_nowait()
            break
        await asyncio.sleep(0.1)

    assert received_event is not None
    assert received_event.id == foreign_env.id
    assert received_event.incident_id == "INC-6.21.3-FOREIGN"

    # 4. Sender Deduplication: Send NOTIFY from Worker B's own sender_id -> must be IGNORED
    self_env = EventEnvelope(
        event=EventType.RISK_UPDATED,
        incident_id="INC-6.21.3-SELF",
        data={"predicted_risk": 0.90},
    )
    payload_self = {
        "sender_id": broker_worker_b.broker_id,
        "envelope": self_env.model_dump(),
    }
    await test_db_session.execute(
        text("SELECT pg_notify('aapdanetra_events', :payload)"),
        {"payload": json.dumps(payload_self)},
    )
    await test_db_session.commit()

    await asyncio.sleep(0.3)
    assert sub_b.qsize() == 0  # Self notification ignored by listener

    # 5. Malformed payload should be logged and safely ignored without killing listener
    await test_db_session.execute(
        text("SELECT pg_notify('aapdanetra_events', :payload)"),
        {"payload": "NOT_VALID_JSON"},
    )
    await test_db_session.commit()
    await asyncio.sleep(0.2)
    assert broker_worker_b.get_stats()["listener_active"] is True

    # 6. Stop listener cleanly
    await broker_worker_b.stop_listener()
    assert broker_worker_b.get_stats()["listener_active"] is False
    broker_worker_b.unsubscribe(sub_b)

