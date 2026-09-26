"""
AapdaNetra-X — Traffic Data Adapter
Provider-safe adapter for road traffic & congestion feeds.
Normalizes actual_speed and freeflow_speed into road_congestion ratio [0.0, 1.0].
Supports TTL caching (default 180s), stale cache serving, and explicit fallback behavior.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Any

import httpx

from app.data.providers.base import DataProvider, DataProviderStatus

logger = logging.getLogger("aapdanetra.traffic")


class TrafficAdapter(DataProvider):
    """
    Provider-safe traffic telemetry adapter.
    Normalizes speed feeds into road_congestion ratio (0.0 = free flow, 1.0 = gridlock).
    """

    def __init__(
        self,
        api_key: str = "",
        endpoint_url: str = "",
        cache_ttl: int = 180,
        timeout: float = 5.0,
    ):
        super().__init__()
        self.api_key = api_key
        self.endpoint_url = endpoint_url
        self.cache_ttl = max(30, cache_ttl)
        self.timeout = timeout

        # Cache state
        self._cached_response: Optional[Dict[str, Any]] = None
        self._cache_timestamp: float = 0.0

        # Metadata
        self.observed_at: Optional[str] = None
        self.age_seconds: Optional[float] = None
        self.is_stale: bool = False
        self.fallback_used: bool = False

    def get_features(self) -> Dict[str, Optional[float]]:
        """
        Fetch and compute road_congestion ratio [0.0, 1.0].
        Returns None if no API endpoint/key is configured or request fails.
        """
        result: Dict[str, Optional[float]] = {
            "road_congestion": None,
        }

        if not self.endpoint_url and not self.api_key:
            self.status = DataProviderStatus.FALLBACK
            self.last_error = "No traffic provider endpoint or API key configured"
            self.fallback_used = True
            logger.debug("[TrafficAdapter] No endpoint/key configured — using fallback.")
            return result

        try:
            raw = self._fetch_with_cache()
            if raw is None:
                self.fallback_used = True
                return result

            actual_speed = raw.get("actual_speed")
            freeflow_speed = raw.get("freeflow_speed")

            if actual_speed is not None and freeflow_speed is not None:
                try:
                    v_act = float(actual_speed)
                    v_free = float(freeflow_speed)

                    if v_free <= 0.0 or v_act < 0.0:
                        logger.warning(f"[TrafficAdapter] Invalid speed values: actual={v_act}, freeflow={v_free}")
                        self.fallback_used = True
                        return result

                    # Congestion = 1.0 - (actual / freeflow)
                    speed_ratio = max(0.0, min(1.0, v_act / v_free))
                    congestion = round(1.0 - speed_ratio, 3)

                    # Bounded check [0.0, 1.0]
                    result["road_congestion"] = max(0.0, min(1.0, congestion))
                    self.status = DataProviderStatus.LIVE
                    self.last_error = None
                    self.fallback_used = False
                    logger.info(f"[TrafficAdapter] Live traffic data: road_congestion={result['road_congestion']}")

                except (ValueError, TypeError) as e:
                    self.status = DataProviderStatus.ERROR
                    self.last_error = f"Malformed speed data: {e}"
                    self.fallback_used = True

            elif "road_congestion" in raw and raw["road_congestion"] is not None:
                # Direct congestion ratio in payload
                try:
                    cong_val = max(0.0, min(1.0, float(raw["road_congestion"])))
                    result["road_congestion"] = cong_val
                    self.status = DataProviderStatus.LIVE
                    self.last_error = None
                    self.fallback_used = False
                except (ValueError, TypeError) as e:
                    self.status = DataProviderStatus.ERROR
                    self.last_error = f"Malformed congestion value: {e}"
                    self.fallback_used = True
            else:
                self.status = DataProviderStatus.FALLBACK
                self.fallback_used = True

        except Exception as e:
            self.status = DataProviderStatus.ERROR
            self.last_error = str(e)
            self.fallback_used = True
            logger.warning(f"[TrafficAdapter] Error fetching traffic data: {e}")

        return result

    def _fetch_with_cache(self) -> Optional[Dict[str, Any]]:
        """Fetches from traffic API with TTL cache."""
        now_mono = time.monotonic()

        if self._cached_response is not None and (now_mono - self._cache_timestamp) < self.cache_ttl:
            self.age_seconds = round(now_mono - self._cache_timestamp, 1)
            self.is_stale = self.age_seconds > (2 * self.cache_ttl)
            return self._cached_response

        if not self.endpoint_url:
            return None

        try:
            params = {}
            if self.api_key:
                params["key"] = self.api_key

            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(self.endpoint_url, params=params)

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
            self.last_error = f"Request error: {e}"

            if self._cached_response is not None:
                self.age_seconds = round(now_mono - self._cache_timestamp, 1)
                self.is_stale = True
                return self._cached_response
            return None

    def invalidate_cache(self):
        """Force-clears cached traffic response."""
        self._cached_response = None
        self._cache_timestamp = 0.0
