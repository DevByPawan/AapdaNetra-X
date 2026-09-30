"""
AapdaNetra-X — Base Hazard Adapter Contract

Phase 6.20.2: Defines abstract BaseHazardAdapter contract that all domain hazard
adapters must fulfill.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from app.hazards.types import (
    HazardType,
    HazardEvaluationResult,
    HazardSpatialResult,
    HazardRoutePenaltyResult,
)


class BaseHazardAdapter(ABC):
    """Abstract base adapter for hazard-specific evaluation and capabilities."""

    @abstractmethod
    def get_hazard_type(self) -> HazardType:
        """Returns the HazardType handled by this adapter."""
        pass

    @abstractmethod
    def evaluate_risk(
        self, telemetry_features: Optional[Dict[str, float]] = None
    ) -> HazardEvaluationResult:
        """
        Evaluates hazard risk for given input features.
        Must return typed HazardEvaluationResult communicating status cleanly.
        """
        pass

    @abstractmethod
    def evaluate_spatial_hazard(
        self, point_geom: Any = None, lat: Optional[float] = None, lon: Optional[float] = None
    ) -> HazardSpatialResult:
        """
        Evaluates spatial hazard score at given coordinates or geometry.
        Must return typed HazardSpatialResult communicating status cleanly.
        """
        pass

    @abstractmethod
    def get_route_penalty(self, route_segment: Any = None) -> HazardRoutePenaltyResult:
        """
        Calculates routing penalty for given route segment.
        Must return typed HazardRoutePenaltyResult communicating status cleanly.
        """
        pass
