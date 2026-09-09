"""
AapdaNetra-X — Routes API Router
Provides GET /api/routes?horizon={0..3} using NetworkX route optimization and SHAP explainability.
"""
from fastapi import APIRouter, Query
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
async def get_routes(horizon: int = Query(default=0, ge=0, le=3)):
    """
    Returns NetworkX risk-optimized evacuation routes and SHAP decision trace for requested time horizon.
    """
    features = get_horizon_features(horizon)

    # 1. ML risk prediction
    ml_risk = predict_risk(features)
    predicted_score = ml_risk["risk_score"]

    # 2. SHAP decision trace
    exp = explain_prediction(features)
    trace_list = [
        DecisionFactor(
            factor=t["factor"],
            contribution=t["contribution"],
            direction=t.get("direction", "increases_risk"),
            percent=t.get("percent", 0.0),
            shapValue=t.get("shapValue", 0.0),
        )
        for t in exp["decision_trace"]
    ]

    # 3. NetworkX Route Optimization
    opt_result = optimize_routes(
        predicted_risk_score=predicted_score,
        route_blockage=False,
        horizon_index=horizon
    )

    rec_route = convert_route_path(opt_result.recommended)
    alt_routes = [convert_route_path(a) for a in opt_result.alternatives]

    recommendation_meta = RouteRecommendation(
        title="Evacuate Sector B",
        text=opt_result.route_reason,
        confidence=ml_risk["prediction_reliability"],
    )

    return RoutesResponse(
        horizon=horizon,
        recommended=rec_route,
        alternatives=alt_routes,
        recommendation=recommendation_meta,
        decisionTrace=trace_list,
        blockedSegments=opt_result.blocked_segments,
        routeReason=opt_result.route_reason,
    )
