from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse

from app.models.schemas import RiskResponse
from app.services.risk_engine import compute_risk_state, compute_risk_state_async
from app.hazards import HazardType, HazardCapabilityStatus, get_hazard_registry

router = APIRouter()


@router.get("/risk")
async def get_risk(
    horizon: int = Query(default=0, ge=0, le=3),
    hazard_type: Optional[str] = Query(default=None, description="Optional hazard type identifier"),
):
    """
    Returns dynamic hazard risk state for requested horizon (0=NOW, 1=+10M, 2=+20M, 3=+30M)
    and optional hazard_type.
    """
    if hazard_type is None or hazard_type.strip().lower() == "flood":
        return await compute_risk_state_async(horizon=horizon)

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

    if ht_enum == HazardType.EXTREME_RAINFALL:
        return JSONResponse(
            status_code=200,
            content={
                "index": horizon,
                "label": f"+{horizon*10}M" if horizon > 0 else "NOW",
                "hazard_type": ht_enum.value,
                "capability_status": defn.capability_status.value,
                "supported": True,
                "model_available": False,
                "predicted_risk": None,
                "predictedRisk": None,
                "riskCategory": None,
                "confidence": None,
                "provenance": eval_res.provenance,
                "disclaimer": eval_res.disclaimer,
                "message": eval_res.message,
                "telemetry_available": True,
                "spatial_available": False,
                "alerts_available": True,
                "routing_available": False,
                "decision_support_available": False,
            },
        )

    # For LANDSLIDE, CYCLONE, HEATWAVE, EARTHQUAKE (unsupported hazards)
    return JSONResponse(
        status_code=200,
        content={
            "index": horizon,
            "label": f"+{horizon*10}M" if horizon > 0 else "NOW",
            "hazard_type": ht_enum.value,
            "capability_status": defn.capability_status.value,
            "supported": False,
            "model_available": False,
            "predicted_risk": None,
            "predictedRisk": None,
            "riskCategory": None,
            "confidence": None,
            "provenance": eval_res.provenance,
            "disclaimer": eval_res.disclaimer,
            "message": eval_res.message,
            "telemetry_available": False,
            "spatial_available": False,
            "alerts_available": False,
            "routing_available": False,
            "decision_support_available": False,
        },
    )
