"""
AapdaNetra-X — Central Hazard Registry

Phase 6.20.1: Singleton/immutable registry mapping all 6 HazardTypes
to their capability status, metadata, and operational support flags.
"""
from typing import Dict, List, Optional, Any
from app.hazards.types import HazardType, HazardCapabilityStatus, HazardDefinition
from app.hazards.base import BaseHazardAdapter
from app.hazards.flood import FloodHazardAdapter
from app.hazards.extreme_rainfall import ExtremeRainfallHazardAdapter
from app.hazards.unsupported import UnsupportedHazardAdapter


class HazardRegistry:
    """Central registry maintaining hazard metadata, operational capabilities, and adapters."""

    def __init__(self) -> None:
        self._registry: Dict[HazardType, HazardDefinition] = {}
        self._adapters: Dict[HazardType, BaseHazardAdapter] = {}
        self._initialize_defaults()

    def _initialize_defaults(self) -> None:
        # 1. FLOOD: Fully supported disaster pipeline model
        self._registry[HazardType.FLOOD] = HazardDefinition(
            hazard_type=HazardType.FLOOD,
            display_name="Flood Risk",
            capability_status=HazardCapabilityStatus.SUPPORTED,
            description="Hydro-meteorological riverine and flash flood risk estimation.",
            supported=True,
            model_available=True,
            spatial_available=True,
            telemetry_available=True,
            alerts_available=True,
            routing_available=True,
            decision_support_available=True,
            provenance="scikit-learn GBR 7-feature model (synthetic disaster dataset)",
            disclaimer="The flood prediction engine is synthetic-trained for demonstration and operational decision support only.",
            supported_features=[
                "rainfall_intensity",
                "rainfall_trend",
                "water_level",
                "water_level_trend",
                "road_congestion",
                "population_exposure",
                "infrastructure_vulnerability",
            ],
            metadata={
                "model_type": "GradientBoostingRegressor",
                "canonical_features": 7,
                "is_flood_specific": True,
            },
        )

        # 2. EXTREME_RAINFALL: Partially supported via flood telemetry pipeline
        self._registry[HazardType.EXTREME_RAINFALL] = HazardDefinition(
            hazard_type=HazardType.EXTREME_RAINFALL,
            display_name="Extreme Rainfall",
            capability_status=HazardCapabilityStatus.PARTIALLY_SUPPORTED,
            description="Heavy rainfall intensity monitoring handled through the hydro-meteorological telemetry pipeline.",
            supported=True,
            model_available=False,  # Handled through flood pipeline, not an independent ML model
            spatial_available=False,
            telemetry_available=True,
            alerts_available=True,
            routing_available=False,
            decision_support_available=False,
            provenance="Hydro-meteorological telemetry observation feed",
            disclaimer="Extreme rainfall is evaluated as a component input to flood risk rather than an independent physical model.",
            supported_features=["rainfall_intensity", "rainfall_trend"],
            metadata={"shared_pipeline": "flood"},
        )

        # 3. LANDSLIDE: Demonstration only / slope vulnerability proxy
        self._registry[HazardType.LANDSLIDE] = HazardDefinition(
            hazard_type=HazardType.LANDSLIDE,
            display_name="Landslide Risk",
            capability_status=HazardCapabilityStatus.DEMONSTRATION_ONLY,
            description="Slope instability and terrain susceptibility proxy.",
            supported=False,
            model_available=False,
            spatial_available=False,
            telemetry_available=False,
            alerts_available=False,
            routing_available=False,
            decision_support_available=False,
            provenance="Provisional terrain slope proxy",
            disclaimer="Landslide risk modeling is not operational; model unavailable.",
            supported_features=[],
            metadata={},
        )

        # 4. CYCLONE: Future extension
        self._registry[HazardType.CYCLONE] = HazardDefinition(
            hazard_type=HazardType.CYCLONE,
            display_name="Cyclone Hazard",
            capability_status=HazardCapabilityStatus.FUTURE_EXTENSION,
            description="Tropical cyclone wind and pressure corridor assessment.",
            supported=False,
            model_available=False,
            spatial_available=False,
            telemetry_available=False,
            alerts_available=False,
            routing_available=False,
            decision_support_available=False,
            provenance="Future extension specification",
            disclaimer="Cyclone hazard assessment is not operational.",
            supported_features=[],
            metadata={},
        )

        # 5. HEATWAVE: Future extension
        self._registry[HazardType.HEATWAVE] = HazardDefinition(
            hazard_type=HazardType.HEATWAVE,
            display_name="Heatwave Hazard",
            capability_status=HazardCapabilityStatus.FUTURE_EXTENSION,
            description="Extreme thermal exposure and urban heat island tracking.",
            supported=False,
            model_available=False,
            spatial_available=False,
            telemetry_available=False,
            alerts_available=False,
            routing_available=False,
            decision_support_available=False,
            provenance="Future extension specification",
            disclaimer="Heatwave hazard tracking is not operational.",
            supported_features=[],
            metadata={},
        )

        # 6. EARTHQUAKE: Future extension
        self._registry[HazardType.EARTHQUAKE] = HazardDefinition(
            hazard_type=HazardType.EARTHQUAKE,
            display_name="Earthquake Hazard",
            capability_status=HazardCapabilityStatus.FUTURE_EXTENSION,
            description="Seismic ground motion and structural vulnerability proxy.",
            supported=False,
            model_available=False,
            spatial_available=False,
            telemetry_available=False,
            alerts_available=False,
            routing_available=False,
            decision_support_available=False,
            provenance="Future extension specification",
            disclaimer="Earthquake hazard monitoring is not operational.",
            supported_features=[],
            metadata={},
        )

        # Initialize hazard domain adapters
        self._adapters[HazardType.FLOOD] = FloodHazardAdapter()
        self._adapters[HazardType.EXTREME_RAINFALL] = ExtremeRainfallHazardAdapter()
        self._adapters[HazardType.LANDSLIDE] = UnsupportedHazardAdapter(
            HazardType.LANDSLIDE, HazardCapabilityStatus.DEMONSTRATION_ONLY
        )
        self._adapters[HazardType.CYCLONE] = UnsupportedHazardAdapter(
            HazardType.CYCLONE, HazardCapabilityStatus.FUTURE_EXTENSION
        )
        self._adapters[HazardType.HEATWAVE] = UnsupportedHazardAdapter(
            HazardType.HEATWAVE, HazardCapabilityStatus.FUTURE_EXTENSION
        )
        self._adapters[HazardType.EARTHQUAKE] = UnsupportedHazardAdapter(
            HazardType.EARTHQUAKE, HazardCapabilityStatus.FUTURE_EXTENSION
        )

    def get_adapter(self, hazard_type: HazardType | str) -> BaseHazardAdapter:
        """
        Returns BaseHazardAdapter for requested hazard type.
        Raises ValueError if hazard_type is invalid or unknown.
        """
        if isinstance(hazard_type, str):
            try:
                hazard_type = HazardType(hazard_type.lower())
            except ValueError as exc:
                raise ValueError(f"Unknown or unsupported hazard type: '{hazard_type}'") from exc

        if hazard_type not in self._adapters:
            raise ValueError(f"Unknown hazard type adapter: '{hazard_type}'")

        return self._adapters[hazard_type]

    def get_definition(self, hazard_type: HazardType | str) -> HazardDefinition:
        """
        Returns HazardDefinition for requested hazard type.
        Raises ValueError if hazard_type is invalid or unknown.
        """
        if isinstance(hazard_type, str):
            try:
                hazard_type = HazardType(hazard_type.lower())
            except ValueError as exc:
                raise ValueError(f"Unknown or unsupported hazard type: '{hazard_type}'") from exc

        if hazard_type not in self._registry:
            raise ValueError(f"Unknown hazard type: '{hazard_type}'")

        return self._registry[hazard_type]

    def get_all(self) -> Dict[str, HazardDefinition]:
        """Returns dict of all registered HazardDefinitions keyed by string hazard_type."""
        return {ht.value: defn for ht, defn in self._registry.items()}

    def get_supported(self) -> List[HazardDefinition]:
        """Returns list of HazardDefinitions where supported=True."""
        return [defn for defn in self._registry.values() if defn.supported]

    def is_supported(self, hazard_type: HazardType | str) -> bool:
        """Returns True if hazard_type exists and supported=True."""
        try:
            defn = self.get_definition(hazard_type)
            return defn.supported
        except ValueError:
            return False

    def capability_matrix(self) -> List[Dict[str, Any]]:
        """Returns structured capability matrix summary for all registered hazards."""
        return [
            {
                "hazard_type": defn.hazard_type.value,
                "display_name": defn.display_name,
                "capability_status": defn.capability_status.value,
                "supported": defn.supported,
                "model_available": defn.model_available,
                "spatial_available": defn.spatial_available,
                "telemetry_available": defn.telemetry_available,
                "alerts_available": defn.alerts_available,
                "routing_available": defn.routing_available,
                "decision_support_available": defn.decision_support_available,
                "provenance": defn.provenance,
            }
            for defn in self._registry.values()
        ]


# Singleton instance accessor
_REGISTRY_INSTANCE: Optional[HazardRegistry] = None


def get_hazard_registry() -> HazardRegistry:
    """Returns global singleton HazardRegistry instance."""
    global _REGISTRY_INSTANCE
    if _REGISTRY_INSTANCE is None:
        _REGISTRY_INSTANCE = HazardRegistry()
    return _REGISTRY_INSTANCE
