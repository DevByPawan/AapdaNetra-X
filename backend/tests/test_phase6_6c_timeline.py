"""AapdaNetra-X — Phase 6.6C Unified Incident Timeline Test Suite

Tests timeline event normalization, multi-entity aggregation, deterministic sorting,
complete timeline cursor continuation, boundary edge-cases, persistence mode compliance,
and error boundaries across all 6 sources.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

pytest_plugins = ("anyio",)

from app.config import settings
from app.main import app
from app.db.models import (
    Incident,
    TelemetryObservation,
    RiskPrediction,
    EvacuationRoute,
    Alert,
    Simulation,
    AuditEvent,
)
from app.db.pagination import PaginationParams
from app.services.timeline_service import TimelineService

client = TestClient(app)


# ── 1. Query Validation Tests ───────────────────────────────────────────

def test_timeline_validation_invalid_limit():
    """Test limit > 100 returns HTTP 422."""
    res = client.get("/api/incidents/INC-001/timeline?limit=101")
    assert res.status_code == 422


def test_timeline_validation_naive_timestamp():
    """Test naive timestamp query param returns HTTP 422."""
    res = client.get("/api/incidents/INC-001/timeline?cursor_timestamp=2026-09-27T08:00:00")
    assert res.status_code == 422


def test_timeline_validation_invalid_time_range():
    """Test from_time > to_time returns HTTP 422."""
    from_t = "2026-09-27T10:00:00Z"
    to_t = "2026-09-27T08:00:00Z"
    res = client.get(f"/api/incidents/INC-001/timeline?from_time={from_t}&to_time={to_t}")
    assert res.status_code == 422


def test_timeline_validation_malformed_cursor():
    """Test malformed cursor_id or incomplete cursor parameters return HTTP 422."""
    inc = Incident(
        id="INC-001", incident_type="flood", status="ACTIVE",
        started_at=datetime.now(timezone.utc), sector="B", severity="HIGH",
        location_name="Yamuna", latitude=28.6, longitude=77.2
    )
    with patch.object(settings, "persistence_mode", "optional"):
        with patch("app.routers.history.get_db_manager") as mock_db_mgr:
            mock_mgr = MagicMock()
            mock_mgr.is_available = True
            mock_session = AsyncMock()
            mock_session.get.return_value = inc
            mock_mgr.get_session.return_value.__aenter__.return_value = mock_session
            mock_db_mgr.return_value = mock_mgr

            res1 = client.get(
                "/api/incidents/INC-001/timeline?cursor_timestamp=2026-09-27T08:00:00Z&cursor_id=invalid_rank:abc"
            )
            assert res1.status_code == 422

            res2 = client.get(
                "/api/incidents/INC-001/timeline?cursor_timestamp=2026-09-27T08:00:00Z&cursor_id=99:abc"
            )
            assert res2.status_code == 422

            res3 = client.get("/api/incidents/INC-001/timeline?cursor_timestamp=2026-09-27T08:00:00Z")
            assert res3.status_code == 422


# ── 2. Persistence Mode & 404 Tests ─────────────────────────────────────

def test_timeline_disabled_persistence_mode():
    """Test timeline endpoint in disabled mode returns 200 with empty items."""
    with patch.object(settings, "persistence_mode", "disabled"):
        res = client.get("/api/incidents/INC-001/timeline")
        assert res.status_code == 200
        data = res.json()
        assert data["items"] == []
        assert data["has_more"] is False


def test_timeline_required_mode_db_down_returns_503():
    """Test timeline endpoint in required mode returns 503 when DB is offline."""
    with patch.object(settings, "persistence_mode", "required"):
        with patch("app.routers.history.get_db_manager") as mock_db_mgr:
            mock_mgr = MagicMock()
            mock_mgr.is_available = False
            mock_db_mgr.return_value = mock_mgr

            res = client.get("/api/incidents/INC-001/timeline")
            assert res.status_code == 503
            assert "unavailable" in res.json()["detail"].lower()


@pytest.mark.anyio
async def test_timeline_incident_not_found():
    """Test GET /api/incidents/{incident_id}/timeline returns 404 when incident does not exist in DB."""
    with patch.object(settings, "persistence_mode", "optional"):
        with patch("app.routers.history.get_db_manager") as mock_db_mgr:
            mock_mgr = MagicMock()
            mock_mgr.is_available = True
            mock_session = AsyncMock()
            mock_session.get.return_value = None  # Incident not found
            mock_mgr.get_session.return_value.__aenter__.return_value = mock_session
            mock_db_mgr.return_value = mock_mgr

            res = client.get("/api/incidents/INC-NONEXISTENT/timeline")
            assert res.status_code == 404


# ── 3. Unit Tests for TimelineService Normalizers & Merging ─────────────

@pytest.mark.anyio
async def test_timeline_service_all_six_sources():
    """Test TimelineService normalizes and merges all 6 domain event sources."""
    mock_session = AsyncMock()
    service = TimelineService(mock_session)
    inc_id = "INC-2026-ALL"
    base_time = datetime(2026, 9, 27, 8, 0, 0, tzinfo=timezone.utc)

    # 1. Telemetry
    obs = TelemetryObservation(
        id=uuid.uuid4(), incident_id=inc_id, data_mode="simulated", fallback_used=False,
        rainfall_intensity=60.0, rainfall_trend=2.0, water_level=5.0, water_level_trend=0.2,
        road_congestion=0.5, population_exposure=10000.0, infrastructure_vulnerability=0.5,
        observed_at=base_time, created_at=base_time
    )

    # 2. Risk
    pred = RiskPrediction(
        id=uuid.uuid4(), incident_id=inc_id, horizon=0, horizon_label="NOW", current_risk=50.0,
        predicted_risk=65.0, risk_category="HIGH", confidence=0.9, prediction_reliability=0.95,
        affected_population=10000, critical_population=2000, critical_assets_count=5,
        affected_assets_count=2, trend="↑", map_status_text="High risk", prediction_note="Note",
        input_features={}, heatmap_zones=[], created_at=base_time + timedelta(minutes=2)
    )

    # 3. Route
    route = EvacuationRoute(
        id=uuid.uuid4(), incident_id=inc_id, route_name="Route Alpha", route_type="primary",
        is_recommended=True, origin_name="Sector B", origin_lat=28.6, origin_lon=77.2,
        destination_name="Shelter A", destination_lat=28.7, destination_lon=77.3,
        waypoint_coords=[[28.6, 77.2]], distance_km=5.0, estimated_minutes=15.0,
        safety_score=85.0, created_at=base_time + timedelta(minutes=3)
    )

    # 4. Alert
    alert = Alert(
        id=uuid.uuid4(), incident_id=inc_id, severity="CRITICAL", title="Flood Flash",
        description="Surging water", status="OPEN", created_at=base_time + timedelta(minutes=5)
    )

    # 5. Simulation
    sim = Simulation(
        id=uuid.uuid4(), incident_id=inc_id, baseline_risk=50.0, scenario_risk=75.0,
        risk_delta=25.0, risk_category="CRITICAL", route_recommendation="Reroute",
        flagged_assets=["Bridge-1"], narrative="Simulation run", severity="SEVERE",
        created_at=base_time + timedelta(minutes=6)
    )

    # 6. Audit
    audit = AuditEvent(
        id=uuid.uuid4(), incident_id=inc_id, event_type="RESPONSE_WORKFLOW_APPROVED",
        severity="INFO", source="Operator", description="Workflow approved", actor="admin",
        created_at=base_time + timedelta(minutes=7)
    )

    def mock_execute_side_effect(stmt):
        m = MagicMock()
        stmt_str = str(stmt)
        if "telemetry_observations" in stmt_str:
            m.scalars.return_value.all.return_value = [obs]
        elif "risk_predictions" in stmt_str:
            m.scalars.return_value.all.return_value = [pred]
        elif "evacuation_routes" in stmt_str:
            m.scalars.return_value.all.return_value = [route]
        elif "alerts" in stmt_str:
            m.scalars.return_value.all.return_value = [alert]
        elif "simulations" in stmt_str:
            m.scalars.return_value.all.return_value = [sim]
        elif "audit_events" in stmt_str:
            m.scalars.return_value.all.return_value = [audit]
        else:
            m.scalars.return_value.all.return_value = []
        return m

    mock_session.execute.side_effect = mock_execute_side_effect

    page = await service.get_incident_timeline(inc_id)
    assert len(page.items) == 6

    # Verify DESC chronological ordering (most recent +7min audit event first)
    assert page.items[0].event_type == "DECISION_APPROVED"
    assert page.items[1].event_type == "SIMULATION_COMPLETED"
    assert page.items[2].event_type == "ALERT_CREATED"
    assert page.items[3].event_type == "ROUTE_UPDATED"
    assert page.items[4].event_type == "RISK_EVALUATED"
    assert page.items[5].event_type == "TELEMETRY_OBSERVED"

    # SHAP records not present as separate events
    event_types = [item.event_type for item in page.items]
    assert "SHAP_RECORD" not in event_types

    # Details payloads are lightweight
    for item in page.items:
        assert len(str(item.details)) < 1000


@pytest.mark.anyio
async def test_timeline_identical_timestamp_different_ranks():
    """Test deterministic tie-breaking when different event sources share the exact same timestamp."""
    mock_session = AsyncMock()
    service = TimelineService(mock_session)
    inc_id = "INC-2026-TIE"
    exact_time = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)

    obs = TelemetryObservation(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        incident_id=inc_id, data_mode="simulated", fallback_used=False,
        rainfall_intensity=60.0, rainfall_trend=2.0, water_level=5.0, water_level_trend=0.2,
        road_congestion=0.5, population_exposure=10000.0, infrastructure_vulnerability=0.5,
        observed_at=exact_time, created_at=exact_time
    )
    pred = RiskPrediction(
        id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        incident_id=inc_id, horizon=0, horizon_label="NOW", current_risk=50.0,
        predicted_risk=65.0, risk_category="HIGH", confidence=0.9, prediction_reliability=0.95,
        affected_population=10000, critical_population=2000, critical_assets_count=5,
        affected_assets_count=2, trend="↑", map_status_text="High risk", prediction_note="Note",
        input_features={}, heatmap_zones=[], created_at=exact_time
    )

    def mock_execute(stmt):
        m = MagicMock()
        stmt_str = str(stmt)
        if "telemetry_observations" in stmt_str:
            m.scalars.return_value.all.return_value = [obs]
        elif "risk_predictions" in stmt_str:
            m.scalars.return_value.all.return_value = [pred]
        else:
            m.scalars.return_value.all.return_value = []
        return m

    mock_session.execute.side_effect = mock_execute

    page = await service.get_incident_timeline(inc_id)
    assert len(page.items) == 2
    # Telemetry rank=6 > Risk rank=5, so TELEMETRY_OBSERVED appears first
    assert page.items[0].event_type == "TELEMETRY_OBSERVED"
    assert page.items[1].event_type == "RISK_EVALUATED"


@pytest.mark.anyio
async def test_timeline_same_timestamp_same_rank_different_ids():
    """Test deterministic tie-breaking for items with identical timestamp AND identical rank but different IDs."""
    mock_session = AsyncMock()
    service = TimelineService(mock_session)
    inc_id = "INC-2026-SAME-RANK"
    exact_time = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)

    obs1 = TelemetryObservation(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"), incident_id=inc_id,
        rainfall_intensity=10.0, water_level=1.0, observed_at=exact_time, created_at=exact_time
    )
    obs2 = TelemetryObservation(
        id=uuid.UUID("22222222-2222-2222-2222-222222222222"), incident_id=inc_id,
        rainfall_intensity=20.0, water_level=2.0, observed_at=exact_time, created_at=exact_time
    )

    def mock_execute(stmt):
        m = MagicMock()
        if "telemetry_observations" in str(stmt):
            m.scalars.return_value.all.return_value = [obs1, obs2]
        else:
            m.scalars.return_value.all.return_value = []
        return m

    mock_session.execute.side_effect = mock_execute

    page = await service.get_incident_timeline(inc_id)
    assert len(page.items) == 2
    # obs2 ID ("2222...") > obs1 ID ("1111...") so obs2 comes first in DESC order
    assert page.items[0].entity_id == "22222222-2222-2222-2222-222222222222"
    assert page.items[1].entity_id == "11111111-1111-1111-1111-111111111111"


@pytest.mark.anyio
async def test_timeline_pagination_page1_page2_continuation():
    """Test complete Page 1 -> Page 2 pagination flow with no skipped or duplicated items."""
    mock_session = AsyncMock()
    service = TimelineService(mock_session)
    inc_id = "INC-2026-PAGINATION"
    base_time = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)

    item1 = TelemetryObservation(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"), incident_id=inc_id,
        rainfall_intensity=30.0, water_level=3.0, observed_at=base_time + timedelta(hours=3),
        created_at=base_time + timedelta(hours=3)
    )
    item2 = RiskPrediction(
        id=uuid.UUID("22222222-2222-2222-2222-222222222222"), incident_id=inc_id, horizon=0,
        horizon_label="NOW", current_risk=50.0, predicted_risk=60.0, risk_category="HIGH",
        confidence=0.9, prediction_reliability=0.9, affected_population=1000,
        critical_population=100, critical_assets_count=1, affected_assets_count=1,
        trend="↑", map_status_text="Text", prediction_note="Note", input_features={},
        heatmap_zones=[], created_at=base_time + timedelta(hours=2)
    )
    item3 = Alert(
        id=uuid.UUID("33333333-3333-3333-3333-333333333333"), incident_id=inc_id, severity="HIGH",
        title="Alert Title", description="Desc", status="OPEN", created_at=base_time + timedelta(hours=1)
    )

    def mock_execute(stmt):
        m = MagicMock()
        stmt_str = str(stmt)
        res = []
        if "telemetry_observations" in stmt_str:
            res = [item1]
        elif "risk_predictions" in stmt_str:
            res = [item2]
        elif "alerts" in stmt_str:
            res = [item3]
        m.scalars.return_value.all.return_value = res
        return m

    mock_session.execute.side_effect = mock_execute

    # Page 1 (limit 2)
    p1_params = PaginationParams(limit=2)
    page1 = await service.get_incident_timeline(inc_id, params=p1_params)

    assert len(page1.items) == 2
    assert page1.has_more is True
    assert page1.items[0].entity_id == "11111111-1111-1111-1111-111111111111"
    assert page1.items[1].entity_id == "22222222-2222-2222-2222-222222222222"
    assert page1.next_cursor is not None
    assert "timestamp" in page1.next_cursor
    assert page1.next_cursor["id"] == "5:22222222-2222-2222-2222-222222222222"

    # Page 2 using next_cursor from Page 1
    p2_ts = datetime.fromisoformat(page1.next_cursor["timestamp"])
    p2_params = PaginationParams(limit=2, cursor_timestamp=p2_ts, cursor_id=page1.next_cursor["id"])
    page2 = await service.get_incident_timeline(inc_id, params=p2_params)

    assert len(page2.items) == 1
    assert page2.has_more is False
    assert page2.items[0].entity_id == "33333333-3333-3333-3333-333333333333"
    assert page2.next_cursor is None

    # Check zero duplicates between page 1 and page 2
    p1_ids = {item.entity_id for item in page1.items}
    p2_ids = {item.entity_id for item in page2.items}
    assert len(p1_ids.intersection(p2_ids)) == 0


@pytest.mark.anyio
async def test_timeline_cursor_boundary_ends_at_rank():
    """Test cursor boundary when Page 1 ends at a specific event rank (e.g. Risk rank=5) at shared timestamp."""
    mock_session = AsyncMock()
    service = TimelineService(mock_session)
    inc_id = "INC-2026-BOUNDARY"
    exact_time = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)

    t = TelemetryObservation(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"), incident_id=inc_id,
        rainfall_intensity=10.0, water_level=1.0, observed_at=exact_time, created_at=exact_time
    )
    r = RiskPrediction(
        id=uuid.UUID("22222222-2222-2222-2222-222222222222"), incident_id=inc_id, horizon=0,
        horizon_label="NOW", current_risk=50.0, predicted_risk=60.0, risk_category="HIGH",
        confidence=0.9, prediction_reliability=0.9, affected_population=1000,
        critical_population=100, critical_assets_count=1, affected_assets_count=1,
        trend="↑", map_status_text="Text", prediction_note="Note", input_features={},
        heatmap_zones=[], created_at=exact_time
    )
    rt = EvacuationRoute(
        id=uuid.UUID("33333333-3333-3333-3333-333333333333"), incident_id=inc_id, route_name="Route A",
        route_type="primary", is_recommended=True, origin_name="Org", origin_lat=0.0, origin_lon=0.0,
        destination_name="Dst", destination_lat=0.0, destination_lon=0.0, waypoint_coords=[],
        distance_km=1.0, estimated_minutes=5.0, safety_score=90.0, created_at=exact_time
    )
    a = Alert(
        id=uuid.UUID("44444444-4444-4444-4444-444444444444"), incident_id=inc_id, severity="LOW",
        title="Alert", description="Desc", status="OPEN", created_at=exact_time
    )

    def mock_execute(stmt):
        m = MagicMock()
        s = str(stmt)
        if "telemetry_observations" in s:
            m.scalars.return_value.all.return_value = [t]
        elif "risk_predictions" in s:
            m.scalars.return_value.all.return_value = [r]
        elif "evacuation_routes" in s:
            m.scalars.return_value.all.return_value = [rt]
        elif "alerts" in s:
            m.scalars.return_value.all.return_value = [a]
        else:
            m.scalars.return_value.all.return_value = []
        return m

    mock_session.execute.side_effect = mock_execute

    # Page 1 limit=2
    page1 = await service.get_incident_timeline(inc_id, params=PaginationParams(limit=2))
    assert len(page1.items) == 2
    assert page1.items[0].event_type == "TELEMETRY_OBSERVED"
    assert page1.items[1].event_type == "RISK_EVALUATED"
    assert page1.next_cursor["id"] == "5:22222222-2222-2222-2222-222222222222"

    # Page 2 from cursor of Page 1
    p2_ts = datetime.fromisoformat(page1.next_cursor["timestamp"])
    page2 = await service.get_incident_timeline(
        inc_id, params=PaginationParams(limit=2, cursor_timestamp=p2_ts, cursor_id=page1.next_cursor["id"])
    )
    assert len(page2.items) == 2
    assert page2.items[0].event_type == "ROUTE_UPDATED"
    assert page2.items[1].event_type == "ALERT_CREATED"
    assert page2.has_more is False


# ── 4. End-to-End API Router & Backward Compatibility Tests ────────────

@pytest.mark.anyio
async def test_timeline_endpoint_success():
    """Test GET /api/incidents/{incident_id}/timeline via FastAPI test client."""
    inc = Incident(
        id="INC-2026-TIMELINE", incident_type="flood", status="ACTIVE",
        started_at=datetime.now(timezone.utc), sector="B", severity="HIGH",
        location_name="Yamuna", latitude=28.6, longitude=77.2
    )

    with patch.object(settings, "persistence_mode", "optional"):
        with patch("app.routers.history.get_db_manager") as mock_db_mgr:
            mock_mgr = MagicMock()
            mock_mgr.is_available = True
            mock_session = AsyncMock()
            mock_session.get.return_value = inc  # Incident exists

            mock_res = MagicMock()
            mock_res.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_res
            mock_mgr.get_session.return_value.__aenter__.return_value = mock_session
            mock_db_mgr.return_value = mock_mgr

            res = client.get("/api/incidents/INC-2026-TIMELINE/timeline")
            assert res.status_code == 200
            data = res.json()
            assert data["items"] == []
            assert data["has_more"] is False


def test_phase_6_6b_endpoints_still_working():
    """Verify Phase 6.6B endpoints (/api/incidents, /api/incidents/{id}/telemetry/history, etc.) remain intact."""
    res_inc = client.get("/api/incidents")
    assert res_inc.status_code == 200

    async def finite_sse_generator(request):
        yield ": connected\n\n"

    with patch(
        "app.routers.events.sse_event_generator",
        new=finite_sse_generator,
    ):
        with client.stream("GET", "/api/events/stream") as res_sse:
            assert res_sse.status_code == 200
            assert res_sse.headers["content-type"].startswith("text/event-stream")
            body = res_sse.read().decode()
            assert ": connected" in body