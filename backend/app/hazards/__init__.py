"""
AapdaNetra-X — Multi-Hazard Architecture Package
"""
from app.hazards.types import (
    HazardType,
    HazardCapabilityStatus,
    HazardDefinition,
    HazardEvaluationResult,
    HazardSpatialResult,
    HazardRoutePenaltyResult,
    HazardContributionSummary,
    ExcludedHazardSummary,
    MultiHazardRiskAggregate,
)
from app.hazards.base import BaseHazardAdapter
from app.hazards.flood import FloodHazardAdapter
from app.hazards.extreme_rainfall import ExtremeRainfallHazardAdapter
from app.hazards.unsupported import UnsupportedHazardAdapter
from app.hazards.registry import HazardRegistry, get_hazard_registry
from app.hazards.aggregation import MultiHazardRiskAggregator

__all__ = [
    "HazardType",
    "HazardCapabilityStatus",
    "HazardDefinition",
    "HazardEvaluationResult",
    "HazardSpatialResult",
    "HazardRoutePenaltyResult",
    "HazardContributionSummary",
    "ExcludedHazardSummary",
    "MultiHazardRiskAggregate",
    "BaseHazardAdapter",
    "FloodHazardAdapter",
    "ExtremeRainfallHazardAdapter",
    "UnsupportedHazardAdapter",
    "HazardRegistry",
    "get_hazard_registry",
    "MultiHazardRiskAggregator",
]
