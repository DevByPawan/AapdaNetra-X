"""AapdaNetra-X — Unified Incident Timeline Service

Aggregates historical disaster occurrences across 6 domain entities:
1. TelemetryObservation (rank 6)
2. RiskPrediction (rank 5)
3. EvacuationRoute (rank 4)
4. Alert (rank 3)
5. Simulation (rank 2)
6. AuditEvent (rank 1)

Produces normalized, deterministically sorted, lightweight TimelineEventItem streams.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Alert,
    AuditEvent,
    EvacuationRoute,
    RiskPrediction,
    Simulation,
    TelemetryObservation,
)
from app.db.pagination import PaginationParams, PageResult
from app.schemas.history import TimelineEventItem

logger = logging.getLogger("aapdanetra.timeline")

# Fixed deterministic event rank tie-breaker across entity types (6 is highest priority)
EVENT_RANKS: Dict[str, int] = {
    "telemetry_observation": 6,
    "risk_prediction": 5,
    "evacuation_route": 4,
    "alert": 3,
    "simulation": 2,
    "audit_event": 1,
}


def parse_timeline_cursor_id(cursor_id: str) -> Tuple[int, str]:
    """Parse a timeline cursor ID into (event_rank, entity_id).

    Supports formats:
      - '6:uuid-string'
      - '6_uuid-string'
      - 'uuid-string' (defaults event_rank to 6)
    """
    if not cursor_id:
        raise ValueError("Invalid timeline cursor: cursor_id is empty")

    if ":" in cursor_id:
        parts = cursor_id.split(":", 1)
    elif "_" in cursor_id:
        parts = cursor_id.split("_", 1)
    else:
        return 6, cursor_id

    try:
        rank = int(parts[0])
        entity_id = parts[1]
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Invalid timeline cursor ID format: '{cursor_id}'") from exc

    if rank < 1 or rank > 6 or not entity_id:
        raise ValueError(f"Invalid timeline cursor rank or entity ID: '{cursor_id}'")

    return rank, entity_id


class TimelineService:
    """Service layer constructing unified incident timeline views."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_incident_timeline(
        self,
        incident_id: str,
        params: Optional[PaginationParams] = None,
    ) -> PageResult:
        """Fetch, aggregate, normalize, and paginate timeline events for an incident."""
        p = params or PaginationParams()
        limit = min(max(1, p.limit), 100)

        # Parse cursor if present
        cur_ts: Optional[datetime] = None
        cur_rank: Optional[int] = None
        cur_entity_id: Optional[str] = None

        if p.cursor_timestamp is not None or p.cursor_id is not None:
            if p.cursor_timestamp is None or p.cursor_id is None:
                raise ValueError("Both cursor_timestamp and cursor_id must be provided for timeline pagination")
            cur_ts = p.cursor_timestamp
            cur_rank, cur_entity_id = parse_timeline_cursor_id(p.cursor_id)

        # Candidate fetch across all 6 sources
        candidates: List[TimelineEventItem] = []

        # 1. TelemetryObservation (rank 6)
        t_stmt = self._build_source_stmt(
            TelemetryObservation, TelemetryObservation.observed_at, incident_id, 6, limit, p, cur_rank, cur_ts, cur_entity_id
        )
        t_res = await self.session.execute(t_stmt)
        for obs in t_res.scalars().all():
            candidates.append(self._normalize_telemetry(obs))

        # 2. RiskPrediction (rank 5)
        r_stmt = self._build_source_stmt(
            RiskPrediction, RiskPrediction.created_at, incident_id, 5, limit, p, cur_rank, cur_ts, cur_entity_id
        )
        r_res = await self.session.execute(r_stmt)
        for pred in r_res.scalars().all():
            candidates.append(self._normalize_risk(pred))

        # 3. EvacuationRoute (rank 4)
        rt_stmt = self._build_source_stmt(
            EvacuationRoute, EvacuationRoute.created_at, incident_id, 4, limit, p, cur_rank, cur_ts, cur_entity_id
        )
        rt_res = await self.session.execute(rt_stmt)
        for route in rt_res.scalars().all():
            candidates.append(self._normalize_route(route))

        # 4. Alert (rank 3)
        a_stmt = self._build_source_stmt(
            Alert, Alert.created_at, incident_id, 3, limit, p, cur_rank, cur_ts, cur_entity_id
        )
        a_res = await self.session.execute(a_stmt)
        for alert in a_res.scalars().all():
            candidates.append(self._normalize_alert(alert))

        # 5. Simulation (rank 2)
        s_stmt = self._build_source_stmt(
            Simulation, Simulation.created_at, incident_id, 2, limit, p, cur_rank, cur_ts, cur_entity_id
        )
        s_res = await self.session.execute(s_stmt)
        for sim in s_res.scalars().all():
            candidates.append(self._normalize_simulation(sim))

        # 6. AuditEvent (rank 1)
        au_stmt = self._build_source_stmt(
            AuditEvent, AuditEvent.created_at, incident_id, 1, limit, p, cur_rank, cur_ts, cur_entity_id
        )
        au_res = await self.session.execute(au_stmt)
        for audit in au_res.scalars().all():
            candidates.append(self._normalize_audit(audit))

        # Sort key helper: (timestamp, event_rank, entity_id)
        def sort_key(item: TimelineEventItem) -> Tuple[datetime, int, str]:
            ts = datetime.fromisoformat(item.timestamp)
            rank = EVENT_RANKS.get(item.entity_type, 0)
            return (ts, rank, str(item.entity_id))

        # Strict Python filter condition for descending ordering:
        # timestamp < cursor_timestamp
        # OR (timestamp == cursor_timestamp AND event_rank < cursor_event_rank)
        # OR (timestamp == cursor_timestamp AND event_rank == cursor_event_rank AND entity_id < cursor_entity_id)
        if cur_ts is not None and cur_rank is not None and cur_entity_id is not None:
            filtered: List[TimelineEventItem] = []
            for item in candidates:
                item_ts, item_rank, item_id = sort_key(item)
                if item_ts < cur_ts:
                    filtered.append(item)
                elif item_ts == cur_ts and item_rank < cur_rank:
                    filtered.append(item)
                elif item_ts == cur_ts and item_rank == cur_rank and item_id < cur_entity_id:
                    filtered.append(item)
            candidates = filtered

        # Deterministic DESC sorting
        candidates.sort(key=sort_key, reverse=True)

        # Page slicing & continuation
        has_more = len(candidates) > limit
        page_items = candidates[:limit] if has_more else candidates

        next_cursor = None
        if has_more and page_items:
            last_item = page_items[-1]
            last_rank = EVENT_RANKS.get(last_item.entity_type, 0)
            next_cursor = {
                "timestamp": last_item.timestamp,
                "id": f"{last_rank}:{last_item.entity_id}",
            }

        return PageResult(
            items=page_items,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    def _build_source_stmt(
        self,
        model_cls: Any,
        timestamp_col: Any,
        incident_id: str,
        event_rank: int,
        limit: int,
        p: PaginationParams,
        cur_rank: Optional[int],
        cur_ts: Optional[datetime],
        cur_entity_id: Optional[str],
    ) -> Any:
        stmt = select(model_cls).where(model_cls.incident_id == incident_id)

        if p.from_time:
            stmt = stmt.where(timestamp_col >= p.from_time)
        if p.to_time:
            stmt = stmt.where(timestamp_col <= p.to_time)

        if cur_ts is not None and cur_rank is not None and cur_entity_id is not None:
            target_id = self._parse_entity_id_for_col(cur_entity_id)
            if event_rank < cur_rank:
                stmt = stmt.where(timestamp_col <= cur_ts)
            elif event_rank > cur_rank:
                stmt = stmt.where(timestamp_col < cur_ts)
            else:
                stmt = stmt.where(
                    (timestamp_col < cur_ts)
                    | ((timestamp_col == cur_ts) & (model_cls.id < target_id))
                )

        stmt = stmt.order_by(timestamp_col.desc(), model_cls.id.desc()).limit(limit + 1)
        return stmt

    @staticmethod
    def _parse_entity_id_for_col(entity_id_str: str) -> Any:
        try:
            return uuid.UUID(entity_id_str)
        except ValueError:
            return entity_id_str

    # ── Source Normalizers ───────────────────────────────────────────────

    def _normalize_telemetry(self, obs: TelemetryObservation) -> TimelineEventItem:
        ts = obs.observed_at if obs.observed_at.tzinfo else obs.observed_at.replace(tzinfo=timezone.utc)
        return TimelineEventItem(
            timestamp=ts.isoformat(),
            event_type="TELEMETRY_OBSERVED",
            entity_type="telemetry_observation",
            entity_id=str(obs.id),
            incident_id=obs.incident_id or "INC-2026-DEFAULT",
            summary=(
                f"Telemetry observed — Rainfall {obs.rainfall_intensity:.1f} mm/h, "
                f"Water level {obs.water_level:.2f} m"
            ),
            details={
                "rainfall_intensity": obs.rainfall_intensity,
                "water_level": obs.water_level,
                "road_congestion": obs.road_congestion,
                "data_mode": obs.data_mode,
            },
        )

    def _normalize_risk(self, pred: RiskPrediction) -> TimelineEventItem:
        ts = pred.created_at if pred.created_at.tzinfo else pred.created_at.replace(tzinfo=timezone.utc)
        return TimelineEventItem(
            timestamp=ts.isoformat(),
            event_type="RISK_EVALUATED",
            entity_type="risk_prediction",
            entity_id=str(pred.id),
            incident_id=pred.incident_id,
            summary=(
                f"Risk evaluated — Score {pred.predicted_risk:.1f} "
                f"({pred.risk_category}) [{pred.horizon_label}]"
            ),
            details={
                "current_risk": pred.current_risk,
                "predicted_risk": pred.predicted_risk,
                "risk_category": pred.risk_category,
                "horizon": pred.horizon,
            },
        )

    def _normalize_route(self, route: EvacuationRoute) -> TimelineEventItem:
        ts = route.created_at if route.created_at.tzinfo else route.created_at.replace(tzinfo=timezone.utc)
        return TimelineEventItem(
            timestamp=ts.isoformat(),
            event_type="ROUTE_UPDATED",
            entity_type="evacuation_route",
            entity_id=str(route.id),
            incident_id=route.incident_id,
            summary=(
                f"Evacuation route calculated — {route.route_name} "
                f"({route.distance_km:.1f} km, safety score {route.safety_score:.0f})"
            ),
            details={
                "route_name": route.route_name,
                "distance_km": route.distance_km,
                "estimated_minutes": route.estimated_minutes,
                "safety_score": route.safety_score,
                "is_recommended": route.is_recommended,
            },
        )

    def _normalize_alert(self, alert: Alert) -> TimelineEventItem:
        ts = alert.created_at if alert.created_at.tzinfo else alert.created_at.replace(tzinfo=timezone.utc)
        return TimelineEventItem(
            timestamp=ts.isoformat(),
            event_type="ALERT_CREATED",
            entity_type="alert",
            entity_id=str(alert.id),
            incident_id=alert.incident_id,
            summary=f"Alert created — {alert.title} ({alert.severity})",
            details={
                "title": alert.title,
                "severity": alert.severity,
                "description": alert.description,
                "status": alert.status,
            },
        )

    def _normalize_simulation(self, sim: Simulation) -> TimelineEventItem:
        ts = sim.created_at if sim.created_at.tzinfo else sim.created_at.replace(tzinfo=timezone.utc)
        return TimelineEventItem(
            timestamp=ts.isoformat(),
            event_type="SIMULATION_COMPLETED",
            entity_type="simulation",
            entity_id=str(sim.id),
            incident_id=sim.incident_id,
            summary=(
                f"Simulation completed — Scenario risk {sim.scenario_risk:.1f} "
                f"(Delta: {sim.risk_delta:+.1f})"
            ),
            details={
                "baseline_risk": sim.baseline_risk,
                "scenario_risk": sim.scenario_risk,
                "risk_delta": sim.risk_delta,
                "severity": sim.severity,
                "route_recommendation": sim.route_recommendation,
            },
        )

    def _normalize_audit(self, audit: AuditEvent) -> TimelineEventItem:
        ts = audit.created_at if audit.created_at.tzinfo else audit.created_at.replace(tzinfo=timezone.utc)
        evt_type = (
            "DECISION_APPROVED"
            if audit.event_type == "RESPONSE_WORKFLOW_APPROVED"
            else "AUDIT_LOGGED"
        )
        return TimelineEventItem(
            timestamp=ts.isoformat(),
            event_type=evt_type,
            entity_type="audit_event",
            entity_id=str(audit.id),
            incident_id=audit.incident_id or "INC-2026-DEFAULT",
            summary=f"{audit.description} ({audit.event_type})",
            details={
                "event_type": audit.event_type,
                "severity": audit.severity,
                "source": audit.source,
                "actor": audit.actor,
            },
        )

