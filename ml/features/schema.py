"""
AapdaNetra-X ML Risk Engine — Feature Definitions & Risk Thresholds
"""
from typing import Dict, Any

# Centralized Risk Thresholds
RISK_THRESHOLDS = {
    "LOW": (0.0, 30.0),
    "MODERATE": (30.0, 60.0),
    "HIGH": (60.0, 85.0),
    "CRITICAL": (85.0, 100.0),
}

FEATURE_SPECS = {
    "rainfall_intensity": {"min": 0.0, "max": 300.0, "default": 45.0, "type": float, "unit": "mm/h"},
    "rainfall_trend": {"min": -50.0, "max": 50.0, "default": 5.0, "type": float, "unit": "mm/h²"},
    "water_level": {"min": 0.0, "max": 15.0, "default": 4.2, "type": float, "unit": "m"},
    "water_level_trend": {"min": -2.0, "max": 5.0, "default": 0.3, "type": float, "unit": "m/h"},
    "road_congestion": {"min": 0.0, "max": 1.0, "default": 0.65, "type": float, "unit": "ratio"},
    "population_exposure": {"min": 0.0, "max": 100000.0, "default": 12430.0, "type": float, "unit": "count"},
    "infrastructure_vulnerability": {"min": 0.0, "max": 1.0, "default": 0.72, "type": float, "unit": "ratio"},
}

FEATURE_NAMES = list(FEATURE_SPECS.keys())


def categorize_risk(score: float) -> str:
    """Categorize risk score into LOW, MODERATE, HIGH, CRITICAL based on centralized thresholds."""
    val = max(0.0, min(100.0, float(score)))
    if val < RISK_THRESHOLDS["LOW"][1]:
        return "LOW"
    elif val < RISK_THRESHOLDS["MODERATE"][1]:
        return "MODERATE"
    elif val < RISK_THRESHOLDS["HIGH"][1]:
        return "HIGH"
    else:
        return "CRITICAL"


def validate_and_clean_features(raw_features: Dict[str, Any]) -> Dict[str, float]:
    """
    Validates input features dict, converts to float, fills missing fields with defaults,
    and clips extreme out-of-bounds values safely.
    """
    cleaned = {}
    if not isinstance(raw_features, dict):
        raw_features = {}

    for name, spec in FEATURE_SPECS.items():
        val = raw_features.get(name)
        if val is None:
            cleaned[name] = float(spec["default"])
        else:
            try:
                val_float = float(val)
                # Clip extreme out-of-bounds inputs safely
                clipped = max(spec["min"], min(spec["max"], val_float))
                cleaned[name] = clipped
            except (ValueError, TypeError):
                cleaned[name] = float(spec["default"])
    return cleaned
