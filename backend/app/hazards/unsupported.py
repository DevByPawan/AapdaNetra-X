"""
AapdaNetra-X — Unsupported Hazard Adapter

Phase 6.20.2: Generic adapter for unsupported or demonstration-only hazard types
(LANDSLIDE, CYCLONE, HEATWAVE, EARTHQUAKE). Exposes explicit capability status
and controlled responses without fabricating scores or re-using flood models.
"""
from typing import Dict, Any, Optional

from app.hazards.base import BaseHazardAdapter
from app.hazards.types import (
    HazardType,
    HazardCapabilityStatus,
    HazardEvaluationResult,
    HazardSpatialResult,
    HazardRoutePenaltyResult,
)


class UnsupportedHazardAdapter(BaseHazardAdapter):
    """
    Adapter for unsupported, demonstration-only, or future-extension hazard types.
    Ensures model_available=False, predicted_risk=None, and returns controlled messages.
    """

    def __init__(
        self,
        hazard_type: HazardType,
        status: HazardCapabilityStatus = HazardCapabilityStatus.FUTURE_EXTENSION,
        description: str = "Hazard capability not operational.",
    ):
        self._hazard_type = hazard_type
        self._status = status
        self._description = description

    def get_hazard_type(self) -> HazardType:
        return self._hazard_type

    def evaluate_risk(
        self, telemetry_features: Optional[Dict[str, float]] = None
    ) -> HazardEvaluationResult:
        """Returns typed evaluation result indicating model is unavailable."""
        return HazardEvaluationResult(
            hazard_type=self._hazard_type,
            supported=False,
            model_available=False,
            predicted_risk=None,
            risk_category=None,
            confidence=None,
            provenance=f"{self._hazard_type.value} model specification",
            disclaimer=f"{self._hazard_type.value.capitalize()} risk model is not operational; independent prediction unavailable.",
            message=f"{self._hazard_type.value.capitalize()} risk evaluation unavailable ({self._status.value}).",
            features_used={},
            details={"capability_status": self._status.value},
        )

    def evaluate_spatial_hazard(
        self, point_geom: Any = None, lat: Optional[float] = None, lon: Optional[float] = None
    ) -> HazardSpatialResult:
        """Returns typed spatial result indicating spatial model is unavailable."""
        return HazardSpatialResult(
            hazard_type=self._hazard_type,
            spatial_available=False,
            spatial_hazard_score=None,
            provenance=f"{self._hazard_type.value} spatial specification",
            message=f"{self._hazard_type.value.capitalize()} spatial hazard model unavailable ({self._status.value}).",
            details={"capability_status": self._status.value},
        )

    def get_route_penalty(self, route_segment: Any = None) -> HazardRoutePenaltyResult:
        """Returns typed route penalty result indicating routing is unavailable."""
        return HazardRoutePenaltyResult(
            hazard_type=self._hazard_type,
            routing_available=False,
            penalty_score=None,
            provenance=f"{self._hazard_type.value} routing specification",
            message=f"{self._hazard_type.value.capitalize()} route penalty model unavailable ({self._status.value}).",
            details={"capability_status": self._status.value},
        )
