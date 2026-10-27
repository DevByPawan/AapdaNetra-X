"""
AapdaNetra-X Real Data Provenance & Feature Record Schema
Enforces strict 7-feature ordering, typed provenance metadata,
temporal/spatial context tracking, and data quality flags.
"""
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List
import datetime

# Centralized Feature Ordering required by existing GBR model
FEATURE_ORDER = [
    "rainfall_intensity",
    "rainfall_trend",
    "water_level",
    "water_level_trend",
    "road_congestion",
    "population_exposure",
    "infrastructure_vulnerability",
]


def resolve_data_path(path_str: str) -> str:
    """Resolves data paths cleanly whether executing from project root or backend directory."""
    if os.path.exists(path_str):
        return path_str
    # Check parent workspace root directory
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    alt_path = os.path.join(workspace_root, path_str)
    if os.path.exists(alt_path):
        return alt_path
    return path_str


class ProvenanceStatus(str, Enum):
    REAL = "REAL"
    DERIVED_FROM_REAL = "DERIVED_FROM_REAL"
    OFFICIAL_EVENT_ONLY = "OFFICIAL_EVENT_ONLY"
    PROVISIONAL = "PROVISIONAL"
    HISTORICAL_BASELINE = "HISTORICAL_BASELINE"
    CONTEXTUAL_STATIC = "CONTEXTUAL_STATIC"
    SIMULATED = "SIMULATED"
    UNAVAILABLE = "UNAVAILABLE"


class FreshnessStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"
    UNAVAILABLE = "UNAVAILABLE"
    CONTEXTUAL_STATIC = "CONTEXTUAL_STATIC"
    HISTORICAL_BASELINE = "HISTORICAL_BASELINE"
    PROVISIONAL = "PROVISIONAL"
    SIMULATED = "SIMULATED"


@dataclass
class FeatureFreshnessRecord:
    feature_name: str
    source: str
    observed_at: Optional[str]
    received_at: Optional[str]
    age_seconds: Optional[float]
    freshness_status: str
    provenance_class: str
    availability_status: str
    is_stale: bool
    fallback_used: bool
    cache_status: Optional[str] = "none"
    unavailability_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "source": self.source,
            "observed_at": self.observed_at,
            "received_at": self.received_at,
            "age_seconds": self.age_seconds,
            "freshness_status": self.freshness_status,
            "provenance_class": self.provenance_class,
            "availability_status": self.availability_status,
            "is_stale": self.is_stale,
            "fallback_used": self.fallback_used,
            "cache_status": self.cache_status,
            "unavailability_reason": self.unavailability_reason,
        }


@dataclass
class RealDataFeatureRecord:
    timestamp_utc: str
    latitude: float
    longitude: float
    # Exactly 7 features in required order
    features: Dict[str, Optional[float]]
    # Provenance status for each feature
    feature_provenance: Dict[str, str]
    # Source dataset for each feature
    source_datasets: Dict[str, str]
    # Detailed temporal context description for each dataset/feature
    temporal_provenance: Dict[str, str]
    # Detailed feature freshness metadata per feature (Phase 6.24)
    feature_freshness: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # Extra real contextual features outside 7-feature schema (e.g. GHSL built_up_surface_m2)
    extra_contextual_features: Dict[str, Any] = field(default_factory=dict)
    # Quality flags and validation status
    data_quality_flags: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Validate 7-feature presence
        for f in FEATURE_ORDER:
            if f not in self.features:
                raise ValueError(f"Missing required feature '{f}' in RealDataFeatureRecord")

    def to_dict(self) -> Dict[str, Any]:
        """Returns JSON-serializable representation of the record."""
        return {
            "timestamp_utc": self.timestamp_utc,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "features": self.features,
            "feature_provenance": self.feature_provenance,
            "source_datasets": self.source_datasets,
            "temporal_provenance": self.temporal_provenance,
            "feature_freshness": self.feature_freshness,
            "extra_contextual_features": self.extra_contextual_features,
            "data_quality_flags": self.data_quality_flags,
        }

    def to_gbr_input_features(self, fill_provisional_defaults: bool = True) -> Dict[str, float]:
        """
        Formats features dictionary for existing GBR predictor.
        Fills missing/unavailable features with schema defaults if fill_provisional_defaults is True.
        """
        try:
            from ml.features.schema import FEATURE_SPECS
        except ImportError:
            from app.ml.features.schema import FEATURE_SPECS

        gbr_dict = {}
        for name in FEATURE_ORDER:
            val = self.features.get(name)
            if val is None:
                if fill_provisional_defaults:
                    gbr_dict[name] = float(FEATURE_SPECS[name]["default"])
                else:
                    gbr_dict[name] = None
            else:
                gbr_dict[name] = float(val)
        return gbr_dict
