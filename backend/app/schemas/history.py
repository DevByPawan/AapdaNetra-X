"""AapdaNetra-X — Historical API Schemas

Defines Pydantic response models and envelopes for historical data endpoints.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class CursorInfo(BaseModel):
    """Cursor metadata for keyset pagination continuation."""

    timestamp: str = Field(..., description="ISO 8601 UTC timestamp threshold")
    id: str = Field(..., description="ID tie-breaker string")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standardized envelope for historical collection endpoints."""

    items: List[T] = Field(default_factory=list, description="Historical data items")
    next_cursor: Optional[CursorInfo] = Field(
        default=None, description="Cursor for fetching the next page"
    )
    has_more: bool = Field(default=False, description="Whether more records exist")


class IncidentHistoryItem(BaseModel):
    """DTO for historical Incident records."""

    id: str
    incident_type: str
    status: str
    started_at: str
    sector: str
    severity: str
    location_name: str
    latitude: float
    longitude: float
    created_at: str
    updated_at: str


class TelemetryHistoryItem(BaseModel):
    """DTO for historical TelemetryObservation records."""

    id: str
    incident_id: Optional[str] = None
    hazard_type: Optional[str] = "flood"
    data_mode: str
    fallback_used: bool
    rainfall_intensity: float
    rainfall_trend: float
    water_level: float
    water_level_trend: float
    road_congestion: float
    population_exposure: float
    infrastructure_vulnerability: float
    location_name: Optional[str] = None
    provenance: Dict[str, Any] = Field(default_factory=dict)
    observed_at: str
    created_at: str


class RiskHistoryItem(BaseModel):
    """DTO for historical RiskPrediction records."""

    id: str
    incident_id: str
    hazard_type: Optional[str] = "flood"
    telemetry_id: Optional[str] = None
    horizon: int
    horizon_label: str
    current_risk: float
    predicted_risk: float
    risk_category: str
    confidence: float
    prediction_reliability: float
    affected_population: int
    critical_population: int
    critical_assets_count: int
    affected_assets_count: int
    trend: str
    map_status_text: str
    prediction_note: str
    input_features: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class RouteHistoryItem(BaseModel):
    """DTO for historical EvacuationRoute records."""

    id: str
    incident_id: str
    hazard_type: Optional[str] = "flood"
    risk_prediction_id: Optional[str] = None
    route_name: str
    route_type: str
    is_recommended: bool
    origin_name: str
    origin_lat: float
    origin_lon: float
    destination_name: str
    destination_lat: float
    destination_lon: float
    waypoint_coords: List[Any] = Field(default_factory=list)
    distance_km: float
    estimated_minutes: float
    safety_score: float
    congestion_index: float = 0.0
    created_at: str


class AuditHistoryItem(BaseModel):
    """DTO for historical AuditEvent records."""

    id: str
    incident_id: Optional[str] = None
    hazard_type: Optional[str] = "flood"
    event_type: str
    severity: str
    source: str
    description: str
    actor: Optional[str] = None
    event_data: Optional[Dict[str, Any]] = None
    created_at: str


class SHAPHistoryResponse(BaseModel):
    """DTO for historical SHAPRecord explainability lookups."""

    id: str
    risk_prediction_id: str
    hazard_type: Optional[str] = "flood"
    horizon: int
    prediction: float
    base_value: float
    total_shap_delta: float
    features: Dict[str, Any] = Field(default_factory=dict)
    decision_trace: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str


class TimelineEventItem(BaseModel):
    """DTO for a normalized incident timeline event."""

    timestamp: str = Field(..., description="ISO 8601 UTC event timestamp")
    event_type: str = Field(..., description="Normalized domain event type")
    entity_type: str = Field(..., description="Source ORM entity type name")
    entity_id: str = Field(..., description="Unique entity primary key ID")
    incident_id: str = Field(..., description="Associated disaster incident ID")
    hazard_type: Optional[str] = Field(default="flood", description="Hazard type classification")
    summary: str = Field(..., description="Human-readable event summary line")
    details: Dict[str, Any] = Field(
        default_factory=dict, description="Lightweight sanitized metadata payload"
    )

