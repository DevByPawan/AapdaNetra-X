"""
AapdaNetra-X — Risk Engine with ML Inference Integration
Connects backend APIs directly to the scikit-learn GBR model via ml.inference.
Phase 6.1: Routes through DataAdapter for live/hybrid data when configured.
"""
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ml.inference import predict_risk
from ml.features.schema import categorize_risk
from app.models.schemas import SimulationResponse, RiskResponse, HeatmapZone, RiskLevel

# Baseline Real-Time Hydro-Meteorological Features (Yamuna Sector B)
# Canonical values — used as fallback when data_mode='simulated' or provider returns None.
BASE_SENSOR_FEATURES = {
    "rainfall_intensity": 95.0,          # mm/h
    "rainfall_trend": 12.0,              # mm/h² escalation
    "water_level": 6.8,                  # meters
    "water_level_trend": 0.45,           # m/h rising
    "road_congestion": 0.72,             # 72% congestion
    "population_exposure": 12430.0,      # 12,430 people in sector
    "infrastructure_vulnerability": 0.78 # high exposure assets
}

# Horizon progression multipliers for deterministic temporal projection
HORIZON_DELTAS = [
    # Horizon 0: NOW
    {"rainfall_mul": 1.0,  "water_add": 0.0,  "trend_add": 0.0,  "congestion_add": 0.0},
    # Horizon 1: +10 MIN
    {"rainfall_mul": 1.15, "water_add": 0.40, "trend_add": 0.10, "congestion_add": 0.06},
    # Horizon 2: +20 MIN
    {"rainfall_mul": 1.32, "water_add": 0.85, "trend_add": 0.20, "congestion_add": 0.13},
    # Horizon 3: +30 MIN
    {"rainfall_mul": 1.48, "water_add": 1.35, "trend_add": 0.30, "congestion_add": 0.20},
]


def _get_base_features() -> Dict[str, float]:
    """
    Returns the base sensor feature dict.
    Phase 6.1: Routes through DataAdapter when data_mode is 'live' or 'hybrid'.
    When data_mode='simulated' (default), returns BASE_SENSOR_FEATURES unchanged.
    """
    from app.config import settings
    if settings.data_mode == "simulated":
        return dict(BASE_SENSOR_FEATURES)

    try:
        from app.data.providers.data_adapter import get_data_adapter
        adapter = get_data_adapter()
        return adapter.get_base_features()
    except Exception:
        # Fallback to simulated if adapter initialization fails
        return dict(BASE_SENSOR_FEATURES)


def get_horizon_features(horizon_index: int = 0) -> Dict[str, float]:
    """Returns evolved features for a given time horizon index (0=NOW, 1=+10M, 2=+20M, 3=+30M)."""
    idx = max(0, min(3, horizon_index))
    delta = HORIZON_DELTAS[idx]

    features = _get_base_features()
    features["rainfall_intensity"] = min(300.0, features["rainfall_intensity"] * delta["rainfall_mul"])
    features["water_level"] = min(15.0, features["water_level"] + delta["water_add"])
    features["water_level_trend"] = min(5.0, features["water_level_trend"] + delta["trend_add"])
    features["road_congestion"] = min(1.0, features["road_congestion"] + delta["congestion_add"])
    return features


def compute_risk_state(horizon: int = 0) -> RiskResponse:
    """
    Runs ML risk inference for requested horizon and returns populated RiskResponse model.
    """
    now_features = get_horizon_features(0)
    horizon_features = get_horizon_features(horizon)

    now_ml = predict_risk(now_features)
    horizon_ml = predict_risk(horizon_features)

    current_risk = now_ml["risk_score"]
    predicted_risk = horizon_ml["risk_score"]
    category = horizon_ml["risk_category"]
    reliability = horizon_ml["prediction_reliability"]

    labels = ["NOW", "+10 MIN", "+20 MIN", "+30 MIN"]
    label = labels[max(0, min(3, horizon))]

    # Scale heatmap radii dynamically with ML predicted risk
    scale = 0.8 + (predicted_risk / 100.0) * 0.5

    heatmap_zones = [
        HeatmapZone(id="zone-critical", lat=28.6448, lng=77.2167, radiusMeters=round(1100.0 * scale), level="CRITICAL"),
        HeatmapZone(id="zone-high", lat=28.6530, lng=77.2320, radiusMeters=round(1050.0 * scale), level="HIGH"),
        HeatmapZone(id="zone-moderate", lat=28.6310, lng=77.2450, radiusMeters=round(920.0 * scale), level="MODERATE"),
        HeatmapZone(id="zone-low", lat=28.6380, lng=77.2050, radiusMeters=round(800.0 * scale), level="LOW"),
    ]

    trend_str = f"↑ {round(predicted_risk - current_risk, 1)}% / 20 min" if predicted_risk >= current_risk else f"↓ {round(current_risk - predicted_risk, 1)}% / 20 min"

    map_text = (
        f"Critical inundation warning — Risk score {predicted_risk:.1f} ({category})"
        if predicted_risk >= 85
        else f"High-risk flood zone expanding toward Sector B — Score {predicted_risk:.1f} ({category})"
    )

    return RiskResponse(
        index=horizon,
        label=label,
        currentRisk=current_risk,
        predictedRisk=predicted_risk,
        riskCategory=category,
        confidence=reliability,
        predictionReliability=reliability,
        prediction_reliability=reliability,
        affectedPopulation=12430 + horizon * 850,
        criticalPopulation=3180 + horizon * 420,
        criticalAssets=17,
        affectedAssets=4 + horizon * 2,
        trend=trend_str,
        mapStatusText=map_text,
        predictionNote=f"ML GBR Prediction ({label}): Sector B flood risk = {predicted_risk:.1f} ({category}). Reliability = {reliability:.2f}.",
        heatmapZones=heatmap_zones,
    )


