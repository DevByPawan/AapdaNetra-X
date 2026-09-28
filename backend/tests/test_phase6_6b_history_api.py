"""AapdaNetra-X — Phase 6.6B Historical REST APIs Test Suite

Tests all historical REST endpoints, query validation, pagination, persistence mode
handling, error isolation, and backward compatibility of existing live APIs.
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
    AuditEvent,
    SHAPRecord,
)

client = TestClient(app)


# ── 1. Query Validation Tests ───────────────────────────────────────────

def test_query_validation_invalid_limit():
    """Test limit < 1 or > 100 returns HTTP 422."""
    res_zero = client.get("/api/incidents?limit=0")
    assert res_zero.status_code == 422

    res_over = client.get("/api/incidents?limit=101")
    assert res_over.status_code == 422


def test_query_validation_naive_timestamps():
    """Test naive timestamp parameters return HTTP 422."""
    res = client.get("/api/incidents?cursor_timestamp=2026-09-27T08:00:00")
    assert res.status_code == 422

    res_from = client.get("/api/incidents?from_time=2026-09-27T08:00:00")
    assert res_from.status_code == 422


def test_query_validation_from_time_greater_than_to_time():
    """Test from_time > to_time returns HTTP 422."""
    from_t = "2026-09-27T10:00:00Z"
    to_t = "2026-09-27T08:00:00Z"
    res = client.get(f"/api/incidents?from_time={from_t}&to_time={to_t}")
    assert res.status_code == 422


# ── 2. Persistence Mode & Empty Result Tests ────────────────────────────

def test_incidents_disabled_persistence_returns_empty():
    """Test GET /api/incidents in disabled mode returns 200 with empty items."""
    with patch.object(settings, "persistence_mode", "disabled"):
        res = client.get("/api/incidents")
        assert res.status_code == 200
        data = res.json()
        assert data["items"] == []
        assert data["has_more"] is False
        assert data["next_cursor"] is None


def test_incident_detail_not_found():
    """Test GET /api/incidents/{incident_id} returns 404 when incident does not exist."""
    with patch.object(settings, "persistence_mode", "disabled"):
        res = client.get("/api/incidents/INC-NONEXISTENT")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()


def test_shap_not_found():
    """Test GET /api/risk/{prediction_id}/explanation returns 404 for missing SHAP record."""
    random_id = str(uuid.uuid4())
    with patch.object(settings, "persistence_mode", "disabled"):
        res = client.get(f"/api/risk/{random_id}/explanation")
        assert res.status_code == 404


def test_shap_invalid_uuid_returns_404():
    """Test GET /api/risk/invalid-uuid/explanation returns 404 cleanly."""
    res = client.get("/api/risk/not-a-uuid/explanation")
    assert res.status_code == 404


# ── 3. DB Mocked Endpoint Success & Pagination Tests ─────────────────────

@pytest.mark.anyio
async def test_incidents_endpoint_success_and_filtering():
    """Test GET /api/incidents returning populated items."""
    base_time = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
    inc = Incident(
        id="INC-2026-001",
        incident_type="flood",
        status="ACTIVE",
        started_at=base_time,
        sector="Sector B",
        severity="HIGH",
        location_name="Yamuna",
        latitude=28.6,
        longitude=77.2,
        created_at=base_time,
        updated_at=base_time,
    )

    with patch.object(settings, "persistence_mode", "optional"):
        with patch("app.routers.history.get_db_manager") as mock_db_mgr:
            mock_mgr = MagicMock()
            mock_mgr.is_available = True

            mock_session = AsyncMock()
            mock_res = MagicMock()
            mock_res.scalars.return_value.all.return_value = [inc]
            mock_session.execute.return_value = mock_res
            mock_mgr.get_session.return_value.__aenter__.return_value = mock_session

            mock_db_mgr.return_value = mock_mgr

            res = client.get("/api/incidents?status=ACTIVE")
            assert res.status_code == 200
            data = res.json()
            assert len(data["items"]) == 1
            assert data["items"][0]["id"] == "INC-2026-001"


@pytest.mark.anyio
async def test_incident_detail_endpoint_success():
    """Test GET /api/incidents/{incident_id} returning incident metadata."""
    base_time = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
    inc = Incident(
        id="INC-2026-001",
        incident_type="flood",
        status="ACTIVE",
        started_at=base_time,
        sector="Sector B",
        severity="HIGH",
        location_name="Yamuna",
        latitude=28.6,
        longitude=77.2,
        created_at=base_time,
        updated_at=base_time,
    )

    with patch.object(settings, "persistence_mode", "optional"):
        with patch("app.routers.history.get_db_manager") as mock_db_mgr:
            mock_mgr = MagicMock()
            mock_mgr.is_available = True

            mock_session = AsyncMock()
            mock_session.get.return_value = inc
            mock_mgr.get_session.return_value.__aenter__.return_value = mock_session

            mock_db_mgr.return_value = mock_mgr

            res = client.get("/api/incidents/INC-2026-001")
            assert res.status_code == 200
            data = res.json()
            assert data["id"] == "INC-2026-001"
            assert data["sector"] == "Sector B"


@pytest.mark.anyio
async def test_telemetry_history_endpoint():
    """Test GET /api/incidents/{incident_id}/telemetry/history."""
    base_time = datetime(2026, 9, 27, 8, 0, 0, tzinfo=timezone.utc)
    obs = TelemetryObservation(
        id=uuid.uuid4(),
        incident_id="INC-2026-001",
        data_mode="simulated",
        fallback_used=False,
        rainfall_intensity=50.0,
        rainfall_trend=2.0,
        water_level=4.5,
        water_level_trend=0.3,
        road_congestion=0.6,
        population_exposure=10000.0,
        infrastructure_vulnerability=0.5,
        provenance={"source": "test"},
        observed_at=base_time,
        created_at=base_time,
    )

    with patch.object(settings, "persistence_mode", "optional"):
        with patch("app.routers.history.get_db_manager") as mock_db_mgr:
            mock_mgr = MagicMock()
            mock_mgr.is_available = True
            mock_session = AsyncMock()
            mock_res = MagicMock()
            mock_res.scalars.return_value.all.return_value = [obs]
            mock_session.execute.return_value = mock_res
            mock_mgr.get_session.return_value.__aenter__.return_value = mock_session
            mock_db_mgr.return_value = mock_mgr

            res = client.get("/api/incidents/INC-2026-001/telemetry/history")
            assert res.status_code == 200
            data = res.json()
            assert len(data["items"]) == 1
            assert data["items"][0]["rainfall_intensity"] == 50.0


@pytest.mark.anyio
async def test_risk_history_and_horizon_filtering():
    """Test GET /api/incidents/{incident_id}/risk/history with horizon filter."""
    base_time = datetime(2026, 9, 27, 8, 0, 0, tzinfo=timezone.utc)
    pred = RiskPrediction(
        id=uuid.uuid4(),
        incident_id="INC-2026-001",
        horizon=0,
        horizon_label="NOW",
        current_risk=45.0,
        predicted_risk=52.0,
        risk_category="MODERATE",
        confidence=0.9,
        prediction_reliability=0.95,
        affected_population=10000,
        critical_population=2000,
        critical_assets_count=5,
        affected_assets_count=2,
        trend="RISING",
        map_status_text="Rising risk",
        prediction_note="Test note",
        input_features={"rainfall_intensity": 50.0},
        heatmap_zones=[],
        created_at=base_time,
    )

    with patch.object(settings, "persistence_mode", "optional"):
        with patch("app.routers.history.get_db_manager") as mock_db_mgr:
            mock_mgr = MagicMock()
            mock_mgr.is_available = True
            mock_session = AsyncMock()
            mock_res = MagicMock()
            mock_res.scalars.return_value.all.return_value = [pred]
            mock_session.execute.return_value = mock_res
            mock_mgr.get_session.return_value.__aenter__.return_value = mock_session
            mock_db_mgr.return_value = mock_mgr

            res = client.get("/api/incidents/INC-2026-001/risk/history?horizon=0")
            assert res.status_code == 200
            data = res.json()
            assert len(data["items"]) == 1
            assert data["items"][0]["horizon"] == 0


@pytest.mark.anyio
async def test_route_and_audit_history_endpoints():
    """Test GET /api/incidents/{incident_id}/routes/history and /audit."""
    base_time = datetime(2026, 9, 27, 8, 0, 0, tzinfo=timezone.utc)
    route = EvacuationRoute(
        id=uuid.uuid4(),
        incident_id="INC-2026-001",
        route_name="Route Alpha",
        route_type="primary",
        is_recommended=True,
        origin_name="Orig",
        origin_lat=28.6,
        origin_lon=77.2,
        destination_name="Dest",
        destination_lat=28.7,
        destination_lon=77.3,
        waypoint_coords=[[28.6, 77.2]],
        distance_km=5.0,
        estimated_minutes=15.0,
        safety_score=0.85,
        created_at=base_time,
    )
    audit = AuditEvent(
        id=uuid.uuid4(),
        incident_id="INC-2026-001",
        event_type="ALERT_DISPATCHED",
        severity="HIGH",
        source="Engine",
        description="Alert sent",
        created_at=base_time,
    )

    with patch.object(settings, "persistence_mode", "optional"):
        with patch("app.routers.history.get_db_manager") as mock_db_mgr:
            mock_mgr = MagicMock()
            mock_mgr.is_available = True
            mock_session = AsyncMock()

            # Test route endpoint
            mock_res_r = MagicMock()
            mock_res_r.scalars.return_value.all.return_value = [route]
            mock_session.execute.return_value = mock_res_r
            mock_mgr.get_session.return_value.__aenter__.return_value = mock_session
            mock_db_mgr.return_value = mock_mgr

            res_r = client.get("/api/incidents/INC-2026-001/routes/history")
            assert res_r.status_code == 200
            assert len(res_r.json()["items"]) == 1

            # Test audit endpoint
            mock_res_a = MagicMock()
            mock_res_a.scalars.return_value.all.return_value = [audit]
            mock_session.execute.return_value = mock_res_a

            res_a = client.get("/api/incidents/INC-2026-001/audit")
            assert res_a.status_code == 200
            assert len(res_a.json()["items"]) == 1


@pytest.mark.anyio
async def test_shap_historical_lookup_endpoint():
    """Test GET /api/risk/{prediction_id}/explanation."""
    base_time = datetime(2026, 9, 27, 8, 0, 0, tzinfo=timezone.utc)
    pred_id = uuid.uuid4()
    shap_rec = SHAPRecord(
        id=uuid.uuid4(),
        risk_prediction_id=pred_id,
        horizon=0,
        prediction=52.0,
        base_value=25.0,
        total_shap_delta=27.0,
        features={"rainfall_intensity": 15.0},
        decision_trace=[],
        created_at=base_time,
    )

    with patch.object(settings, "persistence_mode", "optional"):
        with patch("app.routers.history.get_db_manager") as mock_db_mgr:
            mock_mgr = MagicMock()
            mock_mgr.is_available = True
            mock_session = AsyncMock()
            mock_res = MagicMock()
            mock_res.scalars.return_value.first.return_value = shap_rec
            mock_session.execute.return_value = mock_res
            mock_mgr.get_session.return_value.__aenter__.return_value = mock_session
            mock_db_mgr.return_value = mock_mgr

            res = client.get(f"/api/risk/{pred_id}/explanation")
            assert res.status_code == 200
            data = res.json()
            assert data["risk_prediction_id"] == str(pred_id)
            assert data["base_value"] == 25.0


# ── 4. Error Isolation & Persistence Mode Required Tests ────────────────

def test_required_persistence_mode_returns_503_on_db_down():
    """Test GET /api/incidents in required mode when DB is unavailable returns 503."""
    with patch.object(settings, "persistence_mode", "required"):
        with patch("app.routers.history.get_db_manager") as mock_db_mgr:
            mock_mgr = MagicMock()
            mock_mgr.is_available = False
            mock_db_mgr.return_value = mock_mgr

            res = client.get("/api/incidents")
            assert res.status_code == 503
            assert "unavailable" in res.json()["detail"].lower()


# ── 5. Backward Compatibility Tests ─────────────────────────────────────

def test_existing_apis_unaffected():
    """Verify existing endpoints (/api/risk, /api/routes, /api/explainability) remain functional."""
    res_risk = client.get("/api/risk")
    assert res_risk.status_code == 200

    res_routes = client.get("/api/routes")
    assert res_routes.status_code == 200

    res_exp = client.get("/api/explainability")
    assert res_exp.status_code == 200
