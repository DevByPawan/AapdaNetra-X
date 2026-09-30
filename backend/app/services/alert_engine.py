"""
AapdaNetra-X — Phase 6.15 / Phase 6.20.7 Intelligent Alert Engine
Evaluates risk, telemetry, spatial, routing, and data freshness signals to produce
explainable, deduplicated, persistence-aware, lifecycle-managed emergency alerts.

Scientific & Integrity Policy:
- Deterministic alert rule evaluation with centralized configuration thresholds.
- Deduplicates active alerts using (incident_id, hazard_type, alert_type, active_signature).
- Strictly distinguishes disaster risk alerts from data freshness / system alerts.
- Incorporates 90% conformal uncertainty intervals and spatial provenance.
- Flood rules remain flood-specific. Contextual extreme rainfall produces telemetry alerts only.
  Unsupported hazards do not trigger operational alerts from flood models or thresholds.
"""
import uuid
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from app.config import settings
from app.events.broker import get_event_broker
from app.events.schemas import EventEnvelope, EventType
from app.data.providers.data_adapter import get_data_adapter
from app.hazards.types import HazardType

logger = logging.getLogger("aapdanetra.alert_engine")

# Canonical Lifecycle States (mapped to DB schema status string)
STATUS_OPEN = "OPEN"           # Active alert state
STATUS_ACKNOWLEDGED = "ACKNOWLEDGED"
STATUS_RESOLVED = "RESOLVED"

# Severity Levels
SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_HIGH = "HIGH"
SEVERITY_CRITICAL = "CRITICAL"


class AlertRecord:
    """In-memory representation of an intelligent alert."""

    def __init__(
        self,
        id: str,
        incident_id: str,
        alert_type: str,
        severity: str,
        title: str,
        description: str,
        source: str,
        status: str = STATUS_OPEN,
        signature: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
        acknowledged_at: Optional[str] = None,
        resolved_at: Optional[str] = None,
        hazard_type: str = "flood",
    ):
        self.id = id
        self.incident_id = incident_id
        self.alert_type = alert_type
        self.severity = severity
        self.title = title
        self.description = description
        self.source = source
        self.status = status
        self.signature = signature
        self.metadata = metadata or {}
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.acknowledged_at = acknowledged_at
        self.resolved_at = resolved_at
        self.hazard_type = hazard_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "status": self.status,
            "signature": self.signature,
            "hazard_type": self.hazard_type,
            "created_at": self.created_at,
            "acknowledged_at": self.acknowledged_at,
            "resolved_at": self.resolved_at,
            "metadata": self.metadata,
        }


