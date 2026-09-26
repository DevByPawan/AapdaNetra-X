"""
AapdaNetra-X — Population Exposure Data Adapter
Provider-safe adapter for spatial population datasets (e.g. WorldPop / Census India / GeoJSON grids).
Aggregates vulnerable head-count within the study area bounding box into population_exposure [0, 100000].

Scientific Notice:
Static population datasets are slow-changing (annual/decennial). Provenance uses 'dataset:worldpop'
or 'dataset:census' rather than 'live:worldpop'. Aggregation is study-area bounded.
"""
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Any, Tuple

from app.data.providers.base import DataProvider, DataProviderStatus

logger = logging.getLogger("aapdanetra.population")

DEFAULT_STUDY_BBOX = (77.1900, 28.6100, 77.2600, 28.6700)  # (west, south, east, north)


class PopulationAdapter(DataProvider):
    """
    Spatial population dataset adapter.
    Aggregates vulnerable population head-count count matching FEATURE_SPECS['population_exposure'].
    """

    def __init__(
        self,
        dataset_path: Optional[Path] = None,
        dataset_name: str = "WorldPop 100m Grid",
        dataset_year: str = "2023",
        bbox: Tuple[float, float, float, float] = DEFAULT_STUDY_BBOX,
        cache_ttl: int = 86400,
    ):
        super().__init__()
        self.dataset_path = dataset_path
        self.dataset_name = dataset_name
        self.dataset_year = dataset_year
        self.bbox = bbox
        self.cache_ttl = max(3600, cache_ttl)

        # Cache state
        self._cached_count: Optional[float] = None
        self._cache_timestamp: float = 0.0

        # Metadata
        self.dataset_source: str = f"dataset:{self.dataset_name.lower().replace(' ', '_')}"
        self.dataset_version: str = f"v{self.dataset_year}"
        self.observed_at: Optional[str] = None
        self.age_seconds: Optional[float] = None
        self.is_stale: bool = False
        self.fallback_used: bool = False

    def get_features(self) -> Dict[str, Optional[float]]:
        """
        Fetch and aggregate population_exposure count [0, 100000].
        Returns None if dataset is missing or unconfigured (falling back safely).
        """
        result: Dict[str, Optional[float]] = {
            "population_exposure": None,
        }

        now_mono = time.monotonic()
        if self._cached_count is not None and (now_mono - self._cache_timestamp) < self.cache_ttl:
            self.age_seconds = round(now_mono - self._cache_timestamp, 1)
            self.is_stale = self.age_seconds > (2 * self.cache_ttl)
            result["population_exposure"] = self._cached_count
            return result

        if self.dataset_path is None or not Path(self.dataset_path).exists():
            self.status = DataProviderStatus.FALLBACK
            self.last_error = "Population dataset not configured or file not found"
            self.fallback_used = True
            logger.debug("[PopulationAdapter] No dataset file configured — using fallback.")
            return result

        try:
            count = self._aggregate_population_dataset(Path(self.dataset_path))
            if count is not None:
                # Clamp to [0.0, 100000.0] vulnerable count
                pop_count = round(max(0.0, min(100000.0, float(count))), 1)
                result["population_exposure"] = pop_count
                self._cached_count = pop_count
                self._cache_timestamp = now_mono
                self.observed_at = datetime.now(timezone.utc).isoformat()
                self.age_seconds = 0.0
                self.is_stale = False
                self.status = DataProviderStatus.LIVE
                self.last_error = None
                self.fallback_used = False
                logger.info(f"[PopulationAdapter] Aggregated population_exposure={pop_count}")
            else:
                self.status = DataProviderStatus.FALLBACK
                self.fallback_used = True

        except Exception as e:
            self.status = DataProviderStatus.ERROR
            self.last_error = str(e)
            self.fallback_used = True
            logger.warning(f"[PopulationAdapter] Error processing dataset: {e}")

        return result

    def _aggregate_population_dataset(self, path: Path) -> Optional[float]:
        """Loads local JSON/GeoJSON population grid and sums intersecting counts."""
        try:
            with open(path, "r") as f:
                data = json.load(f)

            if isinstance(data, dict) and "vulnerable_population" in data:
                return float(data["vulnerable_population"])

            if isinstance(data, dict) and "features" in data:
                total_pop = 0.0
                west, south, east, north = self.bbox
                for feat in data["features"]:
                    props = feat.get("properties", {})
                    pop = props.get("population", 0.0)
                    geom = feat.get("geometry", {})
                    coords = geom.get("coordinates", [])
                    if coords:
                        lng, lat = coords[0], coords[1]
                        if west <= lng <= east and south <= lat <= north:
                            total_pop += float(pop)
                return total_pop

        except Exception as e:
            logger.warning(f"[PopulationAdapter] Failed parsing {path}: {e}")

        return None

    def invalidate_cache(self):
        """Force-clears cached population result."""
        self._cached_count = None
        self._cache_timestamp = 0.0
