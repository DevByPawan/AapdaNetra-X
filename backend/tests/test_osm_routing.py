"""
AapdaNetra-X — Phase 6.2 OpenStreetMap Routing Engine Tests
Tests GraphML loading, node/edge attribute contracts, nearest node mapping,
speed parsing, spatial risk scoring, route optimization on OSM graph,
routing modes (simulated, osm, auto), error handling, and 8-node fallback regression.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Ensure root workspace and backend directories are in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
for p in [str(ROOT_DIR), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
import networkx as nx
from fastapi.testclient import TestClient

from app.config import settings
from app.data.providers.osm_adapter import (
    OSMAdapter,
    parse_maxspeed,
    compute_provisional_spatial_risk,
    reset_osm_adapter,
)
from ml.routing.optimizer import RouteOptimizer, reset_optimizer, optimize_routes
from app.main import app

client = TestClient(app)

TEST_GRAPHML_PATH = str(ROOT_DIR / "backend" / "app" / "data" / "osm_cache" / "delhi_sector_b.graphml")


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons before each test."""
    reset_osm_adapter()
    reset_optimizer()
    yield
    reset_osm_adapter()
    reset_optimizer()


# ── 1. Unit Tests for Helper Functions ──────────────────────────────────
def test_maxspeed_parsing():
    """Test maxspeed parsing for numeric, string, list, and malformed inputs."""
    assert parse_maxspeed(50) == 50.0
    assert parse_maxspeed("50 km/h") == 50.0
    assert parse_maxspeed("30 mph") == pytest.approx(48.28, rel=1e-2)
    assert parse_maxspeed(["40", "50"]) == 40.0
    assert parse_maxspeed("invalid", highway_type="primary") == 50.0
    assert parse_maxspeed("invalid", highway_type="secondary") == 40.0
    assert parse_maxspeed("invalid", highway_type="residential") == 25.0
    assert parse_maxspeed(None) == 30.0


def test_spatial_risk_calculation():
    """Test provisional spatial risk decays with distance from Yamuna epicenter."""
    epicenter_risk = compute_provisional_spatial_risk(28.6480, 77.2300)
    far_risk = compute_provisional_spatial_risk(28.6000, 77.1000)
    assert epicenter_risk > far_risk
    assert 10.0 <= far_risk <= 85.0
    assert epicenter_risk >= 75.0


# ── 2. OSM Adapter Tests ─────────────────────────────────────────────────
def test_osm_adapter_load_cached_graph():
    """Test OSMAdapter loads cached GraphML file cleanly."""
    if not os.path.exists(TEST_GRAPHML_PATH):
        pytest.skip("Cached GraphML not found")

    adapter = OSMAdapter(routing_mode="osm", graphml_path=TEST_GRAPHML_PATH)
    G = adapter.get_road_graph()

    assert isinstance(G, nx.DiGraph)
    assert G.number_of_nodes() > 100
    assert G.number_of_edges() > 100


def test_node_and_edge_attribute_schema():
    """Test that all converted OSM nodes and edges satisfy the engine contract."""
    if not os.path.exists(TEST_GRAPHML_PATH):
        pytest.skip("Cached GraphML not found")

    adapter = OSMAdapter(routing_mode="osm", graphml_path=TEST_GRAPHML_PATH)
    G = adapter.get_road_graph()

    # Verify node attribute schema
    for node, data in list(G.nodes(data=True))[:20]:
        assert "lat" in data and isinstance(data["lat"], float)
        assert "lng" in data and isinstance(data["lng"], float)
        assert "label" in data and isinstance(data["label"], str)
        assert "id" in data and isinstance(data["id"], str)

    # Verify edge attribute schema
    for u, v, data in list(G.edges(data=True))[:20]:
        assert "distance_km" in data and data["distance_km"] > 0
        assert "base_time_min" in data and data["base_time_min"] > 0
        assert "base_risk" in data and 0 <= data["base_risk"] <= 100
        assert "congestion" in data and 0 <= data["congestion"] <= 1
        assert "is_blocked" in data and isinstance(data["is_blocked"], bool)
        assert "risk_score" in data


def test_nearest_node_mapping():
    """Test mapping lat/lng coordinates to nearest node in OSM graph."""
    if not os.path.exists(TEST_GRAPHML_PATH):
        pytest.skip("Cached GraphML not found")

    adapter = OSMAdapter(routing_mode="osm", graphml_path=TEST_GRAPHML_PATH)
    G = adapter.get_road_graph()

    # Sector B coordinates
    node_id = adapter.find_nearest_node(G, lat=28.6448, lng=77.2167)
    assert node_id in G.nodes
    assert "lat" in G.nodes[node_id]


# ── 3. Routing Modes & Fallback Tests ────────────────────────────────────
def test_routing_mode_simulated_returns_8node_graph():
    """Test ROUTING_MODE=simulated returns Phase 5D 8-node graph."""
    adapter = OSMAdapter(routing_mode="simulated")
    G = adapter.get_road_graph()

    assert G.number_of_nodes() == 8
    assert "Sector_B" in G.nodes
    assert "Shelter_H" in G.nodes


def test_routing_mode_auto_fallback_on_missing_file():
    """Test ROUTING_MODE=auto automatically falls back to 8-node graph if file missing."""
    adapter = OSMAdapter(routing_mode="auto", graphml_path="non_existent_file.graphml")
    G = adapter.get_road_graph()

    assert G.number_of_nodes() == 8
    assert "Sector_B" in G.nodes


def test_routing_mode_osm_raises_on_missing_file():
    """Test ROUTING_MODE=osm raises exception explicitly if file missing."""
    adapter = OSMAdapter(routing_mode="osm", graphml_path="non_existent_file.graphml")
    with pytest.raises(ValueError, match="OSM graph load failed"):
        adapter.get_road_graph()


# ── 4. Optimizer Tests on OSM Graph ──────────────────────────────────────
def test_osm_route_optimization_execution():
    """Test RouteOptimizer produces valid RoutePath on OSM graph."""
    if not os.path.exists(TEST_GRAPHML_PATH):
        pytest.skip("Cached GraphML not found")

    with patch("app.config.settings.routing_mode", "osm"):
        result = optimize_routes(predicted_risk_score=65.0)

        assert result.recommended is not None
        assert result.recommended.distance_km > 0
        assert result.recommended.eta > 0
        assert len(result.recommended.waypoints) > 1
        assert 0.0 <= result.recommended.safetyScore <= 1.0


def test_blocked_edge_behavior_in_osm():
    """Test blocked edge option in simulation/optimization works with OSM mode."""
    if not os.path.exists(TEST_GRAPHML_PATH):
        pytest.skip("Cached GraphML not found")

    with patch("app.config.settings.routing_mode", "osm"):
        res = optimize_routes(predicted_risk_score=50.0, route_blockage=True)
        assert res.recommended is not None
        assert res.recommended.is_blocked is False


# ── 5. Integration API Test ──────────────────────────────────────────────
def test_routes_api_osm_mode_integration():
    """Test GET /api/routes in ROUTING_MODE=osm returns 200 OK and valid schema."""
    if not os.path.exists(TEST_GRAPHML_PATH):
        pytest.skip("Cached GraphML not found")

    with patch("app.config.settings.routing_mode", "osm"):
        response = client.get("/api/routes?horizon=1")
        assert response.status_code == 200
        data = response.json()

        assert "recommended" in data
        assert "alternatives" in data
        assert "decisionTrace" in data
        assert data["recommended"]["distanceKm"] > 0
        assert len(data["recommended"]["waypoints"]) > 0
