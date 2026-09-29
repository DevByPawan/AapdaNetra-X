"""
AapdaNetra-X — Evacuation Intelligence API Router

Phase 6.18: Provides structured endpoints for dynamic evacuation route recommendations
and deterministic event-driven recomputation.
"""

from typing import Optional
from fastapi import APIRouter, Query

from app.models.schemas import (
    EvacuationIntelligenceResponse,
    EvacuationRecomputeRequest,
)
from app.services.evacuation_service import get_evacuation_service

router = APIRouter()


@router.get("/evacuation/recommendation", response_model=EvacuationIntelligenceResponse)
async def get_evacuation_recommendation(
    incident_id: str = Query(default="INC-2026-DEFAULT"),
    horizon: int = Query(default=0, ge=0, le=4),
):
    """
    Returns dynamic evacuation intelligence synthesizing ML risk, NetworkX Dijkstra paths,
    GIS spatial hazard exposure, transparent scoring, and route status.
    """
    svc = get_evacuation_service()
    return svc.evaluate_evacuation_routes(
        incident_id=incident_id,
        horizon=horizon,
        publish_sse=False,
    )


@router.post("/evacuation/recompute", response_model=EvacuationIntelligenceResponse)
async def recompute_evacuation_routes(request: EvacuationRecomputeRequest):
    """
    Triggers explicit deterministic recomputation of evacuation routes upon state changes
    (e.g., risk escalation, route blockage, spatial hazard updates).
    Publishes EventType.ROUTE_UPDATED SSE event when publish_sse is True.
    """
    svc = get_evacuation_service()
    return svc.evaluate_evacuation_routes(
        incident_id=request.incident_id,
        horizon=request.horizon,
        route_blockage_override=request.route_blockage_override,
        publish_sse=request.publish_sse,
    )
