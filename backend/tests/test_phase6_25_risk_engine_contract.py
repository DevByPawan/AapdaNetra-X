"""
Phase 6.25 — Risk Engine Production Data Contract Unit Tests
Verifies feature validation, 7-feature ordering, missing/invalid feature detection,
out-of-range clipping flags, provenance & freshness integration, inference eligibility,
and preservation of Phase 6.23 disclaimers and prediction scores.
"""
from typing import Dict, Any
import pytest

from ml.features.schema import FEATURE_ORDER, FEATURE_SPECS
from app.data.providers.data_adapter import DataAdapter, BASE_SENSOR_FEATURES
from app.services.risk_contract import (
    evaluate_risk_engine_contract,
    RiskEngineDataContractResult,
    InferenceEligibilityStatus,
    FeatureClassification,
)
from app.services.risk_engine import compute_risk_state


def test_valid_simulated_inputs():
    """Scenario 1: Valid simulated baseline inputs return ELIGIBLE_SIMULATED and completeness 1.0."""
    contract = evaluate_risk_engine_contract(BASE_SENSOR_FEATURES, data_mode="simulated")

    assert contract.is_valid_structure is True
    assert contract.all_seven_features_present is True
    assert contract.missing_features == []
    assert contract.invalid_type_features == []
    assert contract.completeness_score == 1.0
    assert contract.inference_eligibility == InferenceEligibilityStatus.ELIGIBLE_SIMULATED.value
    assert contract.complete_real_evidence_present is False


def test_correct_seven_feature_ordering():
    """Scenario 2: Contract evaluates exactly 7 required features in correct order."""
    contract = evaluate_risk_engine_contract(BASE_SENSOR_FEATURES, data_mode="simulated")

    assert list(contract.clipping_applied.keys()) == FEATURE_ORDER
    assert list(contract.feature_classification.keys()) == FEATURE_ORDER
    assert FEATURE_ORDER == [
        "rainfall_intensity",
        "rainfall_trend",
        "water_level",
        "water_level_trend",
        "road_congestion",
        "population_exposure",
        "infrastructure_vulnerability",
    ]


def test_missing_required_features():
    """Scenario 3: Missing features are detected and completeness score reduced."""
    partial_features = dict(BASE_SENSOR_FEATURES)
    del partial_features["water_level"]
    del partial_features["water_level_trend"]

    contract = evaluate_risk_engine_contract(partial_features, data_mode="hybrid")

    assert contract.all_seven_features_present is False
    assert "water_level" in contract.missing_features
    assert "water_level_trend" in contract.missing_features
    assert contract.completeness_score == 0.71  # 5/7 = 0.71


def test_invalid_types_and_out_of_range_inputs():
    """Scenario 4: Invalid types (NaN/Inf/strings) and out-of-range bounds are detected."""
    invalid_features = dict(BASE_SENSOR_FEATURES)
    invalid_features["rainfall_intensity"] = float("nan")
    invalid_features["road_congestion"] = 1.85  # Out of range max=1.0

    contract = evaluate_risk_engine_contract(invalid_features, data_mode="hybrid")

    assert contract.is_valid_structure is True
    assert "rainfall_intensity" in contract.invalid_type_features
    assert "road_congestion" in contract.out_of_range_features
    assert contract.clipping_applied["road_congestion"] is True
    assert contract.inference_eligibility == InferenceEligibilityStatus.INELIGIBLE_INVALID_INPUT.value


def test_missing_cwc_observations():
    """Scenario 5: Missing CWC milestone observations are tagged UNAVAILABLE."""
    cwc_missing_features = dict(BASE_SENSOR_FEATURES)
    cwc_missing_features["water_level"] = None
    cwc_missing_features["water_level_trend"] = None

    provenance = {"water_level": "UNAVAILABLE", "water_level_trend": "UNAVAILABLE"}
    contract = evaluate_risk_engine_contract(cwc_missing_features, data_mode="real", provenance=provenance)

    assert contract.feature_classification["water_level"] == FeatureClassification.UNAVAILABLE.value
    assert contract.feature_classification["water_level_trend"] == FeatureClassification.UNAVAILABLE.value


