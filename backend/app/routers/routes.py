"""
AapdaNetra-X — Routes API Router
Provides GET /api/routes?horizon={0..3} using NetworkX route optimization and SHAP explainability.
"""
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from app.models.schemas import (
    RoutesResponse, EvacRoute, RouteWaypoint,
    RouteRecommendation, DecisionFactor
)
from app.services.risk_engine import get_horizon_features
from ml.inference import predict_risk
from ml.explainability import explain_prediction
from ml.routing import optimize_routes, RoutePath

router = APIRouter()


def convert_route_path(path_obj: RoutePath) -> EvacRoute:
    """Helper to convert ml.routing RoutePath dataclass to Pydantic EvacRoute model."""
    waypoints = [
        RouteWaypoint(id=wp.id, lat=wp.lat, lng=wp.lng, label=wp.label)
        for wp in path_obj.waypoints
    ]
    return EvacRoute(
        id=path_obj.id,
        name=path_obj.name,
        eta=path_obj.eta,
        failureProbability=path_obj.failureProbability,
        safetyScore=path_obj.safetyScore,
        distanceKm=path_obj.distance_km,
        riskScore=path_obj.riskScore,
        waypoints=waypoints,
        nodes=path_obj.nodes,
        isBlocked=path_obj.is_blocked,
    )


@router.get("/routes", response_model=RoutesResponse)
async def get_routes(
    horizon: int = Query(default=0, ge=0, le=3),
    hazard_type: Optional[str] = Query(default=None, description="Optional hazard type identifier"),
):
    """
    Returns NetworkX risk-optimized evacuation routes and SHAP decision trace for requested time horizon and hazard_type.
    """
    from app.hazards import HazardType, get_hazard_registry
    from fastapi import HTTPException

    if hazard_type is not None and hazard_type.strip().lower() != "flood":
        h_str = hazard_type.strip().lower()
        try:
            ht_enum = HazardType(h_str)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown or unsupported hazard_type: '{hazard_type}'"
            ) from exc

        registry = get_hazard_registry()
        defn = registry.get_definition(ht_enum)
        hazard_adapter = registry.get_adapter(ht_enum)
        penalty_res = hazard_adapter.get_route_penalty()

        # Generate structural base fallback routes without claiming flood GBR prediction or safety
        opt_fallback = optimize_routes(predicted_risk_score=30.0, horizon_index=horizon)
        rec_route = convert_route_path(opt_fallback.recommended)
        alt_routes = [convert_route_path(a) for a in opt_fallback.alternatives]

        reason_str = f"[HAZARD: {defn.display_name.upper()}] Route optimization unavailable ({defn.capability_status.value}). {penalty_res.message}"
        contract_info = {
            "hazard_type": defn.hazard_type.value,
            "capability_status": defn.capability_status.value,
            "routing_available": False,
            "is_eligible": False,
            "message": penalty_res.message,
        }

        return RoutesResponse(
            horizon=horizon,
            recommended=rec_route,
            alternatives=alt_routes,
            recommendation=RouteRecommendation(
                title="Evacuation Routing Status",
                text=reason_str,
                confidence=0.0,
            ),
            decisionTrace=[],
            blockedSegments=opt_fallback.blocked_segments,
            routeReason=reason_str,
            data_contract=contract_info,
            input_contract=contract_info,
            hazard_type=defn.hazard_type.value,
        )

    from app.data.providers.data_adapter import get_data_adapter
    adapter = get_data_adapter()
    features = get_horizon_features(horizon)

    # 1. ML risk prediction
    ml_risk = predict_risk(
        features,
        data_mode=adapter.data_mode,
        provenance=adapter.provenance,
        freshness=adapter.get_feature_freshness(),
    )
    predicted_score = ml_risk["risk_score"]

    # 2. SHAP decision trace
    exp = explain_prediction(
        features,
        data_mode=adapter.data_mode,
        provenance=adapter.provenance,
        freshness=adapter.get_feature_freshness(),
    )
    trace_list = [
        DecisionFactor(
            factor=t["factor"],
            contribution=t["contribution"],
            direction=t.get("direction", "increases_risk"),
            percent=t.get("percent", 0.0),
            shapValue=t.get("shapValue", 0.0),
            attributionStatement=t.get("attributionStatement", ""),
        )
        for t in exp["decision_trace"]
    ]

    contract_dict = ml_risk.get("data_contract")

    # 3. NetworkX Route Optimization
    opt_result = optimize_routes(
        predicted_risk_score=predicted_score,
        route_blockage=False,
        horizon_index=horizon,
        data_contract=contract_dict,
    )

    rec_route = convert_route_path(opt_result.recommended)
    alt_routes = [convert_route_path(a) for a in opt_result.alternatives]

    is_eligible = ml_risk.get("is_eligible", True)
    confidence_val = ml_risk.get("prediction_reliability", 0.95) if is_eligible else 0.0

    recommendation_meta = RouteRecommendation(
        title="Evacuate Sector B",
        text=opt_result.route_reason,
        confidence=confidence_val,
    )

    return RoutesResponse(
        horizon=horizon,
        recommended=rec_route,
        alternatives=alt_routes,
        recommendation=recommendation_meta,
        decisionTrace=trace_list,
        blockedSegments=opt_result.blocked_segments,
        routeReason=opt_result.route_reason,
        data_contract=contract_dict,
        input_contract=contract_dict,
        hazard_type="flood",
    )
