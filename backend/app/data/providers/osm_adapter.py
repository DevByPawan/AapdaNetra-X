"""
AapdaNetra-X — Phase 6.2 OpenStreetMap Road Graph Adapter
Loads local cached GraphML road networks and converts them into standard NetworkX DiGraphs
matching the exact node and edge attribute schema expected by RouteOptimizer.

Routing Modes:
  - 'simulated': Returns Phase 5D 8-node graph unchanged.
  - 'osm': Loads cached GraphML. If missing/corrupt, fails explicitly.
  - 'auto': Loads cached GraphML if available; falls back to Phase 5D 8-node graph on failure.

Performance Mandate:
  - Reads GraphML once at load time, caches in memory. Zero Overpass/HTTP API calls at runtime.
"""
import logging
import math
import os
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
import networkx as nx

from ml.routing.graph import create_road_graph, NODE_METADATA
from ml.routing.models import Waypoint

logger = logging.getLogger("aapdanetra.osm_adapter")

# Fixed coordinate anchors for canonical Phase 5D locations
LOCATION_ANCHORS = {
    "Sector_B": (28.6448, 77.2167),
    "Sector_A": (28.6530, 77.2060),
    "Checkpoint_D": (28.6475, 77.2200),
    "Checkpoint_E": (28.6390, 77.2290),
    "Checkpoint_F": (28.6320, 77.2150),
    "Checkpoint_G": (28.6350, 77.2380),
    "Shelter_H": (28.6310, 77.2450),
    "Shelter_H2": (28.6250, 77.2500),
}


def parse_maxspeed(val: Any, highway_type: Any = None) -> float:
    """
    Safely parses OSM maxspeed tag into float speed in km/h.
    Uses documented fallback values if missing or malformed:
      - primary / trunk / motorway: 50 km/h
      - secondary / tertiary: 40 km/h
      - residential / unclassified: 25 km/h
      - default: 30 km/h
    """
    if isinstance(val, list):
        val = val[0]
    if isinstance(val, (int, float)):
        return float(val) if float(val) > 0 else 30.0
    if isinstance(val, str):
        # Strip text like '50 km/h' or '30 mph'
        digits = "".join(c for c in val.split()[0] if c.isdigit() or c == ".")
        if digits:
            try:
                speed = float(digits)
                if "mph" in val.lower():
                    speed *= 1.60934
                return max(10.0, min(120.0, speed))
            except ValueError:
                pass

    hw_str = str(highway_type[0] if isinstance(highway_type, list) else highway_type).lower()
    if any(k in hw_str for k in ["primary", "trunk", "motorway"]):
        return 50.0
    elif any(k in hw_str for k in ["secondary", "tertiary"]):
        return 40.0
    elif any(k in hw_str for k in ["residential", "living_street", "unclassified"]):
        return 25.0
    return 30.0


def compute_provisional_spatial_risk(lat: float, lng: float) -> float:
    """
    Computes a deterministic provisional spatial hazard score (10.0 to 85.0) based on
    proximity to the Yamuna River corridor (28.648 N, 77.230 E).
    Provisional spatial component — ML predicted risk still dynamically scales final edge cost.
    """
    # Yamuna river flood exposure epicenter
    ref_lat, ref_lng = 28.6480, 77.2300
    d_lat = (lat - ref_lat) * 111.0
    d_lng = (lng - ref_lng) * 111.0 * math.cos(math.radians(ref_lat))
    dist_km = math.sqrt(d_lat * d_lat + d_lng * d_lng)

    # Risk decays with distance from riverbed epicenter
    if dist_km <= 1.0:
        return 80.0 - dist_km * 20.0
    elif dist_km <= 3.0:
        return 60.0 - (dist_km - 1.0) * 15.0
    else:
        return max(10.0, 30.0 - (dist_km - 3.0) * 5.0)


