"""
AapdaNetra-X — Centralized NetworkX Road Graph Construction
Defines nodes (sectors, checkpoints, shelters) and edges (road segments) with metadata.
"""
import networkx as nx
from typing import Dict, Any
from ml.routing.models import Waypoint

# Node Metadata (Coordinates & Labels)
NODE_METADATA: Dict[str, Waypoint] = {
    "Sector_B": Waypoint("wp-B", 28.6448, 77.2167, "Sector B (Origin)"),
    "Sector_A": Waypoint("wp-A", 28.6530, 77.2060, "Sector A (Origin)"),
    "Checkpoint_D": Waypoint("wp-D", 28.6475, 77.2200, "Checkpoint D (HIGH RISK)"),
    "Checkpoint_E": Waypoint("wp-E", 28.6390, 77.2290, "Checkpoint E"),
    "Checkpoint_F": Waypoint("wp-F", 28.6320, 77.2150, "Checkpoint F (South Bypass)"),
    "Checkpoint_G": Waypoint("wp-G", 28.6350, 77.2380, "Checkpoint G (East Link)"),
    "Shelter_H": Waypoint("wp-H", 28.6310, 77.2450, "SHELTER-04 (Safe Zone)"),
    "Shelter_H2": Waypoint("wp-H2", 28.6250, 77.2500, "SHELTER-02 (Secondary Shelter)"),
}

# Raw Road Edges Definition: (u, v, {distance_km, base_time_min, base_risk, congestion, infra_vuln})
ROAD_EDGES = [
    # Route A Corridor (North — High Flood Risk)
    ("Sector_B", "Checkpoint_D", {"distance_km": 1.8, "base_time_min": 4.0, "base_risk": 82.0, "congestion": 0.85, "infra_vuln": 0.85}),
    ("Checkpoint_D", "Shelter_H", {"distance_km": 2.2, "base_time_min": 4.0, "base_risk": 75.0, "congestion": 0.75, "infra_vuln": 0.80}),
    
    # Route B Corridor (Central — Recommended Preferred Path)
    ("Sector_B", "Checkpoint_E", {"distance_km": 1.4, "base_time_min": 4.0, "base_risk": 28.0, "congestion": 0.45, "infra_vuln": 0.40}),
    ("Checkpoint_E", "Shelter_H", {"distance_km": 2.1, "base_time_min": 5.0, "base_risk": 25.0, "congestion": 0.40, "infra_vuln": 0.35}),
    
    # Route C Corridor (South Bypass — Long Safe Route)
    ("Sector_B", "Checkpoint_F", {"distance_km": 1.9, "base_time_min": 5.0, "base_risk": 18.0, "congestion": 0.30, "infra_vuln": 0.25}),
    ("Checkpoint_F", "Checkpoint_G", {"distance_km": 1.6, "base_time_min": 4.0, "base_risk": 15.0, "congestion": 0.25, "infra_vuln": 0.20}),
    ("Checkpoint_G", "Shelter_H", {"distance_km": 1.2, "base_time_min": 3.0, "base_risk": 15.0, "congestion": 0.20, "infra_vuln": 0.20}),
    
    # Secondary Feeder Links
    ("Sector_A", "Checkpoint_D", {"distance_km": 1.5, "base_time_min": 3.0, "base_risk": 70.0, "congestion": 0.60, "infra_vuln": 0.70}),
    ("Checkpoint_G", "Shelter_H2", {"distance_km": 1.5, "base_time_min": 4.0, "base_risk": 10.0, "congestion": 0.20, "infra_vuln": 0.15}),
]


def create_road_graph() -> nx.DiGraph:
    """
    Constructs a NetworkX DiGraph representing the disaster area road network.
    """
    G = nx.DiGraph()

    # Add nodes with attributes
    for node_id, wp in NODE_METADATA.items():
        G.add_node(node_id, lat=wp.lat, lng=wp.lng, label=wp.label, id=wp.id)

    # Add bidirectional edges with metadata
    for u, v, data in ROAD_EDGES:
        edge_data = dict(data)
        edge_data["is_blocked"] = False
        edge_data["risk_score"] = float(data.get("base_risk", 30.0))

        # Add directed edge u -> v
        G.add_edge(u, v, **edge_data)

        # Add reverse edge v -> u
        rev_data = dict(edge_data)
        G.add_edge(v, u, **rev_data)

    return G
