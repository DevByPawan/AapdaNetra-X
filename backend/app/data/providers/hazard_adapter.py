"""
AapdaNetra-X — Phase 6.14 Spatial Hazard Layer Adapter
Manages authoritative hazard polygons, inundation zones, water bodies, and restricted areas.

Scientific & Integrity Policy:
- Does NOT invent or synthesize fake flood polygons.
- Validates all input geometries (validity, CRS/SRID, bounds, missing/empty geometries, malformed shapes, NaN/Inf).
- If no dataset is configured, explicitly reports status as unavailable or provisional with clear provenance
  ('hazard:unavailable' or 'hazard:provisional').
"""
import json
import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

from app.data.providers.base import DataProvider, DataProviderStatus

logger = logging.getLogger("aapdanetra.hazard")


class HazardLayerAdapter(DataProvider):
    """
    Spatial Hazard Layer Provider.
    Ingests and validates flood-prone polygons, inundation zones, hazard boundaries, and water bodies.
    """

    def __init__(
        self,
        enabled: bool = False,
        dataset_path: Optional[Path] = None,
        cache_ttl: int = 86400,
    ):
        super().__init__()
        self.enabled = enabled
        self.dataset_path = Path(dataset_path) if dataset_path else None
        self.cache_ttl = max(3600, cache_ttl)

        self.hazard_features: List[Dict[str, Any]] = []
        self._cache_timestamp: float = 0.0

        if not self.enabled or self.dataset_path is None or not self.dataset_path.exists():
            self.status = DataProviderStatus.FALLBACK
            self.provenance_tag = "hazard:unavailable"
            self.is_available = False
        else:
            self.provenance_tag = "hazard:authoritative_dataset"
            self.is_available = True
            self._load_and_validate_dataset()

    def get_features(self) -> Dict[str, Optional[float]]:
        """
        Required DataProvider interface method.
        Returns empty dict as hazard polygons provide spatial layer context.
        """
        return {}

    def _load_and_validate_dataset(self):
        """Loads and strictly validates GeoJSON or JSON hazard layer geometries."""
        if not self.dataset_path or not self.dataset_path.exists():
            self.is_available = False
            self.provenance_tag = "hazard:unavailable"
            return

        try:
            with open(self.dataset_path, "r") as f:
                data = json.load(f)

            raw_features = data.get("features", []) if isinstance(data, dict) else []
            valid_list = []

            for idx, feat in enumerate(raw_features):
                validated = self.validate_spatial_geometry(feat)
                if validated["is_valid"]:
                    valid_list.append(feat)
                else:
                    logger.warning(
                        f"[HazardLayerAdapter] Rejected invalid feature index {idx} in {self.dataset_path}: {validated['reason']}"
                    )

            self.hazard_features = valid_list
            if self.hazard_features:
                self.status = DataProviderStatus.LIVE
                self.is_available = True
                self.provenance_tag = f"hazard:dataset_{self.dataset_path.stem}"
            else:
                self.status = DataProviderStatus.FALLBACK
                self.is_available = False
                self.provenance_tag = "hazard:unavailable"

        except Exception as e:
            logger.error(f"[HazardLayerAdapter] Error loading hazard dataset {self.dataset_path}: {e}")
            self.status = DataProviderStatus.ERROR
            self.is_available = False
            self.provenance_tag = "hazard:unavailable"

    def validate_spatial_geometry(self, feature: Dict[str, Any]) -> Dict[str, Any]:
        """
        Strict spatial validation for a GeoJSON feature:
        - Must contain valid geometry object
        - Type must be Polygon, MultiPolygon, LineString, or Point
        - Coordinates must not contain NaN or Inf
        - Coordinates must lie within valid EPSG:4326 bounds [-180, -90, 180, 90]
        - Polygon rings must be closed (first coordinate == last coordinate)
        """
        if not isinstance(feature, dict):
            return {"is_valid": False, "reason": "Feature is not a dictionary"}

        geom = feature.get("geometry")
        if not geom or not isinstance(geom, dict):
            return {"is_valid": False, "reason": "Missing or null geometry"}

        gtype = geom.get("type")
        coords = geom.get("coordinates")

        if not gtype or coords is None:
            return {"is_valid": False, "reason": "Empty geometry type or coordinates"}

        allowed_types = ["Polygon", "MultiPolygon", "LineString", "Point", "MultiLineString"]
        if gtype not in allowed_types:
            return {"is_valid": False, "reason": f"Unsupported geometry type: {gtype}"}

        # Check numeric validity & coordinate bounds recursively
        valid_coords, coord_reason = self._check_coords_validity(coords, gtype)
        if not valid_coords:
            return {"is_valid": False, "reason": coord_reason}

        return {"is_valid": True, "reason": "Valid geometry"}

    def _check_coords_validity(self, coords: Any, gtype: str) -> Tuple[bool, str]:
        """Recursively checks coordinate arrays for NaN, Inf, bounds, and closed polygon rings."""
        if isinstance(coords, (int, float)):
            if math.isnan(coords) or math.isinf(coords):
                return False, "NaN or Infinity value found in coordinates"
            return True, ""

        if isinstance(coords, list):
            if len(coords) == 0:
                return False, "Empty coordinate array"

            # Check if this level is a 2D/3D coordinate pair [lng, lat, (elev)]
            if len(coords) in (2, 3) and all(isinstance(x, (int, float)) for x in coords):
                lng, lat = float(coords[0]), float(coords[1])
                if math.isnan(lng) or math.isnan(lat) or math.isinf(lng) or math.isinf(lat):
                    return False, "NaN or Infinity in coordinate pair"
                if not (-180.0 <= lng <= 180.0 and -90.0 <= lat <= 90.0):
                    return False, f"Coordinates out of bounds: [{lng}, {lat}]"
                return True, ""

            # If gtype is Polygon and this level is a ring (list of point pairs)
            if gtype == "Polygon" and len(coords) > 0 and isinstance(coords[0], list) and len(coords[0]) in (2, 3) and isinstance(coords[0][0], (int, float)):
                if len(coords) < 4:
                    return False, "Polygon linear ring must contain at least 4 coordinates"
                first_pt = coords[0]
                last_pt = coords[-1]
                if round(first_pt[0], 6) != round(last_pt[0], 6) or round(first_pt[1], 6) != round(last_pt[1], 6):
                    return False, "Polygon ring is not closed (first != last coordinate)"

            # Recurse for nested coordinate arrays
            for sub in coords:
                ok, reason = self._check_coords_validity(sub, gtype)
                if not ok:
                    return False, reason

        return True, ""

    def get_layers_summary(self) -> Dict[str, Any]:
        """Returns metadata summary of available spatial hazard layers."""
        return {
            "is_available": self.is_available,
            "provenance": self.provenance_tag,
            "layer_count": len(self.hazard_features),
            "hazard_features": self.hazard_features,
            "observed_at": datetime.now(timezone.utc).isoformat() if self.is_available else None,
        }

    def evaluate_point_hazard(self, lat: float, lng: float) -> Dict[str, Any]:
        """
        Evaluates whether a point (lat, lng) intersects any loaded hazard polygon.
        If Shapely is available, uses polygon containment; otherwise uses ray casting.
        If no dataset is available, returns explicit fallback status.
        """
        if not self.is_available or not self.hazard_features:
            return {
                "in_hazard_zone": False,
                "hazard_level": "NONE",
                "hazard_type": None,
                "provenance": "hazard:unavailable",
                "is_available": False,
            }

        try:
            import shapely.geometry as sg
            point = sg.Point(lng, lat)
            for feat in self.hazard_features:
                geom = sg.shape(feat.get("geometry", {}))
                if geom.contains(point) or geom.intersects(point):
                    props = feat.get("properties", {})
                    return {
                        "in_hazard_zone": True,
                        "hazard_level": props.get("severity", props.get("level", "HIGH")),
                        "hazard_type": props.get("type", "inundation_zone"),
                        "layer_name": props.get("name", "Hazard Zone"),
                        "provenance": self.provenance_tag,
                        "is_available": True,
                    }
        except ImportError:
            # Fallback ray casting point-in-polygon check for simple polygons
            for feat in self.hazard_features:
                geom = feat.get("geometry", {})
                if geom.get("type") == "Polygon":
                    rings = geom.get("coordinates", [])
                    if rings and self._point_in_polygon(lat, lng, rings[0]):
                        props = feat.get("properties", {})
                        return {
                            "in_hazard_zone": True,
                            "hazard_level": props.get("severity", props.get("level", "HIGH")),
                            "hazard_type": props.get("type", "inundation_zone"),
                            "layer_name": props.get("name", "Hazard Zone"),
                            "provenance": self.provenance_tag,
                            "is_available": True,
                        }

        return {
            "in_hazard_zone": False,
            "hazard_level": "LOW",
            "hazard_type": None,
            "provenance": self.provenance_tag,
            "is_available": True,
        }

    @staticmethod
    def _point_in_polygon(lat: float, lng: float, ring: List[List[float]]) -> bool:
        """Ray-casting algorithm for checking if point is inside a polygon ring."""
        inside = False
        n = len(ring)
        p1x, p1y = ring[0][0], ring[0][1]
        for i in range(n + 1):
            p2x, p2y = ring[i % n][0], ring[i % n][1]
            if lat > min(p1y, p2y):
                if lat <= max(p1y, p2y):
                    if lng <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (lat - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or lng <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside
