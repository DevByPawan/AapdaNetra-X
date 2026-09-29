"""
AapdaNetra-X — Phase 6.14 Advanced GIS / Spatial Risk Intelligence Test Suite
Validates DEM provider, Hazard provider, Spatial exposure, PostGIS spatial queries,
Route-level spatial safety enrichment, API contracts, and non-regression guarantees.
"""
import json
import math
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.config import settings
from app.data.providers.elevation_adapter import ElevationAdapter
from app.data.providers.hazard_adapter import HazardLayerAdapter
from app.data.providers.data_adapter import DataAdapter, reset_data_adapter
from app.services.spatial_service import SpatialService, get_spatial_service
from ml.routing.scoring import calculate_route_metrics
from ml.routing.optimizer import RouteOptimizer, reset_optimizer
from app.main import app

client = TestClient(app)


# ── A. DEM / Elevation Provider Tests ────────────────────────────────────
class TestElevationProvider:
    def test_elevation_provider_disabled_fallback(self):
        adapter = ElevationAdapter(enabled=False, source_name="unavailable")
        res = adapter.get_elevation_and_slope(28.6448, 77.2167)
        assert res["is_available"] is False
        assert res["elevation_m"] is None
        assert res["provenance"] == "elevation:unavailable"
        assert res["source"] == "unavailable"

    def test_elevation_provider_invalid_coords(self):
        adapter = ElevationAdapter(enabled=True, source_name="test_dem")
        # Out of bounds lat
        res1 = adapter.get_elevation_and_slope(120.0, 77.2167)
        assert res1["is_available"] is False
        assert res1["provenance"] == "elevation:unavailable"

        # NaN coords
        res2 = adapter.get_elevation_and_slope(float("nan"), 77.2167)
        assert res2["is_available"] is False
        assert res2["provenance"] == "elevation:unavailable"

    def test_elevation_provider_valid_json_dem(self, tmp_path):
        dem_file = tmp_path / "sample_dem.json"
        dem_data = {
            "bbox": [77.1900, 28.6100, 77.2600, 28.6700],
            "elevation_grid": [
                {"lat": 28.6448, "lng": 77.2167, "elevation": 215.0, "slope": 2.1},
                {"lat": 28.6530, "lng": 77.2320, "elevation": 207.5, "slope": 0.5},
            ],
        }
        dem_file.write_text(json.dumps(dem_data))

        adapter = ElevationAdapter(enabled=True, source_name="Delhi_SRTM_30m", dem_data_path=dem_file)
        res = adapter.get_elevation_and_slope(28.6448, 77.2167)
        assert res["is_available"] is True
        assert res["elevation_m"] == 215.0
        assert res["slope_deg"] == 2.1
        assert res["provenance"] == "elevation:delhi_srtm_30m"
        assert res["observed_at"] is not None


# ── B. Spatial Hazard Provider Tests ─────────────────────────────────────
class TestHazardProvider:
    def test_hazard_provider_disabled_fallback(self):
        adapter = HazardLayerAdapter(enabled=False)
        assert adapter.is_available is False
        assert adapter.provenance_tag == "hazard:unavailable"

        eval_res = adapter.evaluate_point_hazard(28.6448, 77.2167)
        assert eval_res["in_hazard_zone"] is False
        assert eval_res["provenance"] == "hazard:unavailable"

    def test_hazard_geometry_validation(self):
        adapter = HazardLayerAdapter(enabled=False)

        # Missing geometry
        invalid_feat1 = {"type": "Feature", "properties": {}}
        val1 = adapter.validate_spatial_geometry(invalid_feat1)
        assert val1["is_valid"] is False

        # Unclosed polygon ring
        invalid_polygon = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[77.2, 28.6], [77.3, 28.6], [77.3, 28.7], [77.2, 28.65]]  # Not closed
                ],
            },
        }
        val2 = adapter.validate_spatial_geometry(invalid_polygon)
        assert val2["is_valid"] is False

        # Valid polygon ring
        valid_polygon = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[77.2, 28.6], [77.3, 28.6], [77.3, 28.7], [77.2, 28.6]]  # Closed
                ],
            },
        }
        val3 = adapter.validate_spatial_geometry(valid_polygon)
        assert val3["is_valid"] is True

    def test_hazard_point_intersection(self, tmp_path):
        hazard_file = tmp_path / "hazards.json"
        hazard_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"name": "Yamuna Sector B Inundation", "severity": "CRITICAL", "type": "inundation_zone"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[77.21, 28.64], [77.25, 28.64], [77.25, 28.66], [77.21, 28.66], [77.21, 28.64]]
                        ],
                    },
                }
            ],
        }
        hazard_file.write_text(json.dumps(hazard_data))

        adapter = HazardLayerAdapter(enabled=True, dataset_path=hazard_file)
        assert adapter.is_available is True
        assert adapter.provenance_tag.startswith("hazard:dataset_")

        # Point inside polygon
        res_inside = adapter.evaluate_point_hazard(28.6500, 77.2300)
        assert res_inside["in_hazard_zone"] is True
        assert res_inside["hazard_level"] == "CRITICAL"

        # Point outside polygon
        res_outside = adapter.evaluate_point_hazard(28.6000, 77.1000)
        assert res_outside["in_hazard_zone"] is False


