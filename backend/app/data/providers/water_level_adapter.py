"""
AapdaNetra-X — Water Level Adapter
Provides water_level and water_level_trend from local override file or
environment variables. Supports TTL caching, timestamping, bounds checking, and station metadata.

Priority:
  1. Environment variables (WATER_LEVEL_OVERRIDE, WATER_LEVEL_TREND_OVERRIDE)
  2. Local JSON file (backend/water_level_override.json)
  3. None (falls through to simulated defaults in DataAdapter)
"""
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Any

from app.data.providers.base import DataProvider, DataProviderStatus

logger = logging.getLogger("aapdanetra.water_level")

# Default location for manual water level override file
_OVERRIDE_FILE = Path(__file__).resolve().parent.parent.parent.parent / "water_level_override.json"


class WaterLevelAdapter(DataProvider):
    """
    Provides water_level (m) and water_level_trend (m/h) from local sources or manual overrides.
    """

    def __init__(
        self,
        source: str = "simulated",
        override_file: Optional[Path] = None,
        cache_ttl: int = 60,
    ):
        super().__init__()
        self.source = source
        self.override_file = override_file or _OVERRIDE_FILE
        self.cache_ttl = max(5, cache_ttl)

        # Cache state
        self._cached_features: Optional[Dict[str, Optional[float]]] = None
        self._cache_timestamp: float = 0.0

        # Metadata
        self.station_id: str = "MANUAL-OVERRIDE-GAGE-01"
        self.observed_at: Optional[str] = None
        self.age_seconds: Optional[float] = None
        self.is_stale: bool = False
        self.fallback_used: bool = False

    def get_features(self) -> Dict[str, Optional[float]]:
        """
        Fetch water_level and water_level_trend from configured source.
        Returns None values if source is 'simulated' or data unavailable.
        """
        result: Dict[str, Optional[float]] = {
            "water_level": None,
            "water_level_trend": None,
        }

        if self.source == "simulated":
            self.status = DataProviderStatus.FALLBACK
            self.fallback_used = True
            return result

        now_mono = time.monotonic()
        if self._cached_features is not None and (now_mono - self._cache_timestamp) < self.cache_ttl:
            self.age_seconds = round(now_mono - self._cache_timestamp, 1)
            self.is_stale = self.age_seconds > (2 * self.cache_ttl)
            return dict(self._cached_features)

        try:
            # Priority 1: Environment variables
            env_wl = os.environ.get("WATER_LEVEL_OVERRIDE")
            env_wlt = os.environ.get("WATER_LEVEL_TREND_OVERRIDE")

            if env_wl is not None:
                wl_val = float(env_wl)
                if 0.0 <= wl_val <= 15.0:
                    result["water_level"] = wl_val
                    self.status = DataProviderStatus.LIVE
                    logger.info(f"[WaterLevelAdapter] ENV override: water_level={wl_val}")

            if env_wlt is not None:
                wlt_val = float(env_wlt)
                if -5.0 <= wlt_val <= 5.0:
                    result["water_level_trend"] = wlt_val
                    self.status = DataProviderStatus.LIVE
                    logger.info(f"[WaterLevelAdapter] ENV override: water_level_trend={wlt_val}")

            # Priority 2: Local JSON file (only for keys still None)
            if result["water_level"] is None or result["water_level_trend"] is None:
                file_data = self._read_override_file()
                if file_data:
                    if result["water_level"] is None and "water_level" in file_data:
                        wl_val = float(file_data["water_level"])
                        if 0.0 <= wl_val <= 15.0:
                            result["water_level"] = wl_val
                            self.status = DataProviderStatus.LIVE
                    if result["water_level_trend"] is None and "water_level_trend" in file_data:
                        wlt_val = float(file_data["water_level_trend"])
                        if -5.0 <= wlt_val <= 5.0:
                            result["water_level_trend"] = wlt_val
                            self.status = DataProviderStatus.LIVE

            if result["water_level"] is not None:
                self.fallback_used = False
                self.observed_at = datetime.now(timezone.utc).isoformat()
                self.age_seconds = 0.0
                self.is_stale = False
            else:
                self.status = DataProviderStatus.FALLBACK
                self.fallback_used = True

            self.last_error = None
            self._cached_features = dict(result)
            self._cache_timestamp = now_mono

        except (ValueError, TypeError) as e:
            self.status = DataProviderStatus.ERROR
            self.last_error = f"Invalid water level value: {e}"
            self.fallback_used = True
            logger.warning(f"[WaterLevelAdapter] Parse error: {e}")

        except Exception as e:
            self.status = DataProviderStatus.ERROR
            self.last_error = str(e)
            self.fallback_used = True
            logger.warning(f"[WaterLevelAdapter] Unexpected error: {e}")

        return result

    def _read_override_file(self) -> Optional[Dict]:
        """Read water_level_override.json if it exists."""
        if not self.override_file.exists():
            return None

        try:
            with open(self.override_file, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[WaterLevelAdapter] Failed reading {self.override_file}: {e}")

        return None

    def invalidate_cache(self):
        """Force-clears cached features."""
        self._cached_features = None
        self._cache_timestamp = 0.0
