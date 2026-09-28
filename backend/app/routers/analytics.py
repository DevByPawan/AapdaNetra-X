"""AapdaNetra-X — Historical Analytics REST API Router

Provides lightweight, high-performance database-side historical analytics
derived from persisted domain entities without duplicating stored data.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.db.repositories.analytics import AnalyticsRepository
from app.db.session import get_db_manager
from app.schemas.analytics import (
    AlertAnalyticsResponse,
    AnalyticsOverviewResponse,
    IncidentAnalyticsResponse,
    RiskAnalyticsResponse,
    RouteAnalyticsResponse,
    SimulationAnalyticsResponse,
    TelemetryAnalyticsResponse,
)

router = APIRouter()


@asynccontextmanager
async def get_analytics_session():
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


def validate_time_range(from_time: Optional[datetime], to_time: Optional[datetime]) -> None:
    """Validate that from_time <= to_time if both are supplied."""
    if from_time and to_time and from_time > to_time:
        raise HTTPException(
            status_code=422,
            detail="from_time must be less than or equal to to_time",
        )


# ── 1. Analytics Overview ──────────────────────────────────────────────────

@router.get("/analytics/overview", response_model=AnalyticsOverviewResponse)
async def get_analytics_overview(
    from_time: Optional[datetime] = Query(None, description="Start timestamp filter"),
    to_time: Optional[datetime] = Query(None, description="End timestamp filter"),
):
    """Retrieve system-wide historical aggregate counts and risk metrics."""
    validate_time_range(from_time, to_time)

    async with get_analytics_session() as session:
        if session is None:
            return AnalyticsOverviewResponse(
                total_incidents=0,
                active_incidents=0,
                total_telemetry_observations=0,
                total_risk_predictions=0,
                total_alerts=0,
                total_evacuation_routes=0,
                total_simulations=0,
                total_audit_events=0,
                avg_system_risk=None,
                max_system_risk=None,
                from_time=from_time.isoformat() if from_time else None,
                to_time=to_time.isoformat() if to_time else None,
            )

        try:
            repo = AnalyticsRepository(session)
            data = await repo.get_overview(from_time=from_time, to_time=to_time)
            return AnalyticsOverviewResponse(
                **data,
                from_time=from_time.isoformat() if from_time else None,
                to_time=to_time.isoformat() if to_time else None,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve analytics overview") from exc


# ── 2. Incident Analytics ──────────────────────────────────────────────────

@router.get("/analytics/incidents/{incident_id}", response_model=IncidentAnalyticsResponse)
async def get_incident_analytics(incident_id: str):
    """Retrieve historical aggregate metrics for a specific incident."""
    async with get_analytics_session() as session:
        if session is None:
            raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

        try:
            repo = AnalyticsRepository(session)
            res = await repo.get_incident_analytics(incident_id)
            if not res:
                raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
            return IncidentAnalyticsResponse(**res)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve incident analytics") from exc


# ── 3. Risk Analytics ──────────────────────────────────────────────────────

@router.get("/analytics/risk", response_model=RiskAnalyticsResponse)
async def get_risk_analytics(
    from_time: Optional[datetime] = Query(None, description="Start timestamp filter"),
    to_time: Optional[datetime] = Query(None, description="End timestamp filter"),
    incident_id: Optional[str] = Query(None, description="Optional incident ID filter"),
):
    """Retrieve historical risk statistics (MIN, MAX, AVG, trend, category distribution)."""
    validate_time_range(from_time, to_time)

    async with get_analytics_session() as session:
        if session is None:
            return RiskAnalyticsResponse(
                total_predictions=0,
                min_risk=None,
                max_risk=None,
                avg_risk=None,
                latest_risk=None,
                earliest_risk=None,
                risk_trend="INSUFFICIENT_DATA",
                risk_category_distribution={},
                from_time=from_time.isoformat() if from_time else None,
                to_time=to_time.isoformat() if to_time else None,
                incident_id=incident_id,
            )

        try:
            repo = AnalyticsRepository(session)
            data = await repo.get_risk_analytics(from_time=from_time, to_time=to_time, incident_id=incident_id)
            return RiskAnalyticsResponse(
                **data,
                from_time=from_time.isoformat() if from_time else None,
                to_time=to_time.isoformat() if to_time else None,
                incident_id=incident_id,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve risk analytics") from exc


# ── 4. Alert Analytics ─────────────────────────────────────────────────────

@router.get("/analytics/alerts", response_model=AlertAnalyticsResponse)
async def get_alert_analytics(
    from_time: Optional[datetime] = Query(None, description="Start timestamp filter"),
    to_time: Optional[datetime] = Query(None, description="End timestamp filter"),
    incident_id: Optional[str] = Query(None, description="Optional incident ID filter"),
):
    """Retrieve historical alert statistics and distributions."""
    validate_time_range(from_time, to_time)

    async with get_analytics_session() as session:
        if session is None:
            return AlertAnalyticsResponse(
                total_alerts=0,
                severity_distribution={},
                status_distribution={},
                from_time=from_time.isoformat() if from_time else None,
                to_time=to_time.isoformat() if to_time else None,
                incident_id=incident_id,
            )

        try:
            repo = AnalyticsRepository(session)
            data = await repo.get_alert_analytics(from_time=from_time, to_time=to_time, incident_id=incident_id)
            return AlertAnalyticsResponse(
                **data,
                from_time=from_time.isoformat() if from_time else None,
                to_time=to_time.isoformat() if to_time else None,
                incident_id=incident_id,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve alert analytics") from exc


# ── 5. Evacuation Route Analytics ──────────────────────────────────────────

@router.get("/analytics/routes", response_model=RouteAnalyticsResponse)
async def get_route_analytics(
    from_time: Optional[datetime] = Query(None, description="Start timestamp filter"),
    to_time: Optional[datetime] = Query(None, description="End timestamp filter"),
    incident_id: Optional[str] = Query(None, description="Optional incident ID filter"),
):
    """Retrieve historical route statistics (ETA, safety scores, recommendation counts)."""
    validate_time_range(from_time, to_time)

    async with get_analytics_session() as session:
        if session is None:
            return RouteAnalyticsResponse(
                total_routes=0,
                recommended_routes_count=0,
                min_estimated_minutes=None,
                max_estimated_minutes=None,
                avg_estimated_minutes=None,
                min_safety_score=None,
                max_safety_score=None,
                avg_safety_score=None,
                route_type_distribution={},
                from_time=from_time.isoformat() if from_time else None,
                to_time=to_time.isoformat() if to_time else None,
                incident_id=incident_id,
            )

        try:
            repo = AnalyticsRepository(session)
            data = await repo.get_route_analytics(from_time=from_time, to_time=to_time, incident_id=incident_id)
            return RouteAnalyticsResponse(
                **data,
                from_time=from_time.isoformat() if from_time else None,
                to_time=to_time.isoformat() if to_time else None,
                incident_id=incident_id,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve route analytics") from exc


# ── 6. Simulation Analytics ────────────────────────────────────────────────

@router.get("/analytics/simulations", response_model=SimulationAnalyticsResponse)
async def get_simulation_analytics(
    from_time: Optional[datetime] = Query(None, description="Start timestamp filter"),
    to_time: Optional[datetime] = Query(None, description="End timestamp filter"),
    incident_id: Optional[str] = Query(None, description="Optional incident ID filter"),
):
    """Retrieve historical What-If simulation execution statistics and risk deltas."""
    validate_time_range(from_time, to_time)

    async with get_analytics_session() as session:
        if session is None:
            return SimulationAnalyticsResponse(
                total_simulations=0,
                min_baseline_risk=None,
                max_baseline_risk=None,
                avg_baseline_risk=None,
                min_scenario_risk=None,
                max_scenario_risk=None,
                avg_scenario_risk=None,
                min_risk_delta=None,
                max_risk_delta=None,
                avg_risk_delta=None,
                severity_distribution={},
                risk_category_distribution={},
                from_time=from_time.isoformat() if from_time else None,
                to_time=to_time.isoformat() if to_time else None,
                incident_id=incident_id,
            )

        try:
            repo = AnalyticsRepository(session)
            data = await repo.get_simulation_analytics(from_time=from_time, to_time=to_time, incident_id=incident_id)
            return SimulationAnalyticsResponse(
                **data,
                from_time=from_time.isoformat() if from_time else None,
                to_time=to_time.isoformat() if to_time else None,
                incident_id=incident_id,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve simulation analytics") from exc


# ── 7. Telemetry Analytics ─────────────────────────────────────────────────

@router.get("/analytics/telemetry", response_model=TelemetryAnalyticsResponse)
async def get_telemetry_analytics(
    from_time: Optional[datetime] = Query(None, description="Start timestamp filter"),
    to_time: Optional[datetime] = Query(None, description="End timestamp filter"),
    incident_id: Optional[str] = Query(None, description="Optional incident ID filter"),
):
    """Retrieve historical telemetry statistics (rainfall, water level, congestion, provenance)."""
    validate_time_range(from_time, to_time)

    async with get_analytics_session() as session:
        if session is None:
            return TelemetryAnalyticsResponse(
                total_observations=0,
                rainfall_min=None,
                rainfall_max=None,
                rainfall_avg=None,
                water_level_min=None,
                water_level_max=None,
                water_level_avg=None,
                congestion_min=None,
                congestion_max=None,
                congestion_avg=None,
                population_exposure_avg=None,
                infrastructure_vulnerability_avg=None,
                data_mode_distribution={},
                fallback_used_count=0,
                from_time=from_time.isoformat() if from_time else None,
                to_time=to_time.isoformat() if to_time else None,
                incident_id=incident_id,
            )

        try:
            repo = AnalyticsRepository(session)
            data = await repo.get_telemetry_analytics(from_time=from_time, to_time=to_time, incident_id=incident_id)
            return TelemetryAnalyticsResponse(
                **data,
                from_time=from_time.isoformat() if from_time else None,
                to_time=to_time.isoformat() if to_time else None,
                incident_id=incident_id,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to retrieve telemetry analytics") from exc