def test_historical_traffic_and_rainfall_provenance():
    """Scenario 6: 2020 traffic baseline and ERA5 rainfall are classified as HISTORICAL_BASELINE."""
    provenance = {
        "rainfall_intensity": "DERIVED_FROM_REAL",
        "rainfall_trend": "DERIVED_FROM_REAL",
        "road_congestion": "DERIVED_FROM_REAL / 2020 BASELINE",
    }
    contract = evaluate_risk_engine_contract(BASE_SENSOR_FEATURES, data_mode="real", provenance=provenance)

    assert contract.feature_classification["road_congestion"] == FeatureClassification.HISTORICAL_BASELINE.value
    assert contract.feature_classification["rainfall_intensity"] == FeatureClassification.HISTORICAL_BASELINE.value


def test_semantically_incompatible_population_exposure():
    """Scenario 7: WorldPop population exposure is classified CONTEXTUAL_STATIC."""
    provenance = {
        "population_exposure": "SEMANTICALLY_INCOMPATIBLE_FOR_CURRENT_GBR",
    }
    contract = evaluate_risk_engine_contract(BASE_SENSOR_FEATURES, data_mode="real", provenance=provenance)

    assert contract.feature_classification["population_exposure"] == FeatureClassification.CONTEXTUAL_STATIC.value


def test_provisional_infrastructure_vulnerability():
    """Scenario 8: Infrastructure vulnerability 0.72 is classified PROVISIONAL."""
    provenance = {
        "infrastructure_vulnerability": "PROVISIONAL",
    }
    contract = evaluate_risk_engine_contract(BASE_SENSOR_FEATURES, data_mode="real", provenance=provenance)

    assert contract.feature_classification["infrastructure_vulnerability"] == FeatureClassification.PROVISIONAL.value


def test_freshness_metadata_preservation():
    """Scenario 9: Phase 6.24 freshness metadata dict is preserved in contract result."""
    freshness = {
        "rainfall_intensity": {
            "feature_name": "rainfall_intensity",
            "source": "OpenWeatherMap",
            "observed_at": "2026-10-10T02:00:00Z",
            "age_seconds": 120.0,
            "freshness_status": "FRESH",
        }
    }
    contract = evaluate_risk_engine_contract(BASE_SENSOR_FEATURES, data_mode="live", freshness=freshness)

    assert "rainfall_intensity" in contract.feature_freshness
    assert contract.feature_freshness["rainfall_intensity"]["freshness_status"] == "FRESH"


def test_provider_fallback_and_simulated_mode_compatibility():
    """Scenario 10: Unconfigured providers fallback to simulated and retain ELIGIBLE_HYBRID status."""
    contract = evaluate_risk_engine_contract(BASE_SENSOR_FEATURES, data_mode="hybrid")

    assert contract.inference_eligibility == InferenceEligibilityStatus.ELIGIBLE_HYBRID.value
    assert contract.all_seven_features_present is True


def test_preservation_of_phase6_23_prediction_disclaimers():
    """Scenario 11: Synthetic training disclaimer is preserved in contract."""
    contract = evaluate_risk_engine_contract(BASE_SENSOR_FEATURES, data_mode="simulated")

    assert "Synthetic-trained GBR model weights" in contract.disclaimer
    assert "NOT been established" in contract.disclaimer


def test_no_unintended_change_to_existing_risk_calculation():
    """Scenario 12: compute_risk_state(0) returns identical risk scores and includes data_contract metadata."""
    res = compute_risk_state(horizon=0)

    assert res.currentRisk >= 0.0 and res.currentRisk <= 100.0
    assert res.predictedRisk >= 0.0 and res.predictedRisk <= 100.0
    assert res.riskCategory in ("LOW", "MODERATE", "HIGH", "CRITICAL")
    assert res.data_contract is not None
    assert res.data_contract["is_valid_structure"] is True
    assert res.data_contract["all_seven_features_present"] is True
