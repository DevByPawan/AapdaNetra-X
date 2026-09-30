"""
AapdaNetra-X — Extreme Rainfall Hazard Adapter

Phase 6.20.2: Represents PARTIALLY_SUPPORTED extreme rainfall capabilities.
Contextual rainfall observations are handled through the hydro-meteorological flood telemetry pipeline.
Does NOT claim an independent ML model or fabricated prediction scores.
"""
from typing import Dict, Any, Optional

from app.hazards.base import BaseHazardAdapter
from app.hazards.types import (
    HazardType,
    HazardEvaluationResult,
    HazardSpatialResult,
    HazardRoutePenaltyResult,
)


class ExtremeRainfallHazardAdapter(BaseHazardAdapter):
    """
    Adapter for EXTREME_RAINFALL hazard type.
    Represents partial support via shared rainfall telemetry feed.
    Does NOT claim an independent ML model or fake spatial risk score.
    """

    def get_hazard_type(self) -> HazardType:
        return HazardType.EXTREME_RAINFALL

    def evaluate_risk(
        self, telemetry_features: Optional[Dict[str, float]] = None
    ) -> HazardEvaluationResult:
        """Communicates partial support cleanly without fabricating independent ML scores."""
        rain_intensity = (telemetry_features or {}).get("rainfall_intensity")
        rain_trend = (telemetry_features or {}).get("rainfall_trend")

        features_used = {}
        if rain_intensity is not None:
            features_used["rainfall_intensity"] = float(rain_intensity)
        if rain_trend is not None:
            features_used["rainfall_trend"] = float(rain_trend)

        return HazardEvaluationResult(
            hazard_type=HazardType.EXTREME_RAINFALL,
            supported=True,
            model_available=False,
            predicted_risk=None,
            risk_category=None,
            confidence=None,
            provenance="Hydro-meteorological rainfall telemetry observation feed",
            disclaimer="Extreme rainfall is evaluated as a component input to flood risk rather than an independent physical model.",
            message="Extreme rainfall telemetry observed; independent ML model unavailable.",
            features_used=features_used,
            details={"shared_pipeline": "flood"},
        )

    def evaluate_spatial_hazard(
        self, point_geom: Any = None, lat: Optional[float] = None, lon: Optional[float] = None
    ) -> HazardSpatialResult:
        """Communicates spatial capability availability without fabricating fake GIS scores."""
        return HazardSpatialResult(
            hazard_type=HazardType.EXTREME_RAINFALL,
            spatial_available=False,
            spatial_hazard_score=None,
            provenance="hydro-meteorological weather telemetry",
            message="No independent extreme rainfall spatial hazard model exists.",
            details={"grid_proxy": True},
        )

    def get_route_penalty(self, route_segment: Any = None) -> HazardRoutePenaltyResult:
        """Communicates route penalty availability cleanly."""
        return HazardRoutePenaltyResult(
            hazard_type=HazardType.EXTREME_RAINFALL,
            routing_available=False,
            penalty_score=None,
            provenance="Extreme rainfall route penalty specification",
            message="Independent extreme rainfall route penalty unavailable.",
            details={},
        )
