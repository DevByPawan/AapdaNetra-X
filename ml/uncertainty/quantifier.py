"""
AapdaNetra-X — Conformal Prediction Uncertainty Quantifier
Phase 6.13: Scientifically defensible regression prediction intervals using split-conformal prediction.

Answers: "How uncertain is the risk prediction?"
Maintains complete separation from SHAP feature explainability.
"""
import json
import math
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import pandas as pd

# Ensure root workspace directory is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

MODELS_DIR = ROOT_DIR / "ml" / "models"
CALIBRATION_PATH = MODELS_DIR / "conformal_calibration.json"


@dataclass
class ConformalInterval:
    """Represents a split-conformal prediction interval for a risk score."""
    point_prediction: float
    lower_bound: float
    upper_bound: float
    interval_width: float
    nominal_coverage: float
    uncertainty_method: str = "conformal_regression"
    data_status: str = "synthetic"
    status: str = "AVAILABLE"
    is_clipped: bool = False
    unclipped_lower: float = 0.0
    unclipped_upper: float = 0.0
    calibration_quantile: float = 0.0
    disclaimer: str = "Prediction interval calibrated on synthetic data under split-conformal assumptions."

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConformalQuantifier:
    """
    Split-conformal prediction interval calculator.

    Phase 6.13:
    1. Calibrates conformal score quantile q on calibration split (validation set).
    2. Computes distribution-free prediction intervals [y_hat - q, y_hat + q].
    3. Handles boundary clipping to target domain [0, 100] with full audit trail.
    4. Evaluates empirical coverage on held-out test sets.
    """

    _instance: Optional["ConformalQuantifier"] = None

    def __init__(self, calibration_path: Optional[Path] = None):
        self.calibration_path = calibration_path or CALIBRATION_PATH
        self.calibration_data: Optional[Dict[str, Any]] = None
        self.quantile: Optional[float] = None
        self.nominal_coverage: float = 0.90
        self.data_status: str = "synthetic"
        self._load_calibration()

    def _load_calibration(self):
        """Loads calibration metadata and quantile from disk if available."""
        if os.path.exists(self.calibration_path):
            try:
                with open(self.calibration_path, "r") as f:
                    self.calibration_data = json.load(f)
                self.quantile = float(self.calibration_data.get("calibration_quantile", 0.0))
                self.nominal_coverage = float(self.calibration_data.get("nominal_coverage", 0.90))
                self.data_status = str(self.calibration_data.get("model_data_status", "synthetic"))
            except Exception as e:
                print(f"[ConformalQuantifier] Warning loading calibration from {self.calibration_path}: {e}")
                self.calibration_data = None
                self.quantile = None

    def calibrate(
        self,
        y_val: pd.Series,
        y_val_pred: np.ndarray,
        nominal_coverage: float = 0.90,
        model_data_status: str = "synthetic",
        y_test: Optional[pd.Series] = None,
        y_test_pred: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Calibrates the conformal prediction interval on calibration data (y_val, y_val_pred).

        Args:
            y_val: Ground truth target values for calibration set
            y_val_pred: Model predictions on calibration set
            nominal_coverage: Target coverage probability 1 - alpha (e.g. 0.90 for 90%)
            model_data_status: Provenance status of training data ("synthetic" / "real" / "hybrid")
            y_test: Optional test set target values for empirical coverage verification
            y_test_pred: Optional test set model predictions for empirical coverage verification
        """
        if len(y_val) == 0 or len(y_val_pred) == 0 or len(y_val) != len(y_val_pred):
            raise ValueError("Calibration inputs y_val and y_val_pred must be non-empty and equal length.")

        alpha = 1.0 - nominal_coverage
        residuals = np.abs(np.array(y_val) - np.clip(np.array(y_val_pred), 0.0, 100.0))
        n_cal = len(residuals)

        # Finite-sample conformal quantile: k = ceil((n + 1) * (1 - alpha))
        k = int(np.ceil((n_cal + 1) * (1.0 - alpha)))
        k = max(1, min(n_cal, k))
        sorted_residuals = np.sort(residuals)
        q = float(sorted_residuals[k - 1])

        # Calculate empirical test coverage if test data provided
        empirical_test_coverage = None
        avg_test_width = None
        if y_test is not None and y_test_pred is not None and len(y_test) > 0:
            y_t = np.array(y_test)
            y_tp = np.clip(np.array(y_test_pred), 0.0, 100.0)
            lowers = np.maximum(0.0, y_tp - q)
            uppers = np.minimum(100.0, y_tp + q)
            covered = (y_t >= lowers) & (y_t <= uppers)
            empirical_test_coverage = round(float(np.mean(covered)), 4)
            avg_test_width = round(float(np.mean(uppers - lowers)), 4)

        self.quantile = q
        self.nominal_coverage = nominal_coverage
        self.data_status = model_data_status

        calibration_info = {
            "uncertainty_method": "conformal_regression",
            "uncertainty_version": "1.0.0",
            "nominal_coverage": nominal_coverage,
            "calibration_dataset": "validation_split",
            "calibration_rows": n_cal,
            "calibration_quantile": round(q, 4),
            "empirical_val_mae": round(float(np.mean(residuals)), 4),
            "empirical_test_coverage": empirical_test_coverage,
            "avg_test_interval_width": avg_test_width,
            "target_bounds": [0.0, 100.0],
            "model_data_status": model_data_status,
            "synthetic_disclaimer": (
                "Prediction interval calibrated on synthetic validation data. "
                "Empirical coverage reflects synthetic data distribution."
                if model_data_status == "synthetic"
                else "Prediction interval calibrated on real observed validation data."
            ),
        }

        self.calibration_data = calibration_info
        self._save_calibration()
        return calibration_info

    def _save_calibration(self):
        """Saves calibration JSON to disk."""
        if self.calibration_data and self.calibration_path:
            self.calibration_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.calibration_path, "w") as f:
                json.dump(self.calibration_data, f, indent=2)

    def quantify(self, point_prediction: float) -> ConformalInterval:
        """
        Computes split-conformal prediction interval for a given point prediction.

        Args:
            point_prediction: Float risk score prediction (0.0 to 100.0)

        Returns:
            ConformalInterval dataclass instance
        """
        # Edge case check: missing or invalid calibration
        if self.quantile is None or not math.isfinite(self.quantile):
            self._load_calibration()

        if self.quantile is None or not math.isfinite(self.quantile):
            return ConformalInterval(
                point_prediction=point_prediction,
                lower_bound=point_prediction,
                upper_bound=point_prediction,
                interval_width=0.0,
                nominal_coverage=self.nominal_coverage,
                status="UNCERTAINTY_UNAVAILABLE",
                disclaimer="Conformal calibration artifact is missing or uncalibrated.",
            )

        # Validate input point prediction
        if not math.isfinite(point_prediction):
            return ConformalInterval(
                point_prediction=0.0,
                lower_bound=0.0,
                upper_bound=0.0,
                interval_width=0.0,
                nominal_coverage=self.nominal_coverage,
                status="INVALID_PREDICTION",
                disclaimer="Point prediction is NaN or non-finite.",
            )

        unclipped_lower = point_prediction - self.quantile
        unclipped_upper = point_prediction + self.quantile

        # Enforce target domain bounds [0.0, 100.0] with clipping flag
        lower = round(float(max(0.0, unclipped_lower)), 1)
        upper = round(float(min(100.0, unclipped_upper)), 1)

        is_clipped = (unclipped_lower < 0.0) or (unclipped_upper > 100.0)
        width = round(upper - lower, 1)

        return ConformalInterval(
            point_prediction=round(point_prediction, 1),
            lower_bound=lower,
            upper_bound=upper,
            interval_width=width,
            nominal_coverage=self.nominal_coverage,
            uncertainty_method="conformal_regression",
            data_status=self.data_status,
            status="AVAILABLE",
            is_clipped=is_clipped,
            unclipped_lower=round(unclipped_lower, 2),
            unclipped_upper=round(unclipped_upper, 2),
            calibration_quantile=round(self.quantile, 2),
            disclaimer=(
                f"{self.nominal_coverage * 100:.0f}% conformal prediction interval "
                f"calibrated on {self.data_status} data."
            ),
        )


# Global singleton instance
_global_quantifier: Optional[ConformalQuantifier] = None


def get_conformal_quantifier() -> ConformalQuantifier:
    global _global_quantifier
    if _global_quantifier is None:
        _global_quantifier = ConformalQuantifier()
    return _global_quantifier


def quantify_uncertainty(point_prediction: float) -> ConformalInterval:
    """Public helper function to quantify uncertainty for a prediction."""
    return get_conformal_quantifier().quantify(point_prediction)
