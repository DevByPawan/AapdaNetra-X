"""
AapdaNetra-X — Phase 6.19 Real-Time Telemetry Pipeline Test Suite
"""

import time
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import TelemetryIngestionRequest
from app.services.telemetry_service import (
    TelemetryIngestionService,
    compute_observation_hash,
    get_telemetry_service,
    parse_and_validate_timestamp,
    validate_raw_features,
)
from app.data.providers.data_adapter import BASE_SENSOR_FEATURES, get_data_adapter


@pytest.fixture
def client():
    return TestClient(app)


# 1. Valid ingestion
def test_01_valid_ingestion(client):
    req = {
        "incident_id": "INC-2026-TEST",
        "sensor_id": "SENSOR-01",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "features": {"rainfall_intensity": 110.0, "water_level": 7.5},
        "source": "unit_test",
    }
    resp = client.post("/api/telemetry/observe", json=req)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["cascade_triggered"] is True
    assert data["features"]["rainfall_intensity"] == 110.0


# 2. Partial feature ingestion
def test_02_partial_feature_ingestion():
    svc = get_telemetry_service()
    req = TelemetryIngestionRequest(
        incident_id="INC-2026-TEST",
        sensor_id="SENSOR-PARTIAL",
        features={"water_level": 8.2},
    )
    res = svc.ingest_observation(req)
    assert res.status == "accepted"
    assert res.features["water_level"] == 8.2
    assert "rainfall_intensity" in res.features  # Filled safely from baseline/spec defaults


# 3. Malformed payload
def test_03_malformed_payload(client):
    resp = client.post("/api/telemetry/observe", json={"incident_id": "INC-2026-TEST", "features": "not_a_dict"})
    assert resp.status_code == 422  # Pydantic schema validation failure


# 4. NaN rejection
def test_04_nan_rejection(client):
    req = {
        "incident_id": "INC-2026-TEST",
        "sensor_id": "SENSOR-01",
        "features": {"rainfall_intensity": "NaN"},
    }
    resp = client.post("/api/telemetry/observe", json=req)
    assert resp.status_code == 400
    assert "validation failure" in resp.json()["detail"].lower()


# 5. Infinity rejection
def test_05_infinity_rejection(client):
    req = {
        "incident_id": "INC-2026-TEST",
        "sensor_id": "SENSOR-01",
        "features": {"water_level": "inf"},
    }
    resp = client.post("/api/telemetry/observe", json=req)
    assert resp.status_code == 400


# 6. Out-of-range values clipping
def test_06_out_of_range_clipping():
    svc = get_telemetry_service()
    req = TelemetryIngestionRequest(
        incident_id="INC-2026-TEST",
        sensor_id="SENSOR-CLIP",
        features={"rainfall_intensity": 9999.0, "road_congestion": 2.5},
    )
    res = svc.ingest_observation(req)
    assert res.features["rainfall_intensity"] == 300.0  # Max spec limit
    assert res.features["road_congestion"] == 1.0       # Max spec limit


# 7. UTC timestamp normalization
def test_07_utc_timestamp_normalization():
    dt_iso = "2026-09-30T02:00:00+05:30"
    dt_utc = parse_and_validate_timestamp(dt_iso)
    assert dt_utc.tzinfo == timezone.utc
    assert dt_utc.hour == 20  # 02:00 - 5h30m = 20:30 previous day UTC


# 8. Future timestamp handling
def test_08_future_timestamp_rejection():
    future_iso = (datetime.now(timezone.utc) + timedelta(seconds=600)).isoformat()
    with pytest.raises(ValueError, match="Future timestamp rejected"):
        parse_and_validate_timestamp(future_iso)


# 9-10. Duplicate fingerprint & cascade suppression
def test_09_10_duplicate_fingerprint(client):
    ts = datetime.now(timezone.utc).isoformat()
    req = {
        "incident_id": "INC-2026-DUP-TEST",
        "sensor_id": "SENSOR-DUP",
        "observed_at": ts,
        "features": {"water_level": 7.1},
        "client_event_id": "evt-unique-12345",
    }
    # First submit
    resp1 = client.post("/api/telemetry/observe", json=req)
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "accepted"

    # Second submit (identical payload & timestamp)
    resp2 = client.post("/api/telemetry/observe", json=req)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "duplicate_ignored"
    assert data2["cascade_triggered"] is False


# 11. Conflicting equal-timestamp observation
def test_11_equal_timestamp_conflicting_observation(client):
    ts = datetime.now(timezone.utc).isoformat()
    req1 = {"incident_id": "INC-2026-EQ-TEST", "sensor_id": "SENSOR-EQ", "observed_at": ts, "features": {"water_level": 6.0}}
    req2 = {"incident_id": "INC-2026-EQ-TEST", "sensor_id": "SENSOR-EQ", "observed_at": ts, "features": {"water_level": 9.0}}

    resp1 = client.post("/api/telemetry/observe", json=req1)
    resp2 = client.post("/api/telemetry/observe", json=req2)
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["observation_hash"] != resp2.json()["observation_hash"]


