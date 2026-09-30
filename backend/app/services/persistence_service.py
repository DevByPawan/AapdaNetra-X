"""AapdaNetra-X — Persistence Service Layer

Coordinates database interactions across domain repositories while strictly enforcing
PERSISTENCE_MODE semantics (disabled | optional | required) and transaction boundaries.

Atomic Pipeline Transaction:
  TelemetryObservation -> RiskPrediction -> SHAPRecord -> EvacuationRoute

Independent Transactions:
  Simulation, Alert, AuditEvent
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any, Tuple
import uuid

import asyncio
import concurrent.futures

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.db.session import get_db_manager
from app.db.repositories import (
    IncidentRepository,
    TelemetryRepository,
    RiskPredictionRepository,
    SHAPRecordRepository,
    EvacuationRouteRepository,
    CriticalAssetRepository,
    SimulationRepository,
    AlertRepository,
    AuditEventRepository,
    DecisionRepository,
)
from app.db.models import (
    Incident,
    TelemetryObservation,
    RiskPrediction,
    SHAPRecord,
    EvacuationRoute,
    CriticalAsset,
    Simulation,
    Alert,
    AuditEvent,
    Decision,
)

logger = logging.getLogger("aapdanetra.persistence")


def run_async_in_sync(async_func: Any, *args: Any, **kwargs: Any) -> Any:
    """Safely executes an async session-based function synchronously by creating an isolated event loop, engine, and session."""
    def worker():
        async def runner():
            url = settings.effective_database_url
            engine = create_async_engine(url, pool_pre_ping=True)
            try:
                session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
                async with session_factory() as session:
                    return await async_func(session, *args, **kwargs)
            finally:
                await engine.dispose()

        return asyncio.run(runner())

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(worker).result()
    else:
        return worker()


class PersistenceService:
    """Service layer coordinating ORM repository operations under persistence mode policy."""

    @property
    def mode(self) -> str:
        return settings.persistence_mode.lower()

    @property
    def is_enabled(self) -> bool:
        return self.mode != "disabled"

    @property
    def db_available(self) -> bool:
        if not self.is_enabled:
            return False
        return get_db_manager().is_available

    async def persist_assessment_pipeline(
        self,
        incident_id: str,
        telemetry: TelemetryObservation,
        prediction: RiskPrediction,
        shap_record: SHAPRecord,
        routes: List[EvacuationRoute],
    ) -> bool:
        """Atomic multi-entity persistence pipeline for risk assessment.

        Persists TelemetryObservation, RiskPrediction, SHAPRecord, and EvacuationRoute
        records within a single AsyncSession transaction.
        """
        if not self.is_enabled:
            return False

        if not self.db_available:
            if self.mode == "required":
                raise RuntimeError(
                    "Persistence mode: required — database is unavailable for assessment pipeline"
                )
            logger.warning("Persistence mode: optional — database unavailable, skipping pipeline persistence")
            return False

        import time

        start_time = time.perf_counter()
        try:
            db_mgr = get_db_manager()
            async with db_mgr.get_session() as session:
                async with session.begin():
                    # 1. Telemetry
                    telemetry.incident_id = incident_id
                    telemetry_repo = TelemetryRepository(session)
                    await telemetry_repo.create_observation(telemetry)

                    # 2. Risk Prediction
                    prediction.incident_id = incident_id
                    prediction.telemetry_id = telemetry.id
                    risk_repo = RiskPredictionRepository(session)
                    await risk_repo.save_prediction(prediction)

                    # 3. SHAP Record (1:1 with RiskPrediction)
                    shap_record.risk_prediction_id = prediction.id
                    shap_repo = SHAPRecordRepository(session)
                    await shap_repo.save_shap_record(shap_record)

                    # 4. Evacuation Routes
                    for route in routes:
                        route.incident_id = incident_id
                        route.risk_prediction_id = prediction.id
                    route_repo = EvacuationRouteRepository(session)
                    await route_repo.save_routes(routes)

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info(
                "Atomic assessment pipeline persisted successfully for incident %s (prediction_id=%s, duration=%.2fms)",
                incident_id,
                prediction.id,
                duration_ms,
            )

            # Publish real-time events post-commit
            self._publish_pipeline_events(incident_id, telemetry, prediction, routes, status="persisted")
            return True

        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "Failed to persist assessment pipeline for incident %s after %.2fms: %s",
                incident_id,
                duration_ms,
                exc,
            )
            if self.mode == "required":
                raise RuntimeError(f"Database transaction failed in required mode: {exc}") from exc
            return False

    async def save_simulation(self, simulation: Simulation) -> bool:
        """Persist a What-If simulation run record in an independent transaction."""
        if not self.is_enabled:
            self._publish_simulation_event(simulation, status="disabled")
            return False

        if not self.db_available:
            if self.mode == "required":
                raise RuntimeError("Persistence mode: required — database is unavailable for simulation")
            logger.warning("Persistence mode: optional — database unavailable, skipping simulation persistence")
            self._publish_simulation_event(simulation, status="in_memory_fallback")
            return False

        try:
            db_mgr = get_db_manager()
            async with db_mgr.get_session() as session:
                async with session.begin():
                    repo = SimulationRepository(session)
                    await repo.save_simulation(simulation)
            logger.info("Simulation record saved successfully (id=%s)", simulation.id)
            self._publish_simulation_event(simulation, status="persisted")
            return True
        except Exception as exc:
            logger.error("Failed to save simulation: %s", exc)
            if self.mode == "required":
                raise RuntimeError(f"Database write failed in required mode: {exc}") from exc
            return False

    async def persist_alert(self, alert: Alert) -> bool:
        """Persists an Alert record within an independent transaction and logs audit event."""
        if not self.is_enabled:
            return False

        if not self.db_available:
            if self.mode == "required":
                raise RuntimeError("Persistence mode: required — database is unavailable for alert persistence")
            logger.warning("Persistence mode: optional — database unavailable, skipping alert persistence")
            return False

        try:
            db_mgr = get_db_manager()
            async with db_mgr.get_session() as session:
                async with session.begin():
                    repo = AlertRepository(session)
                    await repo.save_alert(alert)
                    audit_repo = AuditEventRepository(session)
                    await audit_repo.log_event(
                        event_type="ALERT_CREATED",
                        severity=alert.severity,
                        source="persistence_service",
                        description=f"Alert created: {alert.title}",
                        actor="system",
                        event_data={"alert_id": str(alert.id)},
                        incident_id=alert.incident_id,
                    )
            logger.info("Alert record saved successfully (id=%s)", alert.id)
            return True
        except Exception as exc:
            logger.error("Failed to save alert: %s", exc)
            if self.mode == "required":
                raise RuntimeError(f"Database write failed in required mode: {exc}") from exc
            return False

    async def update_alert_status_in_db(self, alert_id: uuid.UUID, new_status: str, actor: str = "system") -> bool:
        """Updates status of an Alert record in DB and logs audit event."""
        if not self.is_enabled or not self.db_available:
            return False

        try:
            db_mgr = get_db_manager()
            async with db_mgr.get_session() as session:
                async with session.begin():
                    repo = AlertRepository(session)
                    alert = await repo.update_status(alert_id, new_status)
                    if alert:
                        audit_repo = AuditEventRepository(session)
                        await audit_repo.log_event(
                            event_type=f"ALERT_{new_status}",
                            severity=alert.severity,
                            source="persistence_service",
                            description=f"Alert {alert.id} status changed to {new_status}",
                            actor=actor,
                            event_data={"alert_id": str(alert.id), "new_status": new_status},
                            incident_id=alert.incident_id,
                        )
            return True
        except Exception as exc:
            logger.error("Failed to update alert status in DB: %s", exc)
            if self.mode == "required":
                raise RuntimeError(f"Database update failed in required mode: {exc}") from exc
            return False

    async def _log_audit_event_impl(
        self,
        session: AsyncSession,
        event_type: str,
        severity: str,
        source: str,
        description: str,
        actor: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
        incident_id: Optional[str] = None,
    ) -> bool:
        repo = AuditEventRepository(session)
        await repo.log_event(
            event_type=event_type,
            severity=severity,
            source=source,
            description=description,
            actor=actor,
            event_data=event_data,
            incident_id=incident_id,
        )
        await session.commit()
        self._publish_audit_event_as_sse(event_type, severity, description, actor, event_data, incident_id, status="persisted")
        return True

    async def log_audit_event(
        self,
        event_type: str,
        severity: str,
        source: str,
        description: str,
        actor: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
        incident_id: Optional[str] = None,
    ) -> bool:
        """Persist an append-only audit log entry in an independent transaction."""
        if not self.is_enabled:
            self._publish_audit_event_as_sse(event_type, severity, description, actor, event_data, incident_id, status="disabled")
            return False

        if not self.db_available:
            if self.mode == "required":
                raise RuntimeError("Persistence mode: required — database is unavailable for audit logging")
            logger.warning("Persistence mode: optional — database unavailable, skipping audit log")
            self._publish_audit_event_as_sse(event_type, severity, description, actor, event_data, incident_id, status="in_memory_fallback")
            return False

        try:
            db_mgr = get_db_manager()
            async with db_mgr.get_session() as session:
                return await self._log_audit_event_impl(
                    session, event_type, severity, source, description, actor, event_data, incident_id
                )
        except Exception as exc:
            logger.error("Failed to log audit event: %s", exc)
            if self.mode == "required":
                raise RuntimeError(f"Database audit write failed in required mode: {exc}") from exc
            return False

    def _publish_pipeline_events(
        self,
        incident_id: str,
        telemetry: TelemetryObservation,
        prediction: RiskPrediction,
        routes: List[EvacuationRoute],
        status: str,
    ) -> None:
        """Helper to publish pipeline events (telemetry, risk, route) post-commit or on fallback."""
        from app.events.broker import get_event_broker
        from app.events.schemas import EventEnvelope, EventType

        broker = get_event_broker()

        # 1. Telemetry event
        broker.publish(
            EventEnvelope(
                event=EventType.TELEMETRY_UPDATED,
                incident_id=incident_id,
                data={
                    "rainfall_intensity": telemetry.rainfall_intensity,
                    "rainfall_trend": telemetry.rainfall_trend,
                    "water_level": telemetry.water_level,
                    "water_level_trend": telemetry.water_level_trend,
                    "road_congestion": telemetry.road_congestion,
                    "population_exposure": telemetry.population_exposure,
                    "infrastructure_vulnerability": telemetry.infrastructure_vulnerability,
                },
                persistence_status=status,
            )
        )

        # 2. Risk event
        broker.publish(
            EventEnvelope(
                event=EventType.RISK_UPDATED,
                incident_id=incident_id,
                data={
                    "horizon": prediction.horizon,
                    "currentRisk": prediction.current_risk,
                    "predictedRisk": prediction.predicted_risk,
                    "riskCategory": prediction.risk_category,
                    "confidence": prediction.confidence,
                    "predictionReliability": prediction.prediction_reliability,
                },
                persistence_status=status,
            )
        )

        # 3. Route event
        if routes:
            rec = routes[0]
            broker.publish(
                EventEnvelope(
                    event=EventType.ROUTE_UPDATED,
                    incident_id=incident_id,
                    data={
                        "recommended_route": rec.route_name,
                        "distance_km": rec.distance_km,
                        "safety_score": rec.safety_score,
                    },
                    persistence_status=status,
                )
            )

    def _publish_simulation_event(self, simulation: Simulation, status: str) -> None:
        from app.events.broker import get_event_broker
        from app.events.schemas import EventEnvelope, EventType

        broker = get_event_broker()
        broker.publish(
            EventEnvelope(
                event=EventType.SIMULATION_COMPLETED,
                incident_id=simulation.incident_id,
                data={
                    "baseline_risk": simulation.baseline_risk,
                    "scenario_risk": simulation.scenario_risk,
                    "risk_delta": simulation.risk_delta,
                    "risk_category": simulation.risk_category,
                    "route_recommendation": simulation.route_recommendation,
                    "severity": simulation.severity,
                },
                persistence_status=status,
            )
        )

    def _publish_audit_event_as_sse(
        self,
        event_type: str,
        severity: str,
        description: str,
        actor: Optional[str],
        event_data: Optional[Dict[str, Any]],
        incident_id: Optional[str],
        status: str,
    ) -> None:
        from app.events.broker import get_event_broker
        from app.events.schemas import EventEnvelope, EventType

        broker = get_event_broker()
        inc_id = incident_id or "INC-2026-DEFAULT"

        if event_type == "RESPONSE_WORKFLOW_APPROVED":
            broker.publish(
                EventEnvelope(
                    event=EventType.DECISION_APPROVED,
                    incident_id=inc_id,
                    data={
                        "workflow_id": (event_data or {}).get("workflow_id"),
                        "responder_id": actor,
                        "description": description,
                    },
                    persistence_status=status,
                )
            )
        elif event_type in ("ALERT_DISPATCHED", "ALERT_CREATED"):
            broker.publish(
                EventEnvelope(
                    event=EventType.ALERT_CREATED,
                    incident_id=inc_id,
                    data={
                        "severity": severity,
                        "description": description,
                    },
                    persistence_status=status,
                )
            )

    def log_audit_event_sync(
        self,
        event_type: str,
        severity: str,
        source: str,
        description: str,
        actor: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
        incident_id: Optional[str] = None,
    ) -> bool:
        if not self.is_enabled or not self.db_available:
            return False
        try:
            return run_async_in_sync(
                self._log_audit_event_impl,
                event_type,
                severity,
                source,
                description,
                actor,
                event_data,
                incident_id,
            )
        except Exception as exc:
            logger.error("Failed to log audit event (sync): %s", exc)
            if self.mode == "required":
                raise RuntimeError(f"Database audit write failed in required mode: {exc}") from exc
            return False

    # ── Telemetry & Risk Durable State Implementation Helpers ────────────────
    def _telemetry_to_dict(self, obs: TelemetryObservation) -> Dict[str, Any]:
        return {
            "id": str(obs.id),
            "incident_id": obs.incident_id,
            "hazard_type": obs.hazard_type,
            "data_mode": obs.data_mode,
            "fallback_used": obs.fallback_used,
            "rainfall_intensity": obs.rainfall_intensity,
            "rainfall_trend": obs.rainfall_trend,
            "water_level": obs.water_level,
            "water_level_trend": obs.water_level_trend,
            "road_congestion": obs.road_congestion,
            "population_exposure": obs.population_exposure,
            "infrastructure_vulnerability": obs.infrastructure_vulnerability,
            "provenance": obs.provenance if isinstance(obs.provenance, dict) else {},
            "provider_metadata": obs.provider_metadata if isinstance(obs.provider_metadata, dict) else {},
            "fingerprint": obs.fingerprint,
            "observed_at": obs.observed_at.isoformat() if obs.observed_at else None,
            "created_at": obs.created_at.isoformat() if obs.created_at else None,
        }

    def _prediction_to_dict(self, pred: RiskPrediction) -> Dict[str, Any]:
        return {
            "id": str(pred.id),
            "incident_id": pred.incident_id,
            "hazard_type": pred.hazard_type,
            "horizon": pred.horizon,
            "current_risk": pred.current_risk,
            "predicted_risk": pred.predicted_risk,
            "risk_category": pred.risk_category,
            "confidence": pred.confidence,
            "prediction_reliability": pred.prediction_reliability,
            "created_at": pred.created_at.isoformat() if pred.created_at else None,
        }

    async def _save_telemetry_observation_impl(
        self, session: AsyncSession, obs_data: Dict[str, Any]
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        from sqlalchemy.exc import IntegrityError
        repo = TelemetryRepository(session)
        fp = obs_data.get("fingerprint")

        if fp:
            existing = await repo.get_by_fingerprint(fp)
            if existing:
                return "duplicate_ignored", self._telemetry_to_dict(existing)

        obs_orm = TelemetryObservation(
            id=uuid.uuid4(),
            incident_id=obs_data.get("incident_id"),
            hazard_type=obs_data.get("hazard_type", "flood"),
            data_mode=obs_data.get("data_mode", settings.data_mode),
            fallback_used=obs_data.get("fallback_used", False),
            rainfall_intensity=obs_data.get("rainfall_intensity", 0.0),
            rainfall_trend=obs_data.get("rainfall_trend", 0.0),
            water_level=obs_data.get("water_level", 0.0),
            water_level_trend=obs_data.get("water_level_trend", 0.0),
            road_congestion=obs_data.get("road_congestion", 0.0),
            population_exposure=obs_data.get("population_exposure", 0.0),
            infrastructure_vulnerability=obs_data.get("infrastructure_vulnerability", 0.0),
            provenance=obs_data.get("provenance", {}),
            provider_metadata=obs_data.get("provider_metadata", {}),
            fingerprint=fp,
            observed_at=obs_data.get("observed_at"),
        )
        try:
            await repo.create_observation(obs_orm)
            await session.commit()
            return "persisted", self._telemetry_to_dict(obs_orm)
        except IntegrityError:
            await session.rollback()
            if fp:
                existing = await repo.get_by_fingerprint(fp)
                if existing:
                    return "duplicate_ignored", self._telemetry_to_dict(existing)
            raise

    async def _get_latest_telemetry_observation_impl(
        self,
        session: AsyncSession,
        incident_id: str,
        hazard_type: Optional[str] = None,
        before_dt: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        repo = TelemetryRepository(session)
        obs = await repo.get_latest_observation(incident_id, hazard_type, before_dt=before_dt)
        return self._telemetry_to_dict(obs) if obs else None

    async def _get_latest_risk_prediction_impl(
        self, session: AsyncSession, incident_id: str, hazard_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        repo = RiskPredictionRepository(session)
        pred = await repo.get_latest_by_horizon(incident_id, horizon=0)
        if pred and (hazard_type is None or pred.hazard_type == hazard_type):
            return self._prediction_to_dict(pred)
        return None

    # ── Telemetry & Risk Durable State Public API ────────────────────────────
    async def save_telemetry_observation(
        self, obs_data: Dict[str, Any]
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        if not self.is_enabled or not self.db_available:
            return "disabled", None
        try:
            db_mgr = get_db_manager()
            async with db_mgr.get_session() as session:
                return await self._save_telemetry_observation_impl(session, obs_data)
        except Exception as exc:
            logger.error("Failed to save telemetry observation to DB: %s", exc)
            if self.mode == "required":
                raise RuntimeError(f"Database telemetry write failed in required mode: {exc}") from exc
            return "failed", None

    def save_telemetry_observation_sync(
        self, obs_data: Dict[str, Any]
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        if not self.is_enabled or not self.db_available:
            return "disabled", None
        try:
            return run_async_in_sync(self._save_telemetry_observation_impl, obs_data)
        except Exception as exc:
            logger.error("Failed to save telemetry observation to DB (sync): %s", exc)
            if self.mode == "required":
                raise RuntimeError(f"Database telemetry write failed in required mode: {exc}") from exc
            return "failed", None

    async def get_latest_telemetry_observation(
        self,
        incident_id: str,
        hazard_type: Optional[str] = None,
        before_dt: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.is_enabled or not self.db_available:
            return None
        try:
            db_mgr = get_db_manager()
            async with db_mgr.get_session() as session:
                return await self._get_latest_telemetry_observation_impl(
                    session, incident_id, hazard_type, before_dt=before_dt
                )
        except Exception as exc:
            logger.error("Failed to fetch latest telemetry observation from DB: %s", exc)
            return None

    def get_latest_telemetry_observation_sync(
        self,
        incident_id: str,
        hazard_type: Optional[str] = None,
        before_dt: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.is_enabled or not self.db_available:
            return None
        try:
            return run_async_in_sync(
                self._get_latest_telemetry_observation_impl,
                incident_id,
                hazard_type,
                before_dt,
            )
        except Exception as exc:
            logger.error("Failed to fetch latest telemetry observation from DB (sync): %s", exc)
            return None

    async def get_latest_risk_prediction(
        self, incident_id: str, hazard_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not self.is_enabled or not self.db_available:
            return None
        try:
            db_mgr = get_db_manager()
            async with db_mgr.get_session() as session:
                return await self._get_latest_risk_prediction_impl(session, incident_id, hazard_type)
        except Exception as exc:
            logger.error("Failed to fetch latest risk prediction from DB: %s", exc)
            return None

    def get_latest_risk_prediction_sync(
        self, incident_id: str, hazard_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not self.is_enabled or not self.db_available:
            return None
        try:
            return run_async_in_sync(self._get_latest_risk_prediction_impl, incident_id, hazard_type)
        except Exception as exc:
            logger.error("Failed to fetch latest risk prediction from DB (sync): %s", exc)
            return None

    # ── Decision Support Implementation Helpers ───────────────────────────────
    async def _save_decision_impl(self, session: AsyncSession, decision_data: Dict[str, Any]) -> bool:
        repo = DecisionRepository(session)
        await repo.supersede_previous_recommendations(
            incident_id=decision_data.get("incident_id", "INC-2026-DEFAULT"),
            hazard_type=decision_data.get("hazard_type", "flood"),
            exclude_decision_id=decision_data.get("decision_id"),
        )
        dec_orm = Decision(
            id=decision_data["decision_id"],
            incident_id=decision_data.get("incident_id", "INC-2026-DEFAULT"),
            hazard_type=decision_data.get("hazard_type", "flood"),
            status=decision_data.get("status", "RECOMMENDED"),
            priority=decision_data.get("priority", "LOW"),
            risk_score=decision_data.get("risk_score"),
            payload=decision_data,
        )
        await repo.save_decision(dec_orm)
        await session.commit()
        return True

    async def _get_decision_impl(self, session: AsyncSession, decision_id: str) -> Optional[Dict[str, Any]]:
        repo = DecisionRepository(session)
        dec = await repo.get_by_id(decision_id)
        if dec:
            payload = dict(dec.payload) if isinstance(dec.payload, dict) else {}
            payload["status"] = dec.status
            return payload
        return None

    async def _get_latest_active_decision_impl(
        self, session: AsyncSession, incident_id: str, hazard_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        repo = DecisionRepository(session)
        dec = await repo.get_latest_active_decision(incident_id, hazard_type)
        if dec:
            payload = dict(dec.payload) if isinstance(dec.payload, dict) else {}
            payload["status"] = dec.status
            return payload
        return None

    async def _transition_decision_status_impl(
        self,
        session: AsyncSession,
        decision_id: str,
        expected_status: str,
        new_status: str,
        responder_id: Optional[str] = None,
        reason: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        repo = DecisionRepository(session)
        dec = await repo.transition_status(
            decision_id=decision_id,
            expected_status=expected_status,
            new_status=new_status,
            reason=reason,
            responder_id=responder_id,
        )
        if dec:
            payload = dict(dec.payload) if isinstance(dec.payload, dict) else {}
            payload["status"] = dec.status
            if responder_id:
                payload["action_by"] = responder_id
            if reason:
                payload["action_reason"] = reason
            if workflow_id:
                payload["workflow_id"] = workflow_id
            dec.payload = payload
            await session.commit()
            return True, payload
        return False, None

    async def _get_latest_recommended_route_impl(
        self, session: AsyncSession, incident_id: str, hazard_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        repo = EvacuationRouteRepository(session)
        route = await repo.get_recommended_route(incident_id, hazard_type=hazard_type)
        if route:
            risk_sum = dict(route.risk_summary) if isinstance(route.risk_summary, dict) else {}
            return {
                "route_id": risk_sum.get("route_id", route.route_name),
                "route_name": route.route_name,
                "created_at": route.created_at.isoformat() if route.created_at else None,
                "safety_score": route.safety_score,
            }
        return None

    async def _save_evacuation_routes_impl(
        self, session: AsyncSession, incident_id: str, response: Any
    ) -> bool:
        repo = EvacuationRouteRepository(session)
        routes_to_save: List[EvacuationRoute] = []

        def _to_dict(obj: Any) -> Dict[str, Any]:
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if hasattr(obj, "dict"):
                return obj.dict()
            return obj if isinstance(obj, dict) else {}

        rec = getattr(response, "recommended_route", None)
        if rec:
            wp_dicts = [_to_dict(w) for w in rec.waypoints] if hasattr(rec, "waypoints") and rec.waypoints else []
            orig_w = wp_dicts[0] if wp_dicts else {}
            dest_w = wp_dicts[-1] if wp_dicts else {}
            score_details_val = _to_dict(rec.score_details)

            routes_to_save.append(
                EvacuationRoute(
                    id=uuid.uuid4(),
                    incident_id=incident_id,
                    route_name=rec.name,
                    route_type="primary",
                    is_recommended=True,
                    hazard_type=getattr(response, "hazard_type", "flood"),
                    origin_name=orig_w.get("label", "Origin"),
                    origin_lat=orig_w.get("lat", 28.6448),
                    origin_lon=orig_w.get("lng", 77.2167),
                    destination_name=dest_w.get("label", "Destination"),
                    destination_lat=dest_w.get("lat", 28.6310),
                    destination_lon=dest_w.get("lng", 77.2450),
                    waypoint_coords=wp_dicts,
                    distance_km=rec.distance_km,
                    estimated_minutes=float(rec.eta),
                    safety_score=rec.safety_score,
                    congestion_index=round(1.0 - float(rec.safety_score), 2),
                    risk_summary={
                        "route_id": rec.id,
                        "route_name": rec.name,
                        "status": rec.status,
                        "score_details": score_details_val,
                    },
                )
            )

        for alt in (getattr(response, "alternative_routes", []) or []):
            wp_dicts = [_to_dict(w) for w in alt.waypoints] if hasattr(alt, "waypoints") and alt.waypoints else []
            orig_w = wp_dicts[0] if wp_dicts else {}
            dest_w = wp_dicts[-1] if wp_dicts else {}
            score_details_val = _to_dict(alt.score_details)

            routes_to_save.append(
                EvacuationRoute(
                    id=uuid.uuid4(),
                    incident_id=incident_id,
                    route_name=alt.name,
                    route_type="alternative",
                    is_recommended=False,
                    hazard_type=getattr(response, "hazard_type", "flood"),
                    origin_name=orig_w.get("label", "Origin"),
                    origin_lat=orig_w.get("lat", 28.6448),
                    origin_lon=orig_w.get("lng", 77.2167),
                    destination_name=dest_w.get("label", "Destination"),
                    destination_lat=dest_w.get("lat", 28.6310),
                    destination_lon=dest_w.get("lng", 77.2450),
                    waypoint_coords=wp_dicts,
                    distance_km=alt.distance_km,
                    estimated_minutes=float(alt.eta),
                    safety_score=alt.safety_score,
                    congestion_index=round(1.0 - float(alt.safety_score), 2),
                    risk_summary={
                        "route_id": alt.id,
                        "route_name": alt.name,
                        "status": alt.status,
                        "score_details": score_details_val,
                    },
                )
            )

        if routes_to_save:
            await repo.save_routes(routes_to_save)
            await session.commit()
        return True

    # ── Decision Support Durable State (Public API) ───────────────────────────
    async def save_decision(self, decision_data: Dict[str, Any]) -> bool:
        """Persist a decision recommendation record into decisions table."""
        if not self.is_enabled or not self.db_available:
            return False

        try:
            db_mgr = get_db_manager()
            async with db_mgr.get_session() as session:
                return await self._save_decision_impl(session, decision_data)
        except Exception as exc:
            logger.error("Failed to persist decision to DB: %s", exc)
            if self.mode == "required":
                raise RuntimeError(f"Database write failed in required mode: {exc}") from exc
            return False

    def save_decision_sync(self, decision_data: Dict[str, Any]) -> bool:
        if not self.is_enabled or not self.db_available:
            return False
        try:
            return run_async_in_sync(self._save_decision_impl, decision_data)
        except Exception as exc:
            logger.error("Failed to persist decision to DB (sync): %s", exc)
            if self.mode == "required":
                raise RuntimeError(f"Database write failed in required mode: {exc}") from exc
            return False

    async def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """Fetch decision record by ID from decisions table."""
        if not self.is_enabled or not self.db_available:
            return None

        try:
            db_mgr = get_db_manager()
            async with db_mgr.get_session() as session:
                return await self._get_decision_impl(session, decision_id)
        except Exception as exc:
            logger.error("Failed to fetch decision from DB: %s", exc)
            return None

    def get_decision_sync(self, decision_id: str) -> Optional[Dict[str, Any]]:
        if not self.is_enabled or not self.db_available:
            return None
        try:
            return run_async_in_sync(self._get_decision_impl, decision_id)
        except Exception as exc:
            logger.error("Failed to fetch decision from DB (sync): %s", exc)
            return None

    async def get_latest_active_decision(
        self, incident_id: str, hazard_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch the latest active decision record from decisions table."""
        if not self.is_enabled or not self.db_available:
            return None

        try:
            db_mgr = get_db_manager()
            async with db_mgr.get_session() as session:
                return await self._get_latest_active_decision_impl(session, incident_id, hazard_type)
        except Exception as exc:
            logger.error("Failed to fetch latest active decision from DB: %s", exc)
            return None

    def get_latest_active_decision_sync(
        self, incident_id: str, hazard_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not self.is_enabled or not self.db_available:
            return None
        try:
            return run_async_in_sync(self._get_latest_active_decision_impl, incident_id, hazard_type)
        except Exception as exc:
            logger.error("Failed to fetch latest active decision from DB (sync): %s", exc)
            return None

    async def transition_decision_status(
        self,
        decision_id: str,
        expected_status: str,
        new_status: str,
        responder_id: Optional[str] = None,
        reason: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Atomic status transition on decisions table."""
        if not self.is_enabled or not self.db_available:
            return False, None

        try:
            db_mgr = get_db_manager()
            async with db_mgr.get_session() as session:
                return await self._transition_decision_status_impl(
                    session, decision_id, expected_status, new_status, responder_id, reason, workflow_id
                )
        except Exception as exc:
            logger.error("Failed to transition decision status in DB: %s", exc)
            if self.mode == "required":
                raise RuntimeError(f"Database status transition failed in required mode: {exc}") from exc
            return False, None

    def transition_decision_status_sync(
        self,
        decision_id: str,
        expected_status: str,
        new_status: str,
        responder_id: Optional[str] = None,
        reason: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        if not self.is_enabled or not self.db_available:
            return False, None
        try:
            return run_async_in_sync(
                self._transition_decision_status_impl,
                decision_id,
                expected_status,
                new_status,
                responder_id,
                reason,
                workflow_id,
            )
        except Exception as exc:
            logger.error("Failed to transition decision status in DB (sync): %s", exc)
            if self.mode == "required":
                raise RuntimeError(f"Database status transition failed in required mode: {exc}") from exc
            return False, None

    # ── Evacuation Route Durable State (Public API) ───────────────────────────
    async def get_latest_recommended_route(
        self, incident_id: str, hazard_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch the latest recommended EvacuationRoute from DB for route change tracking."""
        if not self.is_enabled or not self.db_available:
            return None

        try:
            db_mgr = get_db_manager()
            async with db_mgr.get_session() as session:
                return await self._get_latest_recommended_route_impl(session, incident_id, hazard_type)
        except Exception as exc:
            logger.error("Failed to fetch latest recommended route from DB: %s", exc)
            return None

    def get_latest_recommended_route_sync(
        self, incident_id: str, hazard_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not self.is_enabled or not self.db_available:
            return None
        try:
            return run_async_in_sync(self._get_latest_recommended_route_impl, incident_id, hazard_type)
        except Exception as exc:
            logger.error("Failed to fetch latest recommended route from DB (sync): %s", exc)
            return None

    async def save_evacuation_routes(
        self, incident_id: str, response: Any
    ) -> bool:
        """Persist recommended and alternative routes from EvacuationIntelligenceResponse into DB."""
        if not self.is_enabled or not self.db_available:
            return False

        try:
            db_mgr = get_db_manager()
            async with db_mgr.get_session() as session:
                return await self._save_evacuation_routes_impl(session, incident_id, response)
        except Exception as exc:
            logger.error("Failed to save evacuation routes to DB: %s", exc)
            if self.mode == "required":
                raise RuntimeError(f"Database evacuation route write failed in required mode: {exc}") from exc
            return False

    def save_evacuation_routes_sync(self, incident_id: str, response: Any) -> bool:
        if not self.is_enabled or not self.db_available:
            return False
        try:
            return run_async_in_sync(self._save_evacuation_routes_impl, incident_id, response)
        except Exception as exc:
            logger.error("Failed to save evacuation routes to DB (sync): %s", exc)
            if self.mode == "required":
                raise RuntimeError(f"Database evacuation route write failed in required mode: {exc}") from exc
            return False


_persistence_service: Optional[PersistenceService] = None


def get_persistence_service() -> PersistenceService:
    """Return singleton instance of PersistenceService."""
    global _persistence_service
    if _persistence_service is None:
        _persistence_service = PersistenceService()
    return _persistence_service
