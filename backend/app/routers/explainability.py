"""
AapdaNetra-X — Explainability API Router
Provides GET /api/explainability?horizon={0..3}&hazard_type={type} returning SHAP feature contributions.
"""
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from ml.explainability import explain_prediction
from app.services.risk_engine import get_horizon_features
from app.models.schemas import ExplainabilityResponse, DecisionFactor, ExplainabilityFeature
from app.hazards import HazardType, get_hazard_registry

router = APIRouter()


@router.get("/explainability", response_model=ExplainabilityResponse)
async def get_explainability(
    horizon: int = Query(default=0, ge=0, le=3),
    hazard_type: Optional[str] = Query(default=None, description="Optional hazard type identifier"),
):
    """
    Returns SHAP-based model explainability for requested time horizon and hazard type.
    """
    if hazard_type is not None and hazard_type.strip().lower() != "flood":
        try:
            ht_enum = HazardType(hazard_type.strip().lower())
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown or unsupported hazard_type: '{hazard_type}'"
            ) from exc

        registry = get_hazard_registry()
        defn = registry.get_definition(ht_enum)
        adapter = registry.get_adapter(ht_enum)
        eval_res = adapter.evaluate_risk()

        return ExplainabilityResponse(
            horizon=horizon,
            prediction=0.0,
            base_value=0.0,
            total_shap_delta=0.0,
            features=[],
            decision_trace=[],
            decisionTrace=[],
            is_shap_consistent=False,
            predictionInterval=None,
            prediction_interval=None,
            data_contract={
                "status": "unsupported_model",
                "hazard_type": ht_enum.value,
                "capability_status": defn.capability_status.value,
                "model_available": False,
                "message": eval_res.message or f"Explainability model unavailable for hazard type '{ht_enum.value}'.",
                "capabilities": defn.model_dump(),
            },
            input_contract={
                "status": "unsupported_model",
                "hazard_type": ht_enum.value,
                "capability_status": defn.capability_status.value,
                "model_available": False,
            },
            hazard_type=ht_enum.value,
        )

    from app.data.providers.data_adapter import get_data_adapter
    adapter = get_data_adapter()

    features = get_horizon_features(horizon)
    exp = explain_prediction(
        features,
        data_mode=adapter.data_mode,
        provenance=adapter.provenance,
        freshness=adapter.get_feature_freshness(),
    )

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
            attributionStatement=t.get("attributionStatement", ""),
        )
        for t in exp["decision_trace"]
    ]

    from ml.uncertainty import quantify_uncertainty
    from app.models.schemas import PredictionInterval
    unc_obj = quantify_uncertainty(exp["prediction"])
    unc_dict = unc_obj.to_dict()
    pred_interval = PredictionInterval(
        lower=unc_obj.lower_bound,
        upper=unc_obj.upper_bound,
        intervalWidth=unc_obj.interval_width,
        interval_width=unc_obj.interval_width,
        nominalCoverage=unc_obj.nominal_coverage,
        nominal_coverage=unc_obj.nominal_coverage,
        method=unc_obj.uncertainty_method,
        dataStatus=unc_obj.data_status,
        data_status=unc_obj.data_status,
        isClipped=unc_obj.is_clipped,
        is_clipped=unc_obj.is_clipped,
        status=unc_obj.status,
        disclaimer=unc_obj.disclaimer,
    )

    contract_dict = exp.get("data_contract")

    return ExplainabilityResponse(
        horizon=horizon,
        prediction=exp["prediction"],
        base_value=exp["base_value"],
        total_shap_delta=exp["total_shap_delta"],
        features=features_list,
        decision_trace=trace_list,
        decisionTrace=trace_list,
        is_shap_consistent=exp.get("is_shap_consistent", True),
        predictionInterval=pred_interval,
        prediction_interval=unc_dict,
        data_contract=contract_dict,
        input_contract=contract_dict,
        hazard_type="flood",
    )
