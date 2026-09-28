"""AapdaNetra-X — Analytics DTO / Schemas

Explicit Pydantic response models for historical analytics endpoints.
"""

from __future__ import annotations

from typing import Dict, Optional
from pydantic import BaseModel, Field


class RiskAnalyticsResponse(BaseModel):
    """Historical risk statistics across persisted risk predictions."""

    total_predictions: int = Field(..., description="Total number of risk predictions recorded")
    min_risk: Optional[float] = Field(None, description="Minimum observed predicted risk")
    max_risk: Optional[float] = Field(None, description="Maximum observed predicted risk")
    avg_risk: Optional[float] = Field(None, description="Average observed predicted risk")
    latest_risk: Optional[float] = Field(None, description="Most recent predicted risk score")
    earliest_risk: Optional[float] = Field(None, description="Oldest predicted risk score in range")
    risk_trend: str = Field(..., description="Observed risk trend label (INCREASING, DECREASING, STABLE, INSUFFICIENT_DATA)")
    risk_category_distribution: Dict[str, int] = Field(default_factory=dict, description="Count of predictions per risk category")
    from_time: Optional[str] = Field(None, description="ISO timestamp start filter")
    to_time: Optional[str] = Field(None, description="ISO timestamp end filter")
    incident_id: Optional[str] = Field(None, description="Incident filter ID if applied")


class IncidentAnalyticsResponse(BaseModel):
    """Historical aggregate statistics for a specific disaster incident."""

    incident_id: str = Field(..., description="Disaster incident ID")
    incident_type: str = Field(..., description="Incident category/type")
    status: str = Field(..., description="Incident current status")
    severity: str = Field(..., description="Incident severity level")
    started_at: str = Field(..., description="ISO timestamp of incident start")
    created_at: str = Field(..., description="ISO timestamp of record creation")
    telemetry_count: int = Field(0, description="Total telemetry observations for incident")
    risk_prediction_count: int = Field(0, description="Total risk predictions for incident")
    route_count: int = Field(0, description="Total evacuation routes generated for incident")
    alert_count: int = Field(0, description="Total emergency alerts for incident")
    simulation_count: int = Field(0, description="Total What-If simulations executed for incident")
    audit_event_count: int = Field(0, description="Total audit events recorded for incident")
    latest_risk: Optional[float] = Field(None, description="Latest predicted risk score for incident")
    max_observed_risk: Optional[float] = Field(None, description="Maximum observed risk for incident")
    avg_observed_risk: Optional[float] = Field(None, description="Average observed risk for incident")


class AlertAnalyticsResponse(BaseModel):
    """Historical alert statistics."""

    total_alerts: int = Field(..., description="Total emergency alerts generated")
    severity_distribution: Dict[str, int] = Field(default_factory=dict, description="Alert counts grouped by severity")
    status_distribution: Dict[str, int] = Field(default_factory=dict, description="Alert counts grouped by lifecycle status")
    from_time: Optional[str] = Field(None, description="ISO timestamp start filter")
    to_time: Optional[str] = Field(None, description="ISO timestamp end filter")
    incident_id: Optional[str] = Field(None, description="Incident filter ID if applied")


class RouteAnalyticsResponse(BaseModel):
    """Historical evacuation route calculation statistics."""

    total_routes: int = Field(..., description="Total evacuation routes generated")
    recommended_routes_count: int = Field(0, description="Number of routes marked as recommended")
    min_estimated_minutes: Optional[float] = Field(None, description="Minimum estimated travel duration in minutes")
    max_estimated_minutes: Optional[float] = Field(None, description="Maximum estimated travel duration in minutes")
    avg_estimated_minutes: Optional[float] = Field(None, description="Average estimated travel duration in minutes")
    min_safety_score: Optional[float] = Field(None, description="Minimum route safety score")
    max_safety_score: Optional[float] = Field(None, description="Maximum route safety score")
    avg_safety_score: Optional[float] = Field(None, description="Average route safety score")
    route_type_distribution: Dict[str, int] = Field(default_factory=dict, description="Route count per route type")
    from_time: Optional[str] = Field(None, description="ISO timestamp start filter")
    to_time: Optional[str] = Field(None, description="ISO timestamp end filter")
    incident_id: Optional[str] = Field(None, description="Incident filter ID if applied")


