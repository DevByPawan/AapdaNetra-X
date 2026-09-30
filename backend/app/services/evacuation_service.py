"""
AapdaNetra-X — Dynamic Evacuation Intelligence Service

Phase 6.18: Continuously derives, scores, ranks, and monitors dynamic evacuation route recommendations
by combining ML predicted risk, NetworkX graph routing, PostGIS/GIS spatial hazard exposure,
road congestion, ETA, and telemetry freshness metadata.

Enforces:
- Transparent, bounded, deterministic multi-factor route scoring.
- Explicit status classification (SAFE, CAUTION, HIGH_RISK, BLOCKED).
- Exclusion of blocked routes from primary recommendations.
- Emergency fallback handling when all routes are unsafe.
- Evidence-based route change detection and reason attribution.
- Persistence to 'evacuation_routes' table obeying PERSISTENCE_MODE.
- SSE publication via EventType.ROUTE_UPDATED ('route.updated').
- Strictly read-only with respect to live telemetry, ML model, and alert state.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.events.broker import get_event_broker
from app.events.schemas import EventEnvelope, EventType
from app.models.schemas import (
    EvacuationIntelligenceResponse,
    EvacuationRouteDetail,
    EvacuationUnavailableResponse,
    RouteChangeNotice,
    RouteScoreDetails,
    RouteStatusEnum,
    RouteWaypoint,
)
from app.hazards.registry import get_hazard_registry
from app.hazards.types import HazardType

logger = logging.getLogger("aapdanetra.evacuation_service")

# Global in-memory cache for route change tracking across re-evaluations
_PREVIOUS_RECOMMENDED_ROUTE: Dict[str, str] = {}

# Centralized, configurable route scoring parameters
SCORING_WEIGHTS = {
    "safety_base_multiplier": 100.0,
    "spatial_hazard_weight": 30.0,
    "congestion_weight": 20.0,
    "eta_penalty_per_min": 1.5,
    "eta_baseline_min": 10,
    "blockage_penalty": 1000.0,
}


def calculate_composite_route_score(
    safety_score: float,
    spatial_exposure_ratio: float,
    eta_min: int,
    is_blocked: bool,
    avg_risk: float = 30.0,
) -> RouteScoreDetails:
    """
    Computes a transparent, bounded, deterministic multi-factor composite route score [0.0, 100.0].
    
    Formula:
    composite_score = max(0.0, (safety_score * 100) - spatial_penalty - eta_penalty - blockage_penalty)
    """
    safety_comp = round(float(safety_score) * SCORING_WEIGHTS["safety_base_multiplier"], 2)
    spatial_penalty = round(float(spatial_exposure_ratio) * SCORING_WEIGHTS["spatial_hazard_weight"], 2)
    
    # Congestion penalty inferred from inverse safety & risk score
    congestion_ratio = max(0.0, min(1.0, 1.0 - float(safety_score)))
    congestion_penalty = round(congestion_ratio * SCORING_WEIGHTS["congestion_weight"], 2)

    eta_excess = max(0, int(eta_min) - SCORING_WEIGHTS["eta_baseline_min"])
    eta_penalty = round(eta_excess * SCORING_WEIGHTS["eta_penalty_per_min"], 2)

    blockage_penalty = SCORING_WEIGHTS["blockage_penalty"] if is_blocked else 0.0

    raw_score = safety_comp - spatial_penalty - eta_penalty - blockage_penalty
    composite = round(max(0.0, min(100.0, raw_score)), 2)

    return RouteScoreDetails(
        safety_score=safety_score,
        spatial_hazard_penalty=spatial_penalty,
        congestion_penalty=congestion_penalty,
        eta_penalty=eta_penalty,
        blockage_penalty=blockage_penalty,
        composite_score=composite,
    )


def classify_route_status(
    safety_score: float,
    composite_score: float,
    is_blocked: bool,
) -> RouteStatusEnum:
    """
    Classifies a candidate route into centralized status categories:
    - BLOCKED: If road segment is blocked by flood inundation or structural failure.
    - SAFE: If safety_score >= 0.80 and composite_score >= 70.0.
    - CAUTION: If safety_score >= 0.50 and composite_score >= 40.0.
    - HIGH_RISK: If safety_score < 0.50 or composite_score < 40.0.
    """
    if is_blocked:
        return "BLOCKED"
    if safety_score >= 0.80 and composite_score >= 70.0:
        return "SAFE"
    if safety_score >= 0.50 and composite_score >= 40.0:
        return "CAUTION"
    return "HIGH_RISK"


class EvacuationService:
    """
    Central Dynamic Evacuation Intelligence Engine.
    Orchestrates NetworkX Dijkstra route candidate generation, GIS spatial hazard evaluation,
    transparent scoring, status classification, dynamic route change detection, persistence, and SSE.
    """

    def evaluate_evacuation_routes(
        self,
        incident_id: str = "INC-2026-DEFAULT",
        horizon: int = 0,
        route_blockage_override: Optional[bool] = None,
        publish_sse: bool = False,
        hazard_type: str = "flood",
    ) -> EvacuationIntelligenceResponse | EvacuationUnavailableResponse:
        """
        Evaluates dynamic evacuation route intelligence for the specified incident, horizon, and hazard_type.
        """
        try:
            h_enum = HazardType(hazard_type.lower())
        except ValueError as exc:
            raise ValueError(f"Unknown or unsupported hazard type: '{hazard_type}'") from exc

        h_val = h_enum.value
        registry = get_hazard_registry()
        h_defn = registry.get_definition(h_enum)

        now_iso = datetime.now(timezone.utc).isoformat()

        # Check hazard routing capability
        if not h_defn.routing_available:
            return EvacuationUnavailableResponse(
                hazard_type=h_val,
                routing_available=False,
                status="UNAVAILABLE",
                reason=f"Operational evacuation routing is not supported for '{h_defn.display_name}'.",
                incident_id=incident_id,
                generated_at=now_iso,
            )

        from app.services.risk_engine import compute_risk_state
        from app.services.spatial_service import get_spatial_service
        from ml.routing import optimize_routes
        from app.data.providers.data_adapter import get_data_adapter

        # 1. Capture current risk state
        risk_state = compute_risk_state(horizon=horizon)
        active_risk = risk_state.predictedRisk
        active_category = risk_state.riskCategory

        blockage_flag = route_blockage_override if route_blockage_override is not None else (active_risk >= 85.0)

        # 2. NetworkX Dijkstra Route Optimization
        opt_res = optimize_routes(
            predicted_risk_score=active_risk,
            route_blockage=blockage_flag,
            horizon_index=horizon,
        )

        spatial_svc = get_spatial_service()
        raw_candidates = [opt_res.recommended] + opt_res.alternatives

        evaluated_routes: List[EvacuationRouteDetail] = []

        # 3. Evaluate each route candidate with SpatialService and Multi-Factor Scoring
        for idx, route_path in enumerate(raw_candidates):
            wp_dicts = [{"lat": wp.lat, "lng": wp.lng} for wp in route_path.waypoints]
            spatial_haz = spatial_svc.calculate_route_spatial_hazard(
                waypoints=wp_dicts,
                base_safety_score=route_path.safetyScore,
            )

            spatial_exp_ratio = float(spatial_haz.get("spatial_exposure_ratio", 0.0))
            adjusted_safety = float(spatial_haz.get("adjusted_safety_score", route_path.safetyScore))

            score_details = calculate_composite_route_score(
                safety_score=adjusted_safety,
                spatial_exposure_ratio=spatial_exp_ratio,
                eta_min=route_path.eta,
                is_blocked=route_path.is_blocked,
                avg_risk=route_path.riskScore,
            )

            status = classify_route_status(
                safety_score=adjusted_safety,
                composite_score=score_details.composite_score,
                is_blocked=route_path.is_blocked,
            )

            # Build waypoint DTOs
            waypoint_dtos = [
                RouteWaypoint(id=wp.id, lat=wp.lat, lng=wp.lng, label=wp.label)
                for wp in route_path.waypoints
            ]

            # Reasoning
            if route_path.is_blocked:
                reason = f"Route {route_path.name} is BLOCKED due to structural inundation or barricades."
            elif status == "SAFE":
                reason = f"Route {route_path.name} offers optimal safety ({int(adjusted_safety * 100)}%) and minimal spatial hazard exposure."
            elif status == "CAUTION":
                reason = f"Route {route_path.name} is viable but requires caution due to moderate risk ({active_risk:.1f}%) and ETA ({route_path.eta} min)."
            else:
                reason = f"Route {route_path.name} presents elevated risk ({active_risk:.1f}%) or high spatial hazard penalty."

            route_dto = EvacuationRouteDetail(
                id=route_path.id,
                name=route_path.name,
                eta=route_path.eta,
                distance_km=route_path.distance_km,
                safety_score=adjusted_safety,
                failure_probability=round(1.0 - adjusted_safety, 2),
                risk_score=route_path.riskScore,
                status=status,
                is_blocked=route_path.is_blocked,
                score_details=score_details,
                spatial_hazard_exposure=spatial_exp_ratio,
                waypoints=waypoint_dtos,
                nodes=route_path.nodes,
                selection_reason=reason,
            )
            evaluated_routes.append(route_dto)

        # 4. Filter and Rank Candidates
        # Unblocked candidates ranked by composite_score descending
        unblocked_candidates = [r for r in evaluated_routes if not r.is_blocked]
        blocked_candidates = [r for r in evaluated_routes if r.is_blocked]

        unblocked_candidates.sort(key=lambda r: r.score_details.composite_score, reverse=True)

        all_routes_unsafe = False
        overall_warning: Optional[str] = None

        if unblocked_candidates:
            recommended = unblocked_candidates[0]
            alternatives = unblocked_candidates[1:] + blocked_candidates
            if recommended.status == "HIGH_RISK" or (active_risk >= 90.0 and recommended.status != "SAFE"):
                all_routes_unsafe = True
                overall_warning = (
                    "CRITICAL EVACUATION WARNING: All available evacuation routes present high risk or elevated hazard "
                    f"(active risk: {active_risk:.1f}%). Displaying the least-hazardous option with extreme caution."
                )
        elif evaluated_routes:
            # Fallback if ALL routes are blocked
            all_routes_unsafe = True
            overall_warning = (
                "EMERGENCY ALERT: ALL evacuation routes are currently BLOCKED by inundation. "
                "Immediate shelter-in-place or emergency airlift required."
            )
            recommended = evaluated_routes[0]
            alternatives = evaluated_routes[1:]
        else:
            raise RuntimeError("No evacuation route candidates generated by routing engine.")

        # 5. Route Change Detection & Reason Attribution
        prev_route_id: Optional[str] = None
        from app.services.persistence_service import get_persistence_service
        ps = get_persistence_service()
        if ps.is_enabled and ps.db_available:
            try:
                latest_rec = ps.get_latest_recommended_route_sync(incident_id, hazard_type=h_val)
                if latest_rec:
                    prev_route_id = latest_rec.get("route_id") or latest_rec.get("route_name")
            except Exception as err:
                logger.debug(f"[EvacuationService] DB route recovery note: {err}")

        if prev_route_id is None:
            prev_route_id = _PREVIOUS_RECOMMENDED_ROUTE.get(incident_id)

        current_route_id = recommended.id
        route_changed = (prev_route_id is not None) and (prev_route_id != current_route_id)

        change_reason: Optional[str] = None
        if route_changed:
            if blockage_flag:
                change_reason = f"Primary route blocked; rerouted to {recommended.name} (Safety Score: {int(recommended.safety_score * 100)}%)."
            elif active_risk >= 75.0:
                change_reason = f"Elevated flood risk ({active_risk:.1f}%) triggered rerouting to safer corridor {recommended.name}."
            else:
                change_reason = f"Dynamic re-evaluation updated optimal route to {recommended.name} (Score: {recommended.score_details.composite_score})."

        # Update cache
        _PREVIOUS_RECOMMENDED_ROUTE[incident_id] = current_route_id

        route_change_notice = RouteChangeNotice(
            route_changed=route_changed,
            previous_route_id=prev_route_id,
            new_route_id=current_route_id,
            change_reason=change_reason,
        )

        # 6. Telemetry & Data Provenance
        adapter = get_data_adapter()
        adapter_meta = adapter.get_telemetry_metadata()
        provenance_str = (
            f"routing:networkx_dijkstra,dem:copernicus_glo_30,"
            f"hazard:{spatial_svc.get_hazards().get('provenance', 'provisional_river_proximity')},"
            f"telemetry:{adapter_meta.get('provider_name', 'default')}"
        )

        # Decision trace items
        decision_trace = [
            {"factor": "Recommended Route", "value": recommended.name, "impact": f"Status: {recommended.status}"},
            {"factor": "Composite Route Score", "value": f"{recommended.score_details.composite_score} / 100", "impact": "Highest ranked candidate"},
            {"factor": "Safety Score", "value": f"{int(recommended.safety_score * 100)}%", "impact": "Spatial hazard adjusted"},
            {"factor": "Evacuation ETA", "value": f"{recommended.eta} min", "impact": f"Distance: {recommended.distance_km} km"},
            {"factor": "Spatial Exposure", "value": f"{int(recommended.spatial_hazard_exposure * 100)}%", "impact": "Yamuna corridor proximity"},
        ]

        response = EvacuationIntelligenceResponse(
            incident_id=incident_id,
            horizon=horizon,
            recommended_route=recommended,
            alternative_routes=alternatives,
            route_change=route_change_notice,
            overall_status_warning=overall_warning,
            all_routes_unsafe=all_routes_unsafe,
            active_risk_score=active_risk,
            active_risk_category=active_category,
            data_freshness={
                "provider": adapter_meta.get("provider_name", "default"),
                "fallback_used": adapter.fallback_used,
                "observed_at": adapter_meta.get("last_updated"),
            },
            decision_trace=decision_trace,
            provenance=provenance_str,
            generated_at=now_iso,
            hazard_type=h_val,
        )

        # 7. Persistence handling if enabled
        try:
            if ps.is_enabled and ps.db_available:
                ps.save_evacuation_routes_sync(incident_id=incident_id, response=response)
                # Log audit event for route recomputation if changed
                if route_changed:
                    ps.log_audit_event_sync(
                        event_type="ROUTE_RECOMMENDATION_CHANGED",
                        severity="INFO",
                        source="EvacuationService",
                        description=f"Evacuation route changed from {prev_route_id} to {current_route_id}. Reason: {change_reason}",
                        actor="SYSTEM_EVACUATION_ENGINE",
                        event_data={
                            "previous_route_id": prev_route_id,
                            "new_route_id": current_route_id,
                            "change_reason": change_reason,
                            "recommended_name": recommended.name,
                            "composite_score": recommended.score_details.composite_score,
                            "hazard_type": h_val,
                        },
                        incident_id=incident_id,
                    )
        except Exception as p_err:
            logger.debug(f"[EvacuationService] Persistence logging note: {p_err}")

        # 8. Publish SSE Event if requested
        if publish_sse:
            try:
                broker = get_event_broker()
                broker.publish(
                    EventEnvelope(
                        event=EventType.ROUTE_UPDATED,
                        incident_id=incident_id,
                        data={
                            "recommended_route_id": recommended.id,
                            "recommended_name": recommended.name,
                            "status": recommended.status,
                            "safety_score": recommended.safety_score,
                            "eta": recommended.eta,
                            "route_changed": route_changed,
                            "change_reason": change_reason,
                            "hazard_type": h_val,
                            "timestamp": now_iso,
                        },
                        persistence_status="persisted",
                    )
                )
            except Exception as sse_err:
                logger.warning(f"[EvacuationService] SSE publishing error: {sse_err}")

        return response



# Global singleton instance
_global_evacuation_service: Optional[EvacuationService] = None


def get_evacuation_service() -> EvacuationService:
    global _global_evacuation_service
    if _global_evacuation_service is None:
        _global_evacuation_service = EvacuationService()
    return _global_evacuation_service
