"""
AapdaNetra-X — Data Adapter Orchestrator
Merges live & dataset provider feeds with existing BASE_SENSOR_FEATURES defaults.
Produces the exact 7-key feature dict expected by the ML pipeline.

Design & Mode Semantics:
  - 'simulated': Returns BASE_SENSOR_FEATURES unchanged. No external calls.
  - 'hybrid': Merges live/dataset feeds where available. Uses simulated defaults for unconfigured feeds.
  - 'live': Attempts configured real providers for all 7 features. If ENABLE_FALLBACK=false and data is missing, marks fallback_used=True and missing status rather than pretending features are live.
"""
import logging
from typing import Dict, Optional, Any

from app.data.providers.base import DataProviderStatus
from app.data.providers.weather_adapter import WeatherAdapter
from app.data.providers.water_level_adapter import WaterLevelAdapter
from app.data.providers.traffic_adapter import TrafficAdapter
from app.data.providers.population_adapter import PopulationAdapter
from app.data.providers.infrastructure_adapter import InfrastructureAdapter

logger = logging.getLogger("aapdanetra.data_adapter")

# Canonical simulated baseline (imported by risk_engine.py)
BASE_SENSOR_FEATURES = {
    "rainfall_intensity": 95.0,
    "rainfall_trend": 12.0,
    "water_level": 6.8,
    "water_level_trend": 0.45,
    "road_congestion": 0.72,
    "population_exposure": 12430.0,
    "infrastructure_vulnerability": 0.78,
}


