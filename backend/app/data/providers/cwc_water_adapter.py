"""
AapdaNetra-X — CWC River Gauge Water Level Adapter
Provider-safe adapter for Central Water Commission (CWC) / river telemetry API feeds.
Supports observation timestamping, TTL caching, trend calculation from history buffer,
and explicit fallback behavior when no live endpoint is configured.
"""
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple, Any

import httpx

from app.data.providers.base import DataProvider, DataProviderStatus

logger = logging.getLogger("aapdanetra.cwc_water")


class CWCWaterLevelAdapter(DataProvider):
    """
    Provider-safe river gauge telemetry adapter.
    Fetches water_level (m) and water_level_trend (m/h) from external station API.
    """

    def __init__(
        self,
        endpoint_url: str = "",
        station_id: str = "EXAMPLE-STN-YAMUNA-01",
        cache_ttl: int = 60,
        timeout: float = 5.0,
    ):
        super().__init__()
        self.endpoint_url = endpoint_url
        self.station_id = station_id
        self.cache_ttl = max(10, cache_ttl)
        self.timeout = timeout

        # Cache state
        self._cached_response: Optional[Dict[str, Any]] = None
        self._cache_timestamp: float = 0.0

        # In-memory history buffer for trend derivation: deque of (monotonic_time, utc_datetime, water_level)
        self._history: deque = deque(maxlen=10)

        # Metadata
        self.observed_at: Optional[str] = None
        self.age_seconds: Optional[float] = None
        self.is_stale: bool = False
        self.fallback_used: bool = False

    def get_features(self) -> Dict[str, Optional[float]]:
        """
        Fetches water_level and water_level_trend from CWC API feed.
        Returns None values safely if no endpoint is configured or request fails.
        """
        result: Dict[str, Optional[float]] = {
            "water_level": None,
            "water_level_trend": None,
        }

        if not self.endpoint_url:
            self.status = DataProviderStatus.FALLBACK
            self.last_error = "No CWC API endpoint configured"
            self.fallback_used = True
            logger.debug("[CWCWaterLevelAdapter] No endpoint configured — using fallback.")
            return result

        try:
            raw = self._fetch_with_cache()
            if raw is None:
                self.fallback_used = True
                return result

            wl_val = raw.get("water_level")
            if wl_val is not None:
                wl_float = float(wl_val)
                # Bounds check: [0.0, 15.0] meters
                if 0.0 <= wl_float <= 15.0:
                    result["water_level"] = wl_float
                else:
                    logger.warning(f"[CWCWaterLevelAdapter] Water level {wl_float} out of range [0, 15].")

            # Trend calculation or extraction
            if "water_level_trend" in raw and raw["water_level_trend"] is not None:
                wlt_float = float(raw["water_level_trend"])
                if -5.0 <= wlt_float <= 5.0:
                    result["water_level_trend"] = wlt_float
            elif result["water_level"] is not None:
                # Derive trend from history buffer
                result["water_level_trend"] = self._derive_trend(result["water_level"])

            if result["water_level"] is not None:
                self.status = DataProviderStatus.LIVE
                self.last_error = None
                self.fallback_used = False
            else:
                self.status = DataProviderStatus.FALLBACK
                self.fallback_used = True

        except Exception as e:
            self.status = DataProviderStatus.ERROR
            self.last_error = str(e)
            self.fallback_used = True
            logger.warning(f"[CWCWaterLevelAdapter] Error processing CWC telemetry: {e}")

        return result

    def _derive_trend(self, current_wl: float) -> Optional[float]:
        """Derives water_level_trend (m/h) using bounded sliding history window."""
        now_mono = time.monotonic()
        now_utc = datetime.now(timezone.utc)

        # Append current reading to history buffer
        self._history.append((now_mono, now_utc, current_wl))

        if len(self._history) < 2:
            return None

        # Compare with oldest reading in history
        prev_mono, _, prev_wl = self._history[0]
        elapsed_seconds = now_mono - prev_mono
        elapsed_hours = elapsed_seconds / 3600.0

        if elapsed_hours >= (60.0 / 3600.0):  # At least 60 seconds
            trend = (current_wl - prev_wl) / elapsed_hours
            trend = max(-5.0, min(5.0, round(trend, 2)))
            return trend

        return None

    def _fetch_with_cache(self) -> Optional[Dict[str, Any]]:
        """Fetches from CWC endpoint with TTL cache."""
        now_mono = time.monotonic()

        if self._cached_response is not None and (now_mono - self._cache_timestamp) < self.cache_ttl:
            self.age_seconds = round(now_mono - self._cache_timestamp, 1)
            self.is_stale = self.age_seconds > (2 * self.cache_ttl)
            return self._cached_response

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(self.endpoint_url, params={"station_id": self.station_id})

            if resp.status_code != 200:
                self.status = DataProviderStatus.ERROR
                self.last_error = f"HTTP {resp.status_code}"
                return None

            data = resp.json()
            self._cached_response = data
            self._cache_timestamp = now_mono
            self.observed_at = datetime.now(timezone.utc).isoformat()
            self.age_seconds = 0.0
            self.is_stale = False
            return data

        except (httpx.TimeoutException, httpx.RequestError) as e:
            self.status = DataProviderStatus.ERROR
            self.last_error = str(e)
            # Serve stale cache if available
            if self._cached_response is not None:
                self.age_seconds = round(now_mono - self._cache_timestamp, 1)
                self.is_stale = True
                return self._cached_response
            return None
