"""
AapdaNetra-X — Phase 6.20.5 Hazard-Aware API Layer Tests

Tests:
1. GET /api/risk (omitted hazard_type -> defaults to flood operational GBR risk)
2. GET /api/risk?hazard_type=flood -> operational GBR risk
3. GET /api/risk?hazard_type=extreme_rainfall -> typed partially supported contextual capability (no ML risk)
4. GET /api/risk?hazard_type=landslide -> typed unavailable response (DEMONSTRATION_ONLY)
5. GET /api/risk?hazard_type=cyclone -> typed unavailable response (FUTURE_EXTENSION)
6. GET /api/risk?hazard_type=heatwave -> typed unavailable response (FUTURE_EXTENSION)
7. GET /api/risk?hazard_type=earthquake -> typed unavailable response (FUTURE_EXTENSION)
8. GET /api/risk?hazard_type=tsunami -> controlled 400 validation error
9. POST /api/telemetry/observe (omitted hazard_type -> defaults to flood persistence)
10. POST /api/telemetry/observe (explicit valid hazard_type -> persisted)
11. POST /api/telemetry/observe (invalid hazard_type -> controlled 400 validation error)
12. GET /api/hazards -> list of registered hazard definitions
13. GET /api/hazards/matrix -> capability matrix
14. GET /api/hazards/aggregate -> multi-hazard composite risk aggregate
15. GET /api/hazards/{hazard_type} -> specific definition & validation
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.hazards.types import HazardType, HazardCapabilityStatus

client = TestClient(app)


def test_risk_api_omitted_hazard_defaults_to_flood():
    """Omitting hazard_type must return operational flood GBR risk."""
    response = client.get("/api/risk?horizon=0")
    assert response.status_code == 200
    data = response.json()
    assert data["hazard_type"] == "flood"
    assert data["capability_status"] == "SUPPORTED"
    assert data["supported"] is True
    assert data["model_available"] is True
    assert data["predictedRisk"] > 0.0
    assert "predictionInterval" in data


def test_risk_api_explicit_flood():
    """Explicit hazard_type=flood returns operational flood GBR risk."""
    response = client.get("/api/risk?horizon=0&hazard_type=flood")
    assert response.status_code == 200
    data = response.json()
    assert data["hazard_type"] == "flood"
    assert data["capability_status"] == "SUPPORTED"
    assert data["supported"] is True
    assert data["model_available"] is True
    assert data["predictedRisk"] > 0.0


def test_risk_api_extreme_rainfall():
    """hazard_type=extreme_rainfall returns typed PARTIALLY_SUPPORTED capability without GBR model."""
    response = client.get("/api/risk?horizon=0&hazard_type=extreme_rainfall")
    assert response.status_code == 200
    data = response.json()
    assert data["hazard_type"] == "extreme_rainfall"
    assert data["capability_status"] == HazardCapabilityStatus.PARTIALLY_SUPPORTED.value
    assert data["supported"] is True
    assert data["model_available"] is False
    assert data["predicted_risk"] is None
    assert data["predictedRisk"] is None
    assert data["telemetry_available"] is True
    assert data["routing_available"] is False


@pytest.mark.parametrize("unsupported_hazard, expected_status", [
    ("landslide", HazardCapabilityStatus.DEMONSTRATION_ONLY.value),
    ("cyclone", HazardCapabilityStatus.FUTURE_EXTENSION.value),
    ("heatwave", HazardCapabilityStatus.FUTURE_EXTENSION.value),
    ("earthquake", HazardCapabilityStatus.FUTURE_EXTENSION.value),
])
def test_risk_api_unsupported_hazards(unsupported_hazard, expected_status):
    """Unsupported hazards return typed unavailable responses without executing flood ML."""
    response = client.get(f"/api/risk?horizon=0&hazard_type={unsupported_hazard}")
    assert response.status_code == 200
    data = response.json()
    assert data["hazard_type"] == unsupported_hazard
    assert data["capability_status"] == expected_status
    assert data["supported"] is False
    assert data["model_available"] is False
    assert data["predicted_risk"] is None
    assert data["predictedRisk"] is None


def test_risk_api_unknown_hazard_validation_error():
    """Unknown hazard_type must return a controlled 400 validation error."""
    response = client.get("/api/risk?horizon=0&hazard_type=tsunami")
    assert response.status_code == 400
    data = response.json()
    assert "Unknown or unsupported hazard_type" in data["detail"]


def test_telemetry_observe_omitted_hazard_defaults_to_flood():
    """Telemetry ingestion without hazard_type defaults to flood."""
    payload = {
        "incident_id": "INC-TEST-001",
        "sensor_id": "SENSOR-API-01",
        "features": {
            "rainfall_intensity": 100.0,
            "rainfall_trend": 10.0,
            "water_level": 7.0,
            "water_level_trend": 0.5,
            "road_congestion": 0.5,
            "population_exposure": 10000,
            "infrastructure_vulnerability": 0.8,
        },
    }
    response = client.post("/api/telemetry/observe", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["hazard_type"] == "flood"


def test_telemetry_observe_explicit_valid_hazard():
    """Telemetry ingestion with explicit valid hazard_type returns and persists hazard_type."""
    payload = {
        "incident_id": "INC-TEST-002",
        "sensor_id": "SENSOR-API-02",
        "hazard_type": "extreme_rainfall",
        "features": {
            "rainfall_intensity": 120.0,
            "rainfall_trend": 15.0,
            "water_level": 5.0,
            "water_level_trend": 0.2,
            "road_congestion": 0.4,
            "population_exposure": 8000,
            "infrastructure_vulnerability": 0.6,
        },
    }
    response = client.post("/api/telemetry/observe", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["hazard_type"] == "extreme_rainfall"


def test_telemetry_observe_invalid_hazard_returns_400():
    """Telemetry ingestion with invalid hazard_type returns controlled 400 error."""
    payload = {
        "incident_id": "INC-TEST-003",
        "sensor_id": "SENSOR-API-03",
        "hazard_type": "volcano",
        "features": {
            "rainfall_intensity": 10.0,
            "water_level": 1.0,
        },
    }
    response = client.post("/api/telemetry/observe", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "Unknown or invalid hazard_type" in data["detail"]


def test_hazards_api_endpoints():
    """Test /api/hazards endpoints."""
    # 1. GET /api/hazards
    res_all = client.get("/api/hazards")
    assert res_all.status_code == 200
    all_data = res_all.json()
    assert "flood" in all_data
    assert "extreme_rainfall" in all_data
    assert "landslide" in all_data

    # 2. GET /api/hazards/matrix
    res_matrix = client.get("/api/hazards/matrix")
    assert res_matrix.status_code == 200
    matrix_data = res_matrix.json()
    assert len(matrix_data) == 6

    # 3. GET /api/hazards/aggregate
    res_agg = client.get("/api/hazards/aggregate")
    assert res_agg.status_code == 200
    agg_data = res_agg.json()
    assert "composite_risk" in agg_data
    assert agg_data["primary_hazard_driver"] == "flood"

    # 4. GET /api/hazards/flood
    res_def = client.get("/api/hazards/flood")
    assert res_def.status_code == 200
    def_data = res_def.json()
    assert def_data["hazard_type"] == "flood"
    assert def_data["supported"] is True

    # 5. GET /api/hazards/invalid
    res_inv = client.get("/api/hazards/invalid_hazard")
    assert res_inv.status_code == 400