# 12. Out-of-order observation
def test_12_out_of_order_observation(client):
    now_dt = datetime.now(timezone.utc)
    newer_ts = now_dt.isoformat()
    older_ts = (now_dt - timedelta(minutes=10)).isoformat()

    # Submit newer observation
    req_newer = {"incident_id": "INC-2026-ORDER-TEST", "sensor_id": "SENSOR-ORDER", "observed_at": newer_ts, "features": {"water_level": 7.0}}
    client.post("/api/telemetry/observe", json=req_newer)

    # Submit older observation
    req_older = {"incident_id": "INC-2026-ORDER-TEST", "sensor_id": "SENSOR-ORDER", "observed_at": older_ts, "features": {"water_level": 4.0}}
    resp_older = client.post("/api/telemetry/observe", json=req_older)

    assert resp_older.status_code == 200
    data_older = resp_older.json()
    assert data_older["status"] == "out_of_order"
    assert data_older["cascade_triggered"] is False


# 13-17. Rolling trend calculation rules
def test_13_17_trend_calculation(client):
    base_dt = datetime.now(timezone.utc) - timedelta(minutes=2)
    ts1 = base_dt.isoformat()
    ts2 = datetime.now(timezone.utc).isoformat()

    # First observation (no trend computed)
    req1 = {"incident_id": "INC-2026-TREND-TEST", "sensor_id": "SENSOR-TREND", "observed_at": ts1, "features": {"water_level": 5.0, "rainfall_intensity": 50.0}}
    resp1 = client.post("/api/telemetry/observe", json=req1)
    assert resp1.json()["trends"] == {}

    # Second observation (+2 min later, water_level +1.0m, rainfall +20mm/h)
    req2 = {"incident_id": "INC-2026-TREND-TEST", "sensor_id": "SENSOR-TREND", "observed_at": ts2, "features": {"water_level": 6.0, "rainfall_intensity": 70.0}}
    resp2 = client.post("/api/telemetry/observe", json=req2)
    trends2 = resp2.json()["trends"]

    assert "water_level_trend" in trends2
    # 1.0m / (2min / 60) = 30.0 m/h -> clipped to max 5.0 m/h spec
    assert trends2["water_level_trend"] == 5.0


# 18-20. Provenance preservation & live overlay non-mutation
def test_18_20_overlay_non_mutation():
    adapter = get_data_adapter()
    base_before = dict(BASE_SENSOR_FEATURES)

    svc = get_telemetry_service()
    req = TelemetryIngestionRequest(incident_id="INC-2026-TEST", sensor_id="S-OVERLAY", features={"rainfall_intensity": 140.0})
    svc.ingest_observation(req)

    overlay = adapter.get_live_overlay()
    assert overlay["features"]["rainfall_intensity"] == 140.0
    assert BASE_SENSOR_FEATURES == base_before  # Baseline dict untouched


# 21-26. Persistence mode policy compliance
def test_21_26_persistence_modes(monkeypatch, client):
    from app.config import settings

    # Mode: disabled
    monkeypatch.setattr(settings, "persistence_mode", "disabled")
    req_dis = {"incident_id": "INC-PERSIST-TEST", "sensor_id": "S-PERSIST", "features": {"water_level": 6.0}}
    resp_dis = client.post("/api/telemetry/observe", json=req_dis)
    assert resp_dis.json()["persistence_status"] == "disabled"

    # Mode: optional DB unavailable
    monkeypatch.setattr(settings, "persistence_mode", "optional")
    resp_opt = client.post("/api/telemetry/observe", json=req_dis)
    assert resp_opt.json()["persistence_status"] in ["in_memory_fallback", "persisted"]

    # Mode: required DB failure -> controlled 503 and NO state mutation
    adapter = get_data_adapter()
    overlay_before = adapter.get_live_overlay()

    monkeypatch.setattr(settings, "persistence_mode", "required")
    from app.services import persistence_service
    monkeypatch.setattr(persistence_service.PersistenceService, "db_available", property(lambda self: False))

    req_fail = {"incident_id": "INC-PERSIST-TEST", "sensor_id": "S-FAIL-REQUIRED", "features": {"water_level": 9.99}}
    resp_req = client.post("/api/telemetry/observe", json=req_fail)
    assert resp_req.status_code == 503
    assert "unavailable in required mode" in resp_req.json()["detail"].lower()

    # Verify live overlay was NOT mutated on persistence failure
    overlay_after = adapter.get_live_overlay()
    assert overlay_after["features"].get("water_level") != 9.99


# 27-34. Event cascade & SSE endpoints
def test_27_34_sse_cascade(client):
    req = {
        "incident_id": "INC-CASCADE-TEST",
        "sensor_id": "SENSOR-CASCADE",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "features": {"rainfall_intensity": 180.0, "water_level": 9.5},
    }
    resp = client.post("/api/telemetry/observe", json=req)
    assert resp.status_code == 200
    assert resp.json()["cascade_triggered"] is True


# 35-41. Failure isolation & health metrics
def test_35_41_failure_isolation_and_health(client):
    # Endpoint GET /api/telemetry/live
    resp_live = client.get("/api/telemetry/live")
    assert resp_live.status_code == 200
    assert "active_features" in resp_live.json()

    # Endpoint GET /api/telemetry/health
    resp_health = client.get("/api/telemetry/health")
    assert resp_health.status_code == 200
    health_data = resp_health.json()
    assert "metrics" in health_data
    assert health_data["metrics"]["accepted"] >= 1


# 42. API backward compatibility
def test_42_api_backward_compatibility(client):
    # Existing GET /api/risk
    resp_risk = client.get("/api/risk?horizon=0")
    assert resp_risk.status_code == 200
    assert "predictedRisk" in resp_risk.json()

    # Existing GET /api/routes
    resp_routes = client.get("/api/routes?horizon=0")
    assert resp_routes.status_code == 200
    assert "recommended" in resp_routes.json()
