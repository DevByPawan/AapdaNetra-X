"""AapdaNetra-X — Phase 6.10 Historical Analytics Unit Tests

Verifies analytics DTOs, router endpoints, query aggregation logic, persistence mode degradation,
time-range validation, and architectural contract preservation.
"""

from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analytics import (
    AlertAnalyticsResponse,
    AnalyticsOverviewResponse,
    IncidentAnalyticsResponse,
    RiskAnalyticsResponse,
    RouteAnalyticsResponse,
    SimulationAnalyticsResponse,
    TelemetryAnalyticsResponse,
)

client = TestClient(app)


# ── 1. Persistence Disabled Tests ───────────────────────────────────────────

def test_analytics_overview_persistence_disabled():
    with patch("app.config.settings.persistence_mode", "disabled"):
        res = client.get("/api/analytics/overview")
        assert res.status_code == 200
        data = res.json()
        assert data["total_incidents"] == 0
        assert data["total_risk_predictions"] == 0
        assert data["avg_system_risk"] is None


def test_incident_analytics_persistence_disabled():
    with patch("app.config.settings.persistence_mode", "disabled"):
        res = client.get("/api/analytics/incidents/INC-2026-TEST")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"]


def test_risk_analytics_persistence_disabled():
    with patch("app.config.settings.persistence_mode", "disabled"):
        res = client.get("/api/analytics/risk")
        assert res.status_code == 200
        data = res.json()
        assert data["total_predictions"] == 0
        assert data["risk_trend"] == "INSUFFICIENT_DATA"


def test_alert_analytics_persistence_disabled():
    with patch("app.config.settings.persistence_mode", "disabled"):
        res = client.get("/api/analytics/alerts")
        assert res.status_code == 200
        data = res.json()
        assert data["total_alerts"] == 0


def test_route_analytics_persistence_disabled():
    with patch("app.config.settings.persistence_mode", "disabled"):
        res = client.get("/api/analytics/routes")
        assert res.status_code == 200
        data = res.json()
        assert data["total_routes"] == 0


def test_simulation_analytics_persistence_disabled():
    with patch("app.config.settings.persistence_mode", "disabled"):
        res = client.get("/api/analytics/simulations")
        assert res.status_code == 200
        data = res.json()
        assert data["total_simulations"] == 0


def test_telemetry_analytics_persistence_disabled():
    with patch("app.config.settings.persistence_mode", "disabled"):
        res = client.get("/api/analytics/telemetry")
        assert res.status_code == 200
        data = res.json()
        assert data["total_observations"] == 0
        assert "synthetic/simulated" in data["data_provenance_note"]


# ── 2. Persistence Required DB Unavailable Tests ────────────────────────────

def test_analytics_required_db_unavailable():
    mock_db = MagicMock()
    mock_db.is_available = False
    with patch("app.config.settings.persistence_mode", "required"), \
         patch("app.db.session.get_db_manager", return_value=mock_db):
        res = client.get("/api/analytics/overview")
        assert res.status_code == 503
        assert "Database service unavailable" in res.json()["detail"]


# ── 3. Time-Range Validation Tests ──────────────────────────────────────────

def test_analytics_inverted_time_range():
    res = client.get(
        "/api/analytics/risk",
        params={
            "from_time": "2026-09-27T12:00:00Z",
            "to_time": "2026-09-27T10:00:00Z",
        },
    )
    assert res.status_code == 422
    assert "from_time must be less than or equal to to_time" in res.json()["detail"]


def test_analytics_valid_time_range_formatting():
    with patch("app.config.settings.persistence_mode", "disabled"):
        res = client.get(
            "/api/analytics/risk",
            params={
                "from_time": "2026-09-27T10:00:00Z",
                "to_time": "2026-09-27T12:00:00Z",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["from_time"] == "2026-09-27T10:00:00+00:00"
        assert data["to_time"] == "2026-09-27T12:00:00+00:00"


# ── 4. Schema Contract & Property Verification ─────────────────────────────

def test_risk_analytics_schema():
    resp = RiskAnalyticsResponse(
        total_predictions=10,
        min_risk=0.12,
        max_risk=0.88,
        avg_risk=0.52,
        latest_risk=0.85,
        earliest_risk=0.15,
        risk_trend="INCREASING",
        risk_category_distribution={"HIGH": 6, "LOW": 4},
        incident_id="INC-001",
    )
    assert resp.total_predictions == 10
    assert resp.risk_trend == "INCREASING"
    assert resp.risk_category_distribution["HIGH"] == 6


def test_telemetry_provenance_note_preserved():
    resp = TelemetryAnalyticsResponse(
        total_observations=100,
        rainfall_min=0.0,
        rainfall_max=120.5,
        rainfall_avg=45.2,
        data_mode_distribution={"simulated": 80, "hybrid": 20},
    )
    assert resp.total_observations == 100
    assert "synthetic" in resp.data_provenance_note


def test_incident_analytics_schema():
    resp = IncidentAnalyticsResponse(
        incident_id="INC-999",
        incident_type="FLOOD",
        status="ACTIVE",
        severity="HIGH",
        started_at="2026-09-27T00:00:00Z",
        created_at="2026-09-27T00:00:00Z",
        telemetry_count=15,
        risk_prediction_count=8,
        route_count=3,
        alert_count=2,
        simulation_count=1,
        audit_event_count=5,
        latest_risk=0.78,
        max_observed_risk=0.92,
        avg_observed_risk=0.65,
    )
    assert resp.incident_id == "INC-999"
    assert resp.telemetry_count == 15
    assert resp.max_observed_risk == 0.92
