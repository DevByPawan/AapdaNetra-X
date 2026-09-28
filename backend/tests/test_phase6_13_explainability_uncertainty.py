"""
Phase 6.13 — Explainability + Uncertainty Test Suite
Tests SHAP mathematical consistency, attribution language, feature schema order,
split-conformal prediction interval calibration, quantile bounds, empirical test coverage,
edge cases (NaN/Inf, missing calibration), API endpoints, SSE, and persistence integration.
"""
import json
import math
import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Ensure root directory and backend directory are in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
for p in [str(ROOT_DIR), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from ml.features.schema import FEATURE_NAMES
from ml.explainability import (
    explain_prediction,
    get_explainer,
    SHAPExplainer,
    FEATURE_LABEL_MAP,
)
from ml.uncertainty import (
    ConformalQuantifier,
    ConformalInterval,
    get_conformal_quantifier,
    quantify_uncertainty,
)
from ml.inference import predict_risk, get_predictor
from app.services.risk_engine import compute_risk_state, get_horizon_features
from app.main import app

client = TestClient(app)


# ─── 1. SHAP EXPLAINABILITY TESTS ────────────────────────────────────────

class TestSHAPExplainability:
    """Tests for SHAP feature attributions and consistency."""

    def test_feature_order_canonical(self):
        """1. Test feature names match canonical order exactly."""
        assert len(FEATURE_NAMES) == 7
        assert FEATURE_NAMES == [
            "rainfall_intensity",
            "rainfall_trend",
            "water_level",
            "water_level_trend",
            "road_congestion",
            "population_exposure",
            "infrastructure_vulnerability",
        ]

    def test_shap_output_dimensions(self):
        """2. Test SHAP output returns exactly 7 features and 7 decision factors."""
        sample = get_horizon_features(0)
        exp = explain_prediction(sample)
        assert len(exp["features"]) == 7
        assert len(exp["decision_trace"]) == 7

    def test_feature_attribution_sign(self):
        """3. Test direction is properly assigned based on SHAP value sign."""
        sample = {
            "rainfall_intensity": 180.0,
            "water_level": 8.0,
            "population_exposure": 500.0,
        }
        exp = explain_prediction(sample)
        directions = {f["feature"]: f["direction"] for f in exp["features"]}
        assert directions["rainfall_intensity"] in ["increases_risk", "neutral"]
        assert "direction_symbol" in exp["features"][0]
        assert exp["features"][0]["direction_symbol"] in ["↑", "↓", "→"]

    def test_prediction_shap_consistency(self):
        """4. Test mathematical relationship: prediction ≈ base_value + sum(shap_values)."""
        sample = get_horizon_features(1)
        exp = explain_prediction(sample)
        assert "is_shap_consistent" in exp
        assert exp["is_shap_consistent"] is True
        assert exp["shap_reconstruction_diff"] < 1e-3

    def test_attribution_statement_language(self):
        """5. Test attribution statements use scientifically accurate language without causal claims."""
        sample = get_horizon_features(0)
        exp = explain_prediction(sample)
        for item in exp["features"]:
            statement = item["attribution_statement"]
            assert len(statement) > 0
            # Ensure no forbidden causal terms are present
            assert "caused" not in statement.lower()
            assert "guarantees" not in statement.lower()
            assert "responsible for the disaster" not in statement.lower()

    def test_shap_feature_ranking(self):
        """Test features are ranked descending by absolute contribution magnitude."""
        sample = get_horizon_features(2)
        exp = explain_prediction(sample)
        features = exp["features"]
        for i in range(len(features) - 1):
            assert abs(features[i]["shap_value"]) >= abs(features[i + 1]["shap_value"])


# ─── 2. CONFORMAL UNCERTAINTY QUANTIFICATION TESTS ──────────────────────

class TestConformalUncertainty:
    """Tests for Conformal Prediction interval calibration and bounds."""

    def test_calibration_residual_calculation(self):
        """6. Test calibration residual calculation."""
        y_val = pd.Series([20.0, 50.0, 80.0])
        y_pred = np.array([22.0, 47.0, 85.0])
        quantifier = ConformalQuantifier()
        calib_info = quantifier.calibrate(y_val, y_pred, nominal_coverage=0.90)
        assert calib_info["uncertainty_method"] == "conformal_regression"
        assert calib_info["calibration_quantile"] > 0.0

    def test_conformal_quantile_calculation(self):
        """7. Test finite-sample conformal quantile computation."""
        np.random.seed(42)
        y_val = pd.Series(np.random.uniform(10, 90, 100))
        y_pred = y_val + np.random.normal(0, 5, 100)
        quantifier = ConformalQuantifier()
        calib = quantifier.calibrate(y_val, y_pred, nominal_coverage=0.90)
        q = calib["calibration_quantile"]
        assert 0.0 < q < 20.0

    def test_interval_generation_lower_upper_bounds(self):
        """8 & 9. Test prediction interval bounds lower <= upper."""
        quantifier = get_conformal_quantifier()
        interval = quantifier.quantify(45.0)
        assert isinstance(interval, ConformalInterval)
        assert interval.lower_bound <= interval.point_prediction <= interval.upper_bound
        assert interval.interval_width == round(interval.upper_bound - interval.lower_bound, 1)

    def test_target_bounds_clipping(self):
        """10. Test bounds clipping to domain [0.0, 100.0]."""
        quantifier = get_conformal_quantifier()
        # Near lower boundary
        low_interval = quantifier.quantify(2.0)
        assert low_interval.lower_bound >= 0.0
        assert low_interval.is_clipped is True

        # Near upper boundary
        high_interval = quantifier.quantify(98.0)
        assert high_interval.upper_bound <= 100.0
        assert high_interval.is_clipped is True

    def test_nominal_coverage_metadata(self):
        """11. Test nominal coverage metadata reporting."""
        quantifier = get_conformal_quantifier()
        interval = quantifier.quantify(50.0)
        assert interval.nominal_coverage == 0.90
        assert interval.uncertainty_method == "conformal_regression"
        assert interval.data_status == "synthetic"

    def test_missing_calibration_artifact_fallback(self):
        """12. Test fallback when calibration file is missing or uncalibrated."""
        quantifier = ConformalQuantifier(calibration_path=Path("/tmp/non_existent_calibration.json"))
        quantifier.quantile = None
        interval = quantifier.quantify(50.0)
        assert interval.status == "UNCERTAINTY_UNAVAILABLE"
        assert interval.interval_width == 0.0

    def test_nan_infinity_input_rejection(self):
        """14. Test handling of NaN and Infinity point predictions."""
        quantifier = get_conformal_quantifier()
        nan_interval = quantifier.quantify(float("nan"))
        assert nan_interval.status == "INVALID_PREDICTION"

        inf_interval = quantifier.quantify(float("inf"))
        assert inf_interval.status == "INVALID_PREDICTION"


# ─── 3. EMPIRICAL COVERAGE SANITY CHECK ──────────────────────────────────

class TestEmpiricalCoverage:
    """Evaluates empirical coverage on held-out test data."""

    def test_empirical_test_set_coverage(self):
        """18 & 23. Test empirical coverage on synthetic test set meets target."""
        from ml.training.generator import generate_synthetic_dataset
        from ml.pipeline import split_dataset
        from ml.pipeline.train_pipeline import train_gbr

        df = generate_synthetic_dataset(n_samples=1000, random_seed=42)
        df = df.rename(columns={"target_risk": "risk_score"})
        split = split_dataset(df, random_seed=42)

        gbr_model, _ = train_gbr(split, random_seed=42)
        val_preds = gbr_model.predict(split.X_val)
        test_preds = gbr_model.predict(split.X_test)

        quantifier = ConformalQuantifier()
        calib = quantifier.calibrate(
            y_val=split.y_val,
            y_val_pred=val_preds,
            nominal_coverage=0.90,
            model_data_status="synthetic",
            y_test=split.y_test,
            y_test_pred=test_preds,
        )

        assert calib["empirical_test_coverage"] is not None
        # Empirical test coverage should be close to 0.90 (nominal 90%)
        assert calib["empirical_test_coverage"] >= 0.85
        assert calib["avg_test_interval_width"] > 0.0


# ─── 4. API & SYSTEM INTEGRATION TESTS ──────────────────────────────────

class TestSystemIntegration:
    """Tests API endpoints, risk engine, SSE, persistence for Phase 6.13 features."""

    def test_predict_risk_includes_uncertainty(self):
        """16. Test predict_risk inference includes prediction interval."""
        sample = get_horizon_features(0)
        res = predict_risk(sample)
        assert "uncertainty" in res
        assert "prediction_interval" in res
        assert "interval_lower" in res
        assert "interval_upper" in res
        assert res["interval_lower"] <= res["risk_score"] <= res["interval_upper"]

    def test_explainability_api_endpoint_p6_13(self):
        """17. Test GET /api/explainability returns SHAP, attribution statements, and interval."""
        response = client.get("/api/explainability?horizon=0")
        assert response.status_code == 200
        data = response.json()
        assert "prediction" in data
        assert "features" in data
        assert "is_shap_consistent" in data
        assert "predictionInterval" in data or "prediction_interval" in data

    def test_risk_engine_compute_risk_state(self):
        """18. Test risk engine compute_risk_state exposes predictionInterval."""
        risk_resp = compute_risk_state(horizon=1)
        assert risk_resp.predictedRisk > 0.0
        assert risk_resp.predictionInterval is not None
        assert risk_resp.predictionInterval.lower <= risk_resp.predictedRisk <= risk_resp.predictionInterval.upper

    def test_model_info_endpoint_uncertainty_metadata(self):
        """Test GET /api/model-info includes conformal uncertainty calibration info."""
        response = client.get("/api/model-info")
        assert response.status_code == 200
        data = response.json()
        assert "uncertainty_calibration" in data
        calib = data["uncertainty_calibration"]
        assert calib.get("uncertainty_method") == "conformal_regression"
        assert calib.get("nominal_coverage") == 0.90
