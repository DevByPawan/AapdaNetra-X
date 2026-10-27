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
import threading
from datetime import datetime, timezone
from typing import Dict, Optional, Any

from app.data.providers.base import DataProviderStatus
from app.data.providers.weather_adapter import WeatherAdapter
from app.data.providers.water_level_adapter import WaterLevelAdapter
from app.data.providers.traffic_adapter import TrafficAdapter
from app.data.providers.population_adapter import PopulationAdapter
from app.data.providers.infrastructure_adapter import InfrastructureAdapter
from app.data.providers.elevation_adapter import ElevationAdapter
from app.data.providers.hazard_adapter import HazardLayerAdapter

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
        elevation_adapter: Optional[ElevationAdapter] = None,
        hazard_adapter: Optional[HazardLayerAdapter] = None,
    ):
        self.data_mode = data_mode
        self.enable_fallback = enable_fallback
        self.weather_adapter = weather_adapter
        self.water_level_adapter = water_level_adapter
        self.traffic_adapter = traffic_adapter
        self.population_adapter = population_adapter
        self.infrastructure_adapter = infrastructure_adapter
        self.elevation_adapter = elevation_adapter
        self.hazard_adapter = hazard_adapter

        # Per-feature provenance tracking
        self._provenance: Dict[str, str] = {}
        self.fallback_used: bool = False
        self.real_data_timestamp: str = "2023-07-13T12:00:00Z"
        self._raw_features: Dict[str, Any] = dict(BASE_SENSOR_FEATURES)
        self._clipping_flags: Dict[str, bool] = {k: False for k in BASE_SENSOR_FEATURES}
        self._extra_contextual_features: Dict[str, Any] = {}
        self._assembler = None

        # Thread-safe in-memory live observation overlay
        self._lock = threading.Lock()
        self._live_overlay: Dict[str, float] = {}
        self._live_provenance: Dict[str, str] = {}
        self._last_live_timestamp: Optional[str] = None

    def update_live_features(
        self,
        features: Dict[str, float],
        provenance_map: Optional[Dict[str, str]] = None,
        observed_at: Optional[str] = None,
    ) -> None:
        """
        Thread-safely updates active live observation overlay.
        """
        with self._lock:
            for k, v in features.items():
                if k in BASE_SENSOR_FEATURES and v is not None:
                    self._live_overlay[k] = float(v)
                    tag = provenance_map.get(k) if provenance_map else f"live_ingest:{k}"
                    self._live_provenance[k] = tag or "live_ingest"
            if observed_at:
                self._last_live_timestamp = observed_at

    def clear_live_features(self) -> None:
        """Thread-safely clears active live overlay."""
        with self._lock:
            self._live_overlay.clear()
            self._live_provenance.clear()
            self._last_live_timestamp = None

    def get_live_overlay(self) -> Dict[str, Any]:
        """Returns thread-safe snapshot of current live overlay."""
        with self._lock:
            return {
                "features": dict(self._live_overlay),
                "provenance": dict(self._live_provenance),
                "observed_at": self._last_live_timestamp,
            }

    def set_real_data_timestamp(self, timestamp_utc: str) -> None:
        """Sets target event timestamp for 'real' data mode."""
        with self._lock:
            self.real_data_timestamp = timestamp_utc

    def get_base_features(self) -> Dict[str, float]:
        """
        Returns the 7-key base feature dict.

        In 'simulated' mode: returns BASE_SENSOR_FEATURES overlaid by any active live telemetry ingestion.
        In 'real' mode: uses RealDataFeatureAssembler for real-derived features & explicit provenance.
        In 'hybrid' / 'live' mode: queries providers and merges with live overlay & defaults according to policy.
        """
        with self._lock:
            live_snapshot = dict(self._live_overlay)
            live_prov_snapshot = dict(self._live_provenance)
            ts_utc = self.real_data_timestamp

        if self.data_mode == "simulated" and not live_snapshot:
            self._provenance = {k: "simulated" for k in BASE_SENSOR_FEATURES}
            self.fallback_used = False
            self._raw_features = dict(BASE_SENSOR_FEATURES)
            self._clipping_flags = {k: False for k in BASE_SENSOR_FEATURES}
            self._extra_contextual_features = {}
            return dict(BASE_SENSOR_FEATURES)

        if self.data_mode == "real":
            try:
                if self._assembler is None:
                    from app.ml.real_data.feature_assembler import RealDataFeatureAssembler
                    self._assembler = RealDataFeatureAssembler()

                rec = self._assembler.assemble_record(timestamp_utc=ts_utc)
                merged = {}
                self._provenance = dict(rec.feature_provenance)
                # Ensure exact provenance tags matching canonical rules
                self._provenance["road_congestion"] = "DERIVED_FROM_REAL / 2020 BASELINE"
                self._provenance["population_exposure"] = "SEMANTICALLY_INCOMPATIBLE_FOR_CURRENT_GBR"
                self._provenance["infrastructure_vulnerability"] = "PROVISIONAL"

                self._raw_features = dict(rec.features)
                self._clipping_flags = {}
                self._extra_contextual_features = dict(rec.extra_contextual_features)

                # ML Boundary protection: validate and clean 7 features for model input
                from ml.features.schema import FEATURE_SPECS
                for k in BASE_SENSOR_FEATURES:
                    raw_v = rec.features.get(k)
                    spec = FEATURE_SPECS[k]
                    if raw_v is None:
                        merged[k] = float(spec["default"])
                        if self._provenance.get(k) == "OFFICIAL_EVENT_ONLY":
                            self._provenance[k] = "UNAVAILABLE"
                    else:
                        val_flt = float(raw_v)
                        clipped_v = max(spec["min"], min(spec["max"], val_flt))
                        merged[k] = clipped_v
                        if abs(val_flt - clipped_v) > 1e-4:
                            self._clipping_flags[k] = True
                        else:
                            self._clipping_flags[k] = False

                self.fallback_used = True  # Real mode relies on provisional vulnerability and raw WorldPop exposure

                # Overlay live telemetry if ingested
                for k, v in live_snapshot.items():
                    merged[k] = float(v)
                    if k in live_prov_snapshot:
                        self._provenance[k] = live_prov_snapshot[k]

                return merged
            except Exception as e:
                logger.warning(f"[DataAdapter] Real data mode error: {e}, falling back to simulated.")
                self.fallback_used = True
                self._provenance = {k: "fallback:simulated" for k in BASE_SENSOR_FEATURES}
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
        # 6. Active live observation overlay (if any ingested)
        for k, v in live_snapshot.items():
            merged[k] = float(v)
            if k in live_prov_snapshot:
                self._provenance[k] = live_prov_snapshot[k]

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

    def get_feature_freshness(self, now_reference: Optional[datetime] = None) -> Dict[str, Dict[str, Any]]:
        """
        Returns structured per-feature freshness and provenance metadata (Phase 6.24).
        Calculates data age deterministically against now_reference or current UTC time.
        """
        ref_time = now_reference or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)
        now_iso = ref_time.isoformat()

        with self._lock:
            live_snapshot = dict(self._live_overlay)
            live_prov_snapshot = dict(self._live_provenance)

        if self.data_mode == "simulated" and not live_snapshot:
            freshness = {}
            for k in BASE_SENSOR_FEATURES:
                freshness[k] = {
                    "feature_name": k,
                    "source": "simulated",
                    "observed_at": None,
                    "received_at": now_iso,
                    "age_seconds": None,
                    "freshness_status": "SIMULATED",
                    "provenance_class": "SIMULATED",
                    "availability_status": "AVAILABLE",
                    "is_stale": False,
                    "fallback_used": False,
                    "cache_status": "none",
                    "unavailability_reason": "Simulated benchmark mode baseline",
                }
            return freshness

        if self.data_mode == "real" and not live_snapshot:
            try:
                if self._assembler is None:
                    from app.ml.real_data.feature_assembler import RealDataFeatureAssembler
                    self._assembler = RealDataFeatureAssembler()

                rec = self._assembler.assemble_record(timestamp_utc=self.real_data_timestamp)
                freshness = dict(rec.feature_freshness)
                for k, v in freshness.items():
                    obs_at = v.get("observed_at")
                    if obs_at:
                        try:
                            dt_obs = datetime.fromisoformat(obs_at.replace("Z", "+00:00"))
                            if dt_obs.tzinfo is None:
                                dt_obs = dt_obs.replace(tzinfo=timezone.utc)
                            diff = (ref_time - dt_obs).total_seconds()
                            v["age_seconds"] = max(0.0, round(diff, 1))
                        except Exception:
                            v["age_seconds"] = None
                    else:
                        v["age_seconds"] = None
                return freshness
            except Exception as e:
                logger.warning(f"[DataAdapter] Error building real freshness: {e}")

        freshness: Dict[str, Dict[str, Any]] = {}

        for k in BASE_SENSOR_FEATURES:
            if k in live_snapshot:
                # Live ingested telemetry overlay
                obs_ts = self._last_live_timestamp or now_iso
                age = None
                try:
                    dt_obs = datetime.fromisoformat(obs_ts.replace("Z", "+00:00"))
                    if dt_obs.tzinfo is None:
                        dt_obs = dt_obs.replace(tzinfo=timezone.utc)
                    age = max(0.0, round((ref_time - dt_obs).total_seconds(), 1))
                except Exception:
                    pass

                stale = (age is not None) and (age > 300.0)
                freshness[k] = {
                    "feature_name": k,
                    "source": live_prov_snapshot.get(k, "live_ingest"),
                    "observed_at": obs_ts,
                    "received_at": now_iso,
                    "age_seconds": age,
                    "freshness_status": "STALE" if stale else "FRESH",
                    "provenance_class": "REAL",
                    "availability_status": "AVAILABLE",
                    "is_stale": stale,
                    "fallback_used": False,
                    "cache_status": "newly_fetched",
                    "unavailability_reason": None,
                }
            elif k in ("rainfall_intensity", "rainfall_trend") and self.weather_adapter is not None:
                w = self.weather_adapter
                age = w.calculate_age(ref_time)
                freshness[k] = {
                    "feature_name": k,
                    "source": w.provider_name,
                    "observed_at": w.observed_at,
                    "received_at": getattr(w, "received_at", None) or now_iso,
                    "age_seconds": age,
                    "freshness_status": getattr(w, "freshness_status", "FRESH" if w.is_live else "MISSING"),
                    "provenance_class": "REAL" if w.is_live else "MISSING",
                    "availability_status": "AVAILABLE" if w.is_live else "MISSING",
                    "is_stale": w.is_stale,
                    "fallback_used": w.fallback_used,
                    "cache_status": getattr(w, "cache_status", "none"),
                    "unavailability_reason": getattr(w, "unavailability_reason", w.last_error),
                }
            elif k in ("water_level", "water_level_trend") and self.water_level_adapter is not None:
                wl = self.water_level_adapter
                age = wl.calculate_age(ref_time)
                freshness[k] = {
                    "feature_name": k,
                    "source": getattr(wl, "source", "water_level_adapter"),
                    "observed_at": wl.observed_at,
                    "received_at": getattr(wl, "received_at", None) or now_iso,
                    "age_seconds": age,
                    "freshness_status": getattr(wl, "freshness_status", "FRESH" if wl.is_live else "UNAVAILABLE"),
                    "provenance_class": "REAL" if wl.is_live else "UNAVAILABLE",
                    "availability_status": "AVAILABLE" if wl.is_live else "UNAVAILABLE",
                    "is_stale": wl.is_stale,
                    "fallback_used": wl.fallback_used,
                    "cache_status": getattr(wl, "cache_status", "none"),
                    "unavailability_reason": getattr(wl, "unavailability_reason", wl.last_error),
                }
            elif k == "road_congestion" and self.traffic_adapter is not None and self.traffic_adapter.is_live:
                tr = self.traffic_adapter
                age = tr.calculate_age(ref_time)
                freshness[k] = {
                    "feature_name": k,
                    "source": tr.provider_name,
                    "observed_at": tr.observed_at,
                    "received_at": getattr(tr, "received_at", None) or now_iso,
                    "age_seconds": age,
                    "freshness_status": getattr(tr, "freshness_status", "FRESH"),
                    "provenance_class": "REAL",
                    "availability_status": "AVAILABLE",
                    "is_stale": tr.is_stale,
                    "fallback_used": tr.fallback_used,
                    "cache_status": getattr(tr, "cache_status", "none"),
                    "unavailability_reason": getattr(tr, "unavailability_reason", tr.last_error),
                }
            elif k == "population_exposure" and self.population_adapter is not None and getattr(self.population_adapter, "dataset_source", ""):
                pop = self.population_adapter
                freshness[k] = {
                    "feature_name": k,
                    "source": pop.dataset_source,
                    "observed_at": pop.observed_at or "2020-01-01T00:00:00Z",
                    "received_at": getattr(pop, "received_at", None) or now_iso,
                    "age_seconds": None,
                    "freshness_status": getattr(pop, "freshness_status", "CONTEXTUAL_STATIC"),
                    "provenance_class": "DERIVED_FROM_REAL",
                    "availability_status": "FALLBACK",
                    "is_stale": False,
                    "fallback_used": True,
                    "cache_status": getattr(pop, "cache_status", "cached"),
                    "unavailability_reason": getattr(pop, "unavailability_reason", "WorldPop demographic baseline count"),
                }
            elif k == "infrastructure_vulnerability" and self.infrastructure_adapter is not None and getattr(self.infrastructure_adapter, "dataset_source", ""):
                inf = self.infrastructure_adapter
                freshness[k] = {
                    "feature_name": k,
                    "source": inf.dataset_source,
                    "observed_at": None,
                    "received_at": getattr(inf, "received_at", None) or now_iso,
                    "age_seconds": None,
                    "freshness_status": getattr(inf, "freshness_status", "PROVISIONAL"),
                    "provenance_class": "PROVISIONAL",
                    "availability_status": "FALLBACK",
                    "is_stale": False,
                    "fallback_used": True,
                    "cache_status": getattr(inf, "cache_status", "none"),
                    "unavailability_reason": getattr(inf, "unavailability_reason", "Provisional score 0.72"),
                }
            else:
                if k == "infrastructure_vulnerability":
                    fresh_stat = "PROVISIONAL"
                    prov_cls = "PROVISIONAL"
                    reason = "Provisional score 0.72; no real-time measured vulnerability feed"
                elif k == "population_exposure":
                    fresh_stat = "CONTEXTUAL_STATIC"
                    prov_cls = "DERIVED_FROM_REAL"
                    reason = "WorldPop demographic baseline count"
                elif self.data_mode == "simulated":
                    fresh_stat = "SIMULATED"
                    prov_cls = "SIMULATED"
                    reason = "Simulated benchmark mode baseline"
                else:
                    fresh_stat = "MISSING"
                    prov_cls = "PROVISIONAL"
                    reason = "Provider unconfigured or fallback used"

                freshness[k] = {
                    "feature_name": k,
                    "source": "simulated" if self.data_mode == "simulated" else "fallback",
                    "observed_at": None,
                    "received_at": now_iso,
                    "age_seconds": None,
                    "freshness_status": fresh_stat,
                    "provenance_class": prov_cls,
                    "availability_status": "AVAILABLE" if self.data_mode == "simulated" else "FALLBACK",
                    "is_stale": False,
                    "fallback_used": self.data_mode != "simulated",
                    "cache_status": "none",
                    "unavailability_reason": reason,
                }

        return freshness

    def get_telemetry_metadata(self, now_reference: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Returns structured telemetry status and metadata for observability.
        Omits any API keys, credentials, or authorization headers.
        """
        ref_time = now_reference or datetime.now(timezone.utc)
        weather_meta = {
            "status": self.weather_adapter.status.value if self.weather_adapter else "not_configured",
            "source": self.weather_adapter.provider_name if self.weather_adapter else "none",
            "observed_at": getattr(self.weather_adapter, "observed_at", None),
            "received_at": getattr(self.weather_adapter, "received_at", None),
            "age_seconds": self.weather_adapter.calculate_age(ref_time) if self.weather_adapter else None,
            "stale": getattr(self.weather_adapter, "is_stale", False),
            "cache_status": getattr(self.weather_adapter, "cache_status", "none"),
            "freshness_status": getattr(self.weather_adapter, "freshness_status", "MISSING"),
            "unavailability_reason": getattr(self.weather_adapter, "unavailability_reason", None),
        }

        water_meta = {
            "status": self.water_level_adapter.status.value if self.water_level_adapter else "not_configured",
            "source": getattr(self.water_level_adapter, "source", "none"),
            "observed_at": getattr(self.water_level_adapter, "observed_at", None),
            "received_at": getattr(self.water_level_adapter, "received_at", None),
            "age_seconds": self.water_level_adapter.calculate_age(ref_time) if self.water_level_adapter else None,
            "stale": getattr(self.water_level_adapter, "is_stale", False),
            "cache_status": getattr(self.water_level_adapter, "cache_status", "none"),
            "freshness_status": getattr(self.water_level_adapter, "freshness_status", "UNAVAILABLE"),
            "unavailability_reason": getattr(self.water_level_adapter, "unavailability_reason", None),
        }

        traffic_meta = {
            "status": self.traffic_adapter.status.value if self.traffic_adapter else "not_configured",
            "source": self.traffic_adapter.provider_name if self.traffic_adapter else "none",
            "observed_at": getattr(self.traffic_adapter, "observed_at", None),
            "received_at": getattr(self.traffic_adapter, "received_at", None),
            "age_seconds": self.traffic_adapter.calculate_age(ref_time) if self.traffic_adapter else None,
            "stale": getattr(self.traffic_adapter, "is_stale", False),
            "cache_status": getattr(self.traffic_adapter, "cache_status", "none"),
            "freshness_status": getattr(self.traffic_adapter, "freshness_status", "HISTORICAL_BASELINE"),
            "unavailability_reason": getattr(self.traffic_adapter, "unavailability_reason", None),
        }

        pop_meta = {
            "status": self.population_adapter.status.value if self.population_adapter else "not_configured",
            "source": getattr(self.population_adapter, "dataset_source", "none"),
            "dataset_version": getattr(self.population_adapter, "dataset_version", None),
            "observed_at": getattr(self.population_adapter, "observed_at", None),
            "received_at": getattr(self.population_adapter, "received_at", None),
            "age_seconds": None,
            "stale": getattr(self.population_adapter, "is_stale", False),
            "cache_status": getattr(self.population_adapter, "cache_status", "none"),
            "freshness_status": getattr(self.population_adapter, "freshness_status", "CONTEXTUAL_STATIC"),
            "unavailability_reason": getattr(self.population_adapter, "unavailability_reason", None),
        }

        infra_meta = {
            "status": self.infrastructure_adapter.status.value if self.infrastructure_adapter else "not_configured",
            "source": getattr(self.infrastructure_adapter, "dataset_source", "none"),
            "dataset_version": getattr(self.infrastructure_adapter, "dataset_version", None),
            "observed_at": getattr(self.infrastructure_adapter, "observed_at", None),
            "received_at": getattr(self.infrastructure_adapter, "received_at", None),
            "age_seconds": None,
            "stale": getattr(self.infrastructure_adapter, "is_stale", False),
            "cache_status": getattr(self.infrastructure_adapter, "cache_status", "none"),
            "freshness_status": getattr(self.infrastructure_adapter, "freshness_status", "PROVISIONAL"),
            "unavailability_reason": getattr(self.infrastructure_adapter, "unavailability_reason", None),
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
            "feature_freshness": self.get_feature_freshness(now_reference=ref_time),
            "provenance": dict(self._provenance),
            "raw_features": dict(self._raw_features),
            "clipping_flags": dict(self._clipping_flags),
            "extra_contextual_features": dict(self._extra_contextual_features),
            "real_data_disclaimer": "Synthetic-trained GBR model weights. Predictive accuracy and operational validity have NOT been established on real-world data.",
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

    elevation = ElevationAdapter(
        enabled=getattr(settings, "dem_enabled", False),
        source_name=getattr(settings, "dem_source", "unavailable"),
        dem_data_path=getattr(settings, "dem_data_path", ""),
        cache_ttl=getattr(settings, "dem_cache_ttl", 86400),
    )

    hazard = HazardLayerAdapter(
        enabled=getattr(settings, "hazard_layer_enabled", False),
        dataset_path=getattr(settings, "hazard_dataset_path", ""),
        cache_ttl=getattr(settings, "hazard_cache_ttl", 86400),
    )

    return DataAdapter(
        data_mode=data_mode,
        enable_fallback=enable_fallback,
        weather_adapter=weather,
        water_level_adapter=water_level,
        traffic_adapter=traffic,
        population_adapter=population,
        infrastructure_adapter=infrastructure,
        elevation_adapter=elevation,
        hazard_adapter=hazard,
    )


def reset_data_adapter():
    """Resets global adapter singleton (used in unit testing)."""
    global _global_adapter
    _global_adapter = None
