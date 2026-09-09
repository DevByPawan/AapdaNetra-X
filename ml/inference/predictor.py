"""
AapdaNetra-X — Model-Agnostic Risk Inference Engine
Loads trained model artifact, validates input features, computes normalized risk,
determines risk category, and calculates prediction reliability safely.
"""
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
    """

    _instance: Optional["RiskPredictor"] = None

    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or MODEL_PATH
        self.model = None
        self._load_model()

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

        return {
            "risk_score": risk_score,
            "risk_category": risk_category,
            "prediction_reliability": reliability,
            "cleaned_features": cleaned,
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
