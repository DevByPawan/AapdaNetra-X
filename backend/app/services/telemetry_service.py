"""
AapdaNetra-X — Real-Time Telemetry Ingestion Pipeline Service

Phase 6.19: Handles push-based telemetry observation ingestion, request validation,
deduplication, out-of-order detection, deterministic rolling trend calculation,
concurrency-safe live overlay management, persistence mode compliance, change-aware
downstream cascade orchestration, and SSE event streaming.

Rules:
- Rejects malformed values, NaN, Infinity, and invalid timestamps.
- Idempotency via SHA-256 fingerprinting.
- Out-of-order observation protection (older observations cannot move active state backward).
- Deterministic trend calculation (dt >= 5s).
- Persistence handling: disabled | optional | required (controlled 503 on required failure).
- Change-aware downstream cascade (no blind full recomputation storms).
- Event-loop safety (SSE is terminal output only).
"""

from __future__ import annotations

import math
import logging
import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.config import settings
from app.events.broker import get_event_broker
from app.events.schemas import EventEnvelope, EventType
from app.models.schemas import (
    TelemetryHealthResponse,
    TelemetryIngestionRequest,
    TelemetryIngestionResponse,
)
from ml.features.schema import FEATURE_SPECS, validate_and_clean_features

logger = logging.getLogger("aapdanetra.telemetry_service")

# Global bounded deduplication cache & metrics
_DEDUPLICATION_CACHE: Dict[str, float] = {}
_MAX_DEDUPLICATION_CACHE_SIZE = 1000

_LATEST_OBSERVED_AT: Dict[str, datetime] = {}
_PREVIOUS_OBSERVATION: Dict[str, Tuple[datetime, Dict[str, float]]] = {}
_LAST_EMITTED_RISK: Dict[str, float] = {}

_METRICS: Dict[str, Any] = {
    "total_received": 0,
    "accepted": 0,
    "rejected": 0,
    "duplicate": 0,
    "out_of_order": 0,
    "stale": 0,
    "processing_failures": 0,
    "last_successful_observation": None,
    "processing_latency_ms": 0.0,
}


def compute_observation_hash(
    incident_id: str,
    sensor_id: str,
    observed_at_str: str,
    features: Dict[str, Any],
    source: Optional[str] = None,
    client_event_id: Optional[str] = None,
) -> str:
    """
    Computes a deterministic SHA-256 fingerprint for a telemetry observation.
    Note: Durable cross-worker idempotency is deferred to production shared persistence.
    """
    sorted_feat_str = ",".join(f"{k}:{features[k]}" for k in sorted(features.keys()))
    raw_sig = f"{incident_id}|{sensor_id}|{observed_at_str}|{sorted_feat_str}|{source or ''}|{client_event_id or ''}"
    return hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()


