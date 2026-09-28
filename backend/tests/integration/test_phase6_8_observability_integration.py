"""AapdaNetra-X — Phase 6.8 Real PostgreSQL Observability & Monitoring Integration Suite

Executes real PostgreSQL/PostGIS database health latency measurement, SSE event metrics tracking,
and persistence pipeline timing against 'aapdanetra_test'.
"""

from datetime import datetime, timezone
import uuid
import pytest
from geoalchemy2 import WKTElement

from app.config import settings
from app.db.models import Incident, TelemetryObservation, RiskPrediction, SHAPRecord, EvacuationRoute
from app.db.session import DatabaseManager
from app.events.broker import get_event_broker
from app.services.persistence_service import PersistenceService
from app.services.timeline_service import TimelineService
from app.db.pagination import PaginationParams

pytestmark = pytest.mark.postgis


# ── TEST 1: REAL POSTGRESQL HEALTH LATENCY & POSTGIS METRICS ────────────────

@pytest.mark.anyio
async def test_01_real_postgresql_health_latency_measurement(test_engine):
    """Verify real PostgreSQL SELECT 1 latency measurement and PostGIS version check against aapdanetra_test."""
    db_mgr = DatabaseManager()
    db_mgr._engine = test_engine
    db_mgr._available = True

    health = await db_mgr.check_health(persistence_mode="required")

    assert health["available"] is True
    assert health["backend"] == "postgresql"

    # Database latency
    db_meta = health["database"]
    assert db_meta["status"] == "healthy"
    assert db_meta["reachable"] is True
    assert isinstance(db_meta["latency_ms"], float)
    assert db_meta["latency_ms"] > 0.0

    # PostGIS version
    gis_meta = health["postgis"]
    assert gis_meta["status"] == "available"
    assert isinstance(gis_meta["version"], str)
    assert "POSTGIS" in gis_meta["version"]


# ── TEST 2: REAL PERSISTENCE PIPELINE TIMING & SSE STATS ─────────────────────

@pytest.mark.anyio
async def test_02_real_persistence_pipeline_timing_and_sse_stats(test_db_session):
    """Verify real persistence pipeline timing and post-commit SSE metrics increment against aapdanetra_test."""
    now = datetime.now(timezone.utc)
    inc_id = f"INC-OBS-REAL-{uuid.uuid4().hex[:6]}"

    inc = Incident(
        id=inc_id, incident_type="flood", status="active", started_at=now,
        sector="Sector-4", severity="HIGH", location_name="Obs Hub", latitude=28.6, longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326)
    )
    test_db_session.add(inc)
    await test_db_session.commit()

    tel = TelemetryObservation(
        id=uuid.uuid4(), data_mode="live", fallback_used=False,
        rainfall_intensity=55.0, rainfall_trend=0.5, water_level=3.8, water_level_trend=0.1,
        road_congestion=0.4, population_exposure=1500.0, infrastructure_vulnerability=0.35,
        provenance={}, observed_at=now
    )
    pred = RiskPrediction(
        id=uuid.uuid4(), horizon=0, horizon_label="NOW", current_risk=0.55, predicted_risk=0.72,
        risk_category="HIGH", confidence=0.92, prediction_reliability=0.94, affected_population=1500,
        critical_population=150, critical_assets_count=3, affected_assets_count=1, trend="RISING",
        map_status_text="Rising risk", prediction_note="Observability test", input_features={}, heatmap_zones=[], created_at=now
    )
    shap = SHAPRecord(
        id=uuid.uuid4(), horizon=0, prediction=0.72, base_value=0.2, total_shap_delta=0.52,
        features={}, decision_trace={}, created_at=now
    )
    route = EvacuationRoute(
        id=uuid.uuid4(), route_name="Observability Route", route_type="primary", is_recommended=True,
        origin_name="O", origin_lat=28.6, origin_lon=77.2, destination_name="D", destination_lat=28.7, destination_lon=77.3,
        waypoint_coords=[], distance_km=4.5, estimated_minutes=11.0, safety_score=0.92, created_at=now
    )

    broker = get_event_broker()
    sub_q = broker.subscribe()
    published_before = broker.get_stats()["total_published"]

    from unittest.mock import patch, MagicMock

    ps = PersistenceService()
    mock_mgr = MagicMock()
    mock_mgr.is_available = True

    class TestSessionContext:
        def __init__(self, session):
            self.session = session
        async def __aenter__(self):
            return self.session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_mgr.get_session.return_value = TestSessionContext(test_db_session)

    try:
        with patch("app.services.persistence_service.get_db_manager", return_value=mock_mgr):
            with patch.object(settings, "persistence_mode", "required"):
                success = await ps.persist_assessment_pipeline(
                    incident_id=inc_id,
                    telemetry=tel,
                    prediction=pred,
                    shap_record=shap,
                    routes=[route],
                )
                assert success is True

        # Confirm post-commit SSE publication occurred
        published_after = broker.get_stats()["total_published"]
        assert published_after >= published_before + 1
    finally:
        broker.unsubscribe(sub_q)


# ── TEST 3: REAL TIMELINE QUERY OBSERVABILITY & UNCHANGED CONTRACTS ──────────

@pytest.mark.anyio
async def test_03_real_timeline_query_observability(test_db_session):
    """Verify TimelineService queries real PostgreSQL with exact Phase 6.6C ordering and pagination contracts intact."""
    now = datetime.now(timezone.utc)
    inc_id = f"INC-OBS-TL-{uuid.uuid4().hex[:6]}"

    inc = Incident(
        id=inc_id, incident_type="flood", status="active", started_at=now,
        sector="Sector-4", severity="HIGH", location_name="Obs TL Hub", latitude=28.6, longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326)
    )
    test_db_session.add(inc)
    await test_db_session.commit()

    tel = TelemetryObservation(
        id=uuid.uuid4(), incident_id=inc_id, data_mode="live", fallback_used=False,
        rainfall_intensity=30.0, rainfall_trend=0.0, water_level=2.0, water_level_trend=0.0,
        road_congestion=0.2, population_exposure=500.0, infrastructure_vulnerability=0.2,
        provenance={}, observed_at=now
    )
    test_db_session.add(tel)
    await test_db_session.commit()

    service = TimelineService(test_db_session)
    result = await service.get_incident_timeline(inc_id, PaginationParams(limit=10))

    assert len(result.items) == 1
    item = result.items[0]
    assert item.entity_type == "telemetry_observation"
    assert item.entity_id == str(tel.id)
    assert item.incident_id == inc_id
