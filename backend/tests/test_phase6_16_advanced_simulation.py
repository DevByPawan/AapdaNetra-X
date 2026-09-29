"""
AapdaNetra-X — Phase 6.16 Advanced What-If Simulation & Scenario Analysis Test Suite
"""

import math
import pytest
from pydantic import ValidationError

from app.models.schemas import (
    ScenarioCompareRequest,
    SimulationRequest,
    SimulationResponse,
)
from app.services.scenario_service import (
    compute_scenario_fingerprint,
    evaluate_scenario_alerts,
    execute_scenario_analysis,
    transform_baseline_features,
)
from ml.features.schema import FEATURE_NAMES, validate_and_clean_features


# ── A. Scenario Validation Tests ──────────────────────────────────────────
def test_scenario_validation_valid_params():
    req = SimulationRequest(
        evacuationPace=1.5,
        rainfallMultiplier=2.0,
        drainageEfficiency=0.8,
        routeBlockage=True,
        rainfallIncrease=50.0,
        populationMovement=5000,
        waterLevelIncrease=1.5,
    )
    assert req.evacuationPace == 1.5
    assert req.rainfallMultiplier == 2.0
    assert req.drainageEfficiency == 0.8
    assert req.routeBlockage is True
    assert req.rainfallIncrease == 50.0
    assert req.populationMovement == 5000
    assert req.waterLevelIncrease == 1.5


def test_scenario_validation_nan_inf_rejection():
    with pytest.raises(ValidationError):
        SimulationRequest(rainfallMultiplier=float("nan"))

    with pytest.raises(ValidationError):
        SimulationRequest(waterLevelIncrease=float("inf"))

    with pytest.raises(ValidationError):
        SimulationRequest(evacuationPace=-float("inf"))


def test_scenario_validation_bounds():
    with pytest.raises(ValidationError):
        SimulationRequest(evacuationPace=0.0)  # ge=0.1

    with pytest.raises(ValidationError):
        SimulationRequest(drainageEfficiency=1.5)  # le=1.0

    with pytest.raises(ValidationError):
        SimulationRequest(rainfallMultiplier=-1.0)  # ge=0.0


# ── B. Baseline Preservation Tests ───────────────────────────────────────
def test_baseline_preservation():
    from app.services.risk_engine import _get_base_features, predict_risk

    base_before = _get_base_features()
    ml_before = predict_risk(base_before)

    # Run simulation
    req = SimulationRequest(rainfallIncrease=100.0, routeBlockage=True, waterLevelIncrease=5.0)
    res = execute_scenario_analysis(req)

    base_after = _get_base_features()
    ml_after = predict_risk(base_after)

    # Base telemetry & live risk prediction must NOT be mutated by simulation
    assert base_before == base_after
    assert ml_before["risk_score"] == ml_after["risk_score"]
    assert res.baselineRisk == ml_before["risk_score"]


# ── C. Feature Transformation Tests ──────────────────────────────────────
def test_feature_transformation_bounds_and_canonical_order():
    base_features = {
        "rainfall_intensity": 45.0,
        "rainfall_trend": 5.0,
        "water_level": 4.2,
        "water_level_trend": 0.3,
        "road_congestion": 0.65,
        "population_exposure": 12430.0,
        "infrastructure_vulnerability": 0.72,
    }

    req = SimulationRequest(
        rainfallMultiplier=2.0,
        rainfallIncrease=50.0,
        waterLevelIncrease=2.0,
        drainageEfficiency=0.5,
        evacuationPace=0.8,
        routeBlockage=True,
        populationMovement=3000,
    )

    transformed = transform_baseline_features(base_features, req)

    # Check 7 ML features present
    for fname in FEATURE_NAMES:
        assert fname in transformed

    # Check bounds clipping
    assert 0.0 <= transformed["rainfall_intensity"] <= 300.0
    assert 0.0 <= transformed["water_level"] <= 15.0
    assert 0.0 <= transformed["road_congestion"] <= 1.0
    assert 0.0 <= transformed["population_exposure"] <= 100000.0


# ── D. ML Scenario Prediction Tests ─────────────────────────────────────
def test_ml_scenario_prediction_deterministic():
    req = SimulationRequest(rainfallIncrease=30.0, waterLevelIncrease=1.0)

    res1 = execute_scenario_analysis(req)
    res2 = execute_scenario_analysis(req)

    assert res1.scenarioRisk == res2.scenarioRisk
    assert res1.riskDelta == res2.riskDelta
    assert res1.label == "SIMULATED SCENARIO OUTPUT"
    assert res1.reproducibility["model_version"] == "v1.0.0"


# ── E. Conformal Uncertainty Tests ──────────────────────────────────────
def test_conformal_uncertainty_integration():
    req = SimulationRequest(rainfallIncrease=25.0)
    res = execute_scenario_analysis(req)

    assert res.uncertainty is not None
    assert "baseline" in res.uncertainty
    assert "scenario" in res.uncertainty
    assert res.uncertainty["nominal_coverage"] == 0.90
    assert res.uncertainty["status"] == "calibrated"

    scen_unc = res.uncertainty["scenario"]
    assert scen_unc["lower_bound"] <= res.scenarioRisk <= scen_unc["upper_bound"]


