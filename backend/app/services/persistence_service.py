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
)

logger = logging.getLogger("aapdanetra.persistence")


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

            logger.info(
                "Atomic assessment pipeline persisted successfully for incident %s (prediction_id=%s)",
                incident_id,
                prediction.id,
            )

            # Publish real-time events post-commit
            self._publish_pipeline_events(incident_id, telemetry, prediction, routes, status="persisted")
            return True

        except Exception as exc:
            logger.error("Failed to persist assessment pipeline: %s", exc)
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
                async with session.begin():
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
            logger.info("Audit log event recorded: %s (%s)", event_type, severity)
            self._publish_audit_event_as_sse(event_type, severity, description, actor, event_data, incident_id, status="persisted")
            return True
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


_persistence_service: Optional[PersistenceService] = None


def get_persistence_service() -> PersistenceService:
    """Return singleton instance of PersistenceService."""
    global _persistence_service
    if _persistence_service is None:
        _persistence_service = PersistenceService()
    return _persistence_service