def run_simulation_engine(
    evacuationPace: float = 1.0,
    rainfallMultiplier: float = 1.0,
    drainageEfficiency: float = 1.0,
    routeBlockage: bool = False,
    rainfallIncrease: float = 0.0,
    populationMovement: int = 0,
    waterLevelIncrease: float = 0.0,
) -> SimulationResponse:
    """
    Executes counterfactual simulation using the ML GBR model.
    Modifies physical scenario inputs and returns baseline risk, scenario risk, risk delta,
    prediction reliability, and category.
    """
    base_features = _get_base_features()
    baseline_ml = predict_risk(base_features)
    baseline_risk = baseline_ml["risk_score"]

    # Calculate scenario-modified feature vector
    scenario_features = _get_base_features()

    # 1. Modify rainfall intensity & trend
    rf_mult = max(0.1, rainfallMultiplier)
    scenario_features["rainfall_intensity"] = min(
        300.0, base_features["rainfall_intensity"] * rf_mult + rainfallIncrease * 1.2
    )
    scenario_features["rainfall_trend"] = min(
        50.0, base_features["rainfall_trend"] * (1.0 + (rf_mult - 1.0) * 0.5)
    )

    # 2. Modify water level & trend (mitigated by drainage efficiency)
    drain_eff = max(0.1, drainageEfficiency)
    water_add = waterLevelIncrease * 0.15 + (rf_mult - 1.0) * 1.8 / drain_eff
    scenario_features["water_level"] = min(15.0, max(0.0, base_features["water_level"] + water_add))
    
    # Scale water level trend proportionally with rainfall & drainage factor
    wl_trend_add = (rf_mult - 1.0) * 0.50 / drain_eff
    scenario_features["water_level_trend"] = min(
        5.0, max(-2.0, base_features["water_level_trend"] + wl_trend_add + (water_add * 0.15))
    )

    # 3. Modify population exposure & road congestion (impacted by evacuation pace, rainfall & route blockage)
    pace = max(0.3, evacuationPace)
    blockage_factor = 1.35 if routeBlockage else 1.0
    rf_congestion_add = max(0.0, (rf_mult - 1.0) * 0.12)
    scenario_features["road_congestion"] = min(
        1.0, max(0.0, ((base_features["road_congestion"] + rf_congestion_add) * blockage_factor) / pace)
    )
    scenario_features["population_exposure"] = min(
        100000.0, max(0.0, base_features["population_exposure"] + populationMovement)
    )

    # Execute ML inference on scenario features
    scenario_ml = predict_risk(scenario_features)
    scenario_risk = scenario_ml["risk_score"]
    risk_category = scenario_ml["risk_category"]
    reliability = scenario_ml["prediction_reliability"]
    risk_delta = round(scenario_risk - baseline_risk, 1)

    # Execute NetworkX route optimization for scenario
    from ml.routing import optimize_routes
    opt_result = optimize_routes(
        predicted_risk_score=scenario_risk,
        route_blockage=routeBlockage,
        horizon_index=0
    )

    recommended_name = f"Route {opt_result.recommended.name}"
    is_severe = scenario_risk >= 80.0 or routeBlockage or (rf_mult >= 1.4)

    narrative = (
        f"ML simulation predicts risk change of {risk_delta:+.1f} points (Scenario Risk: {scenario_risk:.1f}, {risk_category}). "
        f"{opt_result.route_reason}"
    )

    return SimulationResponse(
        newRisk=scenario_risk,
        baselineRisk=baseline_risk,
        baseline_risk=baseline_risk,
        scenarioRisk=scenario_risk,
        scenario_risk=scenario_risk,
        riskDelta=risk_delta,
        risk_delta=risk_delta,
        riskCategory=risk_category,
        predictionReliability=reliability,
        prediction_reliability=reliability,
        routeRecommendation=recommended_name,
        flaggedAssets=["Bridge-04", "Pump-Station-7"] if is_severe else ["Bridge-04"],
        narrative=narrative,
        severity="SEVERE" if is_severe else ("MODERATE" if scenario_risk >= 50.0 else "MINOR"),
    )