# ── F. SHAP Explanation Tests ───────────────────────────────────────────
def test_shap_explanation_integration():
    req = SimulationRequest(rainfallIncrease=40.0, waterLevelIncrease=2.0)
    res = execute_scenario_analysis(req)

    assert res.shap is not None
    assert res.shap["canonical_features"] == FEATURE_NAMES
    assert len(res.shap["attribution_changes"]) == 7

    for shift in res.shap["attribution_changes"]:
        assert "feature" in shift
        assert "shap_attribution_change" in shift
        assert "explanation" in shift
        assert "model attribution changed" in shift["explanation"].lower()


# ── G. Spatial Integration Tests ─────────────────────────────────────────
def test_spatial_integration():
    req = SimulationRequest(waterLevelIncrease=3.0)
    res = execute_scenario_analysis(req)

    assert res.spatial is not None
    assert "baseline_route_spatial_exposure" in res.spatial
    assert "scenario_route_spatial_exposure" in res.spatial
    assert "spatial_exposure_delta" in res.spatial
    assert "PROVISIONAL" in res.spatial["terminology_notice"]


# ── H. Route Comparison Tests ───────────────────────────────────────────
def test_route_comparison_integration():
    req_clear = SimulationRequest(routeBlockage=False)
    req_blocked = SimulationRequest(routeBlockage=True)

    res_clear = execute_scenario_analysis(req_clear)
    res_blocked = execute_scenario_analysis(req_blocked)

    assert res_blocked.routes is not None
    assert res_blocked.routes["route_changed"] is True
    assert "blockage" in res_blocked.routes["reason"] or res_blocked.routes["scenario_route"]["name"] != res_blocked.routes["baseline_route"]["name"]


# ── I. Scenario-Only Alert Tests ────────────────────────────────────────
def test_scenario_alerts_isolated():
    from app.services.alert_engine import IntelligentAlertEngine

    engine = IntelligentAlertEngine()
    active_alerts_before = len(engine._active_alerts)

    base_features = {
        "rainfall_intensity": 45.0,
        "rainfall_trend": 5.0,
        "water_level": 4.2,
        "water_level_trend": 0.3,
        "road_congestion": 0.65,
        "population_exposure": 12430.0,
        "infrastructure_vulnerability": 0.72,
    }
    scen_features = dict(base_features)
    scen_features["water_level"] = 12.0
    scen_features["rainfall_intensity"] = 250.0

    eval_result = evaluate_scenario_alerts(
        incident_id="INC-2026-DEFAULT",
        baseline_features=base_features,
        scenario_features=scen_features,
        baseline_risk=45.0,
        scenario_risk=92.0,
        baseline_unc={"lower_bound": 38.0, "upper_bound": 52.0},
        scenario_unc={"lower_bound": 85.0, "upper_bound": 98.0},
        baseline_spatial={},
        scenario_spatial={},
        route_blockage=True,
    )

    active_alerts_after = len(engine._active_alerts)

    # Active alerts in live engine must NOT be mutated
    assert active_alerts_before == active_alerts_after

    # Scenario alerts must be marked SIMULATION ONLY / SCENARIO ONLY
    assert eval_result["newly_triggered_count"] > 0
    for alt in eval_result["scenario_triggered_alerts"]:
        assert alt["simulation_only"] is True
        assert alt["status"] == "SCENARIO_ONLY"
        assert "[SIMULATION]" in alt["title"]


# ── J. Reproducibility & Fingerprint Tests ──────────────────────────────
def test_scenario_reproducibility_fingerprint():
    base_features = {"rainfall_intensity": 45.0, "water_level": 4.2}
    params = {"rainfallIncrease": 20.0, "populationMovement": 1000}

    fp1 = compute_scenario_fingerprint(base_features, params, "v1.0.0")
    fp2 = compute_scenario_fingerprint(base_features, params, "v1.0.0")

    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex string


# ── K. Endpoint & Comparison Router Tests ───────────────────────────────
def test_simulation_router_endpoints():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    req_payload = {
        "evacuationPace": 1.0,
        "rainfallMultiplier": 1.2,
        "drainageEfficiency": 0.9,
        "routeBlockage": False,
        "rainfallIncrease": 15.0,
        "populationMovement": 500,
        "waterLevelIncrease": 0.5,
    }

    # POST /api/simulation
    resp1 = client.post("/api/simulation", json=req_payload)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "newRisk" in data1
    assert data1["label"] == "SIMULATED SCENARIO OUTPUT"

    # POST /api/simulations (plural)
    resp2 = client.post("/api/simulations", json=req_payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["newRisk"] == data1["newRisk"]

    # POST /api/simulations/compare
    compare_payload = {
        "scenario_a": req_payload,
        "scenario_b": {**req_payload, "routeBlockage": True, "rainfallIncrease": 80.0},
        "incident_id": "INC-2026-DEFAULT",
    }
    resp3 = client.post("/api/simulations/compare", json=compare_payload)
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert "scenario_a" in data3
    assert "scenario_b" in data3
    assert "risk_delta_between_scenarios" in data3

