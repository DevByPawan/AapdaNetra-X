"""AapdaNetra-X — Analytics Persistence Repository

Provides optimized database-side aggregation queries over existing persisted domain entities:
Incident, TelemetryObservation, RiskPrediction, EvacuationRoute, Alert, Simulation, AuditEvent.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Alert,
    AuditEvent,
    EvacuationRoute,
    Incident,
    RiskPrediction,
    Simulation,
    TelemetryObservation,
)
from app.db.repositories.base import BaseRepository


class AnalyticsRepository(BaseRepository[Any]):
    """Repository handling SQL aggregation queries across all historical entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(Incident, session)

    async def get_overview(
        self,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Compute system-wide historical aggregate counts and risk averages."""
        # 1. Incident counts
        inc_stmt = select(func.count(Incident.id))
        if from_time:
            inc_stmt = inc_stmt.where(Incident.started_at >= from_time)
        if to_time:
            inc_stmt = inc_stmt.where(Incident.started_at <= to_time)
        inc_count = (await self.session.execute(inc_stmt)).scalar() or 0

        act_stmt = select(func.count(Incident.id)).where(func.upper(Incident.status) == "ACTIVE")
        if from_time:
            act_stmt = act_stmt.where(Incident.started_at >= from_time)
        if to_time:
            act_stmt = act_stmt.where(Incident.started_at <= to_time)
        act_count = (await self.session.execute(act_stmt)).scalar() or 0

        # 2. Telemetry count
        telem_stmt = select(func.count(TelemetryObservation.id))
        if from_time:
            telem_stmt = telem_stmt.where(TelemetryObservation.observed_at >= from_time)
        if to_time:
            telem_stmt = telem_stmt.where(TelemetryObservation.observed_at <= to_time)
        telem_count = (await self.session.execute(telem_stmt)).scalar() or 0

        # 3. Risk prediction count and risk stats
        risk_stmt = select(
            func.count(RiskPrediction.id),
            func.avg(RiskPrediction.predicted_risk),
            func.max(RiskPrediction.predicted_risk),
        )
        if from_time:
            risk_stmt = risk_stmt.where(RiskPrediction.created_at >= from_time)
        if to_time:
            risk_stmt = risk_stmt.where(RiskPrediction.created_at <= to_time)
        risk_res = (await self.session.execute(risk_stmt)).one()
        risk_count, avg_risk, max_risk = risk_res[0] or 0, risk_res[1], risk_res[2]

        # 4. Alert count
        alert_stmt = select(func.count(Alert.id))
        if from_time:
            alert_stmt = alert_stmt.where(Alert.created_at >= from_time)
        if to_time:
            alert_stmt = alert_stmt.where(Alert.created_at <= to_time)
        alert_count = (await self.session.execute(alert_stmt)).scalar() or 0

        # 5. Route count
        route_stmt = select(func.count(EvacuationRoute.id))
        if from_time:
            route_stmt = route_stmt.where(EvacuationRoute.created_at >= from_time)
        if to_time:
            route_stmt = route_stmt.where(EvacuationRoute.created_at <= to_time)
        route_count = (await self.session.execute(route_stmt)).scalar() or 0

        # 6. Simulation count
        sim_stmt = select(func.count(Simulation.id))
        if from_time:
            sim_stmt = sim_stmt.where(Simulation.created_at >= from_time)
        if to_time:
            sim_stmt = sim_stmt.where(Simulation.created_at <= to_time)
        sim_count = (await self.session.execute(sim_stmt)).scalar() or 0

        # 7. Audit event count
        audit_stmt = select(func.count(AuditEvent.id))
        if from_time:
            audit_stmt = audit_stmt.where(AuditEvent.created_at >= from_time)
        if to_time:
            audit_stmt = audit_stmt.where(AuditEvent.created_at <= to_time)
        audit_count = (await self.session.execute(audit_stmt)).scalar() or 0

        return {
            "total_incidents": inc_count,
            "active_incidents": act_count,
            "total_telemetry_observations": telem_count,
            "total_risk_predictions": risk_count,
            "total_alerts": alert_count,
            "total_evacuation_routes": route_count,
            "total_simulations": sim_count,
            "total_audit_events": audit_count,
            "avg_system_risk": round(avg_risk, 4) if avg_risk is not None else None,
            "max_system_risk": round(max_risk, 4) if max_risk is not None else None,
        }

    async def get_incident_analytics(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Compute aggregated statistics specifically for a given incident."""
        inc_stmt = select(Incident).where(Incident.id == incident_id)
        inc = (await self.session.execute(inc_stmt)).scalar_one_or_none()
        if not inc:
            return None

        telem_count = (await self.session.execute(
            select(func.count(TelemetryObservation.id)).where(TelemetryObservation.incident_id == incident_id)
        )).scalar() or 0

        risk_count = (await self.session.execute(
            select(func.count(RiskPrediction.id)).where(RiskPrediction.incident_id == incident_id)
        )).scalar() or 0

        route_count = (await self.session.execute(
            select(func.count(EvacuationRoute.id)).where(EvacuationRoute.incident_id == incident_id)
        )).scalar() or 0

        alert_count = (await self.session.execute(
            select(func.count(Alert.id)).where(Alert.incident_id == incident_id)
        )).scalar() or 0

        sim_count = (await self.session.execute(
            select(func.count(Simulation.id)).where(Simulation.incident_id == incident_id)
        )).scalar() or 0

        audit_count = (await self.session.execute(
            select(func.count(AuditEvent.id)).where(AuditEvent.incident_id == incident_id)
        )).scalar() or 0

        risk_stats = (await self.session.execute(
            select(
                func.max(RiskPrediction.predicted_risk),
                func.avg(RiskPrediction.predicted_risk),
            ).where(RiskPrediction.incident_id == incident_id)
        )).one()
        max_r, avg_r = risk_stats[0], risk_stats[1]

        latest_risk_stmt = (
            select(RiskPrediction.predicted_risk)
            .where(RiskPrediction.incident_id == incident_id)
            .order_by(RiskPrediction.created_at.desc())
            .limit(1)
        )
        latest_r = (await self.session.execute(latest_risk_stmt)).scalar_one_or_none()

        return {
            "incident_id": inc.id,
            "incident_type": inc.incident_type,
            "status": inc.status,
            "severity": inc.severity,
            "started_at": inc.started_at.isoformat(),
            "created_at": inc.created_at.isoformat(),
            "telemetry_count": telem_count,
            "risk_prediction_count": risk_count,
            "route_count": route_count,
            "alert_count": alert_count,
            "simulation_count": sim_count,
            "audit_event_count": audit_count,
            "latest_risk": round(latest_r, 4) if latest_r is not None else None,
            "max_observed_risk": round(max_r, 4) if max_r is not None else None,
            "avg_observed_risk": round(avg_r, 4) if avg_r is not None else None,
        }

    async def get_risk_analytics(
        self,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        incident_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute min, max, avg, trend, and distribution for risk predictions."""
        filters = []
        if incident_id:
            filters.append(RiskPrediction.incident_id == incident_id)
        if from_time:
            filters.append(RiskPrediction.created_at >= from_time)
        if to_time:
            filters.append(RiskPrediction.created_at <= to_time)

        stat_stmt = select(
            func.count(RiskPrediction.id),
            func.min(RiskPrediction.predicted_risk),
            func.max(RiskPrediction.predicted_risk),
            func.avg(RiskPrediction.predicted_risk),
        )
        if filters:
            stat_stmt = stat_stmt.where(*filters)
        row = (await self.session.execute(stat_stmt)).one()
        cnt, min_r, max_r, avg_r = row[0] or 0, row[1], row[2], row[3]

        latest_r, earliest_r = None, None
        if cnt > 0:
            l_stmt = select(RiskPrediction.predicted_risk).order_by(RiskPrediction.created_at.desc()).limit(1)
            if filters:
                l_stmt = select(RiskPrediction.predicted_risk).where(*filters).order_by(RiskPrediction.created_at.desc()).limit(1)
            latest_r = (await self.session.execute(l_stmt)).scalar_one_or_none()

            e_stmt = select(RiskPrediction.predicted_risk).order_by(RiskPrediction.created_at.asc()).limit(1)
            if filters:
                e_stmt = select(RiskPrediction.predicted_risk).where(*filters).order_by(RiskPrediction.created_at.asc()).limit(1)
            earliest_r = (await self.session.execute(e_stmt)).scalar_one_or_none()

        if cnt < 2 or latest_r is None or earliest_r is None:
            trend = "INSUFFICIENT_DATA"
        elif latest_r > earliest_r + 0.05:
            trend = "INCREASING"
        elif latest_r < earliest_r - 0.05:
            trend = "DECREASING"
        else:
            trend = "STABLE"

        # Risk category distribution
        cat_stmt = select(RiskPrediction.risk_category, func.count(RiskPrediction.id))
        if filters:
            cat_stmt = cat_stmt.where(*filters)
        cat_stmt = cat_stmt.group_by(RiskPrediction.risk_category)
        cat_res = await self.session.execute(cat_stmt)
        cat_dist = {r[0]: r[1] for r in cat_res.all()}

        return {
            "total_predictions": cnt,
            "min_risk": round(min_r, 4) if min_r is not None else None,
            "max_risk": round(max_r, 4) if max_r is not None else None,
            "avg_risk": round(avg_r, 4) if avg_r is not None else None,
            "latest_risk": round(latest_r, 4) if latest_r is not None else None,
            "earliest_risk": round(earliest_r, 4) if earliest_r is not None else None,
            "risk_trend": trend,
            "risk_category_distribution": cat_dist,
        }

    async def get_alert_analytics(
        self,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        incident_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute severity and status distribution for alerts."""
        filters = []
        if incident_id:
            filters.append(Alert.incident_id == incident_id)
        if from_time:
            filters.append(Alert.created_at >= from_time)
        if to_time:
            filters.append(Alert.created_at <= to_time)

        cnt_stmt = select(func.count(Alert.id))
        if filters:
            cnt_stmt = cnt_stmt.where(*filters)
        total = (await self.session.execute(cnt_stmt)).scalar() or 0

        sev_stmt = select(Alert.severity, func.count(Alert.id))
        if filters:
            sev_stmt = sev_stmt.where(*filters)
        sev_stmt = sev_stmt.group_by(Alert.severity)
        sev_dist = {r[0]: r[1] for r in (await self.session.execute(sev_stmt)).all()}

        st_stmt = select(Alert.status, func.count(Alert.id))
        if filters:
            st_stmt = st_stmt.where(*filters)
        st_stmt = st_stmt.group_by(Alert.status)
        st_dist = {r[0]: r[1] for r in (await self.session.execute(st_stmt)).all()}

        return {
            "total_alerts": total,
            "severity_distribution": sev_dist,
            "status_distribution": st_dist,
        }

    async def get_route_analytics(
        self,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        incident_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute ETA and safety score statistics for evacuation routes."""
        filters = []
        if incident_id:
            filters.append(EvacuationRoute.incident_id == incident_id)
        if from_time:
            filters.append(EvacuationRoute.created_at >= from_time)
        if to_time:
            filters.append(EvacuationRoute.created_at <= to_time)

        stat_stmt = select(
            func.count(EvacuationRoute.id),
            func.min(EvacuationRoute.estimated_minutes),
            func.max(EvacuationRoute.estimated_minutes),
            func.avg(EvacuationRoute.estimated_minutes),
            func.min(EvacuationRoute.safety_score),
            func.max(EvacuationRoute.safety_score),
            func.avg(EvacuationRoute.safety_score),
        )
        if filters:
            stat_stmt = stat_stmt.where(*filters)
        row = (await self.session.execute(stat_stmt)).one()
        cnt, min_eta, max_eta, avg_eta, min_safe, max_safe, avg_safe = (
            row[0] or 0, row[1], row[2], row[3], row[4], row[5], row[6]
        )

        rec_stmt = select(func.count(EvacuationRoute.id)).where(EvacuationRoute.is_recommended == True)
        if filters:
            rec_stmt = rec_stmt.where(*filters)
        rec_cnt = (await self.session.execute(rec_stmt)).scalar() or 0

        type_stmt = select(EvacuationRoute.route_type, func.count(EvacuationRoute.id))
        if filters:
            type_stmt = type_stmt.where(*filters)
        type_stmt = type_stmt.group_by(EvacuationRoute.route_type)
        type_dist = {r[0]: r[1] for r in (await self.session.execute(type_stmt)).all()}

        return {
            "total_routes": cnt,
            "recommended_routes_count": rec_cnt,
            "min_estimated_minutes": round(min_eta, 2) if min_eta is not None else None,
            "max_estimated_minutes": round(max_eta, 2) if max_eta is not None else None,
            "avg_estimated_minutes": round(avg_eta, 2) if avg_eta is not None else None,
            "min_safety_score": round(min_safe, 4) if min_safe is not None else None,
            "max_safety_score": round(max_safe, 4) if max_safe is not None else None,
            "avg_safety_score": round(avg_safe, 4) if avg_safe is not None else None,
            "route_type_distribution": type_dist,
        }

    async def get_simulation_analytics(
        self,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        incident_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute baseline risk, scenario risk, and risk delta stats for simulations."""
        filters = []
        if incident_id:
            filters.append(Simulation.incident_id == incident_id)
        if from_time:
            filters.append(Simulation.created_at >= from_time)
        if to_time:
            filters.append(Simulation.created_at <= to_time)

        stat_stmt = select(
            func.count(Simulation.id),
            func.min(Simulation.baseline_risk),
            func.max(Simulation.baseline_risk),
            func.avg(Simulation.baseline_risk),
            func.min(Simulation.scenario_risk),
            func.max(Simulation.scenario_risk),
            func.avg(Simulation.scenario_risk),
            func.min(Simulation.risk_delta),
            func.max(Simulation.risk_delta),
            func.avg(Simulation.risk_delta),
        )
        if filters:
            stat_stmt = stat_stmt.where(*filters)
        row = (await self.session.execute(stat_stmt)).one()
        cnt = row[0] or 0
        min_b, max_b, avg_b = row[1], row[2], row[3]
        min_s, max_s, avg_s = row[4], row[5], row[6]
        min_d, max_d, avg_d = row[7], row[8], row[9]

        sev_stmt = select(Simulation.severity, func.count(Simulation.id))
        if filters:
            sev_stmt = sev_stmt.where(*filters)
        sev_stmt = sev_stmt.group_by(Simulation.severity)
        sev_dist = {r[0]: r[1] for r in (await self.session.execute(sev_stmt)).all()}

        cat_stmt = select(Simulation.risk_category, func.count(Simulation.id))
        if filters:
            cat_stmt = cat_stmt.where(*filters)
        cat_stmt = cat_stmt.group_by(Simulation.risk_category)
        cat_dist = {r[0]: r[1] for r in (await self.session.execute(cat_stmt)).all()}

        return {
            "total_simulations": cnt,
            "min_baseline_risk": round(min_b, 4) if min_b is not None else None,
            "max_baseline_risk": round(max_b, 4) if max_b is not None else None,
            "avg_baseline_risk": round(avg_b, 4) if avg_b is not None else None,
            "min_scenario_risk": round(min_s, 4) if min_s is not None else None,
            "max_scenario_risk": round(max_s, 4) if max_s is not None else None,
            "avg_scenario_risk": round(avg_s, 4) if avg_s is not None else None,
            "min_risk_delta": round(min_d, 4) if min_d is not None else None,
            "max_risk_delta": round(max_d, 4) if max_d is not None else None,
            "avg_risk_delta": round(avg_d, 4) if avg_d is not None else None,
            "severity_distribution": sev_dist,
            "risk_category_distribution": cat_dist,
        }

    async def get_telemetry_analytics(
        self,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        incident_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute rainfall, water level, congestion, and vulnerability stats for telemetry."""
        filters = []
        if incident_id:
            filters.append(TelemetryObservation.incident_id == incident_id)
        if from_time:
            filters.append(TelemetryObservation.observed_at >= from_time)
        if to_time:
            filters.append(TelemetryObservation.observed_at <= to_time)

        stat_stmt = select(
            func.count(TelemetryObservation.id),
            func.min(TelemetryObservation.rainfall_intensity),
            func.max(TelemetryObservation.rainfall_intensity),
            func.avg(TelemetryObservation.rainfall_intensity),
            func.min(TelemetryObservation.water_level),
            func.max(TelemetryObservation.water_level),
            func.avg(TelemetryObservation.water_level),
            func.min(TelemetryObservation.road_congestion),
            func.max(TelemetryObservation.road_congestion),
            func.avg(TelemetryObservation.road_congestion),
            func.avg(TelemetryObservation.population_exposure),
            func.avg(TelemetryObservation.infrastructure_vulnerability),
        )
        if filters:
            stat_stmt = stat_stmt.where(*filters)
        row = (await self.session.execute(stat_stmt)).one()
        cnt = row[0] or 0
        r_min, r_max, r_avg = row[1], row[2], row[3]
        w_min, w_max, w_avg = row[4], row[5], row[6]
        c_min, c_max, c_avg = row[7], row[8], row[9]
        pop_avg, inf_avg = row[10], row[11]

        mode_stmt = select(TelemetryObservation.data_mode, func.count(TelemetryObservation.id))
        if filters:
            mode_stmt = mode_stmt.where(*filters)
        mode_stmt = mode_stmt.group_by(TelemetryObservation.data_mode)
        mode_dist = {r[0]: r[1] for r in (await self.session.execute(mode_stmt)).all()}

        fb_stmt = select(func.count(TelemetryObservation.id)).where(TelemetryObservation.fallback_used == True)
        if filters:
            fb_stmt = fb_stmt.where(*filters)
        fb_cnt = (await self.session.execute(fb_stmt)).scalar() or 0

        return {
            "total_observations": cnt,
            "rainfall_min": round(r_min, 4) if r_min is not None else None,
            "rainfall_max": round(r_max, 4) if r_max is not None else None,
            "rainfall_avg": round(r_avg, 4) if r_avg is not None else None,
            "water_level_min": round(w_min, 4) if w_min is not None else None,
            "water_level_max": round(w_max, 4) if w_max is not None else None,
            "water_level_avg": round(w_avg, 4) if w_avg is not None else None,
            "congestion_min": round(c_min, 4) if c_min is not None else None,
            "congestion_max": round(c_max, 4) if c_max is not None else None,
            "congestion_avg": round(c_avg, 4) if c_avg is not None else None,
            "population_exposure_avg": round(pop_avg, 4) if pop_avg is not None else None,
            "infrastructure_vulnerability_avg": round(inf_avg, 4) if inf_avg is not None else None,
            "data_mode_distribution": mode_dist,
            "fallback_used_count": fb_cnt,
        }
