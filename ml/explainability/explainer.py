"""
AapdaNetra-X — Explainable AI (SHAP) Service
Computes real SHAP feature attributions for GradientBoostingRegressor predictions.
"""
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
import shap
import joblib

# Ensure root workspace directory is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ml.features.schema import FEATURE_NAMES, validate_and_clean_features
from ml.inference.predictor import get_predictor

MODELS_DIR = ROOT_DIR / "ml" / "models"
MODEL_PATH = MODELS_DIR / "risk_gbr.joblib"

# Professional Emergency-Management Feature Labels
FEATURE_LABEL_MAP = {
    "rainfall_intensity": "Rainfall Intensity",
    "rainfall_trend": "Rainfall Trend",
    "water_level": "Water Level",
    "water_level_trend": "Water-Level Trend",
    "road_congestion": "Congestion Exposure",
    "population_exposure": "Population Exposure",
    "infrastructure_vulnerability": "Infrastructure Vulnerability",
}


class SHAPExplainer:
    """
    SHAP Explainability service using shap.TreeExplainer on the trained GBR model.
    """

    _instance: Optional["SHAPExplainer"] = None

    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or MODEL_PATH
        self.explainer: Optional[shap.TreeExplainer] = None
        self.model = None
        self._init_explainer()

    def _init_explainer(self):
        """Initializes TreeExplainer with pre-trained GBR model artifact."""
        predictor = get_predictor()
        if predictor.model is not None:
            self.model = predictor.model
        elif os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
            except Exception as e:
                print(f"[SHAPExplainer] Failed loading model from {self.model_path}: {e}")

        if self.model is not None:
            try:
                self.explainer = shap.TreeExplainer(self.model)
            except Exception as e:
                print(f"[SHAPExplainer] Failed initializing TreeExplainer: {e}")

    def explain(self, raw_features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes SHAP feature attribution calculation.
        Returns:
          {
            "prediction": float,
            "base_value": float,
            "total_shap_delta": float,
            "features": list of feature attribution dicts sorted by absolute impact,
            "decision_trace": list of formatted trace dicts for UI panel
          }
        """
        cleaned = validate_and_clean_features(raw_features)
        df_vector = pd.DataFrame([cleaned])[FEATURE_NAMES]

        if self.explainer is None:
            self._init_explainer()

        if self.explainer is not None and self.model is not None:
            try:
                raw_pred = float(self.model.predict(df_vector)[0])
                shap_raw = self.explainer.shap_values(df_vector)

                # Handle single-sample SHAP output array shapes
                if isinstance(shap_raw, list):
                    shap_arr = shap_raw[0][0]
                elif shap_raw.ndim == 2:
                    shap_arr = shap_raw[0]
                else:
                    shap_arr = shap_raw

                expected_val = float(
                    self.explainer.expected_value[0]
                    if isinstance(self.explainer.expected_value, (list, np.ndarray))
                    else self.explainer.expected_value
                )
            except Exception as e:
                print(f"[SHAPExplainer] SHAP computation exception: {e}")
                return self._fallback_explanation(cleaned)
        else:
            return self._fallback_explanation(cleaned)

        prediction = round(float(np.clip(raw_pred, 0.0, 100.0)), 1)
        base_value = round(float(expected_val), 1)

        # Calculate relative contribution percentages based on total absolute SHAP magnitude
        abs_sum = float(np.sum(np.abs(shap_arr)))
        if abs_sum <= 1e-6:
            abs_sum = 1.0

        feature_items = []
        for i, name in enumerate(FEATURE_NAMES):
            s_val = float(shap_arr[i])
            pct = round((abs(s_val) / abs_sum) * 100.0, 1)
            direction = (
                "increases_risk" if s_val > 0.01
                else ("decreases_risk" if s_val < -0.01 else "neutral")
            )
            direction_symbol = "↑" if s_val > 0.01 else ("↓" if s_val < -0.01 else "→")

            feature_items.append({
                "feature": name,
                "label": FEATURE_LABEL_MAP.get(name, name),
                "shap_value": round(s_val, 3),
                "direction": direction,
                "direction_symbol": direction_symbol,
                "contribution_percent": pct,
                "formatted_contribution": f"{direction_symbol} {pct:.0f}%" if direction != "neutral" else f"{pct:.0f}%",
                "raw_value": cleaned[name],
            })

        # Rank features descending by absolute SHAP contribution
        sorted_features = sorted(feature_items, key=lambda x: abs(x["shap_value"]), reverse=True)

        # Format decision trace array for frontend UI compatibility
        decision_trace = [
            {
                "factor": item["label"],
                "contribution": item["formatted_contribution"],
                "direction": item["direction"],
                "percent": item["contribution_percent"],
                "shapValue": item["shap_value"],
            }
            for item in sorted_features
        ]

        return {
            "prediction": prediction,
            "base_value": base_value,
            "total_shap_delta": round(prediction - base_value, 1),
            "features": sorted_features,
            "decision_trace": decision_trace,
        }

    def _fallback_explanation(self, cleaned: Dict[str, float]) -> Dict[str, Any]:
        """Fallback explanation if SHAP calculation fails."""
        items = []
        for name in FEATURE_NAMES:
            val = cleaned[name]
            items.append({
                "feature": name,
                "label": FEATURE_LABEL_MAP.get(name, name),
                "shap_value": 0.0,
                "direction": "neutral",
                "direction_symbol": "→",
                "contribution_percent": 14.3,
                "formatted_contribution": "14%",
                "raw_value": val,
            })
        return {
            "prediction": 50.0,
            "base_value": 50.0,
            "total_shap_delta": 0.0,
            "features": items,
            "decision_trace": [{"factor": item["label"], "contribution": item["formatted_contribution"]} for item in items],
        }


# Global singleton instance & convenience helper
_global_explainer: Optional[SHAPExplainer] = None


def get_explainer() -> SHAPExplainer:
    global _global_explainer
    if _global_explainer is None:
        _global_explainer = SHAPExplainer()
    return _global_explainer


def explain_prediction(raw_features: Dict[str, Any]) -> Dict[str, Any]:
    """Public helper function to explain a feature dict."""
    return get_explainer().explain(raw_features)
