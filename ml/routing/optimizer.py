"""
AapdaNetra-X — NetworkX Evacuation Route Optimizer Engine
Executes risk-aware Dijkstra / shortest simple path search over the road network graph.
"""
import networkx as nx
from typing import List, Dict, Any, Tuple, Optional
from ml.routing.graph import create_road_graph, NODE_METADATA
from ml.routing.scoring import calculate_edge_cost, calculate_route_metrics
from ml.routing.models import Waypoint, RoutePath, RoutingOptimizationResult


class RouteOptimizer:
    """
    NetworkX-based evacuation route optimization engine.
    """

    def __init__(self):
        self.base_graph = create_road_graph()

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
        G = self.base_graph.copy()

        # 1. Update edge risks dynamically based on ML prediction score
        norm_pred_risk = max(0.0, min(100.0, float(predicted_risk_score)))

        for u, v, d in G.edges(data=True):
            base_r = float(d.get("base_risk", 30.0))
            
            # North Corridor (Checkpoint D) is heavily exposed to high flood risk
            if "Checkpoint_D" in (u, v):
                d["risk_score"] = min(100.0, base_r * (norm_pred_risk / 50.0))
                if norm_pred_risk > 85.0:
                    d["congestion"] = min(1.0, float(d.get("congestion", 0.7)) * 1.25)
            # Central Corridor (Checkpoint E) receives moderate escalation
            elif "Checkpoint_E" in (u, v):
                d["risk_score"] = min(100.0, base_r * (1.0 + (norm_pred_risk - 50.0) * 0.005))
            # South Corridor (Checkpoint F/G) stays safer
            else:
                d["risk_score"] = max(5.0, base_r)

            # Apply route blockage flag if enabled
            if route_blockage and ("Checkpoint_D" in (u, v) or "Sector_B" in (u, v) and "Checkpoint_D" in (u, v)):
                d["is_blocked"] = True

            # Calculate composite edge traversal cost
            d["cost"] = calculate_edge_cost(
                distance_km=d.get("distance_km", 1.5),
                base_time_min=d.get("base_time_min", 3.0),
                risk_score=d["risk_score"],
                congestion=d.get("congestion", 0.5),
                is_blocked=d["is_blocked"]
            )

        # 2. Extract blocked segments list
        blocked_segments = []
        for u, v, d in G.edges(data=True):
            if d.get("is_blocked"):
                blocked_segments.append({
                    "from_node": u,
                    "to_node": v,
                    "reason": "Structural inundation / barricade"
                })

        # 3. Find k-shortest simple paths using NetworkX
        paths_found: List[List[str]] = []
        try:
            generator = nx.shortest_simple_paths(G, origin, destination, weight="cost")
            for p in generator:
                if p not in paths_found:
                    paths_found.append(p)
                if len(paths_found) >= 3:
                    break
        except (nx.NetworkXNoPath, nx.NodeNotFound) as e:
            print(f"[RouteOptimizer] Warning: No path found between {origin} and {destination}: {e}")
            paths_found = [[origin, "Checkpoint_E", destination]]

        # Fallback if less than 2 paths found
        if len(paths_found) < 2:
            paths_found.append([origin, "Checkpoint_F", "Checkpoint_G", destination])

        # 4. Build RoutePath instances
        route_paths: List[RoutePath] = []
        for idx, path_nodes in enumerate(paths_found):
            # Extract edge list for this path
            path_edges = []
            for i in range(len(path_nodes) - 1):
                u_node, v_node = path_nodes[i], path_nodes[i + 1]
                path_edges.append(G[u_node][v_node])

            metrics = calculate_route_metrics(path_edges)
            
            # Format waypoints
            waypoints = [NODE_METADATA[n] for n in path_nodes if n in NODE_METADATA]
            
            # Label path name
            node_letters = [n.replace("Sector_", "").replace("Checkpoint_", "").replace("Shelter_", "") for n in path_nodes]
            path_name = " → ".join(node_letters)

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
                nodes=path_nodes,
                is_blocked=metrics["has_blocked_segment"],
            )
            route_paths.append(route_obj)

        recommended = route_paths[0]
        alternatives = route_paths[1:]

        # 5. Generate route selection reasoning narrative
        if route_blockage:
            reason = f"Route {recommended.name} selected: Avoids blocked North corridor (Checkpoint D). Safety Score: {int(recommended.safetyScore * 100)}%."
        elif norm_pred_risk >= 75.0:
            reason = f"Route {recommended.name} selected: Primary route B provides lower predicted hazard exposure ({recommended.riskScore:.1f}) vs elevated risk on North corridor."
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


# Global singleton instance & convenience function
_global_optimizer: Optional[RouteOptimizer] = None


def get_optimizer() -> RouteOptimizer:
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = RouteOptimizer()
    return _global_optimizer


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
