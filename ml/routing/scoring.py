"""
AapdaNetra-X — Route Scoring and Cost Functions
Centralizes weight configurations and cost calculation logic for NetworkX routing.
"""
from typing import Dict, Any, List

# Centralized Configurable Weights for Route Cost Matrix
ROUTING_WEIGHTS = {
    "distance_weight": 1.0,     # Weight per km
    "time_weight": 1.2,         # Weight per minute travel time
    "risk_weight": 4.5,         # High penalty weight for predicted flood risk
    "congestion_weight": 2.0,   # Weight for road traffic congestion
    "blockage_penalty": 10000.0 # Extreme penalty for blocked road segments
}


def calculate_edge_cost(
    distance_km: float,
    base_time_min: float,
    risk_score: float,
    congestion: float,
    is_blocked: bool = False,
    weights: Dict[str, float] = None
) -> float:
    """
    Computes traversal cost for a single road edge using a weighted combination
    of distance, travel time, ML flood risk score, congestion ratio, and blockage status.
    """
    w = weights or ROUTING_WEIGHTS

    if is_blocked:
        return w["blockage_penalty"]

    norm_risk = max(0.0, min(100.0, float(risk_score))) / 100.0
    norm_cong = max(0.0, min(1.0, float(congestion)))

    cost = (
        w["distance_weight"] * float(distance_km) +
        w["time_weight"] * float(base_time_min) +
        w["risk_weight"] * norm_risk * 15.0 +
        w["congestion_weight"] * norm_cong * 10.0
    )
    return max(0.1, float(cost))


def calculate_route_metrics(
    edge_list: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculates aggregated metrics (distance, ETA, risk score, safety score, failure probability)
    for a completed path composed of road edges.
    """
    if not edge_list:
        return {
            "total_distance_km": 0.0,
            "total_time_min": 0,
            "avg_risk": 0.0,
            "safety_score": 0.5,
            "failure_probability": 0.5,
            "has_blocked_segment": False,
        }

    total_dist = sum(float(e.get("distance_km", 1.0)) for e in edge_list)
    base_time = sum(float(e.get("base_time_min", 2.0)) for e in edge_list)
    
    # Congestion-adjusted travel time
    avg_congestion = sum(float(e.get("congestion", 0.5)) for e in edge_list) / len(edge_list)
    actual_time = round(base_time * (1.0 + avg_congestion * 0.8))

    avg_risk = sum(float(e.get("risk_score", 30.0)) for e in edge_list) / len(edge_list)
    has_blocked = any(e.get("is_blocked", False) for e in edge_list)

    if has_blocked:
        safety_score = 0.05
        failure_prob = 0.95
    else:
        # Safety score normalized between 0.05 and 0.95
        norm_risk = avg_risk / 100.0
        raw_safety = 1.0 - (norm_risk * 0.65 + avg_congestion * 0.35)
        safety_score = round(float(max(0.05, min(0.95, raw_safety))), 2)
        failure_prob = round(float(1.0 - safety_score), 2)

    return {
        "total_distance_km": round(float(total_dist), 2),
        "total_time_min": max(1, int(actual_time)),
        "avg_risk": round(float(avg_risk), 1),
        "safety_score": safety_score,
        "failure_probability": failure_prob,
        "has_blocked_segment": has_blocked,
    }