# ── C. Spatial Exposure & Spatial Service Tests ─────────────────────────
class TestSpatialService:
    def test_spatial_exposure_summary(self):
        reset_data_adapter()
        svc = get_spatial_service()
        exp = svc.get_exposure_summary()

        assert "population_exposure" in exp
        assert "infrastructure_vulnerability" in exp
        assert exp["spatial_crs"] == "EPSG:4326"
        assert exp["projected_crs"] == "EPSG:3857"

    def test_route_spatial_hazard_calculation(self):
        svc = get_spatial_service()

        waypoints = [
            {"lat": 28.6448, "lng": 77.2167},
            {"lat": 28.6500, "lng": 77.2300},
            {"lat": 28.6600, "lng": 77.2400},
        ]

        res = svc.calculate_route_spatial_hazard(waypoints, base_safety_score=0.90)

        assert "spatial_exposure_ratio" in res
        assert "adjusted_safety_score" in res
        assert 0.05 <= res["adjusted_safety_score"] <= 0.95
        assert res["water_proximity_km"] >= 0.0


# ── D. Route Spatial Safety & Scoring Tests ──────────────────────────────
class TestRouteSpatialSafety:
    def test_scoring_with_spatial_exposure(self):
        edges = [
            {"distance_km": 1.5, "base_time_min": 3.0, "congestion": 0.4, "risk_score": 25.0},
            {"distance_km": 2.0, "base_time_min": 4.0, "congestion": 0.5, "risk_score": 30.0},
        ]

        # No spatial penalty
        m_base = calculate_route_metrics(edges)

        # With spatial penalty
        spatial_exp = {"hazard_penalty": 0.10, "spatial_exposure_ratio": 0.3}
        m_spatial = calculate_route_metrics(edges, spatial_exposure=spatial_exp)

        # ETA & Distance preserved
        assert m_spatial["total_distance_km"] == m_base["total_distance_km"]
        assert m_spatial["total_time_min"] == m_base["total_time_min"]

        # Safety score adjusted
        assert m_spatial["safety_score"] <= m_base["safety_score"]
        assert m_spatial["spatial_exposure_ratio"] == 0.3

    def test_optimizer_uses_spatial_enrichment(self):
        reset_optimizer()
        optimizer = RouteOptimizer()
        result = optimizer.optimize(predicted_risk_score=75.0)

        assert result.recommended is not None
        assert result.recommended.safetyScore >= 0.05
        assert result.recommended.eta > 0
        assert "selected" in result.route_reason.lower()


# ── E. Phase 6.14 REST API Tests ──────────────────────────────────────────
class TestSpatialAPIEndpoints:
    def test_get_spatial_summary_endpoint(self):
        res = client.get("/api/spatial/summary")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["data"]["spatial_crs"] == "EPSG:4326"
        assert "dem_enabled" in data["data"]
        assert "hazard_layers" in data["data"]

    def test_get_spatial_elevation_endpoint(self):
        res = client.get("/api/spatial/elevation?lat=28.6448&lng=77.2167")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "elevation_m" in data["data"]
        assert "provenance" in data["data"]

    def test_get_spatial_hazards_endpoint(self):
        res = client.get("/api/spatial/hazards")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "is_available" in data["data"]

    def test_get_spatial_exposure_endpoint(self):
        res = client.get("/api/spatial/exposure")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "population_exposure" in data["data"]

    def test_get_route_spatial_safety_endpoint(self):
        res = client.get("/api/spatial/routes/route-rec?origin_lat=28.6448&origin_lng=77.2167&dest_lat=28.6600&dest_lng=77.2300")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "modeled_safety_score" in data["data"]
        assert "water_proximity_km" in data["data"]


# ── F. Regression Tests ──────────────────────────────────────────────────
class TestRegressionSuite:
    def test_gbr_model_7_features_preserved(self):
        from ml.features.schema import FEATURE_NAMES
        assert len(FEATURE_NAMES) == 7
        assert "rainfall_intensity" in FEATURE_NAMES
        assert "infrastructure_vulnerability" in FEATURE_NAMES
        assert "elevation" not in FEATURE_NAMES  # ML GBR schema unchanged

    def test_risk_inference_unmodified(self):
        from ml.inference import predict_risk
        features = {
            "rainfall_intensity": 95.0,
            "rainfall_trend": 12.0,
            "water_level": 6.8,
            "water_level_trend": 0.45,
            "road_congestion": 0.72,
            "population_exposure": 12430.0,
            "infrastructure_vulnerability": 0.78,
        }
        res = predict_risk(features)
        assert "risk_score" in res
        assert 0.0 <= res["risk_score"] <= 100.0
        assert "uncertainty" in res
