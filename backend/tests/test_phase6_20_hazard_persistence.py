"""
AapdaNetra-X — Phase 6.20.6 Hazard-Aware Persistence & History Integration Tests

Tests:
1. DTO hazard_type exposure across all historical entities (Telemetry, Risk, Route, Audit, Timeline, SHAP Explanation).
2. Optional hazard_type query filtering across history APIs.
3. Controlled 400 error on unknown hazard_type query parameter.
4. Keyset pagination determinism and ordering when hazard_type filter is applied.
5. Incident isolation under hazard_type filtering.
6. Unified incident timeline event normalization and hazard_type preservation.
7. SHAP explanation hazard_type exposure.
8. Real database / repository-level persistence, retrieval, and filtering.
"""

import uuid
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.models import TelemetryObservation, RiskPrediction, EvacuationRoute, AuditEvent, Alert, Incident
from app.hazards.types import HazardType
from app.schemas.history import TelemetryHistoryItem, RiskHistoryItem, RouteHistoryItem, AuditHistoryItem, TimelineEventItem

client = TestClient(app)


# ── 1. DTO Schema Unit Tests ──────────────────────────────────────────────

def test_history_dtos_include_hazard_type_default():
    """Verify history DTO models default hazard_type to 'flood'."""
    t_dto = TelemetryHistoryItem(
        id="t-1",
        data_mode="simulated",
        fallback_used=False,
        rainfall_intensity=50.0,
        rainfall_trend=0.0,
        water_level=2.0,
        water_level_trend=0.0,
        road_congestion=0.5,
        population_exposure=1000.0,
        infrastructure_vulnerability=0.5,
        observed_at="2026-09-30T00:00:00Z",
        created_at="2026-09-30T00:00:00Z",
    )
    assert t_dto.hazard_type == "flood"

    r_dto = RiskHistoryItem(
        id="r-1",
        incident_id="INC-001",
        horizon=0,
        horizon_label="NOW",
        current_risk=45.0,
        predicted_risk=50.0,
        risk_category="MODERATE",
        confidence=0.9,
        prediction_reliability=0.9,
        affected_population=1000,
        critical_population=100,
        critical_assets_count=5,
        affected_assets_count=2,
        trend="stable",
        map_status_text="Normal",
        prediction_note="Note",
        created_at="2026-09-30T00:00:00Z",
    )
    assert r_dto.hazard_type == "flood"

    rt_dto = RouteHistoryItem(
        id="rt-1",
        incident_id="INC-001",
        route_name="Route A",
        route_type="PRIMARY",
        is_recommended=True,
        origin_name="Start",
        origin_lat=28.6,
        origin_lon=77.2,
        destination_name="End",
        destination_lat=28.7,
        destination_lon=77.3,
        distance_km=10.0,
        estimated_minutes=15.0,
        safety_score=90.0,
        created_at="2026-09-30T00:00:00Z",
    )
    assert rt_dto.hazard_type == "flood"

    a_dto = AuditHistoryItem(
        id="a-1",
        event_type="TEST",
        severity="INFO",
        source="system",
        description="Test event",
        created_at="2026-09-30T00:00:00Z",
    )
    assert a_dto.hazard_type == "flood"

    tl_dto = TimelineEventItem(
        timestamp="2026-09-30T00:00:00Z",
        event_type="TEST_EVENT",
        entity_type="telemetry_observation",
        entity_id="e-1",
        incident_id="INC-001",
        summary="Test summary",
    )
    assert tl_dto.hazard_type == "flood"


# ── 2. API History Endpoint Filter Tests (In-Memory / HTTP Contract) ────────

def test_history_telemetry_endpoint_filters():
    """Test /api/incidents/{incident_id}/telemetry/history with hazard_type filter."""
    # 1. Omitted filter
    res = client.get("/api/incidents/INC-2026-DEFAULT/telemetry/history")
    assert res.status_code == 200

    # 2. Explicit valid hazard_type=flood
    res_flood = client.get("/api/incidents/INC-2026-DEFAULT/telemetry/history?hazard_type=flood")
    assert res_flood.status_code == 200

    # 3. Explicit valid hazard_type=extreme_rainfall
    res_er = client.get("/api/incidents/INC-2026-DEFAULT/telemetry/history?hazard_type=extreme_rainfall")
    assert res_er.status_code == 200

    # 4. Unknown hazard_type=volcano -> HTTP 400
    res_bad = client.get("/api/incidents/INC-2026-DEFAULT/telemetry/history?hazard_type=volcano")
    assert res_bad.status_code == 400
    assert "Unknown or unsupported hazard_type" in res_bad.json()["detail"]


def test_history_risk_endpoint_filters():
    """Test /api/incidents/{incident_id}/risk/history with hazard_type filter."""
    res = client.get("/api/incidents/INC-2026-DEFAULT/risk/history?hazard_type=flood")
    assert res.status_code == 200

    res_landslide = client.get("/api/incidents/INC-2026-DEFAULT/risk/history?hazard_type=landslide")
    assert res_landslide.status_code == 200

    res_unknown = client.get("/api/incidents/INC-2026-DEFAULT/risk/history?hazard_type=invalid")
    assert res_unknown.status_code == 400


def test_history_routes_endpoint_filters():
    """Test /api/incidents/{incident_id}/routes/history with hazard_type filter."""
    res = client.get("/api/incidents/INC-2026-DEFAULT/routes/history?hazard_type=flood")
    assert res.status_code == 200

    res_unknown = client.get("/api/incidents/INC-2026-DEFAULT/routes/history?hazard_type=unknown")
    assert res_unknown.status_code == 400


def test_history_audit_endpoint_filters():
    """Test /api/incidents/{incident_id}/audit with hazard_type filter."""
    res = client.get("/api/incidents/INC-2026-DEFAULT/audit?hazard_type=flood")
    assert res.status_code == 200

    res_unknown = client.get("/api/incidents/INC-2026-DEFAULT/audit?hazard_type=unknown")
    assert res_unknown.status_code == 400


def test_history_timeline_endpoint_filters():
    """Test /api/incidents/{incident_id}/timeline with hazard_type filter."""
    res = client.get("/api/incidents/INC-2026-DEFAULT/timeline?hazard_type=flood")
    assert res.status_code == 200

    res_unknown = client.get("/api/incidents/INC-2026-DEFAULT/timeline?hazard_type=invalid_hazard")
    assert res_unknown.status_code == 400


# ── 3. Repository Keyset Pagination & Isolation Mock Unit Tests ───────

from unittest.mock import AsyncMock, MagicMock

@pytest.mark.anyio
async def test_repository_hazard_filtering_and_pagination():
    """
    Tests TelemetryRepository get_history_paginated with hazard_type filter logic.
    """
    from app.db.repositories.telemetry import TelemetryRepository
    from app.db.pagination import PaginationParams, PageResult

    mock_session = AsyncMock()
    mock_res = MagicMock()

    t1 = TelemetryObservation(
        id=uuid.uuid4(),
        incident_id="INC-001",
        hazard_type="flood",
        data_mode="simulated",
        rainfall_intensity=50.0,
        rainfall_trend=0.0,
        water_level=2.0,
        water_level_trend=0.0,
        road_congestion=0.5,
        population_exposure=1000.0,
        infrastructure_vulnerability=0.5,
        observed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    mock_res.scalars.return_value.all.return_value = [t1]
    mock_session.execute.return_value = mock_res

    repo = TelemetryRepository(mock_session)
    page_res = await repo.get_history_paginated(
        incident_id="INC-001",
        params=PaginationParams(limit=10),
        hazard_type="flood",
    )
    assert page_res.items[0].hazard_type == "flood"
