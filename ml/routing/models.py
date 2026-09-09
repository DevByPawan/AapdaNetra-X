"""
AapdaNetra-X — Routing Engine Data Models
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class Waypoint:
    id: str
    lat: float
    lng: float
    label: str


@dataclass
class RoutePath:
    id: str
    name: str
    eta: int  # minutes
    distance_km: float
    failureProbability: float
    safetyScore: float  # 0.0 to 1.0 (for frontend compat) or 0 to 100
    riskScore: float
    waypoints: List[Waypoint]
    nodes: List[str]
    is_blocked: bool = False
    route_reason: str = ""


@dataclass
class RoutingOptimizationResult:
    recommended: RoutePath
    alternatives: List[RoutePath]
    blocked_segments: List[Dict[str, Any]]
    route_reason: str
    horizon_index: int = 0
