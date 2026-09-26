"""
AapdaNetra-X — Weather Adapter (OpenWeatherMap)
Fetches live rainfall data from OpenWeatherMap Current Weather API and maps
to ML feature names: rainfall_intensity, rainfall_trend.

Supports bounded sliding-window trend calculation, TTL caching, UTC timestamping,
stale cache fallback, and bounds validation.
"""
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Tuple

import httpx

from app.data.providers.base import DataProvider, DataProviderStatus

logger = logging.getLogger("aapdanetra.weather")


class WeatherAdapter(DataProvider):
    """
    Fetches current weather data from OpenWeatherMap API.

    Maps:
      - rain.1h (mm/h) → rainfall_intensity
      - Δ rainfall over successive observations → rainfall_trend (mm/h²)
    """

    OWM_URL = "https://api.openweathermap.org/data/2.5/weather"

    def __init__(
        self,
        api_key: str = "",
        lat: float = 28.6448,
        lon: float = 77.2167,
        cache_ttl: int = 300,
        timeout: float = 5.0,
    ):
        super().__init__()
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.cache_ttl = max(30, cache_ttl)
        self.timeout = timeout

        # Cache state
        self._cached_response: Optional[Dict[str, Any]] = None
        self._cache_timestamp: float = 0.0

        # Bounded sliding window history buffer for trend derivation: deque of (monotonic_time, utc_dt, rainfall)
        self._history: deque = deque(maxlen=10)

        # Metadata
        self.observed_at: Optional[str] = None
        self.age_seconds: Optional[float] = None
        self.is_stale: bool = False
        self.fallback_used: bool = False

    def get_features(self) -> Dict[str, Optional[float]]:
        """
        Fetch rainfall_intensity and rainfall_trend from OpenWeatherMap.
        Returns None values on failure so orchestrator handles fallback appropriately.
        """
        result: Dict[str, Optional[float]] = {
            "rainfall_intensity": None,
            "rainfall_trend": None,
        }

        if not self.api_key:
            self.status = DataProviderStatus.FALLBACK
            self.last_error = "No API key configured"
            self.fallback_used = True
            logger.debug("[WeatherAdapter] No API key — using fallback.")
            return result

        try:
            raw = self._fetch_with_cache()
            if raw is None:
                self.fallback_used = True
                return result

            # Extract rainfall_intensity
            rain_data = raw.get("rain", {})
            rain_1h = rain_data.get("1h")
            rain_3h = rain_data.get("3h")

            if rain_1h is not None:
                raw_rf = float(rain_1h)
            elif rain_3h is not None:
                raw_rf = float(rain_3h) / 3.0
            else:
                raw_rf = 0.0

            # Bounds validation: [0.0, 300.0] mm/h
            rf_intensity = max(0.0, min(300.0, raw_rf))
            result["rainfall_intensity"] = rf_intensity

            # Derived rainfall_trend via history deque
            result["rainfall_trend"] = self._derive_trend(rf_intensity)

            if self.observed_at is None:
                self.observed_at = datetime.now(timezone.utc).isoformat()

            self.status = DataProviderStatus.LIVE
            self.last_error = None
            self.fallback_used = False
            logger.info(f"[WeatherAdapter] Live weather data: rainfall_intensity={rf_intensity:.1f} mm/h")

        except Exception as e:
            self.status = DataProviderStatus.ERROR
            self.last_error = str(e)
            self.fallback_used = True
            logger.warning(f"[WeatherAdapter] Error fetching weather data: {e}")

        return result

    def _derive_trend(self, current_rf: float) -> Optional[float]:
        """Derives rainfall_trend (mm/h²) using bounded sliding history window."""
        now_mono = time.monotonic()
        now_utc = datetime.now(timezone.utc)

        self._history.append((now_mono, now_utc, current_rf))

        if len(self._history) < 2:
            return None

        prev_mono, _, prev_rf = self._history[0]
        elapsed_seconds = now_mono - prev_mono
        elapsed_hours = elapsed_seconds / 3600.0

        if elapsed_hours >= (60.0 / 3600.0):  # At least 60 seconds
            trend = (current_rf - prev_rf) / elapsed_hours
            trend = max(-50.0, min(50.0, round(trend, 2)))
            return trend

        return None

    def _fetch_with_cache(self) -> Optional[Dict[str, Any]]:
        """Fetches from OpenWeatherMap with in-memory cache and stale fallback handling."""
        now_mono = time.monotonic()

        # Check valid cache
        if self._cached_response is not None and (now_mono - self._cache_timestamp) < self.cache_ttl:
            self.age_seconds = round(now_mono - self._cache_timestamp, 1)
            self.is_stale = self.age_seconds > (2 * self.cache_ttl)
            return self._cached_response

        # Make HTTP request
        try:
            params = {
                "lat": self.lat,
                "lon": self.lon,
                "appid": self.api_key,
                "units": "metric",
            }
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(self.OWM_URL, params=params)

            if resp.status_code == 401:
                self.status = DataProviderStatus.ERROR
                self.last_error = "Invalid API key (HTTP 401)"
                logger.error("[WeatherAdapter] Invalid API key.")
                return None

            if resp.status_code != 200:
                self.status = DataProviderStatus.ERROR
                self.last_error = f"HTTP {resp.status_code}"
                logger.warning(f"[WeatherAdapter] HTTP {resp.status_code} from OWM.")
                return None

            data = resp.json()
            self._cached_response = data
            self._cache_timestamp = now_mono

            # Extract UTC observation timestamp if present in OWM response ('dt' field)
            dt_ts = data.get("dt")
            if dt_ts:
                self.observed_at = datetime.fromtimestamp(dt_ts, timezone.utc).isoformat()
            else:
                self.observed_at = datetime.now(timezone.utc).isoformat()

            self.age_seconds = 0.0
            self.is_stale = False
            return data

        except httpx.TimeoutException as e:
            self.status = DataProviderStatus.ERROR
            self.last_error = f"Request timeout: {e}"
            logger.warning(f"[WeatherAdapter] Request timeout to OWM: {e}")

            # Serve stale cache if available
            if self._cached_response is not None:
                self.age_seconds = round(now_mono - self._cache_timestamp, 1)
                self.is_stale = True
                logger.info("[WeatherAdapter] Serving stale cached weather response.")
                return self._cached_response

            return None

        except httpx.RequestError as e:
            self.status = DataProviderStatus.ERROR
            self.last_error = f"Request error: {e}"
            logger.warning(f"[WeatherAdapter] Request error: {e}")

            # Serve stale cache if available
            if self._cached_response is not None:
                self.age_seconds = round(now_mono - self._cache_timestamp, 1)
                self.is_stale = True
                logger.info("[WeatherAdapter] Serving stale cached weather response.")
                return self._cached_response

            return None

    def invalidate_cache(self):
        """Force-clears the cached response and history buffer."""
        self._cached_response = None
        self._cache_timestamp = 0.0
        self._history.clear()
