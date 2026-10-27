"""
AapdaNetra-X Real Data Feature Assembler
Orchestrates ERA5, WorldPop, GHSL, Traffic, and CWC preprocessors into a unified
RealDataFeatureRecord maintaining strict 7-feature ordering and explicit provenance.
"""
import math
import datetime
from typing import Dict, Any, Optional, List, Tuple
from app.ml.real_data.provenance import RealDataFeatureRecord, ProvenanceStatus, FEATURE_ORDER
from app.ml.real_data.era5_preprocessor import ERA5Preprocessor
from app.ml.real_data.worldpop_preprocessor import WorldPopPreprocessor
from app.ml.real_data.ghsl_preprocessor import GHSLPreprocessor
from app.ml.real_data.traffic_preprocessor import TrafficPreprocessor
from app.ml.real_data.cwc_observations import CWCObservations


class RealDataFeatureAssembler:
    """
    Unified assembler for assembling real-data feature records compatible with the 7-feature GBR schema.
    """

    DEFAULT_LAT = 28.6400
    DEFAULT_LON = 77.2200
    PROVISIONAL_INFRA_VULNERABILITY = 0.72

    def __init__(
        self,
        era5_path: str = "data/raw/era5_land_delhi_july2023.grib",
        worldpop_path: str = "data/raw/ind_ppp_2020_constrained.tif",
        ghsl_path: str = "data/raw/GHS_BUILT_S_E2020_GLOBE_R2023A_4326_3ss_V1_0_R7_C26.zip",
        traffic_path: str = "data/raw/delhi_traffic_density_2020.zip",
    ):
        self.era5 = ERA5Preprocessor(grib_path=era5_path)
        self.worldpop = WorldPopPreprocessor(tif_path=worldpop_path)
        self.ghsl = GHSLPreprocessor(zip_path=ghsl_path)
        self.traffic = TrafficPreprocessor(zip_path=traffic_path)
        self.cwc = CWCObservations()

    def assemble_record(
        self,
        timestamp_utc: str = "2023-07-13T12:00:00Z",
        lat: float = DEFAULT_LAT,
        lon: float = DEFAULT_LON,
        hour_ist: Optional[int] = None,
    ) -> RealDataFeatureRecord:
        """
        Assembles a RealDataFeatureRecord for given timestamp and location.
        """
        # 1 & 2. ERA5 Rainfall
        rf_intensity, rf_trend, era5_meta = self.era5.get_rainfall_features(timestamp_utc)

        # 3 & 4. CWC Water Level
        wl, wl_trend, cwc_meta = self.cwc.get_water_level_features(timestamp_utc)

        # 5. Traffic Congestion Baseline (derived from 2020)
        if hour_ist is None:
            try:
                dt_obj = datetime.datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
                # IST = UTC + 5:30
                dt_ist = dt_obj + datetime.timedelta(hours=5, minutes=30)
                hour_ist = dt_ist.hour
            except Exception:
                hour_ist = 12

        congestion, traffic_meta = self.traffic.get_road_congestion(hour_ist=hour_ist)

        # 6. WorldPop Exposure
        pop_count, pop_meta = self.worldpop.get_population_exposure(lat=lat, lon=lon)

        # 7. Infrastructure Vulnerability (PROVISIONAL ONLY)
        infra_vuln = self.PROVISIONAL_INFRA_VULNERABILITY

        # Extra Contextual Feature: GHSL Built-Up Surface Area (NOT mapped to vulnerability)
        built_up_m2, ghsl_meta = self.ghsl.get_built_up_surface(lat=lat, lon=lon)

        # Build strict 7-feature dictionary in required order
        features: Dict[str, Optional[float]] = {
            "rainfall_intensity": rf_intensity,
            "rainfall_trend": rf_trend,
            "water_level": wl,
            "water_level_trend": wl_trend,
            "road_congestion": congestion,
            "population_exposure": pop_count,
            "infrastructure_vulnerability": infra_vuln,
        }

        # Build provenance mapping
        feature_provenance: Dict[str, str] = {
            "rainfall_intensity": ProvenanceStatus.DERIVED_FROM_REAL.value,
            "rainfall_trend": ProvenanceStatus.DERIVED_FROM_REAL.value,
            "water_level": ProvenanceStatus.OFFICIAL_EVENT_ONLY.value,
            "water_level_trend": ProvenanceStatus.OFFICIAL_EVENT_ONLY.value,
            "road_congestion": ProvenanceStatus.DERIVED_FROM_REAL.value,
            "population_exposure": ProvenanceStatus.DERIVED_FROM_REAL.value,
            "infrastructure_vulnerability": ProvenanceStatus.PROVISIONAL.value,
        }

        # Build source datasets mapping
        source_datasets: Dict[str, str] = {
            "rainfall_intensity": era5_meta["source"],
            "rainfall_trend": era5_meta["source"],
            "water_level": cwc_meta["source"],
            "water_level_trend": cwc_meta["source"],
            "road_congestion": traffic_meta["source"],
            "population_exposure": pop_meta["source"],
            "infrastructure_vulnerability": "Provisional Default (No verified real dataset available)",
        }

        # Build temporal provenance mapping
        temporal_provenance: Dict[str, str] = {
            "rainfall_intensity": "July 2023 hourly forecast step",
            "rainfall_trend": "July 2023 hourly derivative",
            "water_level": "July 2023 official milestone observation (Old Railway Bridge)",
            "water_level_trend": "July 2023 official milestone observation (Old Railway Bridge)",
            "road_congestion": traffic_meta["temporal_context"],
            "population_exposure": "2020 WorldPop demographic baseline",
            "infrastructure_vulnerability": "Provisional static score",
        }

        # Build feature freshness metadata mapping (Phase 6.24)
        rec_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        feature_freshness: Dict[str, Dict[str, Any]] = {
            "rainfall_intensity": {
                "feature_name": "rainfall_intensity",
                "source": era5_meta["source"],
                "observed_at": timestamp_utc,
                "received_at": rec_time,
                "age_seconds": None,
                "freshness_status": "HISTORICAL_BASELINE",
                "provenance_class": ProvenanceStatus.DERIVED_FROM_REAL.value,
                "availability_status": "AVAILABLE" if rf_intensity is not None else "UNAVAILABLE",
                "is_stale": False,
                "fallback_used": False,
                "cache_status": "cached",
                "unavailability_reason": None,
            },
            "rainfall_trend": {
                "feature_name": "rainfall_trend",
                "source": era5_meta["source"],
                "observed_at": timestamp_utc,
                "received_at": rec_time,
                "age_seconds": None,
                "freshness_status": "HISTORICAL_BASELINE",
                "provenance_class": ProvenanceStatus.DERIVED_FROM_REAL.value,
                "availability_status": "AVAILABLE" if rf_trend is not None else "UNAVAILABLE",
                "is_stale": False,
                "fallback_used": False,
                "cache_status": "cached",
                "unavailability_reason": None,
            },
            "water_level": {
                "feature_name": "water_level",
                "source": cwc_meta["source"],
                "observed_at": timestamp_utc if wl is not None else None,
                "received_at": rec_time,
                "age_seconds": None,
                "freshness_status": "OFFICIAL_EVENT_ONLY" if wl is not None else "UNAVAILABLE",
                "provenance_class": ProvenanceStatus.OFFICIAL_EVENT_ONLY.value if wl is not None else "UNAVAILABLE",
                "availability_status": "AVAILABLE" if wl is not None else "UNAVAILABLE",
                "is_stale": False,
                "fallback_used": wl is None,
                "cache_status": "cached" if wl is not None else "none",
                "unavailability_reason": None if wl is not None else "No official CWC observation available for requested non-milestone timestamp",
            },
            "water_level_trend": {
                "feature_name": "water_level_trend",
                "source": cwc_meta["source"],
                "observed_at": timestamp_utc if wl_trend is not None else None,
                "received_at": rec_time,
                "age_seconds": None,
                "freshness_status": "OFFICIAL_EVENT_ONLY" if wl_trend is not None else "UNAVAILABLE",
                "provenance_class": ProvenanceStatus.OFFICIAL_EVENT_ONLY.value if wl_trend is not None else "UNAVAILABLE",
                "availability_status": "AVAILABLE" if wl_trend is not None else "UNAVAILABLE",
                "is_stale": False,
                "fallback_used": wl_trend is None,
                "cache_status": "cached" if wl_trend is not None else "none",
                "unavailability_reason": None if wl_trend is not None else "No official CWC observation available for requested non-milestone timestamp",
            },
            "road_congestion": {
                "feature_name": "road_congestion",
                "source": traffic_meta["source"],
                "observed_at": "2020-07-01T00:00:00Z",
                "received_at": rec_time,
                "age_seconds": None,
                "freshness_status": "HISTORICAL_BASELINE",
                "provenance_class": ProvenanceStatus.DERIVED_FROM_REAL.value,
                "availability_status": "AVAILABLE",
                "is_stale": False,
                "fallback_used": False,
                "cache_status": "cached",
                "unavailability_reason": "Derived from 2020 historical traffic density baseline; not live traffic",
            },
            "population_exposure": {
                "feature_name": "population_exposure",
                "source": pop_meta["source"],
                "observed_at": "2020-01-01T00:00:00Z",
                "received_at": rec_time,
                "age_seconds": None,
                "freshness_status": "CONTEXTUAL_STATIC",
                "provenance_class": ProvenanceStatus.DERIVED_FROM_REAL.value,
                "availability_status": "FALLBACK",
                "is_stale": False,
                "fallback_used": True,
                "cache_status": "cached",
                "unavailability_reason": "SEMANTICALLY_INCOMPATIBLE_FOR_CURRENT_GBR: WorldPop 2020 demographic baseline count",
            },
            "infrastructure_vulnerability": {
                "feature_name": "infrastructure_vulnerability",
                "source": "Provisional Default",
                "observed_at": None,
                "received_at": rec_time,
                "age_seconds": None,
                "freshness_status": "PROVISIONAL",
                "provenance_class": ProvenanceStatus.PROVISIONAL.value,
                "availability_status": "FALLBACK",
                "is_stale": False,
                "fallback_used": True,
                "cache_status": "none",
                "unavailability_reason": "PROVISIONAL: Default static vulnerability score 0.72",
            },
        }

        # Extra real contextual features outside 7-feature schema
        extra_features = {
            "built_up_surface_m2": built_up_m2,
            "ghsl_metadata": ghsl_meta,
        }

        # Data quality checks
        has_nan_or_inf = False
        for k, v in features.items():
            if v is not None and (math.isnan(v) or math.isinf(v)):
                has_nan_or_inf = True

        quality_flags = {
            "is_valid": not has_nan_or_inf,
            "has_nan_or_inf": has_nan_or_inf,
            "all_7_features_present_in_dict": all(k in features for k in FEATURE_ORDER),
            "water_level_observed": wl is not None,
            "era5_within_valid_window": era5_meta["is_within_valid_window"],
        }

        return RealDataFeatureRecord(
            timestamp_utc=timestamp_utc,
            latitude=lat,
            longitude=lon,
            features=features,
            feature_provenance=feature_provenance,
            source_datasets=source_datasets,
            temporal_provenance=temporal_provenance,
            feature_freshness=feature_freshness,
            extra_contextual_features=extra_features,
            data_quality_flags=quality_flags,
        )

    def assemble_july2023_hourly_records(
        self, lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON
    ) -> List[RealDataFeatureRecord]:
        """
        Assembles RealDataFeatureRecord for all 744 hours of July 2023.
        """
        records = []
        self.era5.load()
        for ts_utc in sorted(self.era5._hourly_data.keys()):
            rec = self.assemble_record(timestamp_utc=ts_utc, lat=lat, lon=lon)
            records.append(rec)
        return records
