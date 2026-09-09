"""
AapdaNetra-X — Explainability API Router
Provides GET /api/explainability?horizon={0..3} returning SHAP feature contributions.
"""
from fastapi import APIRouter, Query
from ml.explainability import explain_prediction
from app.services.risk_engine import get_horizon_features
from app.models.schemas import ExplainabilityResponse, DecisionFactor, ExplainabilityFeature

router = APIRouter()


@router.get("/explainability", response_model=ExplainabilityResponse)
async def get_explainability(horizon: int = Query(default=0, ge=0, le=3)):
    """
    Returns SHAP-based model explainability for requested time horizon.
    """
    features = get_horizon_features(horizon)
    exp = explain_prediction(features)

    features_list = [
        ExplainabilityFeature(**item) for item in exp["features"]
    ]
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

    return ExplainabilityResponse(
        horizon=horizon,
        prediction=exp["prediction"],
        base_value=exp["base_value"],
        total_shap_delta=exp["total_shap_delta"],
        features=features_list,
        decision_trace=trace_list,
        decisionTrace=trace_list,
    )
