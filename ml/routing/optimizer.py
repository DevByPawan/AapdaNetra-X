"""
AapdaNetra-X — NetworkX Evacuation Route Optimizer Engine
Executes risk-aware Dijkstra / shortest simple path search over the road network graph.
Phase 6.2: Supports dynamic OSM road graphs while preserving Phase 5D 8-node routing behavior.
"""
import logging
import networkx as nx
from typing import List, Dict, Any, Tuple, Optional

from ml.routing.graph import create_road_graph, NODE_METADATA
from ml.routing.scoring import calculate_edge_cost, calculate_route_metrics
from ml.routing.models import Waypoint, RoutePath, RoutingOptimizationResult

logger = logging.getLogger("aapdanetra.optimizer")


class RouteOptimizer:
    """
    NetworkX-based evacuation route optimization engine.
    Supports both simulated 8-node graph and OpenStreetMap road graphs via OSMAdapter.
    """

    def __init__(self, custom_graph: Optional[nx.DiGraph] = None):
        self._custom_graph = custom_graph

    def _get_active_graph(self) -> nx.DiGraph:
        """Retrieves active road graph based on settings / adapter configuration."""
        if self._custom_graph is not None:
            return self._custom_graph.copy()

        try:
            from app.data.providers.osm_adapter import get_osm_adapter
            adapter = get_osm_adapter()
            return adapter.get_road_graph()
        except Exception as e:
            logger.warning(f"[RouteOptimizer] Failed to get graph from OSMAdapter ({e}). Using 8-node fallback.")
            return create_road_graph()

    def optimize(
        self,
        predicted_risk_score: float = 74.0,
        route_blockage: bool = False,
        horizon_index: int = 0,
        origin: str = "Sector_B",
        destination: str = "Shelter_H"
    ) -> RoutingOptimizationResult:
        """
        Executes graph-based route optimization taking ML predicted risk state into account.
        Returns recommended route, alternative routes, blocked segments, and route reasoning.
        """
        G = self._get_active_graph()

        # Resolve origin & destination node IDs if needed
        resolved_origin = origin
        resolved_dest = destination

        try:
            from app.data.providers.osm_adapter import get_osm_adapter
            adapter = get_osm_adapter()
            resolved_origin = adapter.resolve_anchor_node(G, origin)
            resolved_dest = adapter.resolve_anchor_node(G, destination)
        except Exception:
            if origin not in G.nodes and list(G.nodes()):
                resolved_origin = list(G.nodes())[0]
            if destination not in G.nodes and list(G.nodes()):
                resolved_dest = list(G.nodes())[-1]

        # 1. Update edge risks dynamically based on ML prediction score
        norm_pred_risk = max(0.0, min(100.0, float(predicted_risk_score)))

        is_8node_graph = all(str(n) in NODE_METADATA for n in G.nodes())

        for u, v, d in G.edges(data=True):
            base_r = float(d.get("base_risk", 30.0))

            # Phase 5D 8-node graph corridor rules
            if "Checkpoint_D" in (str(u), str(v)):
                d["risk_score"] = min(100.0, base_r * (norm_pred_risk / 50.0))
                if norm_pred_risk > 85.0:
                    d["congestion"] = min(1.0, float(d.get("congestion", 0.7)) * 1.25)
            elif "Checkpoint_E" in (str(u), str(v)):
                d["risk_score"] = min(100.0, base_r * (1.0 + (norm_pred_risk - 30.0) * 0.025))
            elif is_8node_graph:
                d["risk_score"] = max(5.0, base_r)
            else:
                # General / OSM edge risk scaling
                d["risk_score"] = min(100.0, max(5.0, base_r * (1.0 + (norm_pred_risk - 50.0) * 0.01)))

            # Apply route blockage flag if enabled
            if route_blockage and ("Checkpoint_E" in (str(u), str(v)) or d.get("is_blocked_override", False)):
                d["is_blocked"] = True

            # Calculate composite edge traversal cost (UNCHANGED scoring function)
            d["cost"] = calculate_edge_cost(
                distance_km=d.get("distance_km", 1.5),
                base_time_min=d.get("base_time_min", 3.0),
                risk_score=d["risk_score"],
                congestion=d.get("congestion", 0.5),
                is_blocked=d.get("is_blocked", False)
            )

        # 2. Extract blocked segments list
        blocked_segments = []
        for u, v, d in G.edges(data=True):
            if d.get("is_blocked"):
                blocked_segments.append({
                    "from_node": str(u),
                    "to_node": str(v),
                    "reason": "Structural inundation / barricade"
                })

        # 3. Find k-shortest simple paths using NetworkX
        paths_found: List[List[str]] = []
        try:
            generator = nx.shortest_simple_paths(G, resolved_origin, resolved_dest, weight="cost")
            for p in generator:
                if p not in paths_found:
                    paths_found.append(p)
                if len(paths_found) >= 3:
                    break
        except (nx.NetworkXNoPath, nx.NodeNotFound) as e:
            logger.warning(f"[RouteOptimizer] Warning: No path found between {resolved_origin} and {resolved_dest}: {e}")
            paths_found = [[resolved_origin, resolved_dest]]

        # Fallback if less than 2 paths found
        if len(paths_found) < 2 and G.number_of_nodes() > 2:
            all_nodes = list(G.nodes())
            mid = all_nodes[len(all_nodes) // 2]
            if mid not in (resolved_origin, resolved_dest):
                paths_found.append([resolved_origin, mid, resolved_dest])

        # 4. Build RoutePath instances
        route_paths: List[RoutePath] = []
        for idx, path_nodes in enumerate(paths_found):
            path_edges = []
            for i in range(len(path_nodes) - 1):
                u_node, v_node = path_nodes[i], path_nodes[i + 1]
                if G.has_edge(u_node, v_node):
                    path_edges.append(G[u_node][v_node])

            # Build waypoints (support both 8-node NODE_METADATA and dynamic OSM nodes)
            waypoints: List[Waypoint] = []
            for n in path_nodes:
                if n in NODE_METADATA:
                    waypoints.append(NODE_METADATA[n])
                elif n in G.nodes:
                    nd = G.nodes[n]
                    wp = Waypoint(
                        id=str(nd.get("id", f"osm-{n}")),
                        lat=float(nd.get("lat", 28.6448)),
                        lng=float(nd.get("lng", 77.2167)),
                        label=str(nd.get("label", f"Junction {n}"))
                    )
                    waypoints.append(wp)

            # Query spatial hazard exposure from SpatialService
            spatial_exp = None
            try:
                from app.services.spatial_service import get_spatial_service
                wp_dicts = [{"lat": wp.lat, "lng": wp.lng} for wp in waypoints]
                spatial_exp = get_spatial_service().calculate_route_spatial_hazard(wp_dicts)
            except Exception as exp_err:
                logger.debug(f"[RouteOptimizer] Spatial hazard evaluation fallback: {exp_err}")

            metrics = calculate_route_metrics(path_edges, spatial_exposure=spatial_exp)

            # Format path name
            if all(n in NODE_METADATA for n in path_nodes):
                node_letters = [n.replace("Sector_", "").replace("Checkpoint_", "").replace("Shelter_", "") for n in path_nodes]
                path_name = " → ".join(node_letters)
            else:
                start_label = waypoints[0].label if waypoints else "Origin"
                end_label = waypoints[-1].label if waypoints else "Destination"
                path_name = f"{start_label} → Path {idx + 1} → {end_label}"

            route_id = f"route-rec" if idx == 0 else f"route-alt-{idx}"

            route_obj = RoutePath(
                id=route_id,
                name=path_name,
                eta=metrics["total_time_min"],
                distance_km=metrics["total_distance_km"],
                failureProbability=metrics["failure_probability"],
                safetyScore=metrics["safety_score"],
                riskScore=metrics["avg_risk"],
                waypoints=waypoints,
                nodes=[str(n) for n in path_nodes],
                is_blocked=metrics["has_blocked_segment"],
            )
            route_paths.append(route_obj)

        recommended = route_paths[0]
        alternatives = route_paths[1:]

        # 5. Generate route selection reasoning narrative
        if route_blockage:
            reason = f"Route {recommended.name} selected: Avoids blocked corridor. Safety Score: {int(recommended.safetyScore * 100)}%."
        elif norm_pred_risk >= 75.0:
            reason = f"Route {recommended.name} selected: Provides lower hazard exposure ({recommended.riskScore:.1f}) vs elevated risk on primary flood corridor."
        else:
            reason = f"Route {recommended.name} selected: Provides optimal balance of ETA ({recommended.eta} min) and safety ({int(recommended.safetyScore * 100)}%)."

        recommended.route_reason = reason

        return RoutingOptimizationResult(
            recommended=recommended,
            alternatives=alternatives,
            blocked_segments=blocked_segments,
            route_reason=reason,
            horizon_index=horizon_index,
        )


# Global singleton instance & convenience functions
_global_optimizer: Optional[RouteOptimizer] = None


def get_optimizer() -> RouteOptimizer:
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = RouteOptimizer()
    return _global_optimizer


def reset_optimizer():
    """Resets global optimizer singleton (used in testing)."""
    global _global_optimizer
    _global_optimizer = None


def optimize_routes(
    predicted_risk_score: float = 74.0,
    route_blockage: bool = False,
    horizon_index: int = 0
) -> RoutingOptimizationResult:
    """Public helper function for networkx route optimization."""
    return get_optimizer().optimize(
        predicted_risk_score=predicted_risk_score,
        route_blockage=route_blockage,
        horizon_index=horizon_index,
    )