class SimulationAnalyticsResponse(BaseModel):
    """Historical What-If simulation execution statistics."""

    total_simulations: int = Field(..., description="Total simulation runs executed")
    min_baseline_risk: Optional[float] = Field(None, description="Minimum baseline risk in simulations")
    max_baseline_risk: Optional[float] = Field(None, description="Maximum baseline risk in simulations")
    avg_baseline_risk: Optional[float] = Field(None, description="Average baseline risk in simulations")
    min_scenario_risk: Optional[float] = Field(None, description="Minimum scenario risk in simulations")
    max_scenario_risk: Optional[float] = Field(None, description="Maximum scenario risk in simulations")
    avg_scenario_risk: Optional[float] = Field(None, description="Average scenario risk in simulations")
    min_risk_delta: Optional[float] = Field(None, description="Minimum risk delta resulting from simulations")
    max_risk_delta: Optional[float] = Field(None, description="Maximum risk delta resulting from simulations")
    avg_risk_delta: Optional[float] = Field(None, description="Average risk delta resulting from simulations")
    severity_distribution: Dict[str, int] = Field(default_factory=dict, description="Simulations grouped by severity")
    risk_category_distribution: Dict[str, int] = Field(default_factory=dict, description="Simulations grouped by resulting risk category")
    from_time: Optional[str] = Field(None, description="ISO timestamp start filter")
    to_time: Optional[str] = Field(None, description="ISO timestamp end filter")
    incident_id: Optional[str] = Field(None, description="Incident filter ID if applied")


class TelemetryAnalyticsResponse(BaseModel):
    """Historical hydro-meteorological telemetry observation statistics."""

    total_observations: int = Field(..., description="Total telemetry snapshots recorded")
    rainfall_min: Optional[float] = Field(None, description="Minimum observed rainfall intensity")
    rainfall_max: Optional[float] = Field(None, description="Maximum observed rainfall intensity")
    rainfall_avg: Optional[float] = Field(None, description="Average observed rainfall intensity")
    water_level_min: Optional[float] = Field(None, description="Minimum observed water level")
    water_level_max: Optional[float] = Field(None, description="Maximum observed water level")
    water_level_avg: Optional[float] = Field(None, description="Average observed water level")
    congestion_min: Optional[float] = Field(None, description="Minimum observed road congestion")
    congestion_max: Optional[float] = Field(None, description="Maximum observed road congestion")
    congestion_avg: Optional[float] = Field(None, description="Average observed road congestion")
    population_exposure_avg: Optional[float] = Field(None, description="Average population exposure index")
    infrastructure_vulnerability_avg: Optional[float] = Field(None, description="Average infrastructure vulnerability index")
    data_mode_distribution: Dict[str, int] = Field(default_factory=dict, description="Observations grouped by data mode (e.g. simulated, live, hybrid)")
    fallback_used_count: int = Field(0, description="Count of observations using fallback data")
    from_time: Optional[str] = Field(None, description="ISO timestamp start filter")
    to_time: Optional[str] = Field(None, description="ISO timestamp end filter")
    incident_id: Optional[str] = Field(None, description="Incident filter ID if applied")
    data_provenance_note: str = Field(
        "Telemetry contains synthetic/simulated observations during testing/demonstration modes. Provenance metadata is preserved per observation.",
        description="Scientific provenance statement regarding synthetic vs live observation data"
    )


class AnalyticsOverviewResponse(BaseModel):
    """System-wide historical analytics overview across all domain entities."""

    total_incidents: int = Field(..., description="Total persisted incidents")
    active_incidents: int = Field(..., description="Currently active incidents")
    total_telemetry_observations: int = Field(..., description="Total telemetry observations")
    total_risk_predictions: int = Field(..., description="Total risk predictions")
    total_alerts: int = Field(..., description="Total emergency alerts")
    total_evacuation_routes: int = Field(..., description="Total evacuation routes")
    total_simulations: int = Field(..., description="Total What-If simulations")
    total_audit_events: int = Field(..., description="Total system audit events")
    avg_system_risk: Optional[float] = Field(None, description="Average risk prediction across all records")
    max_system_risk: Optional[float] = Field(None, description="Maximum risk prediction across all records")
    from_time: Optional[str] = Field(None, description="ISO timestamp start filter")
    to_time: Optional[str] = Field(None, description="ISO timestamp end filter")