class DataAdapter:
    """
    Central data orchestrator. Merges live/dataset provider values with simulated defaults
    to produce the exact 7-key feature dict consumed by validate_and_clean_features().
    """

    def __init__(
        self,
        data_mode: str = "simulated",
        enable_fallback: bool = True,
        weather_adapter: Optional[WeatherAdapter] = None,
        water_level_adapter: Optional[WaterLevelAdapter] = None,
        traffic_adapter: Optional[TrafficAdapter] = None,
        population_adapter: Optional[PopulationAdapter] = None,
        infrastructure_adapter: Optional[InfrastructureAdapter] = None,
    ):
        self.data_mode = data_mode
        self.enable_fallback = enable_fallback
        self.weather_adapter = weather_adapter
        self.water_level_adapter = water_level_adapter
        self.traffic_adapter = traffic_adapter
        self.population_adapter = population_adapter
        self.infrastructure_adapter = infrastructure_adapter

        # Per-feature provenance tracking
        self._provenance: Dict[str, str] = {}
        self.fallback_used: bool = False

    def get_base_features(self) -> Dict[str, float]:
        """
        Returns the 7-key base feature dict.

        In 'simulated' mode: returns BASE_SENSOR_FEATURES unchanged.
        In 'hybrid' / 'live' mode: queries providers and merges with defaults according to policy.
        """
        if self.data_mode == "simulated":
            self._provenance = {k: "simulated" for k in BASE_SENSOR_FEATURES}
            self.fallback_used = False
            return dict(BASE_SENSOR_FEATURES)

        merged = dict(BASE_SENSOR_FEATURES)
        self._provenance = {k: "simulated" for k in BASE_SENSOR_FEATURES}
        self.fallback_used = False

        # 1. Weather provider
        if self.weather_adapter is not None:
            try:
                weather_data = self.weather_adapter.get_features()
                for key in ["rainfall_intensity", "rainfall_trend"]:
                    val = weather_data.get(key)
                    if val is not None:
                        merged[key] = float(val)
                        self._provenance[key] = "live:weather"
                    else:
                        self._record_fallback(key)
            except Exception as e:
                logger.warning(f"[DataAdapter] Weather adapter error: {e}")
                self._record_fallback("rainfall_intensity")
                self._record_fallback("rainfall_trend")
        else:
            self._record_fallback("rainfall_intensity")
            self._record_fallback("rainfall_trend")

        # 2. Water level provider
        if self.water_level_adapter is not None:
            try:
                water_data = self.water_level_adapter.get_features()
                for key in ["water_level", "water_level_trend"]:
                    val = water_data.get(key)
                    if val is not None:
                        merged[key] = float(val)
                        self._provenance[key] = "live:water_level"
                    else:
                        self._record_fallback(key)
            except Exception as e:
                logger.warning(f"[DataAdapter] Water level adapter error: {e}")
                self._record_fallback("water_level")
                self._record_fallback("water_level_trend")
        else:
            self._record_fallback("water_level")
            self._record_fallback("water_level_trend")

        # 3. Traffic provider
        if self.traffic_adapter is not None:
            try:
                traffic_data = self.traffic_adapter.get_features()
                val = traffic_data.get("road_congestion")
                if val is not None:
                    merged["road_congestion"] = float(val)
                    self._provenance["road_congestion"] = "live:traffic_adapter"
                else:
                    self._record_fallback("road_congestion")
            except Exception as e:
                logger.warning(f"[DataAdapter] Traffic adapter error: {e}")
                self._record_fallback("road_congestion")
        else:
            self._record_fallback("road_congestion")

        # 4. Population dataset provider
        if self.population_adapter is not None:
            try:
                pop_data = self.population_adapter.get_features()
                val = pop_data.get("population_exposure")
                if val is not None:
                    merged["population_exposure"] = float(val)
                    self._provenance["population_exposure"] = self.population_adapter.dataset_source
                else:
                    self._record_fallback("population_exposure")
            except Exception as e:
                logger.warning(f"[DataAdapter] Population adapter error: {e}")
                self._record_fallback("population_exposure")
        else:
            self._record_fallback("population_exposure")

        # 5. Infrastructure dataset provider
        if self.infrastructure_adapter is not None:
            try:
                infra_data = self.infrastructure_adapter.get_features()
                val = infra_data.get("infrastructure_vulnerability")
                if val is not None:
                    merged["infrastructure_vulnerability"] = float(val)
                    self._provenance["infrastructure_vulnerability"] = self.infrastructure_adapter.dataset_source
                else:
                    self._record_fallback("infrastructure_vulnerability")
            except Exception as e:
                logger.warning(f"[DataAdapter] Infrastructure adapter error: {e}")
                self._record_fallback("infrastructure_vulnerability")
        else:
            self._record_fallback("infrastructure_vulnerability")

        logger.info(f"[DataAdapter] Feature provenance ({self.data_mode}): {self._provenance}")
        return merged

    def _record_fallback(self, feature_key: str):
        """Records fallback provenance based on data_mode and enable_fallback settings."""
        self.fallback_used = True
        if self.data_mode == "live" and not self.enable_fallback:
            self._provenance[feature_key] = "missing:no_fallback"
        else:
            self._provenance[feature_key] = "fallback:simulated"

    @property
    def provenance(self) -> Dict[str, str]:
        """Returns per-feature provenance from the last get_base_features() call."""
        return dict(self._provenance)

    def get_telemetry_metadata(self) -> Dict[str, Any]:
        """
        Returns structured telemetry status and metadata for observability.
        Omits any API keys, credentials, or authorization headers.
        """
        weather_meta = {
            "status": self.weather_adapter.status.value if self.weather_adapter else "not_configured",
            "source": self.weather_adapter.provider_name if self.weather_adapter else "none",
            "observed_at": getattr(self.weather_adapter, "observed_at", None),
            "age_seconds": getattr(self.weather_adapter, "age_seconds", None),
            "stale": getattr(self.weather_adapter, "is_stale", False),
        }

        water_meta = {
            "status": self.water_level_adapter.status.value if self.water_level_adapter else "not_configured",
            "source": getattr(self.water_level_adapter, "source", "none"),
            "observed_at": getattr(self.water_level_adapter, "observed_at", None),
            "age_seconds": getattr(self.water_level_adapter, "age_seconds", None),
            "stale": getattr(self.water_level_adapter, "is_stale", False),
        }

        traffic_meta = {
            "status": self.traffic_adapter.status.value if self.traffic_adapter else "not_configured",
            "source": self.traffic_adapter.provider_name if self.traffic_adapter else "none",
            "observed_at": getattr(self.traffic_adapter, "observed_at", None),
            "age_seconds": getattr(self.traffic_adapter, "age_seconds", None),
            "stale": getattr(self.traffic_adapter, "is_stale", False),
        }

        pop_meta = {
            "status": self.population_adapter.status.value if self.population_adapter else "not_configured",
            "source": getattr(self.population_adapter, "dataset_source", "none"),
            "dataset_version": getattr(self.population_adapter, "dataset_version", None),
            "observed_at": getattr(self.population_adapter, "observed_at", None),
            "age_seconds": getattr(self.population_adapter, "age_seconds", None),
            "stale": getattr(self.population_adapter, "is_stale", False),
        }

        infra_meta = {
            "status": self.infrastructure_adapter.status.value if self.infrastructure_adapter else "not_configured",
            "source": getattr(self.infrastructure_adapter, "dataset_source", "none"),
            "dataset_version": getattr(self.infrastructure_adapter, "dataset_version", None),
            "observed_at": getattr(self.infrastructure_adapter, "observed_at", None),
            "age_seconds": getattr(self.infrastructure_adapter, "age_seconds", None),
            "stale": getattr(self.infrastructure_adapter, "is_stale", False),
        }

        return {
            "data_mode": self.data_mode,
            "fallback_used": self.fallback_used,
            "providers": {
                "weather": weather_meta,
                "water_level": water_meta,
                "traffic": traffic_meta,
                "population": pop_meta,
                "infrastructure": infra_meta,
            },
            "provenance": dict(self._provenance),
        }

    @property
    def provider_statuses(self) -> Dict[str, str]:
        """Returns status summary of all configured providers."""
        statuses: Dict[str, str] = {"data_mode": self.data_mode}
        for name, adapter in [
            ("weather", self.weather_adapter),
            ("water_level", self.water_level_adapter),
            ("traffic", self.traffic_adapter),
            ("population", self.population_adapter),
            ("infrastructure", self.infrastructure_adapter),
        ]:
            if adapter is not None:
                st = getattr(adapter, "status", None)
                statuses[name] = st.value if hasattr(st, "value") else str(st)
            else:
                statuses[name] = "not_configured"

        return statuses


