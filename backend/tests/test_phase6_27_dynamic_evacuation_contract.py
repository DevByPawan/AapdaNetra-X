"""
AapdaNetra-X — Phase 6.27 Dynamic Evacuation with Real-Derived Risk Test Suite
Validates risk data contract and explainability integration with dynamic route optimization.
"""
import pytest
from ml.routing.optimizer import optimize_routes, RouteOptimizer
from ml.inference.predictor import predict_risk
from ml.explainability.explainer import explain_prediction
from app.services.risk_engine import get_horizon_features
from app.services.risk_contract import evaluate_risk_engine_contract, InferenceEligibilityStatus

BASE_FEATURES = {
    "rainfall_intensity": 95.0,
    "rainfall_trend": 12.0,
    "water_level": 6.8,
    "water_level_trend": 0.45,
    "road_congestion": 0.72,
    "population_exposure": 12430.0,
    "infrastructure_vulnerability": 0.78,
}


def test_route_selection_uses_correct_validated_risk_result_and_horizon():
    """Scenario 1: Route selection uses the correct validated risk score for requested horizon."""
    for h in [0, 1, 2, 3]:
        h_feats = get_horizon_features(h)
        ml_res = predict_risk(h_feats, data_mode="simulated")
        opt_res = optimize_routes(
            predicted_risk_score=ml_res["risk_score"],
            horizon_index=h,
            data_contract=ml_res["data_contract"],
        )

        assert opt_res.horizon_index == h
        assert opt_res.recommended is not None
        assert opt_res.recommended.eta > 0
        assert opt_res.recommended.safetyScore >= 0.0


def test_risk_provenance_and_eligibility_metadata_propagates_into_route_decisions():
    """Scenario 2: Risk provenance and eligibility metadata propagate into route optimization results."""
    provenance = {
        "rainfall_intensity": "DERIVED_FROM_REAL",
        "road_congestion": "DERIVED_FROM_REAL / 2020 BASELINE",
    }
    contract = evaluate_risk_engine_contract(BASE_FEATURES, data_mode="real", provenance=provenance)
    contract_dict = contract.to_dict()

    opt_res = optimize_routes(predicted_risk_score=82.0, data_contract=contract_dict)

    assert opt_res.data_contract is not None
    assert opt_res.data_contract["inference_eligibility"] == InferenceEligibilityStatus.ELIGIBLE_REAL.value
    assert "[REAL_DERIVED_EVIDENCE]" in opt_res.route_reason
    assert opt_res.is_eligible is True


def test_invalid_or_ineligible_risk_inputs_and_explicit_fallback_behavior():
    """Scenario 3: Invalid or ineligible risk inputs trigger explicit fallback warning narrative."""
    bad_features = dict(BASE_FEATURES)
    bad_features["rainfall_intensity"] = float("nan")

    contract = evaluate_risk_engine_contract(bad_features, data_mode="real")
    contract_dict = contract.to_dict()

    opt_res = optimize_routes(predicted_risk_score=50.0, data_contract=contract_dict)

    assert opt_res.is_eligible is False
    assert "[INELIGIBLE_INVALID_INPUT]" in opt_res.route_reason
    assert "fallback policy" in opt_res.route_reason


def test_missing_cwc_observations_and_provisional_vulnerability():
    """Scenario 4: Missing CWC observations & provisional vulnerability propagate metadata cleanly."""
    provenance = {
        "water_level": "UNAVAILABLE",
        "infrastructure_vulnerability": "PROVISIONAL",
    }
    contract = evaluate_risk_engine_contract(BASE_FEATURES, data_mode="real", provenance=provenance)
    contract_dict = contract.to_dict()

    opt_res = optimize_routes(predicted_risk_score=75.0, data_contract=contract_dict)

    assert opt_res.data_contract["complete_real_evidence_present"] is False
    assert opt_res.data_contract["feature_classification"]["water_level"] == "UNAVAILABLE"
    assert opt_res.data_contract["feature_classification"]["infrastructure_vulnerability"] == "PROVISIONAL"


def test_stable_existing_behavior_in_simulated_mode():
    """Scenario 5: Simulated mode routing remains backward compatible."""
    opt_res = optimize_routes(predicted_risk_score=74.0, route_blockage=False)

    assert opt_res.recommended is not None
    assert opt_res.recommended.id == "route-rec"
    assert len(opt_res.alternatives) >= 1
    assert "selected" in opt_res.route_reason


def test_route_decision_trace_consistency_with_risk_result():
    """Scenario 6: Route decision trace (SHAP) matches risk prediction input."""
    exp = explain_prediction(BASE_FEATURES, data_mode="simulated")
    opt_res = optimize_routes(predicted_risk_score=exp["prediction"])

    assert opt_res.recommended is not None
    assert exp["is_shap_consistent"] is True
    assert len(exp["decision_trace"]) == 7
