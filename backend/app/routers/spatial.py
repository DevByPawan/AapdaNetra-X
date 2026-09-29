"""
AapdaNetra-X — Phase 6.14 Advanced Spatial Intelligence API Router
Exposes DEM elevation, spatial hazard layers, population/infrastructure exposure, and route spatial safety endpoints.
"""
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.spatial_service import get_spatial_service
from app.db.session import get_db

router = APIRouter(prefix="/spatial", tags=["Spatial Intelligence"])


def _build_api_response(data: Any) -> Dict[str, Any]:
    """Helper formatting API envelope according to project standards."""
    return {
        "success": True,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": settings.api_version,
    }


@router.get("/summary")
def get_spatial_summary():
    """
    Returns overall spatial intelligence summary including active CRS,
    DEM availability, hazard layer counts, and provider provenance.
    """
    svc = get_spatial_service()
    hazards = svc.get_hazards()
    exposure = svc.get_exposure_summary()

    summary_data = {
        "spatial_crs": settings.spatial_crs,
        "projected_crs": settings.projected_crs,
        "dem_enabled": settings.dem_enabled,
        "dem_source": settings.dem_source,
        "hazard_layers": hazards,
        "exposure": exposure,
        "limitation_notice": (
            "Provisional spatial risk layers are explicitly labeled. "
            "ML risk prediction schema (7 features) is preserved independently."
        ),
    }
    return _build_api_response(summary_data)


@router.get("/elevation")
def get_elevation(
    lat: float = Query(..., ge=-90.0, le=90.0, description="WGS84 Latitude"),
    lng: float = Query(..., ge=-180.0, le=180.0, description="WGS84 Longitude"),
):
    """
    Queries DEM elevation (meters) and derived slope (degrees) for given lat/lng.
    Reports explicit fallback/unavailable status if no DEM dataset is configured.
    """
    svc = get_spatial_service()
    result = svc.get_elevation(lat, lng)
    return _build_api_response(result)


@router.get("/hazards")
def get_hazards():
    """
    Returns spatial hazard polygons, inundation boundaries, and water body layers.
    Exposes dataset provenance and validation status.
    """
    svc = get_spatial_service()
    result = svc.get_hazards()
    return _build_api_response(result)


@router.get("/exposure")
def get_exposure():
    """
    Returns population exposure headcount and critical infrastructure spatial vulnerability.
    """
    svc = get_spatial_service()
    result = svc.get_exposure_summary()
    return _build_api_response(result)


@router.get("/routes/{route_id}")
def get_route_spatial_safety(
    route_id: str,
    origin_lat: float = Query(28.6448, ge=-90.0, le=90.0),
    origin_lng: float = Query(77.2167, ge=-180.0, le=180.0),
    dest_lat: float = Query(28.6600, ge=-90.0, le=90.0),
    dest_lng: float = Query(77.2300, ge=-180.0, le=180.0),
):
    """
    Calculates route-level spatial hazard exposure for a route candidate.
    """
    svc = get_spatial_service()
    sample_waypoints = [
        {"lat": origin_lat, "lng": origin_lng},
        {"lat": (origin_lat + dest_lat) / 2.0, "lng": (origin_lng + dest_lng) / 2.0},
        {"lat": dest_lat, "lng": dest_lng},
    ]
    spatial_res = svc.calculate_route_spatial_hazard(sample_waypoints)
    res_data = {
        "route_id": route_id,
        "spatial_hazard_exposure": spatial_res["spatial_exposure_ratio"],
        "hazard_penalty": spatial_res["hazard_penalty"],
        "modeled_safety_score": spatial_res["adjusted_safety_score"],
        "water_proximity_km": spatial_res["water_proximity_km"],
        "elevation_min_m": spatial_res["elevation_min_m"],
        "provenance": spatial_res["provenance"],
        "terminology_notice": "Higher modeled route safety score indicates lower estimated spatial exposure.",
    }
    return _build_api_response(res_data)