class IntelligentAlertEngine:
    """
    Deterministic Alert Evaluation and Lifecycle Management Engine.
    """

    def __init__(self):
        # Active alerts indexed by dedup key (incident_id:hazard_type:alert_type:signature)
        self._active_alerts: Dict[str, AlertRecord] = {}
        # All alerts (including RESOLVED) indexed by alert.id
        self._history: Dict[str, AlertRecord] = {}

    def evaluate_all_rules(
        self,
        incident_id: str = "INC-2026-DEFAULT",
        predicted_risk: float = 74.0,
        current_risk: float = 65.0,
        uncertainty: Optional[Dict[str, Any]] = None,
        telemetry_features: Optional[Dict[str, float]] = None,
        spatial_exposure: Optional[Dict[str, Any]] = None,
        route_blockage: bool = False,
        hazard_type: str = "flood",
    ) -> List[AlertRecord]:
        """
        Runs deterministic alert evaluation cycle across all signal categories for a given hazard.
        Validates hazard_type, applies hazard-isolated deduplication, and updates active alerts.
        """
        try:
            h_enum = HazardType(hazard_type.lower())
        except ValueError as exc:
            raise ValueError(f"Unknown or unsupported hazard type: '{hazard_type}'") from exc

        h_val = h_enum.value

        telemetry = telemetry_features or {}
        unc = uncertainty or {}
        sp_exp = spatial_exposure or {}

        evaluated_alerts: List[AlertRecord] = []

        if h_val == HazardType.FLOOD.value:
            # ── FLOOD: Operational ML & Hydro-Meteorological Alert Rules ──
            if predicted_risk >= settings.alert_risk_critical_threshold:
                evaluated_alerts.append(self._build_risk_threshold_alert(
                    incident_id, predicted_risk, current_risk, SEVERITY_CRITICAL, unc, hazard_type=h_val
                ))
            elif predicted_risk >= settings.alert_risk_high_threshold:
                evaluated_alerts.append(self._build_risk_threshold_alert(
                    incident_id, predicted_risk, current_risk, SEVERITY_HIGH, unc, hazard_type=h_val
                ))

            risk_delta = round(predicted_risk - current_risk, 1)
            if risk_delta >= settings.alert_risk_escalation_rate and predicted_risk < settings.alert_risk_critical_threshold:
                evaluated_alerts.append(self._build_risk_escalation_alert(
                    incident_id, predicted_risk, current_risk, risk_delta, unc, hazard_type=h_val
                ))

            rf = float(telemetry.get("rainfall_intensity", 0.0))
            if rf >= settings.alert_rainfall_intensity_threshold:
                evaluated_alerts.append(self._build_telemetry_rainfall_alert(incident_id, rf, hazard_type=h_val))

            wl = float(telemetry.get("water_level", 0.0))
            wl_trend = float(telemetry.get("water_level_trend", 0.0))
            if wl >= settings.alert_water_level_threshold:
                evaluated_alerts.append(self._build_telemetry_water_alert(incident_id, wl, wl_trend, hazard_type=h_val))

            if route_blockage:
                evaluated_alerts.append(self._build_route_blockage_alert(incident_id, hazard_type=h_val))

            spatial_hazard_ratio = float(sp_exp.get("spatial_exposure_ratio", 0.0))
            if spatial_hazard_ratio >= settings.alert_spatial_hazard_exposure_threshold:
                evaluated_alerts.append(self._build_spatial_exposure_alert(
                    incident_id, spatial_hazard_ratio, sp_exp.get("provenance", "hazard:provisional_river_proximity"), hazard_type=h_val
                ))

            adapter = get_data_adapter()
            telemetry_meta = adapter.get_telemetry_metadata()
            if adapter.fallback_used:
                evaluated_alerts.append(self._build_data_freshness_alert(incident_id, telemetry_meta, hazard_type=h_val))

        elif h_val == HazardType.EXTREME_RAINFALL.value:
            # ── EXTREME RAINFALL: Contextual Telemetry Only ──
            rf = float(telemetry.get("rainfall_intensity", 0.0))
            if rf >= settings.alert_rainfall_intensity_threshold:
                evaluated_alerts.append(self._build_telemetry_rainfall_alert(incident_id, rf, hazard_type=h_val))

            adapter = get_data_adapter()
            telemetry_meta = adapter.get_telemetry_metadata()
            if adapter.fallback_used:
                evaluated_alerts.append(self._build_data_freshness_alert(incident_id, telemetry_meta, hazard_type=h_val))

        else:
            # ── UNSUPPORTED HAZARDS (landslide, cyclone, heatwave, earthquake) ──
            # Do NOT evaluate flood risk thresholds, water levels, spatial exposure, or route blockages.
            adapter = get_data_adapter()
            telemetry_meta = adapter.get_telemetry_metadata()
            if adapter.fallback_used:
                evaluated_alerts.append(self._build_data_freshness_alert(incident_id, telemetry_meta, hazard_type=h_val))

        # ── Deduplication & Lifecycle Sync (Scoped by incident_id + hazard_type) ──
        new_active_keys = set()

        for candidate in evaluated_alerts:
            dedup_key = f"{candidate.incident_id}:{candidate.hazard_type}:{candidate.alert_type}:{candidate.signature}"
            new_active_keys.add(dedup_key)

            if dedup_key in self._active_alerts:
                existing = self._active_alerts[dedup_key]
                if existing.severity != candidate.severity:
                    existing.severity = candidate.severity
                    existing.description = candidate.description
                    existing.metadata = candidate.metadata
                    self._publish_alert_event(existing)
            else:
                self._active_alerts[dedup_key] = candidate
                self._history[candidate.id] = candidate
                self._publish_alert_event(candidate)

        # Automatically resolve alerts for this specific incident + hazard_type whose conditions no longer fire
        active_keys_snapshot = list(self._active_alerts.keys())
        for key in active_keys_snapshot:
            a_rec = self._active_alerts[key]
            if a_rec.incident_id == incident_id and a_rec.hazard_type == h_val:
                if key not in new_active_keys:
                    alert_to_resolve = self._active_alerts.pop(key)
                    alert_to_resolve.status = STATUS_RESOLVED
                    alert_to_resolve.resolved_at = datetime.now(timezone.utc).isoformat()
                    self._publish_alert_event(alert_to_resolve)

        return [a for a in self._active_alerts.values() if a.incident_id == incident_id and a.hazard_type == h_val]

    # ── Alert Builder Helpers ─────────────────────────────────────────────
    def _build_risk_threshold_alert(
        self, incident_id: str, predicted_risk: float, current_risk: float, severity: str, uncertainty: Dict[str, Any], hazard_type: str = "flood"
    ) -> AlertRecord:
        lower = uncertainty.get("lower_bound", max(0.0, predicted_risk - 6.6))
        upper = uncertainty.get("upper_bound", min(100.0, predicted_risk + 6.6))
        cov = uncertainty.get("nominal_coverage", 0.90)

        alert_id = f"alt-risk-{uuid.uuid4().hex[:8]}"
        title = f"{severity} Risk Warning — Predicted Score {predicted_risk:.1f}"
        desc = (
            f"ML prediction indicates elevated flood risk of {predicted_risk:.1f}% ({severity}). "
            f"90% Conformal Prediction Interval: [{lower:.1f}, {upper:.1f}]. "
            f"Model: GBR v1.0.0."
        )
        metadata = {
            "predicted_risk": predicted_risk,
            "current_risk": current_risk,
            "risk_delta": round(predicted_risk - current_risk, 1),
            "uncertainty": {
                "lower_bound": lower,
                "upper_bound": upper,
                "nominal_coverage": cov,
            },
            "source": "ml:risk_prediction",
            "provenance": "model:gbr_v1.0.0",
        }
        return AlertRecord(
            id=alert_id,
            incident_id=incident_id,
            alert_type="RISK_THRESHOLD",
            severity=severity,
            title=title,
            description=desc,
            source="ml:risk_prediction",
            signature=f"risk_score_{int(predicted_risk / 10) * 10}",
            metadata=metadata,
            hazard_type=hazard_type,
        )

    def _build_risk_escalation_alert(
        self, incident_id: str, predicted_risk: float, current_risk: float, delta: float, uncertainty: Dict[str, Any], hazard_type: str = "flood"
    ) -> AlertRecord:
        alert_id = f"alt-esc-{uuid.uuid4().hex[:8]}"
        title = f"Rapid Risk Increase — +{delta:.1f}% Acceleration"
        desc = (
            f"Disaster risk score escalated rapidly by {delta:+.1f}% points (from {current_risk:.1f} to {predicted_risk:.1f}). "
            f"Accelerated monitoring recommended."
        )
        metadata = {
            "predicted_risk": predicted_risk,
            "current_risk": current_risk,
            "risk_delta": delta,
            "source": "ml:risk_prediction",
        }
        return AlertRecord(
            id=alert_id,
            incident_id=incident_id,
            alert_type="RISK_ESCALATION",
            severity=SEVERITY_WARNING if delta < 15.0 else SEVERITY_HIGH,
            title=title,
            description=desc,
            source="ml:risk_prediction",
            signature=f"escalation_{int(delta)}",
            metadata=metadata,
            hazard_type=hazard_type,
        )

    def _build_telemetry_rainfall_alert(self, incident_id: str, rainfall: float, hazard_type: str = "flood") -> AlertRecord:
        alert_id = f"alt-rf-{uuid.uuid4().hex[:8]}"
        if hazard_type == "extreme_rainfall":
            title = f"Heavy Rainfall Warning (Extreme Rainfall) — {rainfall:.1f} mm/h"
            desc = f"Observed rainfall intensity reached {rainfall:.1f} mm/h exceeding safety threshold ({settings.alert_rainfall_intensity_threshold} mm/h). Contextual telemetry alert for Extreme Rainfall."
            meta = {
                "rainfall_intensity": rainfall,
                "threshold": settings.alert_rainfall_intensity_threshold,
                "hazard_type": "extreme_rainfall",
                "alert_capability": "contextual_telemetry",
            }
        else:
            title = f"Heavy Rainfall Warning — {rainfall:.1f} mm/h"
            desc = f"Observed rainfall intensity reached {rainfall:.1f} mm/h exceeding safety threshold ({settings.alert_rainfall_intensity_threshold} mm/h)."
            meta = {"rainfall_intensity": rainfall, "threshold": settings.alert_rainfall_intensity_threshold}

        return AlertRecord(
            id=alert_id,
            incident_id=incident_id,
            alert_type="TELEMETRY_RAINFALL",
            severity=SEVERITY_HIGH if rainfall >= 100.0 else SEVERITY_WARNING,
            title=title,
            description=desc,
            source="telemetry:weather",
            signature=f"rainfall_{int(rainfall / 20) * 20}",
            metadata=meta,
            hazard_type=hazard_type,
        )

    def _build_telemetry_water_alert(self, incident_id: str, water_level: float, trend: float, hazard_type: str = "flood") -> AlertRecord:
        alert_id = f"alt-wl-{uuid.uuid4().hex[:8]}"
        title = f"Water Level Elevation Warning — {water_level:.2f} m"
        desc = f"River gauge height reached {water_level:.2f} m (Rising trend: +{trend:.2f} m/h)."
        return AlertRecord(
            id=alert_id,
            incident_id=incident_id,
            alert_type="TELEMETRY_WATER_LEVEL",
            severity=SEVERITY_HIGH if water_level >= 7.0 else SEVERITY_WARNING,
            title=title,
            description=desc,
            source="telemetry:water_level",
            signature=f"water_level_{int(water_level)}",
            metadata={"water_level": water_level, "water_level_trend": trend},
            hazard_type=hazard_type,
        )

    def _build_route_blockage_alert(self, incident_id: str, hazard_type: str = "flood") -> AlertRecord:
        alert_id = f"alt-blk-{uuid.uuid4().hex[:8]}"
        title = "Evacuation Route Blockage Flagged"
        desc = "Structural inundation or barricade detected along primary evacuation corridor Checkpoint E. Traffic rerouted."
        return AlertRecord(
            id=alert_id,
            incident_id=incident_id,
            alert_type="ROUTE_BLOCKAGE",
            severity=SEVERITY_HIGH,
            title=title,
            description=desc,
            source="routing:networkx",
            signature="corridor_checkpoint_e_blocked",
            metadata={"blocked_corridor": "Checkpoint_E", "source": "routing:networkx"},
            hazard_type=hazard_type,
        )

    def _build_spatial_exposure_alert(
        self, incident_id: str, spatial_ratio: float, provenance: str, hazard_type: str = "flood"
    ) -> AlertRecord:
        alert_id = f"alt-sp-{uuid.uuid4().hex[:8]}"
        is_provisional = "provisional" in provenance.lower()
        tag = "[PROVISIONAL DEMONSTRATION]" if is_provisional else "[AUTHORITATIVE]"

        title = f"{tag} Route Spatial Exposure Notice — {int(spatial_ratio * 100)}%"
        desc = (
            f"Candidate evacuation route segment intersects spatial hazard corridor ({int(spatial_ratio * 100)}% exposure). "
            f"Notice: {provenance}. Demonstration decision-support signal only."
        )
        return AlertRecord(
            id=alert_id,
            incident_id=incident_id,
            alert_type="SPATIAL_HAZARD_EXPOSURE",
            severity=SEVERITY_WARNING,
            title=title,
            description=desc,
            source="spatial:hazard",
            signature=f"spatial_exp_{int(spatial_ratio * 10)}",
            metadata={"spatial_exposure_ratio": spatial_ratio, "provenance": provenance, "is_provisional": is_provisional},
            hazard_type=hazard_type,
        )

    def _build_data_freshness_alert(self, incident_id: str, meta: Dict[str, Any], hazard_type: str = "flood") -> AlertRecord:
        alert_id = f"alt-sys-{uuid.uuid4().hex[:8]}"
        title = "System Data Quality Notice — Provider Fallback"
        desc = "One or more external data providers are using simulated fallback defaults. This is a system data-quality alert, not a flood risk warning."
        return AlertRecord(
            id=alert_id,
            incident_id=incident_id,
            alert_type="SYSTEM_DATA_FRESHNESS",
            severity=SEVERITY_INFO,
            title=title,
            description=desc,
            source="system:data_freshness",
            signature="provider_fallback_active",
            metadata={"telemetry_metadata": meta, "is_data_quality_alert": True},
            hazard_type=hazard_type,
        )

    # ── Lifecycle Actions & Transitions ────────────────────────────────────
    def acknowledge_alert(self, alert_id: str) -> Optional[AlertRecord]:
        """Transitions alert from OPEN to ACKNOWLEDGED state."""
        target = self._history.get(alert_id)
        if target is None:
            for a in self._active_alerts.values():
                if a.id == alert_id:
                    target = a
                    break

        if target is None:
            return None

        if target.status == STATUS_OPEN:
            target.status = STATUS_ACKNOWLEDGED
            target.acknowledged_at = datetime.now(timezone.utc).isoformat()
            self._publish_alert_event(target)
            return target
        elif target.status == STATUS_ACKNOWLEDGED:
            return target
        else:
            raise ValueError(f"Cannot acknowledge alert in state '{target.status}'")

    def resolve_alert(self, alert_id: str) -> Optional[AlertRecord]:
        """Transitions alert from OPEN/ACKNOWLEDGED to RESOLVED state."""
        target = self._history.get(alert_id)
        if target is None:
            for a in self._active_alerts.values():
                if a.id == alert_id:
                    target = a
                    break

        if target is None:
            return None

        if target.status in (STATUS_OPEN, STATUS_ACKNOWLEDGED):
            target.status = STATUS_RESOLVED
            target.resolved_at = datetime.now(timezone.utc).isoformat()

            # Remove from active index
            for key, a in list(self._active_alerts.items()):
                if a.id == alert_id:
                    del self._active_alerts[key]
                    break

            self._publish_alert_event(target)
            return target
        else:
            raise ValueError(f"Cannot resolve alert in state '{target.status}'")

    def _publish_alert_event(self, alert: AlertRecord):
        """Publishes EventEnvelope with EventType.ALERT_CREATED for real-time subscribers."""
        broker = get_event_broker()
        broker.publish(
            EventEnvelope(
                event=EventType.ALERT_CREATED,
                incident_id=alert.incident_id,
                data=alert.to_dict(),
                persistence_status="in_memory",
            )
        )


# Global singleton instance & accessor
_global_alert_engine: Optional[IntelligentAlertEngine] = None


def get_alert_engine() -> IntelligentAlertEngine:
    global _global_alert_engine
    if _global_alert_engine is None:
        _global_alert_engine = IntelligentAlertEngine()
    return _global_alert_engine
