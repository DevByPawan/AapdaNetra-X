"""
AapdaNetra-X — Advanced What-If Scenario Analysis Engine

Phase 6.16: Deterministic, reproducible, explainable scenario-analysis engine.
Compares simulated scenario against baseline state without mutating live telemetry,
current risk state, live routing, or real alert streams.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.schemas import RiskLevel, SimulationRequest, SimulationResponse
from ml.explainability import get_explainer
from ml.features.schema import FEATURE_NAMES, FEATURE_SPECS, categorize_risk, validate_and_clean_features
from ml.inference import get_predictor, predict_risk
from ml.routing import optimize_routes
from ml.uncertainty import get_conformal_quantifier

logger = logging.getLogger("aapdanetra.scenario_service")


def compute_scenario_fingerprint(
    baseline_features: Dict[str, float],
    scenario_params: Dict[str, Any],
    model_version: str = "v1.0.0",
) -> str:
    """
    Computes a deterministic SHA-256 fingerprint for a scenario run.
    Ensures identical baseline + identical parameters produce identical fingerprint.
    """
    clean_baseline = {k: round(float(baseline_features[k]), 4) for k in sorted(baseline_features.keys())}
    clean_params = {}
    for k in sorted(scenario_params.keys()):
        val = scenario_params[k]
        if isinstance(val, float):
            clean_params[k] = round(val, 4)
        else:
            clean_params[k] = val

    payload = {
        "model_version": model_version,
        "baseline_features": clean_baseline,
        "scenario_params": clean_params,
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def transform_baseline_features(
    base_features: Dict[str, float],
    params: SimulationRequest,
) -> Dict[str, float]:
    """
    Deterministically transforms baseline features using scenario input parameters.
    Maintains 7 ML feature schema and respects feature bounds.
    """
    scenario_features = dict(base_features)

    rf_mult = max(0.1, params.rainfallMultiplier)
    drain_eff = max(0.1, params.drainageEfficiency)
    pace = max(0.3, params.evacuationPace)
    blockage_factor = 1.35 if params.routeBlockage else 1.0

    # 1. Modify rainfall intensity & trend
    rf_intensity = base_features["rainfall_intensity"] * rf_mult + params.rainfallIncrease * 1.2
    rf_trend = base_features["rainfall_trend"] * (1.0 + (rf_mult - 1.0) * 0.5)
    scenario_features["rainfall_intensity"] = rf_intensity
    scenario_features["rainfall_trend"] = rf_trend

    # 2. Modify water level & trend (mitigated by drainage efficiency)
    water_add = params.waterLevelIncrease * 0.15 + (rf_mult - 1.0) * 1.8 / drain_eff
    wl_trend_add = (rf_mult - 1.0) * 0.50 / drain_eff
    scenario_features["water_level"] = base_features["water_level"] + water_add
    scenario_features["water_level_trend"] = base_features["water_level_trend"] + wl_trend_add + (water_add * 0.15)

    # 3. Modify road congestion & population exposure
    rf_congestion_add = max(0.0, (rf_mult - 1.0) * 0.12)
    scenario_features["road_congestion"] = ((base_features["road_congestion"] + rf_congestion_add) * blockage_factor) / pace
    scenario_features["population_exposure"] = base_features["population_exposure"] + params.populationMovement

    # Clean and clip to canonical ML schema bounds
    return validate_and_clean_features(scenario_features)


def evaluate_scenario_alerts(
    incident_id: str,
    baseline_features: Dict[str, float],
    scenario_features: Dict[str, float],
    baseline_risk: float,
    scenario_risk: float,
    baseline_unc: Dict[str, Any],
    scenario_unc: Dict[str, Any],
    baseline_spatial: Dict[str, Any],
    scenario_spatial: Dict[str, Any],
    route_blockage: bool,
) -> Dict[str, Any]:
    """
    Evaluates hypothetical alerts for scenario state without mutating live alert store.
    All alerts are explicitly tagged SIMULATION / SCENARIO ONLY.
    """
    from app.services.alert_engine import IntelligentAlertEngine

    engine = IntelligentAlertEngine()

    baseline_alert_records = engine.evaluate_all_rules(
        incident_id=incident_id,
        predicted_risk=baseline_risk,
        current_risk=baseline_risk,
        uncertainty=baseline_unc,
        telemetry_features=baseline_features,
        spatial_exposure=baseline_spatial,
        route_blockage=False,
    )

    scenario_alert_records = engine.evaluate_all_rules(
        incident_id=incident_id,
        predicted_risk=scenario_risk,
        current_risk=baseline_risk,
        uncertainty=scenario_unc,
        telemetry_features=scenario_features,
        spatial_exposure=scenario_spatial,
        route_blockage=route_blockage,
    )

    baseline_sigs = {f"{a.alert_type}:{a.signature}": a for a in baseline_alert_records}
    scenario_sigs = {f"{a.alert_type}:{a.signature}": a for a in scenario_alert_records}

    simulated_alerts = []
    newly_triggered_count = 0
    severity_changes_count = 0
    resolved_count = 0

    for sig, s_rec in scenario_sigs.items():
        impact = "SIMULATED_ACTIVE"
        if sig not in baseline_sigs:
            impact = "NEWLY_TRIGGERED"
            newly_triggered_count += 1
        elif baseline_sigs[sig].severity != s_rec.severity:
            impact = f"SEVERITY_CHANGED_{baseline_sigs[sig].severity}_TO_{s_rec.severity}"
            severity_changes_count += 1

        simulated_alerts.append({
            "id": f"sim-alt-{s_rec.id}",
            "title": f"[SIMULATION] {s_rec.title}",
            "description": f"{s_rec.description} (Hypothetical scenario evaluation)",
            "severity": s_rec.severity,
            "alert_type": s_rec.alert_type,
            "impact_type": impact,
            "simulation_only": True,
            "status": "SCENARIO_ONLY",
        })

    for sig, b_rec in baseline_sigs.items():
        if sig not in scenario_sigs:
            resolved_count += 1
            simulated_alerts.append({
                "id": f"sim-alt-res-{b_rec.id}",
                "title": f"[SIMULATION RESOLVED] {b_rec.title}",
                "description": "Alert condition would resolve under simulated scenario conditions.",
                "severity": b_rec.severity,
                "alert_type": b_rec.alert_type,
                "impact_type": "RESOLVED_UNDER_SCENARIO",
                "simulation_only": True,
                "status": "SCENARIO_ONLY",
            })

    return {
        "baseline_active_alerts_count": len(baseline_alert_records),
        "scenario_triggered_alerts": simulated_alerts,
        "newly_triggered_count": newly_triggered_count,
        "severity_changes_count": severity_changes_count,
        "resolved_alerts_count": resolved_count,
        "notice": "SIMULATION ONLY — Scenario alerts are hypothetical and do not affect live alert streams.",
    }


def execute_scenario_analysis(
    request: SimulationRequest,
    incident_id: str = "INC-2026-DEFAULT",
) -> SimulationResponse:
    """
    Executes a complete counterfactual scenario analysis.
    Produces deterministic baseline vs scenario comparison.
    """
    from app.services.risk_engine import _get_base_features

    # 1. Capture baseline state
    base_features = _get_base_features()
    baseline_ml = predict_risk(base_features)
    baseline_risk = float(baseline_ml["risk_score"])
    baseline_category = str(baseline_ml["risk_category"])

    # Baseline conformal uncertainty
    quantifier = get_conformal_quantifier()
    baseline_unc_obj = quantifier.quantify(baseline_risk)
    baseline_unc = {
        "lower_bound": baseline_unc_obj.lower_bound,
        "upper_bound": baseline_unc_obj.upper_bound,
        "nominal_coverage": baseline_unc_obj.nominal_coverage,
        "uncertainty_method": baseline_unc_obj.uncertainty_method,
    }

    # Baseline SHAP attributions
    explainer = get_explainer()
    baseline_shap_raw = explainer.explain(base_features)

    # Baseline route & spatial evaluation
    baseline_route_opt = optimize_routes(
        predicted_risk_score=baseline_risk,
        route_blockage=False,
        horizon_index=0,
    )
    
    from app.services.spatial_service import get_spatial_service
    spatial_svc = get_spatial_service()
    
    baseline_waypoints = [
        {"lat": wp.lat, "lng": wp.lng} for wp in baseline_route_opt.recommended.waypoints
    ]
    baseline_spatial = spatial_svc.calculate_route_spatial_hazard(
        waypoints=baseline_waypoints,
        base_safety_score=baseline_route_opt.recommended.safetyScore,
    )

    # 2. Derive scenario state
    scenario_features = transform_baseline_features(base_features, request)

    # 3. ML Scenario Inference & Reliability
    scenario_ml = predict_risk(scenario_features)
    scenario_risk = float(scenario_ml["risk_score"])
    scenario_category = str(scenario_ml["risk_category"])
    reliability = float(scenario_ml["prediction_reliability"])
    raw_ver = str(scenario_ml.get("model_version", "1.0.0")).lstrip("v")
    model_version = f"v{raw_ver}"
    model_status = str(scenario_ml.get("model_data_status", "synthetic"))

    risk_delta = round(scenario_risk - baseline_risk, 1)
    risk_delta_pct = round((risk_delta / baseline_risk) * 100, 1) if baseline_risk > 0 else 0.0

    # Scenario conformal uncertainty
    scenario_unc_obj = quantifier.quantify(scenario_risk)
    scenario_unc = {
        "lower_bound": scenario_unc_obj.lower_bound,
        "upper_bound": scenario_unc_obj.upper_bound,
        "nominal_coverage": scenario_unc_obj.nominal_coverage,
        "uncertainty_method": scenario_unc_obj.uncertainty_method,
    }

    # Scenario SHAP attributions
    scenario_shap_raw = explainer.explain(scenario_features)

    # Calculate SHAP feature attribution shifts ("model attribution changed")
    shap_attribution_changes = []
    base_shap_dict = {
        item["feature"]: float(item["shap_value"])
        for item in baseline_shap_raw.get("features", [])
        if isinstance(item, dict) and "feature" in item
    }
    scen_shap_dict = {
        item["feature"]: float(item["shap_value"])
        for item in scenario_shap_raw.get("features", [])
        if isinstance(item, dict) and "feature" in item
    }

    for fname in FEATURE_NAMES:
        b_val = float(base_shap_dict.get(fname, 0.0))
        s_val = float(scen_shap_dict.get(fname, 0.0))
        shift = round(s_val - b_val, 3)
        shap_attribution_changes.append({
            "feature": fname,
            "baseline_value": base_features.get(fname, 0.0),
            "simulated_value": scenario_features.get(fname, 0.0),
            "baseline_shap": round(b_val, 3),
            "scenario_shap": round(s_val, 3),
            "shap_attribution_change": shift,
            "direction": "positive" if s_val >= 0 else "negative",
            "explanation": f"Model attribution changed by {shift:+.3f} points for {fname}",
        })

    # Sort attribution changes by absolute magnitude of shift
    shap_attribution_changes.sort(key=lambda x: abs(x["shap_attribution_change"]), reverse=True)

    # 4. Scenario Routing & Spatial Impact
    scenario_route_opt = optimize_routes(
        predicted_risk_score=scenario_risk,
        route_blockage=request.routeBlockage,
        horizon_index=0,
    )

    scenario_waypoints = [
        {"lat": wp.lat, "lng": wp.lng} for wp in scenario_route_opt.recommended.waypoints
    ]
    scenario_spatial = spatial_svc.calculate_route_spatial_hazard(
        waypoints=scenario_waypoints,
        base_safety_score=scenario_route_opt.recommended.safetyScore,
    )

    b_safety = float(baseline_spatial.get("modeled_safety_score", baseline_route_opt.recommended.safetyScore))
    s_safety = float(scenario_spatial.get("modeled_safety_score", scenario_route_opt.recommended.safetyScore))

    b_exp = float(baseline_spatial.get("spatial_exposure_ratio", 0.0))
    s_exp = float(scenario_spatial.get("spatial_exposure_ratio", 0.0))

    eta_delta = round(scenario_route_opt.recommended.eta - baseline_route_opt.recommended.eta, 1)
    safety_delta = round(s_safety - b_safety, 3)
    spatial_exposure_delta = round(s_exp - b_exp, 3)
    route_changed = (baseline_route_opt.recommended.id != scenario_route_opt.recommended.id) or request.routeBlockage

    route_change_reason = (
        f"Route recommendation changed from {baseline_route_opt.recommended.name} to {scenario_route_opt.recommended.name} "
        f"due to simulated risk/blockage conditions."
        if route_changed else
        f"Route {scenario_route_opt.recommended.name} remains optimal under simulated conditions."
    )

    # 5. Alert Impact (Scenario-Only)
    alert_impact = evaluate_scenario_alerts(
        incident_id=incident_id,
        baseline_features=base_features,
        scenario_features=scenario_features,
        baseline_risk=baseline_risk,
        scenario_risk=scenario_risk,
        baseline_unc=baseline_unc,
        scenario_unc=scenario_unc,
        baseline_spatial=baseline_spatial,
        scenario_spatial=scenario_spatial,
        route_blockage=request.routeBlockage,
    )

    # 6. Reproducibility & Fingerprint
    scenario_params_dict = request.model_dump()
    fingerprint = compute_scenario_fingerprint(base_features, scenario_params_dict, model_version)
    scenario_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    is_severe = scenario_risk >= 80.0 or request.routeBlockage or (request.rainfallMultiplier >= 1.4)
    flagged_assets = ["Bridge-04", "Pump-Station-7"] if is_severe else ["Bridge-04"]
    recommended_name = f"Route {scenario_route_opt.recommended.name}"

    narrative = (
        f"SIMULATED SCENARIO OUTPUT: ML model predicts risk change of {risk_delta:+.1f} points "
        f"(Baseline: {baseline_risk:.1f} → Scenario: {scenario_risk:.1f}, {scenario_category}). "
        f"{route_change_reason}"
    )

    # Structured response
    return SimulationResponse(
        newRisk=scenario_risk,
        baselineRisk=baseline_risk,
        baseline_risk=baseline_risk,
        scenarioRisk=scenario_risk,
        scenario_risk=scenario_risk,
        riskDelta=risk_delta,
        risk_delta=risk_delta,
        riskCategory=scenario_category,
        predictionReliability=reliability,
        prediction_reliability=reliability,
        routeRecommendation=recommended_name,
        flaggedAssets=flagged_assets,
        narrative=narrative,
        severity="SEVERE" if is_severe else ("MODERATE" if scenario_risk >= 50.0 else "MINOR"),
        
        # Extended Phase 6.16 Metadata
        scenario_id=scenario_id,
        fingerprint=fingerprint,
        label="SIMULATED SCENARIO OUTPUT",
        baseline_features=base_features,
        scenario_features=scenario_features,
        feature_deltas={k: round(scenario_features[k] - base_features[k], 4) for k in FEATURE_NAMES},
        uncertainty={
            "baseline": baseline_unc,
            "scenario": scenario_unc,
            "nominal_coverage": 0.90,
            "status": "calibrated",
            "disclaimer": "Split-conformal prediction intervals. Wider interval does not imply higher physical severity.",
        },
        shap={
            "canonical_features": FEATURE_NAMES,
            "baseline_total_shap_delta": baseline_shap_raw.get("total_shap_delta", 0.0),
            "scenario_total_shap_delta": scenario_shap_raw.get("total_shap_delta", 0.0),
            "attribution_changes": shap_attribution_changes,
            "disclaimer": "SHAP attributions describe model scoring behavior and do not constitute causal physical mechanisms.",
        },
        spatial={
            "baseline_route_spatial_exposure": b_exp,
            "scenario_route_spatial_exposure": s_exp,
            "spatial_exposure_delta": spatial_exposure_delta,
            "baseline_modeled_safety": b_safety,
            "scenario_modeled_safety": s_safety,
            "safety_score_delta": safety_delta,
            "provenance": scenario_spatial.get("provenance", "hazard:provisional_river_proximity"),
            "terminology_notice": "PROVISIONAL / DEMONSTRATION — Decision support layer only.",
        },
        routes={
            "baseline_route": {
                "id": baseline_route_opt.recommended.id,
                "name": baseline_route_opt.recommended.name,
                "eta": baseline_route_opt.recommended.eta,
                "safety_score": b_safety,
            },
            "scenario_route": {
                "id": scenario_route_opt.recommended.id,
                "name": scenario_route_opt.recommended.name,
                "eta": scenario_route_opt.recommended.eta,
                "safety_score": s_safety,
            },
            "eta_delta": eta_delta,
            "safety_score_delta": safety_delta,
            "route_changed": route_changed,
            "reason": route_change_reason,
        },
        alerts=alert_impact,
        reproducibility={
            "timestamp": now_iso,
            "incident_id": incident_id,
            "fingerprint": fingerprint,
            "model_version": model_version,
            "model_data_status": model_status,
            "deterministic": True,
        },
        disclaimer="SIMULATED SCENARIO OUTPUT — Decision support simulation only, not an official flood forecast or real-world disaster prediction.",
    )


async def execute_scenario_analysis_async(
    request: SimulationRequest,
    incident_id: str = "INC-2026-DEFAULT",
) -> SimulationResponse:
    """
    Async wrapper that executes scenario analysis, persists Simulation record,
    and publishes simulation.completed SSE event.
    """
    res = execute_scenario_analysis(request, incident_id=incident_id)

    from app.services.persistence_service import get_persistence_service
    ps = get_persistence_service()

    from app.db.models import Simulation
    sim = Simulation(
        id=uuid.UUID(res.scenario_id) if res.scenario_id else uuid.uuid4(),
        incident_id=incident_id,
        evacuation_pace=request.evacuationPace,
        rainfall_multiplier=request.rainfallMultiplier,
        drainage_efficiency=request.drainageEfficiency,
        route_blockage=request.routeBlockage,
        rainfall_increase=request.rainfallIncrease,
        population_movement=request.populationMovement,
        water_level_increase=request.waterLevelIncrease,
        baseline_risk=res.baselineRisk,
        scenario_risk=res.scenarioRisk,
        risk_delta=res.riskDelta,
        risk_category=res.riskCategory,
        prediction_reliability=res.predictionReliability,
        route_recommendation=res.routeRecommendation,
        flagged_assets=res.flaggedAssets,
        narrative=res.narrative,
        severity=res.severity,
    )

    await ps.save_simulation(sim)
    return res

