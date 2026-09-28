"""AapdaNetra-X — Historical REST APIs Router

Provides persistence-backed historical queries for Incidents, Telemetry, Risk,
Evacuation Routes, Audit Logs, and SHAP Explainability records.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.pagination import PaginationParams
from app.db.repositories import (
    AuditEventRepository,
    EvacuationRouteRepository,
    IncidentRepository,
    RiskPredictionRepository,
    SHAPRecordRepository,
    TelemetryRepository,
)
from app.db.session import get_db_manager
from app.schemas.history import (
    AuditHistoryItem,
    CursorInfo,
    IncidentHistoryItem,
    PaginatedResponse,
    RiskHistoryItem,
    RouteHistoryItem,
    SHAPHistoryResponse,
    TelemetryHistoryItem,
    TimelineEventItem,
)
from app.services.timeline_service import TimelineService


router = APIRouter()


@asynccontextmanager
async def get_history_session():
    """Async context manager to provide a DB session based on persistence mode."""
    mode = settings.persistence_mode.lower()
    if mode == "disabled":
        yield None
        return

    db_mgr = get_db_manager()
    if not db_mgr.is_available:
        if mode == "required":
            raise HTTPException(
                status_code=503,
                detail="Database service unavailable in required persistence mode",
            )
        yield None
        return

    async with db_mgr.get_session() as session:
        yield session


def get_pagination_params(
    limit: int = Query(default=50, ge=1, le=100, description="Page limit (1..100)"),
    cursor_timestamp: Optional[datetime] = Query(
        default=None, description="ISO 8601 UTC cursor timestamp"
    ),
    cursor_id: Optional[str] = Query(default=None, description="Cursor ID tie-breaker"),
    from_time: Optional[datetime] = Query(default=None, description="Start time filter"),
    to_time: Optional[datetime] = Query(default=None, description="End time filter"),
) -> PaginationParams:
    """Parse and validate keyset pagination query parameters."""
    try:
        return PaginationParams(
            limit=limit,
            cursor_timestamp=cursor_timestamp,
            cursor_id=cursor_id,
            from_time=from_time,
            to_time=to_time,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ── 1. Incidents Historical Endpoints ────────────────────────────────────

@router.get("/incidents", response_model=PaginatedResponse[IncidentHistoryItem])
async def list_incidents(
    status: Optional[str] = Query(None, description="Filter status (e.g. ACTIVE, CLOSED)"),
    params: PaginationParams = Depends(get_pagination_params),
):
    """List persisted disaster incidents with pagination and optional status filter."""
    async with get_history_session() as session:
        if session is None:
            return PaginatedResponse(items=[], next_cursor=None, has_more=False)

        try:
            repo = IncidentRepository(session)
            page_res = await repo.list_incidents_paginated(params=params, status=status)

            items = [
                IncidentHistoryItem(
                    id=item.id,
                    incident_type=item.incident_type,
                    status=item.status,
                    started_at=item.started_at.isoformat(),
                    sector=item.sector,
                    severity=item.severity,
                    location_name=item.location_name,
                    latitude=item.latitude,
                    longitude=item.longitude,
                    created_at=item.created_at.isoformat(),
                    updated_at=item.updated_at.isoformat(),
                )
                for item in page_res.items
            ]
            next_c = CursorInfo(**page_res.next_cursor) if page_res.next_cursor else None
            return PaginatedResponse(items=items, next_cursor=next_c, has_more=page_res.has_more)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve incidents history") from exc


@router.get("/incidents/{incident_id}", response_model=IncidentHistoryItem)
async def get_incident(incident_id: str):
    """Retrieve persisted metadata for a specific incident."""
    async with get_history_session() as session:
        if session is None:
            raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

        try:
            repo = IncidentRepository(session)
            inc = await repo.get_by_id(incident_id)
            if not inc:
                raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

            return IncidentHistoryItem(
                id=inc.id,
                incident_type=inc.incident_type,
                status=inc.status,
                started_at=inc.started_at.isoformat(),
                sector=inc.sector,
                severity=inc.severity,
                location_name=inc.location_name,
                latitude=inc.latitude,
                longitude=inc.longitude,
                created_at=inc.created_at.isoformat(),
                updated_at=inc.updated_at.isoformat(),
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve incident details") from exc


# ── 2. Telemetry History Endpoint ────────────────────────────────────────

@router.get(
    "/incidents/{incident_id}/telemetry/history",
    response_model=PaginatedResponse[TelemetryHistoryItem],
)
async def get_telemetry_history(
    incident_id: str,
    params: PaginationParams = Depends(get_pagination_params),
):
    """Retrieve time-series telemetry observation history for an incident."""
    async with get_history_session() as session:
        if session is None:
            return PaginatedResponse(items=[], next_cursor=None, has_more=False)

        try:
            repo = TelemetryRepository(session)
            page_res = await repo.get_history_paginated(incident_id=incident_id, params=params)

            items = [
                TelemetryHistoryItem(
                    id=str(item.id),
                    incident_id=item.incident_id,
                    data_mode=item.data_mode,
                    fallback_used=item.fallback_used,
                    rainfall_intensity=item.rainfall_intensity,
                    rainfall_trend=item.rainfall_trend,
                    water_level=item.water_level,
                    water_level_trend=item.water_level_trend,
                    road_congestion=item.road_congestion,
                    population_exposure=item.population_exposure,
                    infrastructure_vulnerability=item.infrastructure_vulnerability,
                    location_name=item.location_name,
                    provenance=item.provenance or {},
                    observed_at=item.observed_at.isoformat(),
                    created_at=item.created_at.isoformat(),
                )
                for item in page_res.items
            ]
            next_c = CursorInfo(**page_res.next_cursor) if page_res.next_cursor else None
            return PaginatedResponse(items=items, next_cursor=next_c, has_more=page_res.has_more)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve telemetry history") from exc


# ── 3. Risk Prediction History Endpoint ──────────────────────────────────

@router.get(
    "/incidents/{incident_id}/risk/history",
    response_model=PaginatedResponse[RiskHistoryItem],
)
async def get_risk_history(
    incident_id: str,
    horizon: Optional[int] = Query(None, ge=0, le=3, description="Filter by horizon index (0..3)"),
    params: PaginationParams = Depends(get_pagination_params),
):
    """Retrieve historical ML risk predictions for an incident."""
    async with get_history_session() as session:
        if session is None:
            return PaginatedResponse(items=[], next_cursor=None, has_more=False)

        try:
            repo = RiskPredictionRepository(session)
            page_res = await repo.get_history_paginated(
                incident_id=incident_id, horizon=horizon, params=params
            )

            items = [
                RiskHistoryItem(
                    id=str(item.id),
                    incident_id=item.incident_id,
                    telemetry_id=str(item.telemetry_id) if item.telemetry_id else None,
                    horizon=item.horizon,
                    horizon_label=item.horizon_label,
                    current_risk=item.current_risk,
                    predicted_risk=item.predicted_risk,
                    risk_category=item.risk_category,
                    confidence=item.confidence,
                    prediction_reliability=item.prediction_reliability,
                    affected_population=item.affected_population,
                    critical_population=item.critical_population,
                    critical_assets_count=item.critical_assets_count,
                    affected_assets_count=item.affected_assets_count,
                    trend=item.trend,
                    map_status_text=item.map_status_text,
                    prediction_note=item.prediction_note,
                    input_features=item.input_features or {},
                    created_at=item.created_at.isoformat(),
                )
                for item in page_res.items
            ]
            next_c = CursorInfo(**page_res.next_cursor) if page_res.next_cursor else None
            return PaginatedResponse(items=items, next_cursor=next_c, has_more=page_res.has_more)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve risk history") from exc


# ── 4. Evacuation Routes History Endpoint ─────────────────────────────────

@router.get(
    "/incidents/{incident_id}/routes/history",
    response_model=PaginatedResponse[RouteHistoryItem],
)
async def get_route_history(
    incident_id: str,
    params: PaginationParams = Depends(get_pagination_params),
):
    """Retrieve historical evacuation route calculations for an incident."""
    async with get_history_session() as session:
        if session is None:
            return PaginatedResponse(items=[], next_cursor=None, has_more=False)

        try:
            repo = EvacuationRouteRepository(session)
            page_res = await repo.get_history_paginated(incident_id=incident_id, params=params)

            items = [
                RouteHistoryItem(
                    id=str(item.id),
                    incident_id=item.incident_id,
                    risk_prediction_id=str(item.risk_prediction_id) if item.risk_prediction_id else None,
                    route_name=item.route_name,
                    route_type=item.route_type,
                    is_recommended=item.is_recommended,
                    origin_name=item.origin_name,
                    origin_lat=item.origin_lat,
                    origin_lon=item.origin_lon,
                    destination_name=item.destination_name,
                    destination_lat=item.destination_lat,
                    destination_lon=item.destination_lon,
                    waypoint_coords=item.waypoint_coords or [],
                    distance_km=item.distance_km,
                    estimated_minutes=item.estimated_minutes,
                    safety_score=item.safety_score,
                    congestion_index=item.congestion_index if item.congestion_index is not None else 0.0,
                    created_at=item.created_at.isoformat(),

                )
                for item in page_res.items
            ]
            next_c = CursorInfo(**page_res.next_cursor) if page_res.next_cursor else None
            return PaginatedResponse(items=items, next_cursor=next_c, has_more=page_res.has_more)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve route history") from exc


# ── 5. Audit Log History Endpoint ─────────────────────────────────────────

@router.get(
    "/incidents/{incident_id}/audit",
    response_model=PaginatedResponse[AuditHistoryItem],
)
async def get_audit_history(
    incident_id: str,
    params: PaginationParams = Depends(get_pagination_params),
):
    """Retrieve historical audit event logs associated with an incident."""
    async with get_history_session() as session:
        if session is None:
            return PaginatedResponse(items=[], next_cursor=None, has_more=False)

        try:
            repo = AuditEventRepository(session)
            page_res = await repo.get_history_paginated(incident_id=incident_id, params=params)

            items = [
                AuditHistoryItem(
                    id=str(item.id),
                    incident_id=item.incident_id,
                    event_type=item.event_type,
                    severity=item.severity,
                    source=item.source,
                    description=item.description,
                    actor=item.actor,
                    event_data=item.event_data,
                    created_at=item.created_at.isoformat(),
                )
                for item in page_res.items
            ]
            next_c = CursorInfo(**page_res.next_cursor) if page_res.next_cursor else None
            return PaginatedResponse(items=items, next_cursor=next_c, has_more=page_res.has_more)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve audit history") from exc


# ── 6. SHAP Explainability Historical Endpoint ────────────────────────────

@router.get(
    "/risk/{prediction_id}/explanation",
    response_model=SHAPHistoryResponse,
)
async def get_risk_explanation_history(prediction_id: str):
    """Retrieve persisted SHAP explainability record for a specific risk prediction."""
    try:
        pred_uuid = uuid.UUID(prediction_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Prediction '{prediction_id}' explanation not found")

    async with get_history_session() as session:
        if session is None:
            raise HTTPException(
                status_code=404, detail=f"Prediction '{prediction_id}' explanation not found"
            )

        try:
            repo = SHAPRecordRepository(session)
            rec = await repo.get_by_prediction_id(pred_uuid)
            if not rec:
                raise HTTPException(
                    status_code=404, detail=f"Prediction '{prediction_id}' explanation not found"
                )

            return SHAPHistoryResponse(
                id=str(rec.id),
                risk_prediction_id=str(rec.risk_prediction_id),
                horizon=rec.horizon,
                prediction=rec.prediction,
                base_value=rec.base_value,
                total_shap_delta=rec.total_shap_delta,
                features=rec.features or {},
                decision_trace=rec.decision_trace or [],
                created_at=rec.created_at.isoformat(),
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve SHAP explanation history") from exc


# ── 7. Unified Incident Timeline Endpoint ──────────────────────────────────

@router.get(
    "/incidents/{incident_id}/timeline",
    response_model=PaginatedResponse[TimelineEventItem],
)
async def get_incident_timeline(
    incident_id: str,
    params: PaginationParams = Depends(get_pagination_params),
):
    """Retrieve unified chronological event timeline for an incident across 6 domain entities."""
    async with get_history_session() as session:
        if session is None:
            return PaginatedResponse(items=[], next_cursor=None, has_more=False)

        try:
            # Check incident existence first
            inc_repo = IncidentRepository(session)
            inc = await inc_repo.get_by_id(incident_id)
            if not inc:
                raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

            service = TimelineService(session)
            page_res = await service.get_incident_timeline(incident_id=incident_id, params=params)

            next_c = CursorInfo(**page_res.next_cursor) if page_res.next_cursor else None
            return PaginatedResponse(
                items=page_res.items,
                next_cursor=next_c,
                has_more=page_res.has_more,
            )
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve incident timeline") from exc

