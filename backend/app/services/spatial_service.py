"""
AapdaNetra-X — Phase 6.14 Spatial Risk Engine Service
Provides GIS / spatial risk intelligence combining DEM elevation/slope, hazard layers,
population exposure, critical infrastructure exposure, and route-level spatial hazard scoring.

Architectural Rule:
- Keeps ML GBR 7-feature prediction schema untouched.
- Integrates spatial intelligence as a separate decision-support / contextual layer:
  ML Risk + Spatial Risk / Context = Decision-Support Spatial Intelligence
- Uses PostGIS spatial functions (ST_Intersects, ST_Within, ST_DWithin, ST_Transform)
  with EPSG:4326 for stored geometries and EPSG:3857 for projected metric distance operations.
"""
import math
import logging
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.data.providers.data_adapter import get_data_adapter

logger = logging.getLogger("aapdanetra.spatial_service")


class SpatialService:
    """
    Central Spatial Risk Engine Service.
    Coordinates spatial queries, DEM lookups, hazard layer evaluation, and route exposure scoring.
    """

    def __init__(self):
        self.default_srid = 4326
        self.projected_srid = 3857

    def get_elevation(self, lat: float, lng: float) -> Dict[str, Any]:
        """Looks up DEM elevation and slope for a point using ElevationAdapter."""
        adapter = get_data_adapter().elevation_adapter
        if adapter is not None:
            return adapter.get_elevation_and_slope(lat, lng)
        return {
            "elevation_m": None,
            "slope_deg": None,
            "source": "unavailable",
            "provenance": "elevation:unavailable",
            "is_available": False,
            "reason": "ElevationAdapter not initialized",
            "observed_at": None,
        }

    def get_hazards(self) -> Dict[str, Any]:
        """Returns spatial hazard layers summary and features."""
        adapter = get_data_adapter().hazard_adapter
        if adapter is not None:
            return adapter.get_layers_summary()
        return {
            "is_available": False,
            "provenance": "hazard:unavailable",
            "layer_count": 0,
            "hazard_features": [],
            "observed_at": None,
        }

    def evaluate_point_hazard(self, lat: float, lng: float) -> Dict[str, Any]:
        """Evaluates hazard intersection for a specific coordinate."""
        adapter = get_data_adapter().hazard_adapter
        if adapter is not None:
            return adapter.evaluate_point_hazard(lat, lng)
        return {
            "in_hazard_zone": False,
            "hazard_level": "LOW",
            "hazard_type": None,
            "provenance": "hazard:unavailable",
            "is_available": False,
        }

    def get_exposure_summary(self) -> Dict[str, Any]:
        """
        Aggregates population exposure and critical infrastructure spatial exposure.
        Combines spatial layer provenance with real dataset metrics.
        """
        adapter = get_data_adapter()
        pop_features = adapter.population_adapter.get_features() if adapter.population_adapter else {}
        infra_features = adapter.infrastructure_adapter.get_features() if adapter.infrastructure_adapter else {}
        hazard_summary = self.get_hazards()

        pop_exposure = pop_features.get("population_exposure")
        infra_vulnerability = infra_features.get("infrastructure_vulnerability")

        return {
            "population_exposure": pop_exposure,
            "population_provenance": adapter.provenance.get("population_exposure", "simulated"),
            "infrastructure_vulnerability": infra_vulnerability,
            "infrastructure_provenance": adapter.provenance.get("infrastructure_vulnerability", "simulated"),
            "hazard_layers_available": hazard_summary.get("is_available", False),
            "hazard_provenance": hazard_summary.get("provenance", "hazard:unavailable"),
            "spatial_crs": settings.spatial_crs,
            "projected_crs": settings.projected_crs,
        }

    def calculate_route_spatial_hazard(
        self,
        waypoints: List[Dict[str, float]],
        base_safety_score: float = 0.85
    ) -> Dict[str, Any]:
        """
        Enriches route evaluation with spatial hazard exposure metrics.

        Parameters:
        - waypoints: List of dicts containing 'lat' and 'lng'
        - base_safety_score: Unadjusted route safety score [0.0, 1.0]

        Returns:
        - spatial_exposure_ratio: Portion of route line segments intersecting or near hazard zones [0.0, 1.0]
        - hazard_penalty: Penalty subtracted from safety score
        - adjusted_safety_score: Final spatially aware safety score [0.05, 0.95]
        - water_proximity_km: Distance to nearest water/flood epicentral corridor
        - elevation_min_m: Minimum elevation along route if DEM available
        - provenance: Spatial data provenance string
        """
        if not waypoints or len(waypoints) == 0:
            return {
                "spatial_exposure_ratio": 0.0,
                "hazard_penalty": 0.0,
                "adjusted_safety_score": base_safety_score,
                "water_proximity_km": 1.5,
                "elevation_min_m": None,
                "provenance": "hazard:unavailable",
            }

        adapter = get_data_adapter()
        hazard_adapter = adapter.hazard_adapter
        elevation_adapter = adapter.elevation_adapter

        hazard_points_count = 0
        elevations = []
        min_water_dist = float("inf")

        ref_water_lat, ref_water_lng = 28.6480, 77.2300  # Sector B Yamuna epicenter

        for wp in waypoints:
            lat = float(wp.get("lat", 28.6448))
            lng = float(wp.get("lng", 77.2167))

            # Water proximity check
            d_lat = (lat - ref_water_lat) * 111.0
            d_lng = (lng - ref_water_lng) * 111.0 * math.cos(math.radians(ref_water_lat))
            dist_km = math.sqrt(d_lat * d_lat + d_lng * d_lng)
            if dist_km < min_water_dist:
                min_water_dist = dist_km

            # Hazard intersection check
            if hazard_adapter and hazard_adapter.is_available:
                eval_res = hazard_adapter.evaluate_point_hazard(lat, lng)
                if eval_res.get("in_hazard_zone"):
                    hazard_points_count += 1

            # Elevation check
            if elevation_adapter and elevation_adapter.is_available:
                elev_res = elevation_adapter.get_elevation_and_slope(lat, lng)
                if elev_res.get("elevation_m") is not None:
                    elevations.append(elev_res["elevation_m"])

        total_pts = len(waypoints)
        exposure_ratio = round(hazard_points_count / total_pts, 3) if total_pts > 0 else 0.0

        # Calculate hazard penalty
        # If real hazard layer is available, use exposure_ratio; otherwise use water proximity curve
        if hazard_adapter and hazard_adapter.is_available:
            hazard_penalty = exposure_ratio * settings.spatial_hazard_weight
            provenance = hazard_adapter.provenance_tag
        else:
            # Fallback proximity penalty: higher near river corridor
            if min_water_dist < 0.5:
                hazard_penalty = 0.25 * settings.spatial_hazard_weight
            elif min_water_dist < 1.5:
                hazard_penalty = 0.12 * settings.spatial_hazard_weight
            else:
                hazard_penalty = 0.0
            provenance = "hazard:provisional_river_proximity"

        adjusted_safety = round(max(0.05, min(0.95, base_safety_score - hazard_penalty)), 2)

        return {
            "spatial_exposure_ratio": exposure_ratio,
            "hazard_penalty": round(hazard_penalty, 3),
            "adjusted_safety_score": adjusted_safety,
            "water_proximity_km": round(min_water_dist, 2),
            "elevation_min_m": min(elevations) if elevations else None,
            "provenance": provenance,
        }

    async def run_postgis_spatial_analysis(
        self,
        db_session: AsyncSession,
        lat: float,
        lng: float,
        radius_meters: float = 1000.0,
    ) -> Dict[str, Any]:
        """
        Executes PostGIS ST_DWithin and ST_Intersects spatial queries on PostGIS tables.
        Uses ST_Transform(geom, 3857) for meter-radius spatial searches when DB is active.
        """
        try:
            # Query nearby assets within metric radius using PostGIS ST_DWithin on ST_Transform
            query = text("""
                SELECT asset_code, name, asset_type, vulnerability, status,
                       ST_Distance(
                           ST_Transform(location_geom, :proj_srid),
                           ST_Transform(ST_SetSRID(ST_MakePoint(:lng, :lat), :default_srid), :proj_srid)
                       ) AS distance_m
                FROM critical_assets
                WHERE ST_DWithin(
                    ST_Transform(location_geom, :proj_srid),
                    ST_Transform(ST_SetSRID(ST_MakePoint(:lng, :lat), :default_srid), :proj_srid),
                    :radius
                )
                ORDER BY distance_m ASC
            """)
            result = await db_session.execute(
                query,
                {
                    "lat": lat,
                    "lng": lng,
                    "radius": radius_meters,
                    "default_srid": self.default_srid,
                    "proj_srid": self.projected_srid,
                },
            )
            rows = result.mappings().all()
            assets = [dict(row) for row in rows]
            return {
                "spatial_query_status": "executed",
                "center": {"lat": lat, "lng": lng},
                "radius_meters": radius_meters,
                "nearby_assets_count": len(assets),
                "assets": assets,
                "crs": f"Stored {settings.spatial_crs} / Measured {settings.projected_crs}",
            }
        except Exception as e:
            logger.warning(f"[SpatialService] PostGIS query execution error: {e}")
            return {
                "spatial_query_status": "fallback",
                "center": {"lat": lat, "lng": lng},
                "radius_meters": radius_meters,
                "nearby_assets_count": 0,
                "assets": [],
                "error": str(e),
                "crs": f"Stored {settings.spatial_crs}",
            }


# Global singleton instance & accessor
_global_spatial_service: Optional[SpatialService] = None


def get_spatial_service() -> SpatialService:
    global _global_spatial_service
    if _global_spatial_service is None:
        _global_spatial_service = SpatialService()
    return _global_spatial_service
