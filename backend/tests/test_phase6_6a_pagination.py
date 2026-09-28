"""AapdaNetra-X — Phase 6.6A Keyset Pagination & Repository History Tests

Tests keyset pagination parameters, timezone-awareness validation, and repository history methods across:
- IncidentRepository
- TelemetryRepository
- RiskPredictionRepository
- EvacuationRouteRepository
- AuditEventRepository
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

pytest_plugins = ("anyio",)

from app.db.pagination import PaginationParams, PageResult, apply_keyset_pagination, build_page_result
from app.db.models import (
    Incident,
    TelemetryObservation,
    RiskPrediction,
    EvacuationRoute,
    AuditEvent,
)
from app.db.repositories import (
    IncidentRepository,
    TelemetryRepository,
    RiskPredictionRepository,
    EvacuationRouteRepository,
    AuditEventRepository,
)


# ── 1. Pagination Utility & Validation Tests ────────────────────────────

def test_pagination_params_defaults_and_limits():
    """Test default limit 50, max limit 100, and bounds enforcement."""
    p = PaginationParams()
    assert p.limit == 50

    p_custom = PaginationParams(limit=10)
    assert p_custom.limit == 10

    p_max = PaginationParams(limit=100)
    assert p_max.limit == 100

    with pytest.raises((ValueError, ValidationError)):
        PaginationParams(limit=0)

    with pytest.raises((ValueError, ValidationError)):
        PaginationParams(limit=101)


def test_naive_timestamps_rejected():
    """Test naive timestamps without timezone info are strictly rejected."""
    naive_ts = datetime(2026, 9, 27, 8, 0, 0)
    tz_ts = datetime(2026, 9, 27, 8, 0, 0, tzinfo=timezone.utc)

    # Naive from_time rejected
    with pytest.raises(ValueError, match="from_time must be timezone-aware"):
        PaginationParams(from_time=naive_ts)

    # Naive to_time rejected
    with pytest.raises(ValueError, match="to_time must be timezone-aware"):
        PaginationParams(to_time=naive_ts)

    # Naive cursor_timestamp rejected
    with pytest.raises(ValueError, match="cursor_timestamp must be timezone-aware"):
        PaginationParams(cursor_timestamp=naive_ts)


def test_timezone_normalization():
    """Test timezone-aware timestamps (+05:30 IST) are normalized to UTC correctly."""
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    ist_time = datetime(2026, 9, 27, 14, 0, 0, tzinfo=ist_tz)  # 14:00 IST = 08:30 UTC

    p = PaginationParams(from_time=ist_time)
    assert p.from_time is not None
    assert p.from_time.tzinfo == timezone.utc
    assert p.from_time.hour == 8
    assert p.from_time.minute == 30


def test_time_range_validation():
    """Test from_time <= to_time validation."""
    now = datetime.now(timezone.utc)
    earlier = now - timedelta(hours=2)

    p = PaginationParams(from_time=earlier, to_time=now)
    assert p.from_time == earlier
    assert p.to_time == now

    # from_time > to_time rejected
    with pytest.raises(ValueError, match="from_time cannot be greater than to_time"):
        PaginationParams(from_time=now, to_time=earlier)


def test_build_page_result_cursor_generation():
    """Test PageResult envelope construction, next_cursor, and has_more flag."""
    now = datetime.now(timezone.utc)
    items = [
        MagicMock(started_at=now, id="INC-001"),
        MagicMock(started_at=now - timedelta(minutes=10), id="INC-002"),
        MagicMock(started_at=now - timedelta(minutes=20), id="INC-003"),
    ]

    # Limit 2 with 3 items fetched (has_more = True)
    res = build_page_result(
        items=items,
        limit=2,
        get_timestamp=lambda x: x.started_at,
        get_id=lambda x: x.id,
    )
    assert len(res.items) == 2
    assert res.has_more is True
    assert res.next_cursor is not None
    assert res.next_cursor["id"] == "INC-002"

    # Limit 5 with 3 items fetched (has_more = False)
    res_full = build_page_result(
        items=items,
        limit=5,
        get_timestamp=lambda x: x.started_at,
        get_id=lambda x: x.id,
    )
    assert len(res_full.items) == 3
    assert res_full.has_more is False
    assert res_full.next_cursor is None


# ── 2. Identical Timestamp & Cursor Boundary Tests ──────────────────────

@pytest.mark.anyio
async def test_identical_timestamp_cursor_boundary():
    """Test cursor pagination when two records share identical timestamps."""
    mock_session = AsyncMock()
    repo = IncidentRepository(mock_session)

    exact_same_time = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)

    # Identical timestamp, different IDs
    inc_a = Incident(id="INC-001", incident_type="flood", status="ACTIVE", started_at=exact_same_time, sector="B", severity="HIGH", location_name="Loc", latitude=28.6, longitude=77.2)
    inc_b = Incident(id="INC-002", incident_type="flood", status="ACTIVE", started_at=exact_same_time, sector="B", severity="HIGH", location_name="Loc", latitude=28.6, longitude=77.2)

    # In DESC order (timestamp DESC, id DESC), INC-002 comes first, then INC-001
    mock_result_page1 = MagicMock()
    mock_result_page1.scalars.return_value.all.return_value = [inc_b, inc_a]
    mock_session.execute.return_value = mock_result_page1

    # Page 1 fetch with limit=1
    page1 = await repo.list_incidents_paginated(params=PaginationParams(limit=1))
    assert len(page1.items) == 1
    assert page1.items[0].id == "INC-002"
    assert page1.has_more is True
    assert page1.next_cursor is not None
    assert page1.next_cursor["id"] == "INC-002"

    # Page 2 fetch using next_cursor from Page 1
    cursor_ts = datetime.fromisoformat(page1.next_cursor["timestamp"])
    cursor_id = page1.next_cursor["id"]

    mock_result_page2 = MagicMock()
    mock_result_page2.scalars.return_value.all.return_value = [inc_a]
    mock_session.execute.return_value = mock_result_page2

    page2 = await repo.list_incidents_paginated(
        params=PaginationParams(limit=1, cursor_timestamp=cursor_ts, cursor_id=cursor_id)
    )
    assert len(page2.items) == 1
    assert page2.items[0].id == "INC-001"
    assert page2.has_more is False
    assert page2.next_cursor is None

    # No duplicate items between page 1 and page 2
    assert page1.items[0].id != page2.items[0].id


# ── 3. Incident Keyset Pagination Repository Tests ──────────────────────

@pytest.mark.anyio
async def test_incident_repository_paginated():
    """Verify IncidentRepository list_incidents_paginated query building and cursor handling."""
    mock_session = AsyncMock()
    repo = IncidentRepository(mock_session)

    base_time = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
    mock_incidents = [
        Incident(id=f"INC-00{i}", incident_type="flood", status="ACTIVE", started_at=base_time - timedelta(minutes=i*10), sector="B", severity="HIGH", location_name="Loc", latitude=28.6, longitude=77.2)
        for i in range(1, 4)
    ]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_incidents
    mock_session.execute.return_value = mock_result

    res = await repo.list_incidents_paginated(
        params=PaginationParams(limit=2),
        status="ACTIVE",
    )
    mock_session.execute.assert_called_once()
    assert len(res.items) == 2
    assert res.has_more is True
    assert res.next_cursor["id"] == "INC-002"


# ── 4. Telemetry Keyset Pagination Repository Tests ─────────────────────

@pytest.mark.anyio
async def test_telemetry_repository_paginated():
    """Verify TelemetryRepository get_history_paginated query building and time filter."""
    mock_session = AsyncMock()
    repo = TelemetryRepository(mock_session)
    inc_id = "INC-2026-001"
    base_time = datetime(2026, 9, 27, 8, 0, 0, tzinfo=timezone.utc)

    mock_obs = [
        TelemetryObservation(
            id=uuid.uuid4(),
            incident_id=inc_id,
            data_mode="simulated",
            fallback_used=False,
            rainfall_intensity=50.0,
            rainfall_trend=2.0,
            water_level=4.5,
            water_level_trend=0.3,
            road_congestion=0.6,
            population_exposure=10000.0,
            infrastructure_vulnerability=0.5,
            provenance={"provider": "test"},
            observed_at=base_time - timedelta(minutes=i*5),
        )
        for i in range(3)
    ]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_obs
    mock_session.execute.return_value = mock_result

    res = await repo.get_history_paginated(
        incident_id=inc_id,
        params=PaginationParams(limit=2, from_time=base_time - timedelta(hours=1)),
    )
    mock_session.execute.assert_called_once()
    assert len(res.items) == 2
    assert res.has_more is True


# ── 5. Risk Prediction Keyset Pagination Repository Tests ──────────────

@pytest.mark.anyio
async def test_risk_prediction_repository_paginated():
    """Verify RiskPredictionRepository get_history_paginated query building."""
    mock_session = AsyncMock()
    repo = RiskPredictionRepository(mock_session)
    inc_id = "INC-2026-001"
    base_time = datetime(2026, 9, 27, 8, 0, 0, tzinfo=timezone.utc)

    mock_preds = [
        RiskPrediction(
            id=uuid.uuid4(),
            incident_id=inc_id,
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
            created_at=base_time - timedelta(minutes=i*10),
        )
        for i in range(2)
    ]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_preds
    mock_session.execute.return_value = mock_result

    res = await repo.get_history_paginated(
        incident_id=inc_id,
        horizon=0,
        params=PaginationParams(limit=5),
    )
    mock_session.execute.assert_called_once()
    assert len(res.items) == 2
    assert res.has_more is False


# ── 6. Route & Audit Keyset Pagination Repository Tests ────────────────

@pytest.mark.anyio
async def test_route_and_audit_repository_paginated():
    """Verify EvacuationRouteRepository and AuditEventRepository get_history_paginated."""
    mock_session = AsyncMock()
    route_repo = EvacuationRouteRepository(mock_session)
    audit_repo = AuditEventRepository(mock_session)

    inc_id = "INC-2026-001"
    base_time = datetime(2026, 9, 27, 8, 0, 0, tzinfo=timezone.utc)

    # Routes
    mock_routes = [
        EvacuationRoute(
            id=uuid.uuid4(),
            incident_id=inc_id,
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
    ]
    mock_res_routes = MagicMock()
    mock_res_routes.scalars.return_value.all.return_value = mock_routes
    mock_session.execute.return_value = mock_res_routes

    route_res = await route_repo.get_history_paginated(inc_id, params=PaginationParams(limit=5))
    assert len(route_res.items) == 1

    # Audits
    mock_audits = [
        AuditEvent(
            id=uuid.uuid4(),
            incident_id=inc_id,
            event_type="TEST",
            severity="INFO",
            source="test",
            description="test desc",
            created_at=base_time,
        )
    ]
    mock_res_audits = MagicMock()
    mock_res_audits.scalars.return_value.all.return_value = mock_audits
    mock_session.execute.return_value = mock_res_audits

    audit_res = await audit_repo.get_history_paginated(inc_id, params=PaginationParams(limit=5))
    assert len(audit_res.items) == 1
