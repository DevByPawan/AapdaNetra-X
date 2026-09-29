"""
AapdaNetra-X — Real-Time Telemetry API Router

Phase 6.19: Endpoints for real-time sensor observation push ingestion, active feature query,
and pipeline health observability.
"""

from typing import Dict, Any
from fastapi import APIRouter

from app.models.schemas import (
    TelemetryHealthResponse,
    TelemetryIngestionRequest,
    TelemetryIngestionResponse,
)
from app.services.telemetry_service import get_telemetry_service

router = APIRouter()


@router.post("/telemetry/observe", response_model=TelemetryIngestionResponse)
async def observe_telemetry(request: TelemetryIngestionRequest):
    """
    Ingests a real-time sensor telemetry observation.
    Executes validation, deduplication, timestamp ordering check, trend calculation,
    live feature overlay update, persistence, and change-aware downstream cascade.
    """
    svc = get_telemetry_service()
    return svc.ingest_observation(request)


@router.get("/telemetry/live", response_model=Dict[str, Any])
async def get_live_telemetry():
    """
    Returns current active live telemetry overlay and per-feature provenance metadata.
    """
    from app.data.providers.data_adapter import get_data_adapter
    adapter = get_data_adapter()
    return {
        "active_features": adapter.get_base_features(),
        "provenance": adapter.provenance,
        "fallback_used": adapter.fallback_used,
        "live_overlay": adapter.get_live_overlay(),
    }


@router.get("/telemetry/health", response_model=TelemetryHealthResponse)
async def get_telemetry_health():
    """
    Returns pipeline health counters and ingestion observability metrics.
    """
    svc = get_telemetry_service()
    return svc.get_health_status()
