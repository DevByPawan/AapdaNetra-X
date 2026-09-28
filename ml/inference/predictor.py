"""
AapdaNetra-X — Model-Agnostic Risk Inference Engine
Loads trained model artifact, validates input features, computes normalized risk,
determines risk category, and calculates prediction reliability safely.

Phase 6.12: Model versioning, metadata loading, feature schema validation.
"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import numpy as np
import pandas as pd
import joblib

# Ensure root directory is in sys.path when imported from anywhere
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ml.features.schema import (
    FEATURE_NAMES,
    FEATURE_SPECS,
    categorize_risk,
    validate_and_clean_features,
)

MODELS_DIR = ROOT_DIR / "ml" / "models"
MODEL_PATH = MODELS_DIR / "risk_gbr.joblib"


class RiskPredictor:
    """
    Model-agnostic inference predictor. Encapsulates ML model loading, feature
    transformation, prediction execution, and reliability evaluation.

    Phase 6.12: Now loads model metadata, validates feature schema,
    and exposes model_data_status (synthetic/real/hybrid).
    """

    _instance: Optional["RiskPredictor"] = None

    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or MODEL_PATH
        self.model = None
        self._metadata: Optional[Dict[str, Any]] = None
        self._load_model()
        self._load_metadata()

    def _load_model(self):
        """Loads the trained GBR model artifact from disk, or auto-trains if missing."""
        if os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
            except Exception as e:
                print(f"[RiskPredictor] Warning: Error loading model from {self.model_path}: {e}")
                self.model = None

        if self.model is None:
            print("[RiskPredictor] Model artifact not found or unreadable. Auto-training now...")
            try:
                from ml.training.train import train_and_evaluate
                self.model, _ = train_and_evaluate(n_samples=1000, random_seed=42)
            except Exception as e:
                print(f"[RiskPredictor] Error auto-training model: {e}")

    def _load_metadata(self):
        """Loads model metadata JSON if available. Validates feature schema compatibility."""
        metadata_path = self.model_path.parent / "model_metadata.json" if isinstance(self.model_path, Path) else Path(str(self.model_path)).parent / "model_metadata.json"
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, "r") as f:
                    self._metadata = json.load(f)
                # Validate feature schema compatibility
                model_features = self._metadata.get("feature_names") or self._metadata.get("features", [])
                if model_features and model_features != FEATURE_NAMES:
                    print(
                        f"[RiskPredictor] WARNING: Feature schema mismatch. "
                        f"Model expects {model_features}, pipeline uses {FEATURE_NAMES}"
                    )
            except Exception as e:
                print(f"[RiskPredictor] Warning: Could not load metadata: {e}")
                self._metadata = None
        else:
            self._metadata = None

    @property
    def model_data_status(self) -> str:
        """Returns the training data status: synthetic, real, hybrid, or unavailable."""
        if self._metadata:
            return self._metadata.get("model_data_status", "synthetic")
        return "synthetic"

    @property
    def model_version(self) -> str:
        """Returns the model version string."""
        if self._metadata:
            return self._metadata.get("model_version", "0.1.0")
        return "0.1.0"

    @property
    def model_info(self) -> Dict[str, Any]:
        """Returns a summary of the loaded model for API/observability."""
        from ml.uncertainty import get_conformal_quantifier
        quantifier = get_conformal_quantifier()
        calib_data = quantifier.calibration_data or {
            "uncertainty_method": "conformal_regression",
            "nominal_coverage": 0.90,
            "data_status": self.model_data_status,
        }
        return {
            "model_name": "GradientBoostingRegressor",
            "model_version": self.model_version,
            "model_data_status": self.model_data_status,
            "feature_schema_version": self._metadata.get("feature_schema_version", "1.0.0") if self._metadata else "1.0.0",
            "training_timestamp": self._metadata.get("training_timestamp", "") if self._metadata else "",
            "training_dataset": self._metadata.get("training_dataset", "synthetic_1000") if self._metadata else "synthetic_1000",
            "uncertainty_calibration": calib_data,
            "disclaimer": self._metadata.get("disclaimer", "Model trained on synthetic data. Not validated for real-world deployment.") if self._metadata else "Model trained on synthetic data. Not validated for real-world deployment.",
        }

    def predict(self, raw_features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes ML risk inference.
        Returns:
          {
            "risk_score": float (0.0 to 100.0),
            "risk_category": str ("LOW" | "MODERATE" | "HIGH" | "CRITICAL"),
            "prediction_reliability": float (0.0 to 1.0),
            "cleaned_features": dict
          }
        """
        # 1. Validate and clean input features
        cleaned = validate_and_clean_features(raw_features)

        # 2. Extract ordered feature DataFrame matching trained feature names
        df_vector = pd.DataFrame([cleaned])[FEATURE_NAMES]

        # 3. Model inference
        if self.model is not None:
            try:
                raw_pred = float(self.model.predict(df_vector)[0])
            except Exception as e:
                print(f"[RiskPredictor] Inference exception: {e}, using heuristic fallback.")
                raw_pred = self._heuristic_fallback(cleaned)
        else:
            raw_pred = self._heuristic_fallback(cleaned)

        risk_score = round(float(np.clip(raw_pred, 0.0, 100.0)), 1)
        risk_category = categorize_risk(risk_score)

        # 4. Calculate prediction reliability deterministically
        reliability = self._calculate_reliability(raw_features, cleaned)

        # 5. Compute split-conformal prediction interval
        from ml.uncertainty import quantify_uncertainty
        interval = quantify_uncertainty(risk_score)
        uncertainty_dict = interval.to_dict()

        return {
            "risk_score": risk_score,
            "risk_category": risk_category,
            "prediction_reliability": reliability,
            "cleaned_features": cleaned,
            "model_data_status": self.model_data_status,
            "model_version": self.model_version,
            "uncertainty": uncertainty_dict,
            "prediction_interval": [interval.lower_bound, interval.upper_bound],
            "interval_lower": interval.lower_bound,
            "interval_upper": interval.upper_bound,
            "nominal_coverage": interval.nominal_coverage,
        }

    def _heuristic_fallback(self, cleaned: Dict[str, float]) -> float:
        """Deterministic heuristic fallback if model inference fails."""
        w_lvl = cleaned.get("water_level", 4.0)
        r_int = cleaned.get("rainfall_intensity", 40.0)
        return float(np.clip(35.0 * (w_lvl / 10.0) + 25.0 * (r_int / 150.0) + 20.0, 0.0, 100.0))

    def _calculate_reliability(self, raw_features: Dict[str, Any], cleaned: Dict[str, float]) -> float:
        """
        Calculates prediction reliability (0.00 to 1.00) based on:
        1. Feature completeness (penalty if raw features were missing or defaulted).
        2. Feature boundary closeness (penalty if inputs were clipped at extreme boundaries).
        """
        if not isinstance(raw_features, dict):
            raw_features = {}

        present_count = sum(1 for name in FEATURE_NAMES if raw_features.get(name) is not None)
        completeness_ratio = present_count / len(FEATURE_NAMES)

        # Boundary penalty
        boundary_penalties = 0.0
        for name in FEATURE_NAMES:
            spec = FEATURE_SPECS[name]
            val = cleaned[name]
            # Near absolute boundary check
            rng = spec["max"] - spec["min"]
            if rng > 0:
                dist_to_edge = min(abs(val - spec["min"]), abs(val - spec["max"]))
                if dist_to_edge / rng < 0.02:
                    boundary_penalties += 0.05

        reliability = max(0.50, min(0.98, completeness_ratio * 0.95 - boundary_penalties))
        return round(float(reliability), 2)


# Global singleton instance & convenience function
_global_predictor: Optional[RiskPredictor] = None


def get_predictor() -> RiskPredictor:
    global _global_predictor
    if _global_predictor is None:
        _global_predictor = RiskPredictor()
    return _global_predictor


def predict_risk(features: Dict[str, Any]) -> Dict[str, Any]:
    """Model-agnostic public inference API."""
    return get_predictor().predict(features)
