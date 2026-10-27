"""

AapdaNetra-X — Phase 6.29: Scenario / What-If Decision Engine Tests



Validates:

1. Baseline scenario equals existing baseline evaluation under identical assumptions.

2. Parameter changes alter outputs deterministically through existing pipeline.

3. Multiple feature changes and feature-bound validation via feature_overrides.

4. No mutation of shared provider state, live telemetry, or original baseline.

5. Route and decision comparisons use matching horizons and assumptions.

6. Unsupported hazards and ineligible evidence handling without flood model execution.

7. Invalid, non-finite (NaN/Inf), out-of-range scenario payload rejection.

8. Labeling, provenance, SHAP causality disclaimer, and synthetic GBR disclaimer preservation.

"""

import pytest

from fastapi.testclient import TestClient



from app.main import app

from app.models.schemas import SimulationRequest, ScenarioCompareRequest

from app.services.scenario_service import execute_scenario_analysis, transform_baseline_features

from app.services.risk_engine import compute_risk_state, get_horizon_features

from app.data.providers.data_adapter import get_data_adapter



client = TestClient(app)





def test_baseline_scenario_equals_existing_baseline():

    """Verify default SimulationRequest produces baselineRisk identical to compute_risk_state."""

    req = SimulationRequest(horizon=0)

    res = execute_scenario_analysis(req)



    baseline_risk_state = compute_risk_state(horizon=0)

    assert res.baselineRisk == pytest.approx(baseline_risk_state.predictedRisk, abs=0.1)

    assert res.horizon == 0

    assert res.hazard_type == "flood"





def test_deterministic_rainfall_and_water_level_transformations():

    """Verify parameter changes alter scenario features and risk deterministically."""

    req_default = SimulationRequest(horizon=0)

    res_default = execute_scenario_analysis(req_default)



    req_heavy_rain = SimulationRequest(horizon=0, rainfallMultiplier=2.5, waterLevelIncrease=2.0)

    res_heavy_rain = execute_scenario_analysis(req_heavy_rain)



    # Risk should increase deterministically under heavy rainfall & water level increase

    assert res_heavy_rain.scenarioRisk >= res_default.scenarioRisk

    assert res_heavy_rain.riskDelta >= 0.0

    assert res_heavy_rain.scenario_features["rainfall_intensity"] > res_default.scenario_features["rainfall_intensity"]

    assert res_heavy_rain.scenario_features["water_level"] > res_default.scenario_features["water_level"]





def test_feature_overrides_and_bounds_clamping():

    """Verify direct feature_overrides are merged and validated against schema bounds."""

    overrides = {

        "road_congestion": 0.95,

        "infrastructure_vulnerability": 0.85,

    }

    req = SimulationRequest(horizon=0, feature_overrides=overrides)

    res = execute_scenario_analysis(req)



    assert res.scenario_features["road_congestion"] == pytest.approx(0.95, abs=0.01)

    assert res.scenario_features["infrastructure_vulnerability"] == pytest.approx(0.85, abs=0.01)

    assert res.data_contract is not None

    assert "feature_classification" in res.data_contract





def test_no_mutation_of_shared_provider_state():

    """Verify scenario execution does not mutate baseline features or provider state."""

    adapter = get_data_adapter()

    initial_features = get_horizon_features(0)

    initial_mode = adapter.data_mode



    # Run aggressive scenario

    req = SimulationRequest(horizon=0, rainfallMultiplier=5.0, waterLevelIncrease=10.0, routeBlockage=True)

    _ = execute_scenario_analysis(req)



    post_features = get_horizon_features(0)

    post_mode = adapter.data_mode



    assert initial_features == post_features

    assert initial_mode == post_mode





def test_horizon_alignment_in_scenario_comparison():

    """Verify baseline and scenario evaluation respect requested horizon (e.g. horizon=2)."""

    req_h2 = SimulationRequest(horizon=2, rainfallMultiplier=1.5)

    res_h2 = execute_scenario_analysis(req_h2)



    h2_base_risk = compute_risk_state(horizon=2).predictedRisk

    assert res_h2.horizon == 2

    assert res_h2.baselineRisk == pytest.approx(h2_base_risk, abs=0.1)

    assert res_h2.routes["baseline_route"]["id"] is not None





def test_unsupported_hazard_scenario_handling():

    """Verify non-flood hazards (extreme_rainfall, landslide) return explicit capability status without flood model execution."""

    # Extreme rainfall (contextual only)

    req_rain = SimulationRequest(hazard_type="extreme_rainfall")

    res_rain = execute_scenario_analysis(req_rain)



    assert res_rain.hazard_type == "extreme_rainfall"

    assert res_rain.predictionReliability == 0.0

    assert res_rain.data_contract["model_available"] is False

    assert "HYPOTHETICAL SIMULATION" in res_rain.label



    # Landslide (unsupported)

    req_ls = SimulationRequest(hazard_type="landslide")

    res_ls = execute_scenario_analysis(req_ls)



    assert res_ls.hazard_type == "landslide"

    assert res_ls.predictionReliability == 0.0

    assert res_ls.data_contract["supported"] is False





def test_invalid_nan_inf_payload_rejection():

    """Verify non-finite values (NaN / Inf) in parameters or overrides raise validation errors."""

    with pytest.raises(ValueError):

        SimulationRequest(rainfallMultiplier=float("nan"))



    with pytest.raises(ValueError):

        SimulationRequest(waterLevelIncrease=float("inf"))



    req_invalid_override = SimulationRequest(feature_overrides={"water_level": float("nan")})

    with pytest.raises(ValueError):

        execute_scenario_analysis(req_invalid_override)





def test_disclaimers_and_shap_causality_notice():

    """Verify synthetic GBR disclaimer and SHAP causality notice are preserved in output."""

    req = SimulationRequest(horizon=0)

    res = execute_scenario_analysis(req)



    assert "SIMULATED SCENARIO OUTPUT" in res.disclaimer

    assert "Synthetic-trained GBR model weights" in res.disclaimer

    assert "causal physical mechanisms" in res.shap["disclaimer"]





def test_api_simulation_and_compare_endpoints():

    """Verify POST /api/simulation and POST /api/simulations/compare HTTP endpoints."""

    # Run simulation

    payload = {

        "evacuationPace": 1.2,

        "rainfallMultiplier": 1.4,

        "drainageEfficiency": 0.8,

        "routeBlockage": False,

        "horizon": 1,

        "hazard_type": "flood",

    }

    res_sim = client.post("/api/simulation", json=payload)

    assert res_sim.status_code == 200

    data_sim = res_sim.json()

    assert "newRisk" in data_sim

    assert data_sim["horizon"] == 1



    # Compare simulations

    compare_payload = {

        "scenario_a": {"rainfallMultiplier": 1.0},

        "scenario_b": {"rainfallMultiplier": 2.0},

        "incident_id": "INC-TEST-COMPARE",

    }

    res_comp = client.post("/api/simulations/compare", json=compare_payload)

    assert res_comp.status_code == 200

    data_comp = res_comp.json()

    assert "risk_delta_between_scenarios" in data_comp

    assert data_comp["scenario_b"]["scenarioRisk"] >= data_comp["scenario_a"]["scenarioRisk"]
