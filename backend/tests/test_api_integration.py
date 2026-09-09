"""
Integration tests for AapdaNetra-X FastAPI Endpoints with ML Risk Engine
"""
import sys
from pathlib import Path

# Ensure root workspace and backend directories are in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
for p in [str(ROOT_DIR), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"


def test_risk_endpoint_horizons():
    for horizon in range(4):
        response = client.get(f"/api/risk?horizon={horizon}")
        assert response.status_code == 200
        data = response.json()
        assert "currentRisk" in data
        assert "predictedRisk" in data
        assert "riskCategory" in data
        assert "predictionReliability" in data
        assert data["index"] == horizon


def test_forecast_endpoint():
    response = client.get("/api/forecast")
    assert response.status_code == 200
    data = response.json()
    assert len(data["points"]) == 6
    assert "predictionReliability" in data


def test_simulation_endpoint():
    payload = {
        "evacuationPace": 1.2,
        "rainfallMultiplier": 1.5,
        "drainageEfficiency": 0.9,
        "routeBlockage": True
    }
    response = client.post("/api/simulation", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "newRisk" in data
    assert "baselineRisk" in data
    assert "scenarioRisk" in data
    assert "riskDelta" in data
    assert "predictionReliability" in data
    assert "riskCategory" in data
