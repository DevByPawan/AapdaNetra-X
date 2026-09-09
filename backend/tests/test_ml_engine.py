"""
Unit tests for AapdaNetra-X ML Risk Engine
Tests model loading, prediction validity, missing features, invalid input values,
zero rainfall, extreme rainfall, risk classification, and simulation logic.
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
from ml.features.schema import (
    RISK_THRESHOLDS,
    FEATURE_NAMES,
    categorize_risk,
    validate_and_clean_features,
)
from ml.inference import predict_risk, RiskPredictor, get_predictor
from app.services.risk_engine import compute_risk_state, run_simulation_engine


def test_model_loading():
    """Test that predictor loads model artifact without error."""
    predictor = get_predictor()
    assert predictor.model is not None, "Model failed to load."


def test_valid_prediction():
    """Test valid feature dict prediction."""
    sample_features = {
        "rainfall_intensity": 85.0,
        "rainfall_trend": 10.0,
        "water_level": 5.5,
        "water_level_trend": 0.4,
        "road_congestion": 0.65,
        "population_exposure": 15000.0,
        "infrastructure_vulnerability": 0.70,
    }
    res = predict_risk(sample_features)
    assert "risk_score" in res
    assert "risk_category" in res
    assert "prediction_reliability" in res
    assert 0.0 <= res["risk_score"] <= 100.0
    assert res["risk_category"] in ["LOW", "MODERATE", "HIGH", "CRITICAL"]
    assert 0.0 <= res["prediction_reliability"] <= 1.0


def test_missing_features_safe_handling():
    """Test missing/partial feature dict fills default values safely."""
    partial_features = {"rainfall_intensity": 100.0}
    res = predict_risk(partial_features)
    assert res["risk_score"] >= 0.0
    # Reliability penalty should reflect partial completeness
    assert res["prediction_reliability"] < 0.95


def test_invalid_values_safe_handling():
    """Test string/null/out-of-bounds input values are handled safely without crashing."""
    invalid_features = {
        "rainfall_intensity": "invalid_string",
        "water_level": None,
        "road_congestion": 999.0, # out of bounds, should be clipped
    }
    res = predict_risk(invalid_features)
    assert 0.0 <= res["risk_score"] <= 100.0
    assert res["cleaned_features"]["road_congestion"] == 1.0


def test_zero_rainfall():
    """Test zero rainfall scenario produces valid non-crashing prediction."""
    zero_rf = {
        "rainfall_intensity": 0.0,
        "rainfall_trend": 0.0,
        "water_level": 1.0,
        "water_level_trend": 0.0,
        "road_congestion": 0.2,
        "population_exposure": 1000.0,
        "infrastructure_vulnerability": 0.3,
    }
    res = predict_risk(zero_rf)
    assert 0.0 <= res["risk_score"] <= 100.0


def test_extreme_rainfall():
    """Test extreme max rainfall scenario clips and returns valid prediction."""
    extreme_rf = {
        "rainfall_intensity": 300.0,
        "rainfall_trend": 50.0,
        "water_level": 15.0,
        "water_level_trend": 5.0,
        "road_congestion": 1.0,
        "population_exposure": 100000.0,
        "infrastructure_vulnerability": 1.0,
    }
    res = predict_risk(extreme_rf)
    assert res["risk_score"] >= 70.0
    assert res["risk_category"] in ["HIGH", "CRITICAL"]


def test_risk_classification():
    """Test threshold categorization logic."""
    assert categorize_risk(15.0) == "LOW"
    assert categorize_risk(45.0) == "MODERATE"
    assert categorize_risk(75.0) == "HIGH"
    assert categorize_risk(95.0) == "CRITICAL"


def test_simulation_engine():
    """Test simulation engine returns baseline risk, scenario risk, and risk delta."""
    sim = run_simulation_engine(
        rainfallMultiplier=1.5,
        evacuationPace=1.2,
        drainageEfficiency=0.8,
        routeBlockage=True,
    )
    assert sim.baseline_risk > 0.0
    assert sim.scenario_risk > 0.0
    assert hasattr(sim, "risk_delta")
    assert sim.prediction_reliability > 0.0
    assert sim.riskCategory in ["LOW", "MODERATE", "HIGH", "CRITICAL"]
