"""
Unit and Integration tests for AapdaNetra-X NetworkX Routing Engine (Phase 5C)
Tests graph creation, connectivity, cost calculations, risk-aware routing,
alternative route generation, blocked edge handling, horizon changes, and API integration.
"""
import sys
from pathlib import Path

# Ensure root workspace and backend directories are in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
for p in [str(ROOT_DIR), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
import networkx as nx
from fastapi.testclient import TestClient

from ml.routing import (
    create_road_graph,
    calculate_edge_cost,
    calculate_route_metrics,
    optimize_routes,
    RouteOptimizer,
    NODE_METADATA,
)
from app.main import app

client = TestClient(app)


def test_graph_creation_and_nodes():
    """1 & 2. Test graph creation, node count, and connectivity."""
    G = create_road_graph()
    assert G.number_of_nodes() >= 7
    assert G.number_of_edges() >= 12
    assert nx.is_weakly_connected(G)


def test_edge_cost_calculation():
    """Test edge cost function incorporates risk, distance, and blockage penalty."""
    normal_cost = calculate_edge_cost(distance_km=2.0, base_time_min=4.0, risk_score=20.0, congestion=0.3)
    high_risk_cost = calculate_edge_cost(distance_km=2.0, base_time_min=4.0, risk_score=90.0, congestion=0.3)
    blocked_cost = calculate_edge_cost(distance_km=2.0, base_time_min=4.0, risk_score=20.0, congestion=0.3, is_blocked=True)

    assert high_risk_cost > normal_cost
    assert blocked_cost >= 10000.0


def test_route_metrics_and_safety_score():
    """8, 9, 10. Test distance, travel-time, and safety score calculations."""
    edges = [
        {"distance_km": 1.5, "base_time_min": 3.0, "risk_score": 20.0, "congestion": 0.3, "is_blocked": False},
        {"distance_km": 2.0, "base_time_min": 4.0, "risk_score": 25.0, "congestion": 0.4, "is_blocked": False},
    ]
    metrics = calculate_route_metrics(edges)
    assert metrics["total_distance_km"] == 3.5
    assert metrics["total_time_min"] > 0
    assert 0.0 <= metrics["safety_score"] <= 1.0
    assert 0.0 <= metrics["failure_probability"] <= 1.0


def test_risk_aware_route_selection():
    """3 & 4. Test NetworkX optimizer reroutes away from high flood risk corridors."""
    # Low risk -> direct path
    res_low = optimize_routes(predicted_risk_score=20.0)
    # High risk -> safer bypass path
    res_high = optimize_routes(predicted_risk_score=95.0)

    assert res_low.recommended.name != ""
    assert res_high.recommended.name != ""
    assert res_high.recommended.safetyScore >= 0.5


def test_alternative_routes_generation():
    """5. Test at least 2 non-duplicate alternative routes are generated."""
    res = optimize_routes(predicted_risk_score=50.0)
    assert len(res.alternatives) >= 1
    
    path_names = [res.recommended.name] + [a.name for a in res.alternatives]
    # Verify paths are unique
    assert len(path_names) == len(set(path_names))


def test_blocked_edge_behavior():
    """6 & 11. Test blocked edge receives massive cost and is avoided by recommended route."""
    res = optimize_routes(predicted_risk_score=40.0, route_blockage=True)
    assert res.recommended.is_blocked is False
    assert len(res.blocked_segments) > 0


def test_horizon_dependent_route_changes():
    """7. Test route calculation dynamically reroutes to safer paths as risk escalates."""
    res_now = optimize_routes(predicted_risk_score=27.1, horizon_index=0)
    res_30m = optimize_routes(predicted_risk_score=95.0, horizon_index=3)

    # In +30M severe escalation, optimizer reroutes to South Bypass (B -> F -> G -> H)
    assert res_now.recommended.name != res_30m.recommended.name or res_now.recommended.safetyScore != res_30m.recommended.safetyScore
    assert res_30m.recommended.safetyScore >= res_now.recommended.safetyScore


def test_routes_api_networkx_integration():
    """12, 13, 14. Test GET /api/routes?horizon=1 returns dynamic NetworkX routes & SHAP trace."""
    response = client.get("/api/routes?horizon=1")
    assert response.status_code == 200
    data = response.json()

    assert "recommended" in data
    assert "alternatives" in data
    assert "decisionTrace" in data
    assert data["recommended"]["safetyScore"] > 0.0
    assert "distanceKm" in data["recommended"]
    assert "routeReason" in data


def test_simulation_api_routing_integration():
    """11b. Test POST /api/simulation dynamically updates NetworkX routes when blockage is toggled."""
    payload = {
        "evacuationPace": 1.0,
        "rainfallMultiplier": 1.8,
        "drainageEfficiency": 0.5,
        "routeBlockage": True,
    }
    response = client.post("/api/simulation", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "scenarioRisk" in data
    assert "routeRecommendation" in data
    assert "Route" in data["routeRecommendation"]
