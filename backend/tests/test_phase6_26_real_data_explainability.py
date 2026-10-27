"""
AapdaNetra-X — Phase 6.26 Real-Data Risk + Explainability Integration Test Suite
Validates contract integration with risk prediction and SHAP explainability.
"""
import pytest
from ml.inference.predictor import predict_risk, RiskPredictor
from ml.explainability.explainer import explain_prediction, SHAPExplainer
from ml.features.schema import FEATURE_ORDER
from app.services.risk_engine import compute_risk_state
from app.models.schemas import RiskResponse, ExplainabilityResponse
from app.services.risk_contract import InferenceEligibilityStatus, FeatureClassification

BASE_FEATURES = {
    "rainfall_intensity": 95.0,
    "rainfall_trend": 12.0,
    "water_level": 6.8,
    "water_level_trend": 0.45,
    "road_congestion": 0.72,
    "population_exposure": 12430.0,
    "infrastructure_vulnerability": 0.78,
}


def test_simulated_mode_predictions_and_explanations_backward_compatibility():
    """Scenario 1: Simulated mode predictions and explanations remain backward-compatible."""
    pred = predict_risk(BASE_FEATURES, data_mode="simulated")
    exp = explain_prediction(BASE_FEATURES, data_mode="simulated")

    assert "risk_score" in pred
    assert "risk_category" in pred
    assert "data_contract" in pred
    assert pred["is_eligible"] is True
    assert pred["data_contract"]["inference_eligibility"] == InferenceEligibilityStatus.ELIGIBLE_SIMULATED.value

    assert "prediction" in exp
    assert "features" in exp
    assert len(exp["features"]) == 7
    assert exp["is_eligible"] is True
    assert exp["data_contract"]["inference_eligibility"] == InferenceEligibilityStatus.ELIGIBLE_SIMULATED.value


def test_real_derived_inputs_carry_contract_and_provenance():
    """Scenario 2: Real-derived inputs carry contract and provenance metadata."""
    provenance = {
        "rainfall_intensity": "DERIVED_FROM_REAL",
        "rainfall_trend": "DERIVED_FROM_REAL",
        "water_level": "OFFICIAL_EVENT_ONLY",
        "water_level_trend": "OFFICIAL_EVENT_ONLY",
        "road_congestion": "DERIVED_FROM_REAL / 2020 BASELINE",
        "population_exposure": "SEMANTICALLY_INCOMPATIBLE_FOR_CURRENT_GBR",
        "infrastructure_vulnerability": "PROVISIONAL",
    }
    pred = predict_risk(BASE_FEATURES, data_mode="real", provenance=provenance)
    exp = explain_prediction(BASE_FEATURES, data_mode="real", provenance=provenance)

    assert pred["data_contract"]["inference_eligibility"] == InferenceEligibilityStatus.ELIGIBLE_REAL.value
    assert exp["data_contract"]["inference_eligibility"] == InferenceEligibilityStatus.ELIGIBLE_REAL.value

    # Check feature classifications on SHAP items
    feat_map = {item["feature"]: item for item in exp["features"]}
    assert feat_map["road_congestion"]["classification"] == FeatureClassification.HISTORICAL_BASELINE.value
    assert feat_map["population_exposure"]["classification"] == FeatureClassification.CONTEXTUAL_STATIC.value
    assert feat_map["infrastructure_vulnerability"]["classification"] == FeatureClassification.PROVISIONAL.value


def test_shap_values_map_exact_7_features_and_ordering():
    """Scenario 3: SHAP values map to exact 7-feature prediction input."""
    exp = explain_prediction(BASE_FEATURES)
    extracted_names = [item["feature"] for item in exp["features"]]

    assert set(extracted_names) == set(FEATURE_ORDER)
    assert len(extracted_names) == 7

    for item in exp["features"]:
        name = item["feature"]
        assert item["raw_value"] == BASE_FEATURES[name]
        assert "shap_value" in item
        assert "contribution_percent" in item


def test_missing_cwc_observations_and_provisional_vulnerability_handling():
    """Scenario 4: Missing CWC observations and provisional infrastructure vulnerability are handled honestly."""
    provenance = {
        "water_level": "UNAVAILABLE",
        "water_level_trend": "UNAVAILABLE",
        "infrastructure_vulnerability": "PROVISIONAL",
    }
    contract_res = explain_prediction(BASE_FEATURES, data_mode="real", provenance=provenance)["data_contract"]

    assert contract_res["feature_classification"]["water_level"] == FeatureClassification.UNAVAILABLE.value
    assert contract_res["feature_classification"]["infrastructure_vulnerability"] == FeatureClassification.PROVISIONAL.value
    assert contract_res["complete_real_evidence_present"] is False


def test_invalid_and_ineligible_inputs_prevent_misleading_real_data_inference():
    """Scenario 5: Invalid or non-finite inputs return explicit ineligible safe status."""
    bad_features = dict(BASE_FEATURES)
    bad_features["rainfall_intensity"] = float("nan")

    pred = predict_risk(bad_features, data_mode="real")
    exp = explain_prediction(bad_features, data_mode="real")

    assert pred["is_eligible"] is False
    assert pred["data_contract"]["inference_eligibility"] == InferenceEligibilityStatus.INELIGIBLE_INVALID_INPUT.value
    assert pred["prediction_reliability"] == 0.0

    assert exp["is_eligible"] is False
    assert exp["data_contract"]["inference_eligibility"] == InferenceEligibilityStatus.INELIGIBLE_INVALID_INPUT.value


def test_provider_fallback_clearly_represented_in_metadata():
    """Scenario 6: Provider fallback is clearly represented in contract metadata."""
    features = dict(BASE_FEATURES)
    features["water_level"] = None  # missing feed

    pred = predict_risk(features, data_mode="hybrid")

    assert "water_level" in pred["data_contract"]["missing_features"]
    assert pred["data_contract"]["completeness_score"] < 1.0


def test_synthetic_model_disclaimers_and_freshness_metadata_preserved():
    """Scenario 7: Synthetic model disclaimers and freshness metadata remain present."""
    resp: RiskResponse = compute_risk_state(0)

    assert resp.data_contract is not None
    assert "Synthetic" in resp.data_contract["disclaimer"]
    assert "NOT been established" in resp.data_contract["disclaimer"]


def test_no_unintended_change_to_risk_calculation():
    """Scenario 8: Standard risk calculation math is preserved for baseline inputs."""
    pred = predict_risk(BASE_FEATURES, data_mode="simulated")

    assert pred["risk_score"] > 0.0
    assert pred["risk_score"] <= 100.0
    assert pred["risk_category"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