class OSMAdapter:
    """
    Adapter bridging OpenStreetMap GraphML road networks with the AapdaNetra-X NetworkX routing engine.
    """

    def __init__(
        self,
        routing_mode: str = "simulated",
        graphml_path: Optional[str] = None
    ):
        self.routing_mode = routing_mode
        self.graphml_path = graphml_path or "backend/app/data/osm_cache/delhi_sector_b.graphml"
        self._cached_graph: Optional[nx.DiGraph] = None
        self._node_waypoints: Dict[str, Waypoint] = {}

    def get_road_graph(self) -> nx.DiGraph:
        """
        Returns the converted NetworkX DiGraph matching the required engine attribute schema.
        Uses in-memory caching.
        """
        if self.routing_mode == "simulated":
            return create_road_graph()

        if self._cached_graph is not None:
            return self._cached_graph

        try:
            self._cached_graph = self._load_and_convert_osm_graph()
            return self._cached_graph
        except Exception as e:
            if self.routing_mode == "osm":
                logger.error(f"[OSMAdapter] Failed to load OSM graph in 'osm' mode: {e}")
                raise ValueError(f"OSM graph load failed in 'osm' mode: {e}") from e
            else:
                logger.warning(
                    f"[OSMAdapter] OSM graph load failed ({e}). Falling back to Phase 5D 8-node graph."
                )
                return create_road_graph()

    def _load_and_convert_osm_graph(self) -> nx.DiGraph:
        """Loads local GraphML and converts nodes/edges to required contract."""
        resolved_path = Path(self.graphml_path)
        if not resolved_path.is_absolute():
            # Try workspace root resolution
            workspace_root = Path(__file__).resolve().parent.parent.parent.parent.parent
            resolved_path = workspace_root / self.graphml_path

        if not resolved_path.exists():
            raise FileNotFoundError(f"OSM GraphML file not found at: {resolved_path}")

        import osmnx as ox
        # Load raw OSM nx.MultiDiGraph
        raw_graph = ox.load_graphml(filepath=resolved_path)

        G = nx.DiGraph()
        self._node_waypoints.clear()

        # 1. Convert nodes
        for node_id, data in raw_graph.nodes(data=True):
            str_id = str(node_id)
            lat = float(data.get("y", data.get("lat", 28.6448)))
            lng = float(data.get("x", data.get("lng", 77.2167)))
            label = str(data.get("name", f"Junction {str_id}"))

            # Save waypoint model for metadata lookup
            wp = Waypoint(id=f"osm-{str_id}", lat=lat, lng=lng, label=label)
            self._node_waypoints[str_id] = wp

            G.add_node(str_id, lat=lat, lng=lng, label=label, id=wp.id)

        # 2. Convert edges
        for u, v, data in raw_graph.edges(data=True):
            str_u, str_v = str(u), str(v)
            if str_u not in G.nodes or str_v not in G.nodes:
                continue

            length_m = float(data.get("length", 100.0))
            distance_km = max(0.01, round(length_m / 1000.0, 3))

            speed_kmh = parse_maxspeed(data.get("maxspeed"), data.get("highway"))
            base_time_min = max(0.1, round((distance_km / speed_kmh) * 60.0, 2))

            u_lat = G.nodes[str_u]["lat"]
            u_lng = G.nodes[str_u]["lng"]
            base_risk = round(compute_provisional_spatial_risk(u_lat, u_lng), 1)

            edge_dict = {
                "distance_km": distance_km,
                "base_time_min": base_time_min,
                "base_risk": base_risk,
                "congestion": 0.35,
                "infra_vuln": 0.40,
                "is_blocked": False,
                "risk_score": base_risk,
            }

            # If edge already exists in DiGraph, keep shortest distance
            if G.has_edge(str_u, str_v):
                if distance_km < G[str_u][str_v]["distance_km"]:
                    G[str_u][str_v].update(edge_dict)
            else:
                G.add_edge(str_u, str_v, **edge_dict)

        logger.info(
            f"[OSMAdapter] Successfully converted OSM graph ({G.number_of_nodes()} nodes, {G.number_of_edges()} edges)"
        )
        return G

    def get_node_waypoint(self, node_id: str) -> Waypoint:
        """Returns Waypoint dataclass for a node ID."""
        if node_id in self._node_waypoints:
            return self._node_waypoints[node_id]
        if node_id in NODE_METADATA:
            return NODE_METADATA[node_id]
        return Waypoint(id=f"wp-{node_id}", lat=28.6448, lng=77.2167, label=f"Node {node_id}")

    def find_nearest_node(self, graph: nx.DiGraph, lat: float, lng: float) -> str:
        """Finds nearest node ID in graph to lat/lng coordinates."""
        min_dist = float("inf")
        best_node = list(graph.nodes())[0]

        for n, data in graph.nodes(data=True):
            n_lat = data.get("lat", 28.6448)
            n_lng = data.get("lng", 77.2167)
            d_lat = (n_lat - lat) * 111.0
            d_lng = (n_lng - lng) * 111.0 * math.cos(math.radians(lat))
            dist = d_lat * d_lat + d_lng * d_lng
            if dist < min_dist:
                min_dist = dist
                best_node = n

        return best_node

    def resolve_anchor_node(self, graph: nx.DiGraph, location_key: str) -> str:
        """Resolves location key (e.g. 'Sector_B') to exact or nearest node ID in graph."""
        if location_key in graph.nodes:
            return location_key

        if location_key in LOCATION_ANCHORS:
            lat, lng = LOCATION_ANCHORS[location_key]
            return self.find_nearest_node(graph, lat, lng)

        return list(graph.nodes())[0]


# ── Global Singleton Instance & Accessor ─────────────────────────────────
_global_osm_adapter: Optional[OSMAdapter] = None


def get_osm_adapter() -> OSMAdapter:
    """Returns global OSMAdapter instance lazily initialized from app settings."""
    global _global_osm_adapter
    if _global_osm_adapter is None:
        _global_osm_adapter = _create_osm_adapter_from_settings()
    return _global_osm_adapter


def _create_osm_adapter_from_settings() -> OSMAdapter:
    from app.config import settings
    return OSMAdapter(
        routing_mode=settings.routing_mode,
        graphml_path=settings.osm_graphml_path
    )


def reset_osm_adapter():
    """Resets the global OSMAdapter singleton (used in unit tests)."""
    global _global_osm_adapter
    _global_osm_adapter = None
