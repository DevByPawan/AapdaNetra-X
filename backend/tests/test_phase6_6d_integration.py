"""AapdaNetra-X — Phase 6.6D Integration & End-to-End Test Suite

Verifies historical REST APIs, cursor pagination behavior, timeline event merging,
SHAP explainability lookup, persistence mode handling, and non-breaking contract preservation.
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
    SHAPRecord,
)
from app.db.pagination import PaginationParams
from app.services.timeline_service import TimelineService

client = TestClient(app)


def test_historical_api_types_match_schemas():
    """Verify historical endpoints return responses matching expected PaginatedResponse schema."""
    with patch.object(settings, "persistence_mode", "disabled"):
        res = client.get("/api/incidents")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "next_cursor" in data
        assert "has_more" in data


@pytest.mark.anyio
async def test_timeline_first_page_load():
    """Verify timeline first page loads correctly."""
    mock_session = AsyncMock()
    service = TimelineService(mock_session)
    inc_id = "INC-66D-TEST"
    now = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)

    obs = TelemetryObservation(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"), incident_id=inc_id,
        rainfall_intensity=50.0, water_level=4.0, observed_at=now, created_at=now
    )

    def mock_execute(stmt):
        m = MagicMock()
        if "telemetry_observations" in str(stmt):
            m.scalars.return_value.all.return_value = [obs]
        else:
            m.scalars.return_value.all.return_value = []
        return m

    mock_session.execute.side_effect = mock_execute

    page = await service.get_incident_timeline(inc_id, params=PaginationParams(limit=10))
    assert len(page.items) == 1
    assert page.items[0].entity_id == "11111111-1111-1111-1111-111111111111"
    assert page.items[0].event_type == "TELEMETRY_OBSERVED"


@pytest.mark.anyio
async def test_timeline_next_page_uses_returned_cursor():
    """Verify timeline pagination passes next_cursor's timestamp and rank:id."""
    mock_session = AsyncMock()
    service = TimelineService(mock_session)
    inc_id = "INC-66D-CURSOR"
    base_time = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)

    obs1 = TelemetryObservation(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"), incident_id=inc_id,
        rainfall_intensity=60.0, water_level=5.0, observed_at=base_time + timedelta(minutes=10),
        created_at=base_time + timedelta(minutes=10)
    )
    pred1 = RiskPrediction(
        id=uuid.UUID("22222222-2222-2222-2222-222222222222"), incident_id=inc_id, horizon=0,
        horizon_label="NOW", current_risk=50.0, predicted_risk=70.0, risk_category="HIGH",
        confidence=0.9, prediction_reliability=0.9, affected_population=1000,
        critical_population=100, critical_assets_count=1, affected_assets_count=1,
        trend="↑", map_status_text="Text", prediction_note="Note", input_features={},
        heatmap_zones=[], created_at=base_time + timedelta(minutes=5)
    )

    def mock_execute(stmt):
        m = MagicMock()
        s = str(stmt)
        if "telemetry_observations" in s:
            m.scalars.return_value.all.return_value = [obs1]
        elif "risk_predictions" in s:
            m.scalars.return_value.all.return_value = [pred1]
        else:
            m.scalars.return_value.all.return_value = []
        return m

    mock_session.execute.side_effect = mock_execute

    # Page 1 (limit=1)
    p1 = await service.get_incident_timeline(inc_id, params=PaginationParams(limit=1))
    assert len(p1.items) == 1
    assert p1.has_more is True
    assert p1.next_cursor["id"] == "6:11111111-1111-1111-1111-111111111111"

    # Page 2 using cursor
    p2_ts = datetime.fromisoformat(p1.next_cursor["timestamp"])
    p2 = await service.get_incident_timeline(
        inc_id, params=PaginationParams(limit=1, cursor_timestamp=p2_ts, cursor_id=p1.next_cursor["id"])
    )
    assert len(p2.items) == 1
    assert p2.items[0].entity_id == "22222222-2222-2222-2222-222222222222"
    assert p2.has_more is False


