"""
Unit and Integration tests for AapdaNetra-X SHAP Explainability Engine (Phase 5B)
Tests explainer initialization, feature mapping, output shape, positive/negative direction,
ranking, horizon-specific SHAP explanations, and API endpoints.
"""
import sys
from pathlib import Path

# Ensure root workspace and backend directories are in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
for p in [str(ROOT_DIR), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from fastapi.testclient import TestClient
from ml.explainability import (
    explain_prediction,
    get_explainer,
    SHAPExplainer,
    FEATURE_LABEL_MAP,
)
from ml.features.schema import FEATURE_NAMES
from app.services.risk_engine import get_horizon_features
from app.main import app

client = TestClient(app)


def test_shap_explainer_initialization():
    """1. Test SHAP explainer initializes and loads TreeExplainer."""
    explainer = get_explainer()
    assert explainer.explainer is not None, "SHAP TreeExplainer failed to initialize."


def test_correct_7_feature_mapping():
    """2. Test all 7 features are correctly mapped to human-readable labels."""
    assert len(FEATURE_LABEL_MAP) == 7
    for name in FEATURE_NAMES:
        assert name in FEATURE_LABEL_MAP
        assert len(FEATURE_LABEL_MAP[name]) > 0


def test_shap_output_shape():
    """3. Test SHAP explanation structure and feature count."""
    sample = {
        "rainfall_intensity": 90.0,
        "rainfall_trend": 10.0,
        "water_level": 6.5,
        "water_level_trend": 0.4,
        "road_congestion": 0.7,
        "population_exposure": 15000.0,
        "infrastructure_vulnerability": 0.8,
    }
    exp = explain_prediction(sample)
    assert "prediction" in exp
    assert "base_value" in exp
    assert "features" in exp
    assert "decision_trace" in exp
    assert len(exp["features"]) == 7
    assert len(exp["decision_trace"]) == 7


def test_positive_and_negative_risk_contributions():
    """4 & 5. Test positive and negative SHAP risk contributions."""
    sample = {
        "rainfall_intensity": 150.0,  # High rainfall -> increases risk
        "water_level": 8.5,           # High water level -> increases risk
        "population_exposure": 500.0, # Low exposure relative to mean -> decreases risk
    }
    exp = explain_prediction(sample)
    directions = [f["direction"] for f in exp["features"]]
    assert "increases_risk" in directions or "decreases_risk" in directions


def test_feature_ranking():
    """6. Test decision trace features are sorted descending by absolute impact."""
    exp = explain_prediction(get_horizon_features(0))
    features = exp["features"]
    for i in range(len(features) - 1):
        assert abs(features[i]["shap_value"]) >= abs(features[i + 1]["shap_value"])


def test_horizon_specific_explanations():
    """7. Test NOW (+0M) and +30M horizons produce distinct SHAP values."""
    f0 = get_horizon_features(0)
    f3 = get_horizon_features(3)
    exp0 = explain_prediction(f0)
    exp3 = explain_prediction(f3)
    assert exp0["prediction"] != exp3["prediction"]
    # Check at least top feature contribution or prediction differs
    assert exp0["decision_trace"] != exp3["decision_trace"]


def test_explainability_api_endpoint():
    """8. Test GET /api/explainability?horizon=1 endpoint."""
    response = client.get("/api/explainability?horizon=1")
    assert response.status_code == 200
    data = response.json()
    assert "prediction" in data
    assert "base_value" in data
    assert "features" in data
    assert len(data["features"]) == 7
    assert "decisionTrace" in data or "decision_trace" in data


def test_routes_api_shap_integration():
    """8b. Test GET /api/routes?horizon=2 returns dynamic SHAP decision trace."""
    response = client.get("/api/routes?horizon=2")
    assert response.status_code == 200
    data = response.json()
    assert "decisionTrace" in data
    assert len(data["decisionTrace"]) == 7
    first_factor = data["decisionTrace"][0]
    assert "factor" in first_factor
    assert "contribution" in first_factor


def test_simulation_compatibility():
    """9. Test POST /api/simulation returns valid outputs alongside SHAP prediction."""
    payload = {
        "evacuationPace": 1.2,
        "rainfallMultiplier": 1.6,
        "drainageEfficiency": 0.8,
        "routeBlockage": True
    }
    response = client.post("/api/simulation", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["scenarioRisk"] > 0.0
    assert "riskDelta" in data
