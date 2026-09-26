"""
AapdaNetra-X — Infrastructure Vulnerability Data Adapter
Provider-safe adapter for critical infrastructure asset vulnerability feeds (OSM tags / Municipal GIS).
Computes infrastructure_vulnerability index [0.0, 1.0] matching FEATURE_SPECS['infrastructure_vulnerability'].

Methodology Notice:
Criticality weights (e.g. Hospital = 1.0, Substation = 0.8, Bridge = 0.7) are PROVISIONAL / CONFIGURABLE
DEMONSTRATION WEIGHTS for decision-support evaluation. Infrastructure feeds are slow-changing (dataset:osm_infrastructure).
This adapter does NOT modify the NetworkX road-routing graph.
"""
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Any, Tuple

from app.data.providers.base import DataProvider, DataProviderStatus

logger = logging.getLogger("aapdanetra.infrastructure")

# Configurable demonstration asset criticality weights
DEFAULT_ASSET_WEIGHTS = {
    "hospital": 1.0,
    "substation": 0.8,
    "water_works": 0.8,
    "bridge": 0.7,
    "shelter": 0.6,
    "fire_station": 0.6,
    "police": 0.5,
}

DEFAULT_STUDY_BBOX = (77.1900, 28.6100, 77.2600, 28.6700)  # (west, south, east, north)


class InfrastructureAdapter(DataProvider):
    """
    Critical infrastructure vulnerability data adapter.
    Computes asset vulnerability index ratio [0.0, 1.0].
    """

    def __init__(
        self,
        dataset_path: Optional[Path] = None,
        asset_weights: Optional[Dict[str, float]] = None,
        bbox: Tuple[float, float, float, float] = DEFAULT_STUDY_BBOX,
        cache_ttl: int = 86400,
    ):
        super().__init__()
        self.dataset_path = dataset_path
        self.asset_weights = asset_weights or dict(DEFAULT_ASSET_WEIGHTS)
        self.bbox = bbox
        self.cache_ttl = max(3600, cache_ttl)

        # Cache state
        self._cached_index: Optional[float] = None
        self._cache_timestamp: float = 0.0

        # Metadata
        self.dataset_source: str = "dataset:osm_infrastructure"
        self.dataset_version: str = "v2023.1"
        self.observed_at: Optional[str] = None
        self.age_seconds: Optional[float] = None
        self.is_stale: bool = False
        self.fallback_used: bool = False

    def get_features(self) -> Dict[str, Optional[float]]:
        """
        Fetch and compute infrastructure_vulnerability ratio [0.0, 1.0].
        Returns None if dataset is unconfigured (falling back safely).
        """
        result: Dict[str, Optional[float]] = {
            "infrastructure_vulnerability": None,
        }

        now_mono = time.monotonic()
        if self._cached_index is not None and (now_mono - self._cache_timestamp) < self.cache_ttl:
            self.age_seconds = round(now_mono - self._cache_timestamp, 1)
            self.is_stale = self.age_seconds > (2 * self.cache_ttl)
            result["infrastructure_vulnerability"] = self._cached_index
            return result

        if self.dataset_path is None or not Path(self.dataset_path).exists():
            self.status = DataProviderStatus.FALLBACK
            self.last_error = "Infrastructure dataset not configured or file not found"
            self.fallback_used = True
            logger.debug("[InfrastructureAdapter] No dataset file configured — using fallback.")
            return result

        try:
            vuln_index = self._calculate_vulnerability_index(Path(self.dataset_path))
            if vuln_index is not None:
                # Clamp to [0.0, 1.0] index
                clamped_idx = round(max(0.0, min(1.0, float(vuln_index))), 3)
                result["infrastructure_vulnerability"] = clamped_idx
                self._cached_index = clamped_idx
                self._cache_timestamp = now_mono
                self.observed_at = datetime.now(timezone.utc).isoformat()
                self.age_seconds = 0.0
                self.is_stale = False
                self.status = DataProviderStatus.LIVE
                self.last_error = None
                self.fallback_used = False
                logger.info(f"[InfrastructureAdapter] Computed infrastructure_vulnerability={clamped_idx}")
            else:
                self.status = DataProviderStatus.FALLBACK
                self.fallback_used = True

        except Exception as e:
            self.status = DataProviderStatus.ERROR
            self.last_error = str(e)
            self.fallback_used = True
            logger.warning(f"[InfrastructureAdapter] Error processing dataset: {e}")

        return result

    def _calculate_vulnerability_index(self, path: Path) -> Optional[float]:
        """Calculates weighted asset vulnerability index from local JSON dataset."""
        try:
            with open(path, "r") as f:
                data = json.load(f)

            if isinstance(data, dict) and "vulnerability_index" in data:
                return float(data["vulnerability_index"])

            if isinstance(data, dict) and "critical_assets" in data:
                weighted_sum = 0.0
                total_weight = 0.0
                for asset in data["critical_assets"]:
                    cat = str(asset.get("category", "other")).lower()
                    weight = self.asset_weights.get(cat, 0.5)
                    exposure = float(asset.get("exposure_score", 0.7))
                    weighted_sum += weight * exposure
                    total_weight += weight

                if total_weight > 0:
                    return weighted_sum / total_weight

        except Exception as e:
            logger.warning(f"[InfrastructureAdapter] Failed parsing {path}: {e}")

        return None

    def invalidate_cache(self):
        """Force-clears cached infrastructure index."""
        self._cached_index = None
        self._cache_timestamp = 0.0