# ── Global Singleton Instance & Accessor ─────────────────────────────────
_global_adapter: Optional[DataAdapter] = None


def get_data_adapter() -> DataAdapter:
    """Returns singleton DataAdapter, lazily initialized from app settings."""
    global _global_adapter
    if _global_adapter is None:
        _global_adapter = _create_adapter_from_settings()
    return _global_adapter


def _create_adapter_from_settings() -> DataAdapter:
    """Creates a DataAdapter from the current app.config.settings."""
    from app.config import settings
    from pathlib import Path

    data_mode = settings.data_mode
    enable_fallback = getattr(settings, "enable_fallback", True)

    weather = None
    if data_mode in ("live", "hybrid") and settings.openweathermap_api_key:
        weather = WeatherAdapter(
            api_key=settings.openweathermap_api_key,
            lat=settings.openweathermap_lat,
            lon=settings.openweathermap_lon,
            cache_ttl=settings.weather_cache_ttl,
        )

    water_level = None
    if data_mode in ("live", "hybrid"):
        water_level = WaterLevelAdapter(
            source=settings.water_level_source,
            cache_ttl=getattr(settings, "water_level_cache_ttl", 60),
        )

    traffic = None
    if data_mode in ("live", "hybrid") and getattr(settings, "traffic_api_url", ""):
        traffic = TrafficAdapter(
            api_key=getattr(settings, "traffic_api_key", ""),
            endpoint_url=getattr(settings, "traffic_api_url", ""),
            cache_ttl=getattr(settings, "traffic_cache_ttl", 180),
        )

    population = None
    pop_path = getattr(settings, "population_dataset_path", "")
    if not pop_path:
        default_pop = Path(__file__).resolve().parent.parent / "population_delhi_sample.json"
        if default_pop.exists():
            pop_path = str(default_pop)
    if data_mode in ("live", "hybrid") and pop_path and Path(pop_path).exists():
        population = PopulationAdapter(
            dataset_path=Path(pop_path),
            cache_ttl=getattr(settings, "population_cache_ttl", 86400),
        )

    infrastructure = None
    infra_path = getattr(settings, "infrastructure_dataset_path", "")
    if not infra_path:
        default_infra = Path(__file__).resolve().parent.parent / "infrastructure_delhi_sample.json"
        if default_infra.exists():
            infra_path = str(default_infra)
    if data_mode in ("live", "hybrid") and infra_path and Path(infra_path).exists():
        infrastructure = InfrastructureAdapter(
            dataset_path=Path(infra_path),
            cache_ttl=getattr(settings, "infrastructure_cache_ttl", 86400),
        )

    return DataAdapter(
        data_mode=data_mode,
        enable_fallback=enable_fallback,
        weather_adapter=weather,
        water_level_adapter=water_level,
        traffic_adapter=traffic,
        population_adapter=population,
        infrastructure_adapter=infrastructure,
    )


def reset_data_adapter():
    """Resets global adapter singleton (used in unit testing)."""
    global _global_adapter
    _global_adapter = None