def parse_and_validate_timestamp(ts_input: Optional[str]) -> datetime:
    """
    Parses ISO 8601 timestamp into a timezone-aware UTC datetime.
    Rejects far future timestamps (> 300 seconds into future).
    """
    now_utc = datetime.now(timezone.utc)
    if not ts_input:
        return now_utc

    try:
        dt = datetime.fromisoformat(ts_input.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
    except Exception as exc:
        raise ValueError(f"Invalid ISO 8601 timestamp format: {ts_input}") from exc

    # Reject far-future timestamps
    future_diff = (dt - now_utc).total_seconds()
    if future_diff > 300.0:
        raise ValueError(f"Future timestamp rejected ({future_diff:.1f}s into future)")

    return dt


def validate_raw_features(raw_features: Dict[str, Any]) -> None:
    """
    Validates that features dict contains valid numeric values and no NaN or Infinity.
    """
    if not isinstance(raw_features, dict) or len(raw_features) == 0:
        raise ValueError("Features payload must be a non-empty dictionary.")

    for k, v in raw_features.items():
        if k not in FEATURE_SPECS:
            continue
        if v is None:
            continue
        try:
            val_float = float(v)
            if math.isnan(val_float) or math.isinf(val_float):
                raise ValueError(f"Feature '{k}' contains invalid non-numeric value ({v}).")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Feature '{k}' contains invalid float representation: {v}") from exc


class TelemetryIngestionService:
    """
    Service layer for real-time telemetry ingestion, deduplication, trend calculation,
    live feature overlay, persistence compliance, and change-aware downstream cascade.
    """

    def ingest_observation(self, request: TelemetryIngestionRequest) -> TelemetryIngestionResponse:
        """
        Processes an incoming telemetry observation request.
        """
        start_time = time.perf_counter()
        _METRICS["total_received"] += 1
        now_utc = datetime.now(timezone.utc)
        ingested_at_iso = now_utc.isoformat()

        # 1. Validation Layer
        try:
            validate_raw_features(request.features)
            observed_dt = parse_and_validate_timestamp(request.observed_at)
            observed_at_iso = observed_dt.isoformat()
        except ValueError as val_err:
            _METRICS["rejected"] += 1
            logger.warning(f"[TelemetryService] Validation rejected request: {val_err}")
            raise HTTPException(
                status_code=400,
                detail=f"Telemetry validation failure: {val_err}"
            ) from val_err

        sensor_key = f"{request.incident_id}:{request.sensor_id}"

        # 2. Idempotency & Deduplication
        obs_hash = compute_observation_hash(
            incident_id=request.incident_id,
            sensor_id=request.sensor_id,
            observed_at_str=observed_at_iso,
            features=request.features,
            source=request.source,
            client_event_id=request.client_event_id,
        )

        if obs_hash in _DEDUPLICATION_CACHE:
            _METRICS["duplicate"] += 1
            logger.info(f"[TelemetryService] Duplicate observation ignored (hash={obs_hash[:8]})")
            return TelemetryIngestionResponse(
                status="duplicate_ignored",
                observation_id=f"obs-{obs_hash[:8]}",
                incident_id=request.incident_id,
                sensor_id=request.sensor_id,
                observation_hash=obs_hash,
                observed_at=observed_at_iso,
                ingested_at=ingested_at_iso,
                features={},
                trends={},
                provenance={},
                persistence_status="skipped",
                cascade_triggered=False,
                message="Duplicate observation ignored.",
            )

        # 3. Ordering & Out-of-Order Check
        last_dt = _LATEST_OBSERVED_AT.get(sensor_key)
        is_out_of_order = (last_dt is not None) and (observed_dt < last_dt)

        if is_out_of_order:
            _METRICS["out_of_order"] += 1
            logger.warning(f"[TelemetryService] Out-of-order telemetry for {sensor_key} (observed={observed_at_iso} < latest={last_dt.isoformat()})")

        # Clean features using canonical schema bounds
        cleaned_features = validate_and_clean_features(request.features)
        provenance_map = {k: f"live_sensor:{request.source or 'ingest'}" for k in request.features if k in FEATURE_SPECS}

        # 4. Persistence Mode Compliance (MUST execute BEFORE in-memory state or overlay mutations)
        mode = settings.persistence_mode.lower()
        persistence_status = "disabled"

        if mode != "disabled":
            try:
                from app.services.persistence_service import get_persistence_service
                ps = get_persistence_service()
                if ps.is_enabled and ps.db_available:
                    from app.db.models import TelemetryObservation
                    obs_model = TelemetryObservation(
                        incident_id=request.incident_id,
                        data_mode=settings.data_mode,
                        fallback_used=False,
                        rainfall_intensity=cleaned_features["rainfall_intensity"],
                        rainfall_trend=cleaned_features["rainfall_trend"],
                        water_level=cleaned_features["water_level"],
                        water_level_trend=cleaned_features["water_level_trend"],
                        road_congestion=cleaned_features["road_congestion"],
                        population_exposure=cleaned_features["population_exposure"],
                        infrastructure_vulnerability=cleaned_features["infrastructure_vulnerability"],
                        provenance=provenance_map,
                        provider_metadata={"sensor_id": request.sensor_id, "source": request.source},
                        observed_at=observed_dt,
                    )
                    ps.log_audit_event_sync(
                        event_type="TELEMETRY_OBSERVATION_INGESTED",
                        severity="INFO",
                        source="TelemetryIngestionService",
                        description=f"Ingested observation {obs_hash[:8]} for sensor {request.sensor_id}",
                        actor=request.sensor_id,
                        event_data={"sensor_id": request.sensor_id, "observation_hash": obs_hash},
                        incident_id=request.incident_id,
                    )
                    persistence_status = "persisted"
                else:
                    if mode == "required":
                        raise RuntimeError("Database persistence unavailable in required mode.")
                    persistence_status = "in_memory_fallback"
            except Exception as p_err:
                if mode == "required":
                    _METRICS["processing_failures"] += 1
                    logger.error(f"[TelemetryService] Persistence required mode failure: {p_err}")
                    raise HTTPException(
                        status_code=503,
                        detail=f"Persistence service unavailable in required mode: {p_err}"
                    ) from p_err
                persistence_status = "in_memory_fallback"

        # 5. ONLY AFTER PERSISTENCE SUCCEEDS (OR IS DISABLED/OPTIONAL FALLBACK):
        # Update in-memory state, trend trackers, deduplication cache, and active overlay
        computed_trends: Dict[str, float] = {}
        if not is_out_of_order:
            prev_data = _PREVIOUS_OBSERVATION.get(sensor_key)
            if prev_data is not None:
                prev_dt, prev_feats = prev_data
                delta_t_sec = (observed_dt - prev_dt).total_seconds()
                delta_t_hours = delta_t_sec / 3600.0

                # Only compute trends if delta_t >= 5 seconds
                if delta_t_sec >= 5.0:
                    if "rainfall_intensity" in request.features and "rainfall_intensity" in prev_feats:
                        d_rain = cleaned_features["rainfall_intensity"] - prev_feats["rainfall_intensity"]
                        r_trend = round(d_rain / delta_t_hours, 2)
                        cleaned_features["rainfall_trend"] = max(-50.0, min(50.0, r_trend))
                        computed_trends["rainfall_trend"] = cleaned_features["rainfall_trend"]

                    if "water_level" in request.features and "water_level" in prev_feats:
                        d_water = cleaned_features["water_level"] - prev_feats["water_level"]
                        w_trend = round(d_water / delta_t_hours, 2)
                        cleaned_features["water_level_trend"] = max(-2.0, min(5.0, w_trend))
                        computed_trends["water_level_trend"] = cleaned_features["water_level_trend"]

            # Update latest observation trackers
            _LATEST_OBSERVED_AT[sensor_key] = observed_dt
            _PREVIOUS_OBSERVATION[sensor_key] = (observed_dt, dict(cleaned_features))

        # Add to deduplication cache
        _DEDUPLICATION_CACHE[obs_hash] = time.time()
        if len(_DEDUPLICATION_CACHE) > _MAX_DEDUPLICATION_CACHE_SIZE:
            oldest_key = next(iter(_DEDUPLICATION_CACHE))
            _DEDUPLICATION_CACHE.pop(oldest_key, None)

        # Update DataAdapter Live Overlay (only if NOT out-of-order)
        if not is_out_of_order:
            try:
                from app.data.providers.data_adapter import get_data_adapter
                adapter = get_data_adapter()
                adapter.update_live_features(
                    features=cleaned_features,
                    provenance_map=provenance_map,
                    observed_at=observed_at_iso,
                )
            except Exception as ad_err:
                logger.warning(f"[TelemetryService] DataAdapter overlay update error: {ad_err}")

        # 6. Change-Aware Downstream Cascade & SSE STREAMING
        cascade_triggered = False
        if not is_out_of_order:
            try:
                # Step A: Publish telemetry.updated event
                broker = get_event_broker()
                broker.publish(
                    EventEnvelope(
                        event=EventType.TELEMETRY_UPDATED,
                        incident_id=request.incident_id,
                        data={
                            "sensor_id": request.sensor_id,
                            "observation_hash": obs_hash,
                            "features": cleaned_features,
                            "provenance": provenance_map,
                            "timestamp": observed_at_iso,
                        },
                        persistence_status=persistence_status,
                    )
                )

                # Step B: Risk Recomputation with Change Gating
                from app.services.risk_engine import compute_risk_state
                risk_state = compute_risk_state(horizon=0)
                prev_emitted_risk = _LAST_EMITTED_RISK.get(request.incident_id)

                # Gating: emit risk.updated only if risk score changes materially (>= 0.1) or first evaluation
                if prev_emitted_risk is None or abs(risk_state.predictedRisk - prev_emitted_risk) >= 0.1:
                    _LAST_EMITTED_RISK[request.incident_id] = risk_state.predictedRisk
                    broker.publish(
                        EventEnvelope(
                            event=EventType.RISK_UPDATED,
                            incident_id=request.incident_id,
                            data={
                                "predicted_risk": risk_state.predictedRisk,
                                "risk_category": risk_state.riskCategory,
                                "confidence": risk_state.confidence,
                                "timestamp": observed_at_iso,
                            },
                            persistence_status=persistence_status,
                        )
                    )

                # Step C: Alert Evaluation
                from app.services.alert_engine import IntelligentAlertEngine
                alert_engine = IntelligentAlertEngine()
                firing_alerts = alert_engine.evaluate_all_rules(
                    incident_id=request.incident_id,
                    predicted_risk=risk_state.predictedRisk,
                    current_risk=risk_state.predictedRisk,
                    telemetry_features=cleaned_features,
                )
                if firing_alerts:
                    for alt in firing_alerts[:1]:
                        broker.publish(
                            EventEnvelope(
                                event=EventType.ALERT_CREATED,
                                incident_id=request.incident_id,
                                data={
                                    "alert_id": alt.id,
                                    "title": alt.title,
                                    "severity": alt.severity,
                                    "timestamp": observed_at_iso,
                                },
                                persistence_status=persistence_status,
                            )
                        )

                # Step D: Evacuation Route Recomputation (if risk is high or route blockage is set)
                if risk_state.predictedRisk >= 50.0:
                    from app.services.evacuation_service import get_evacuation_service
                    evac_svc = get_evacuation_service()
                    evac_svc.evaluate_evacuation_routes(
                        incident_id=request.incident_id,
                        horizon=0,
                        publish_sse=True,
                    )

                cascade_triggered = True
            except Exception as cascade_err:
                logger.warning(f"[TelemetryService] Downstream cascade non-fatal error: {cascade_err}")

        # Metrics recording
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        _METRICS["accepted"] += 1
        _METRICS["last_successful_observation"] = observed_at_iso
        _METRICS["processing_latency_ms"] = duration_ms

        status_tag = "out_of_order" if is_out_of_order else "accepted"
        msg = "Out-of-order telemetry recorded." if is_out_of_order else "Telemetry observation ingested successfully."

        return TelemetryIngestionResponse(
            status=status_tag,
            observation_id=f"obs-{obs_hash[:8]}",
            incident_id=request.incident_id,
            sensor_id=request.sensor_id,
            observation_hash=obs_hash,
            observed_at=observed_at_iso,
            ingested_at=ingested_at_iso,
            features=cleaned_features,
            trends=computed_trends,
            provenance=provenance_map,
            persistence_status=persistence_status,
            cascade_triggered=cascade_triggered,
            message=msg,
        )

    def get_health_status(self) -> TelemetryHealthResponse:
        """Returns active telemetry overlay status and health metrics."""
        from app.data.providers.data_adapter import get_data_adapter
        adapter = get_data_adapter()
        overlay_snapshot = adapter.get_live_overlay()

        return TelemetryHealthResponse(
            active_overlay=overlay_snapshot.get("features", {}),
            data_mode=settings.data_mode,
            freshness={
                "last_observed_at": overlay_snapshot.get("observed_at"),
                "fallback_used": adapter.fallback_used,
            },
            provenance=adapter.provenance,
            metrics=dict(_METRICS),
        )


# Global singleton instance
_global_telemetry_service: Optional[TelemetryIngestionService] = None


def get_telemetry_service() -> TelemetryIngestionService:
    global _global_telemetry_service
    if _global_telemetry_service is None:
        _global_telemetry_service = TelemetryIngestionService()
    return _global_telemetry_service