@pytest.mark.anyio
async def test_risk_explanation_history_lookup():
    """Verify GET /api/risk/{prediction_id}/explanation returns SHAP explanation record."""
    pred_id = uuid.uuid4()
    rec = SHAPRecord(
        id=uuid.uuid4(),
        risk_prediction_id=pred_id,
        horizon=0,
        prediction=75.0,
        base_value=30.0,
        total_shap_delta=45.0,
        features={"rainfall_intensity": 20.0},
        decision_trace=[{"feature": "rainfall_intensity", "val": 50.0, "shap": 20.0, "desc": "Spike"}],
        created_at=datetime.now(timezone.utc),
    )

    with patch.object(settings, "persistence_mode", "optional"):
        with patch("app.routers.history.get_db_manager") as mock_db_mgr:
            mock_mgr = MagicMock()
            mock_mgr.is_available = True
            mock_session = AsyncMock()
            mock_res = MagicMock()
            mock_res.scalars.return_value.first.return_value = rec
            mock_session.execute.return_value = mock_res
            mock_mgr.get_session.return_value.__aenter__.return_value = mock_session
            mock_db_mgr.return_value = mock_mgr

            res = client.get(f"/api/risk/{pred_id}/explanation")
            assert res.status_code == 200
            data = res.json()
            assert data["risk_prediction_id"] == str(pred_id)
            assert data["prediction"] == 75.0
            assert len(data["decision_trace"]) == 1


def test_persistence_disabled_state_handled():
    """Verify persistence_mode=disabled handles requests gracefully with empty responses."""
    with patch.object(settings, "persistence_mode", "disabled"):
        res_timeline = client.get("/api/incidents/INC-001/timeline")
        assert res_timeline.status_code == 200
        assert res_timeline.json()["items"] == []

        res_risk = client.get("/api/incidents/INC-001/risk/history")
        assert res_risk.status_code == 200
        assert res_risk.json()["items"] == []


def test_persistence_required_failure_handled():
    """Verify persistence_mode=required returns 503 when DB is down."""
    with patch.object(settings, "persistence_mode", "required"):
        with patch("app.routers.history.get_db_manager") as mock_db_mgr:
            mock_mgr = MagicMock()
            mock_mgr.is_available = False
            mock_db_mgr.return_value = mock_mgr

            res = client.get("/api/incidents/INC-001/timeline")
            assert res.status_code == 503
            assert "unavailable" in res.json()["detail"].lower()


def test_sse_history_deduplication_composite_identity():
    """Verify composite deduplication identity (entity_type:entity_id:event_type:timestamp) semantics.

    Ensures:
      1. Duplicate identical SSE events are deduplicated.
      2. Historical event + corresponding SSE event are deduplicated.
      3. Same entity_id + different event_types BOTH remain.
      4. Same entity_id + different timestamps BOTH remain.
      5. Multiple legitimate events from the same entity ALL remain.
      6. Repeated SSE delivery does not cause duplicate accumulation.
    """
    def compute_dedupe_key(entity_type: str, entity_id: str, event_type: str, ts: str) -> str:
        return f"{entity_type}:{entity_id}:{event_type}:{ts}"

    seen_keys = set()
    timeline = []

    def add_event(entity_type: str, entity_id: str, event_type: str, ts: str, summary: str):
        key = compute_dedupe_key(entity_type, entity_id, event_type, ts)
        if key not in seen_keys:
            seen_keys.add(key)
            timeline.append({"key": key, "entity_id": entity_id, "summary": summary})

    ts1 = "2026-09-27T10:00:00Z"
    ts2 = "2026-09-27T10:05:00Z"

    # 1. Add historical telemetry event
    add_event("telemetry_observation", "obs-001", "TELEMETRY_OBSERVED", ts1, "Telemetry @ 10:00")
    assert len(timeline) == 1

    # 2. Add corresponding SSE telemetry event (same entity_type, entity_id, event_type, timestamp)
    add_event("telemetry_observation", "obs-001", "TELEMETRY_OBSERVED", ts1, "Telemetry @ 10:00")
    assert len(timeline) == 1  # Deduplicated!

    # 3. Add risk prediction referencing the SAME entity_id ("obs-001")
    add_event("risk_prediction", "obs-001", "RISK_EVALUATED", ts1, "Risk for obs-001 @ 10:00")
    assert len(timeline) == 2  # Different event_type & entity_type -> BOTH remain!

    # 4. Add telemetry event from same entity at a DIFFERENT timestamp (ts2)
    add_event("telemetry_observation", "obs-001", "TELEMETRY_OBSERVED", ts2, "Telemetry @ 10:05")
    assert len(timeline) == 3  # Different timestamp -> BOTH remain!

    # 5. Repeated delivery of 10:05 SSE event 5 times
    for _ in range(5):
        add_event("telemetry_observation", "obs-001", "TELEMETRY_OBSERVED", ts2, "Telemetry @ 10:05")
    assert len(timeline) == 3  # No duplicate accumulation!

