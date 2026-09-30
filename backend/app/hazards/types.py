"""
AapdaNetra-X — Multi-Hazard Architecture Enums and Type Definitions

Phase 6.20.1: Defines core hazard enums, capability status classifications,
and hazard definition data models.
"""
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class HazardType(str, Enum):
    """Enumeration of system hazard types."""
    FLOOD = "flood"
    EXTREME_RAINFALL = "extreme_rainfall"
    LANDSLIDE = "landslide"
    CYCLONE = "cyclone"
    HEATWAVE = "heatwave"
    EARTHQUAKE = "earthquake"


class HazardCapabilityStatus(str, Enum):
    """Capability status classification for hazard types."""
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    DEMONSTRATION_ONLY = "DEMONSTRATION_ONLY"
    FUTURE_EXTENSION = "FUTURE_EXTENSION"


class HazardDefinition(BaseModel):
    """Typed metadata and capability definition for a specific hazard."""
    hazard_type: HazardType
    display_name: str
    capability_status: HazardCapabilityStatus
    description: str
    supported: bool = False
    model_available: bool = False
    spatial_available: bool = False
    telemetry_available: bool = False
    alerts_available: bool = False
    routing_available: bool = False
    decision_support_available: bool = False
    provenance: str
    disclaimer: str
    supported_features: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HazardEvaluationResult(BaseModel):
    """Result container for hazard-specific risk evaluation."""
    hazard_type: HazardType
    supported: bool = False
    model_available: bool = False
    predicted_risk: Optional[float] = None
    risk_category: Optional[str] = None
    confidence: Optional[float] = None
    provenance: str
    disclaimer: str
    message: str
    features_used: Dict[str, float] = Field(default_factory=dict)
    details: Dict[str, Any] = Field(default_factory=dict)


class HazardSpatialResult(BaseModel):
    """Result container for hazard-specific spatial risk evaluation."""
    hazard_type: HazardType
    spatial_available: bool = False
    spatial_hazard_score: Optional[float] = None
    provenance: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class HazardRoutePenaltyResult(BaseModel):
    """Result container for hazard-specific route penalty evaluation."""
    hazard_type: HazardType
    routing_available: bool = False
    penalty_score: Optional[float] = None
    provenance: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class HazardContributionSummary(BaseModel):
    """Summary of an operational hazard contributing to composite risk."""
    hazard_type: HazardType
    capability_status: HazardCapabilityStatus
    contributed: bool = True
    risk: Optional[float] = None
    reason: str
    provenance: str


class ExcludedHazardSummary(BaseModel):
    """Summary of a non-contributing or unsupported hazard excluded from composite risk."""
    hazard_type: HazardType
    capability_status: HazardCapabilityStatus
    risk: Optional[float] = None
    reason: str


class MultiHazardRiskAggregate(BaseModel):
    """Aggregated multi-hazard risk container representing composite risk and explicit hazard breakdown."""
    composite_risk: Optional[float] = None
    primary_hazard_driver: Optional[HazardType] = None
    contributing_hazards: List[HazardContributionSummary] = Field(default_factory=list)
    excluded_hazards: List[ExcludedHazardSummary] = Field(default_factory=list)
    hazard_breakdown: Dict[str, Any] = Field(default_factory=dict)
    aggregation_policy: str = "MAX_SEVERITY_OPERATIONAL_HAZARD"
    provenance: str = "Multi-hazard decision-support aggregation service"
    disclaimer: str = (
        "Multi-hazard composite risk reflects operational supported hazard risk models only. "
        "Unsupported or proxy hazard capabilities are explicitly excluded and not converted to zero risk."
    )
    explanation_hazard: Optional[HazardType] = None
    primary_hazard_uncertainty: Optional[Dict[str, Any]] = None
    details: Dict[str, Any] = Field(default_factory=dict)
