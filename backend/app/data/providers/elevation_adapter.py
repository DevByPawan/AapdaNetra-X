"""
AapdaNetra-X — Phase 6.14 DEM / Elevation Data Adapter
Provides elevation and derived slope spatial lookups from real DEM datasets when configured.

Scientific & Integrity Policy:
- Never fabricates elevation or slope values.
- Never generates fake DEM tiles to present as real data.
- If no valid DEM dataset is configured or available, explicitly reports unavailable status
  and returns None for elevation/slope with provenance 'elevation:unavailable'.
"""
import math
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from app.data.providers.base import DataProvider, DataProviderStatus

logger = logging.getLogger("aapdanetra.elevation")


class ElevationAdapter(DataProvider):
    """
    DEM Elevation and Slope Spatial Data Provider.
    Extracts elevation (meters above sea level) and calculates slope (degrees) when real DEM sources are present.
    """

    def __init__(
        self,
        enabled: bool = False,
        source_name: str = "unavailable",
        dem_data_path: Optional[Path] = None,
        cache_ttl: int = 86400,
    ):
        super().__init__()
        self.enabled = enabled
        self.source_name = source_name or "unavailable"
        self.dem_data_path = Path(dem_data_path) if dem_data_path else None
        self.cache_ttl = max(3600, cache_ttl)

        # Cache state
        self._cache: Dict[Tuple[float, float], Dict[str, Any]] = {}
        self._cache_timestamp: float = 0.0

        # Provenance & Status
        if not self.enabled or self.dem_data_path is None or not self.dem_data_path.exists():
            self.status = DataProviderStatus.FALLBACK
            self.provenance_tag = "elevation:unavailable"
            self.is_available = False
        else:
            self.provenance_tag = f"elevation:{self.source_name.lower().replace(' ', '_')}"
            self.is_available = True

    def get_features(self) -> Dict[str, Optional[float]]:
        """
        Required DataProvider interface method.
        Elevation is a spatial contextual feature rather than a direct 7-feature ML schema input.
        Returns empty feature mapping subset while maintaining contract.
        """
        return {}

    def get_elevation_and_slope(self, lat: float, lng: float) -> Dict[str, Any]:
        """
        Queries elevation (meters) and slope (degrees) for given geographic coordinates.

        Validates inputs:
        - Lat [-90, 90], Lng [-180, 180]
        - Rejects NaN/Inf coordinates

        Returns dictionary with keys:
          - elevation_m: Optional[float]
          - slope_deg: Optional[float]
          - source: str
          - provenance: str
          - is_available: bool
          - observed_at: Optional[str]
        """
        # Validate coordinates
        if not (isinstance(lat, (int, float)) and isinstance(lng, (int, float))):
            return self._build_unavailable_result("Invalid coordinate types")

        if math.isnan(lat) or math.isnan(lng) or math.isinf(lat) or math.isinf(lng):
            return self._build_unavailable_result("NaN or Infinity coordinates")

        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            return self._build_unavailable_result("Coordinates out of WGS84 bounds")

        if not self.is_available or self.dem_data_path is None or not self.dem_data_path.exists():
            return self._build_unavailable_result("No real DEM dataset configured")

        coord_key = (round(lat, 5), round(lng, 5))
        now_mono = time.monotonic()

        if coord_key in self._cache and (now_mono - self._cache_timestamp) < self.cache_ttl:
            return self._cache[coord_key]

        try:
            lookup = self._read_dem_file(self.dem_data_path, lat, lng)
            if lookup is not None:
                elev, slope = lookup
                res = {
                    "elevation_m": round(float(elev), 2),
                    "slope_deg": round(float(slope), 2) if slope is not None else None,
                    "source": self.source_name,
                    "provenance": self.provenance_tag,
                    "is_available": True,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                }
                self._cache[coord_key] = res
                self._cache_timestamp = now_mono
                return res
            else:
                return self._build_unavailable_result("Point outside DEM raster coverage")
        except Exception as e:
            logger.warning(f"[ElevationAdapter] Error querying DEM file ({self.dem_data_path}): {e}")
            return self._build_unavailable_result(f"DEM read error: {e}")

    def _read_dem_file(self, path: Path, lat: float, lng: float) -> Optional[Tuple[float, Optional[float]]]:
        """
        Parses configured DEM file (JSON grid, GeoTIFF via rasterio if installed, or ASCII grid).
        Extracts elevation value at (lat, lng) and derives slope if neighbor cells exist.
        """
        suffix = path.suffix.lower()

        # JSON grid format (for structured offline DEM datasets)
        if suffix == ".json":
            import json
            with open(path, "r") as f:
                data = json.load(f)

            grid = data.get("elevation_grid", [])
            bbox = data.get("bbox")  # [min_lng, min_lat, max_lng, max_lat]
            if bbox and len(bbox) == 4:
                min_lng, min_lat, max_lng, max_lat = bbox
                if not (min_lng <= lng <= max_lng and min_lat <= lat <= max_lat):
                    return None

            # Look up closest sample point in grid
            if isinstance(grid, list):
                closest_dist = float("inf")
                best_elev = None
                best_slope = None
                for cell in grid:
                    c_lat = cell.get("lat")
                    c_lng = cell.get("lng")
                    if c_lat is not None and c_lng is not None:
                        d = (c_lat - lat) ** 2 + (c_lng - lng) ** 2
                        if d < closest_dist:
                            closest_dist = d
                            best_elev = cell.get("elevation")
                            best_slope = cell.get("slope")
                if best_elev is not None:
                    return float(best_elev), float(best_slope) if best_slope is not None else None

        # GeoTIFF raster format if rasterio is available
        elif suffix in (".tif", ".tiff"):
            try:
                import rasterio
                with rasterio.open(path) as src:
                    row, col = src.index(lng, lat)
                    elev_val = src.read(1)[row, col]
                    if elev_val != src.nodata and not math.isnan(elev_val):
                        return float(elev_val), None
            except ImportError:
                logger.warning("[ElevationAdapter] rasterio module not installed. GeoTIFF parsing unavailable.")
            except Exception as e:
                logger.warning(f"[ElevationAdapter] rasterio read error: {e}")

        return None

    def _build_unavailable_result(self, reason: str) -> Dict[str, Any]:
        """Builds explicit unavailable result without fabricating any data."""
        return {
            "elevation_m": None,
            "slope_deg": None,
            "source": self.source_name if self.is_available else "unavailable",
            "provenance": "elevation:unavailable",
            "is_available": False,
            "reason": reason,
            "observed_at": None,
        }
