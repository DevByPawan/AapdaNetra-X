"""
AapdaNetra-X — Evacuation Intelligence API Router

Phase 6.18 / Phase 6.20.8: Provides structured endpoints for dynamic evacuation route recommendations
and deterministic event-driven recomputation across hazard capabilities.
"""

from typing import Optional, Union
from fastapi import APIRouter, Query, HTTPException

from app.models.schemas import (
    EvacuationIntelligenceResponse,
    EvacuationUnavailableResponse,
    EvacuationRecomputeRequest,
)
from app.services.evacuation_service import get_evacuation_service
from app.routers.history import validate_optional_hazard_type

router = APIRouter()


@router.get(
    "/evacuation/recommendation",
    response_model=Union[EvacuationIntelligenceResponse, EvacuationUnavailableResponse],
)
async def get_evacuation_recommendation(
    incident_id: str = Query(default="INC-2026-DEFAULT"),
    horizon: int = Query(default=0, ge=0, le=4),
    hazard_type: Optional[str] = Query(default=None, description="Optional hazard type filter"),
):
    """
    Returns dynamic evacuation intelligence synthesizing ML risk, NetworkX Dijkstra paths,
    GIS spatial hazard exposure, transparent scoring, and route status.
    Returns UNAVAILABLE for hazards without operational routing models.
    """
    h_val = validate_optional_hazard_type(hazard_type) or "flood"
    svc = get_evacuation_service()
    try:
        return svc.evaluate_evacuation_routes(
            incident_id=incident_id,
            horizon=horizon,
            publish_sse=False,
            hazard_type=h_val,
        )
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err)) from val_err


@router.post(
    "/evacuation/recompute",
    response_model=Union[EvacuationIntelligenceResponse, EvacuationUnavailableResponse],
)
async def recompute_evacuation_routes(request: EvacuationRecomputeRequest):
    """
    Triggers explicit deterministic recomputation of evacuation routes upon state changes
    (e.g., risk escalation, route blockage, spatial hazard updates).
    Publishes EventType.ROUTE_UPDATED SSE event when publish_sse is True.
    """
    h_val = validate_optional_hazard_type(request.hazard_type) or "flood"
    svc = get_evacuation_service()
    try:
        return svc.evaluate_evacuation_routes(
            incident_id=request.incident_id,
            horizon=request.horizon,
            route_blockage_override=request.route_blockage_override,
            publish_sse=request.publish_sse,
            hazard_type=h_val,
        )
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err)) from val_err
