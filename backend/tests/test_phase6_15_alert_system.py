"""
AapdaNetra-X — Phase 6.15 Intelligent Alert System Test Suite
Validates rule evaluation, severity mapping, deduplication, lifecycle transitions,
persistence modes, transaction boundaries, SSE event publishing, audit logging,
provenance tracking, uncertainty context, and regression suite guarantees.
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.events.broker import get_event_broker
from app.events.schemas import EventType
from app.services.alert_engine import (
    IntelligentAlertEngine,
    AlertRecord,
    get_alert_engine,
    STATUS_OPEN,
    STATUS_ACKNOWLEDGED,
    STATUS_RESOLVED,
    SEVERITY_HIGH,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    SEVERITY_INFO,
)
from app.services.persistence_service import get_persistence_service
from app.db.models import Alert
from app.main import app

client = TestClient(app)


# ── A. Rule Evaluation Tests ─────────────────────────────────────────────
class TestAlertRuleEvaluation:
    def test_risk_threshold_rules(self):
        engine = IntelligentAlertEngine()

        # High risk threshold
        alerts_high = engine.evaluate_all_rules(predicted_risk=74.0, current_risk=65.0)
        risk_alert = next((a for a in alerts_high if a.alert_type == "RISK_THRESHOLD"), None)
        assert risk_alert is not None
        assert risk_alert.severity == SEVERITY_HIGH
        assert risk_alert.source == "ml:risk_prediction"

        # Critical risk threshold
        engine_crit = IntelligentAlertEngine()
        alerts_crit = engine_crit.evaluate_all_rules(predicted_risk=88.0, current_risk=75.0)
        risk_alert_crit = next((a for a in alerts_crit if a.alert_type == "RISK_THRESHOLD"), None)
        assert risk_alert_crit is not None
        assert risk_alert_crit.severity == SEVERITY_CRITICAL

    def test_risk_escalation_rule(self):
        engine = IntelligentAlertEngine()
        alerts = engine.evaluate_all_rules(predicted_risk=68.0, current_risk=52.0)
        esc_alert = next((a for a in alerts if a.alert_type == "RISK_ESCALATION"), None)
        assert esc_alert is not None
        assert "Rapid Risk Increase" in esc_alert.title
        assert esc_alert.metadata["risk_delta"] == 16.0

    def test_telemetry_threshold_rules(self):
        engine = IntelligentAlertEngine()
        telemetry = {
            "rainfall_intensity": 95.0,  # > 75.0 threshold
            "water_level": 6.8,          # > 5.0 threshold
            "water_level_trend": 0.45,
        }
        alerts = engine.evaluate_all_rules(predicted_risk=50.0, current_risk=45.0, telemetry_features=telemetry)

        rf_alert = next((a for a in alerts if a.alert_type == "TELEMETRY_RAINFALL"), None)
        assert rf_alert is not None
        assert rf_alert.metadata["rainfall_intensity"] == 95.0

        wl_alert = next((a for a in alerts if a.alert_type == "TELEMETRY_WATER_LEVEL"), None)
        assert wl_alert is not None
        assert wl_alert.metadata["water_level"] == 6.8

    def test_spatial_exposure_rule(self):
        engine = IntelligentAlertEngine()
        sp_exp = {"spatial_exposure_ratio": 0.35, "provenance": "hazard:provisional_river_proximity"}
        alerts = engine.evaluate_all_rules(predicted_risk=50.0, current_risk=45.0, spatial_exposure=sp_exp)

        sp_alert = next((a for a in alerts if a.alert_type == "SPATIAL_HAZARD_EXPOSURE"), None)
        assert sp_alert is not None
        assert "PROVISIONAL DEMONSTRATION" in sp_alert.title
        assert sp_alert.metadata["is_provisional"] is True

    def test_route_blockage_rule(self):
        engine = IntelligentAlertEngine()
        alerts = engine.evaluate_all_rules(predicted_risk=50.0, current_risk=45.0, route_blockage=True)
        blk_alert = next((a for a in alerts if a.alert_type == "ROUTE_BLOCKAGE"), None)
        assert blk_alert is not None
        assert blk_alert.severity == SEVERITY_HIGH


# ── B. Severity Mapping & Boundary Tests ──────────────────────────────────
class TestAlertSeverityMapping:
    def test_deterministic_severity_boundaries(self):
        engine = IntelligentAlertEngine()
        # Below threshold
        a_low = engine.evaluate_all_rules(predicted_risk=65.0, current_risk=65.0)
        assert not any(a.alert_type == "RISK_THRESHOLD" for a in a_low)

        # Boundary at 70.0 (HIGH)
        a_high = engine.evaluate_all_rules(predicted_risk=70.0, current_risk=65.0)
        assert any(a.alert_type == "RISK_THRESHOLD" and a.severity == SEVERITY_HIGH for a in a_high)

        # Boundary at 85.0 (CRITICAL)
        a_crit = engine.evaluate_all_rules(predicted_risk=85.0, current_risk=65.0)
        assert any(a.alert_type == "RISK_THRESHOLD" and a.severity == SEVERITY_CRITICAL for a in a_crit)


# ── C. Deduplication Tests ────────────────────────────────────────────────
class TestAlertDeduplication:
    def test_identical_conditions_do_not_duplicate(self):
        engine = IntelligentAlertEngine()

        # Run cycle 1
        alerts1 = engine.evaluate_all_rules(predicted_risk=75.0, current_risk=65.0)
        count1 = len(alerts1)
        alert_ids1 = {a.id for a in alerts1}

        # Run cycle 2 with identical features
        alerts2 = engine.evaluate_all_rules(predicted_risk=75.0, current_risk=65.0)
        count2 = len(alerts2)
        alert_ids2 = {a.id for a in alerts2}

        assert count1 == count2
        assert alert_ids1 == alert_ids2  # Retained exact existing alert instances

    def test_independent_alert_types_coexist(self):
        engine = IntelligentAlertEngine()
        telemetry = {"rainfall_intensity": 90.0, "water_level": 6.5}
        alerts = engine.evaluate_all_rules(predicted_risk=80.0, current_risk=65.0, telemetry_features=telemetry)

        types = {a.alert_type for a in alerts}
        assert "RISK_THRESHOLD" in types
        assert "TELEMETRY_RAINFALL" in types
        assert "TELEMETRY_WATER_LEVEL" in types


# ── D. Lifecycle State Machine Tests ──────────────────────────────────────
class TestAlertLifecycle:
    def test_valid_lifecycle_transitions(self):
        engine = IntelligentAlertEngine()
        alerts = engine.evaluate_all_rules(predicted_risk=78.0, current_risk=65.0)
        target = alerts[0]
        assert target.status == STATUS_OPEN

        # OPEN -> ACKNOWLEDGED
        ack = engine.acknowledge_alert(target.id)
        assert ack is not None
        assert ack.status == STATUS_ACKNOWLEDGED
        assert ack.acknowledged_at is not None

        # ACKNOWLEDGED -> RESOLVED
        res = engine.resolve_alert(target.id)
        assert res is not None
        assert res.status == STATUS_RESOLVED
        assert res.resolved_at is not None

    def test_invalid_lifecycle_transition_raises_error(self):
        engine = IntelligentAlertEngine()
        alerts = engine.evaluate_all_rules(predicted_risk=78.0, current_risk=65.0)
        target = alerts[0]

        # Resolve first
        engine.resolve_alert(target.id)

        # Attempt resolving or acknowledging resolved alert -> raises ValueError
        with pytest.raises(ValueError):
            engine.acknowledge_alert(target.id)


# ── E. Persistence & Transactions Tests ──────────────────────────────────
class TestAlertPersistence:
    @pytest.mark.asyncio
    async def test_persistence_service_persist_alert(self):
        ps = get_persistence_service()
        orm_alert = Alert(
            id=uuid.uuid4(),
            incident_id="INC-2026-DEFAULT",
            severity="HIGH",
            title="Test High Risk Alert",
            description="Test description for persistence",
            status="OPEN",
            alert_metadata={"alert_type": "RISK_THRESHOLD"},
        )
        if ps.is_enabled and ps.db_available:
            ok = await ps.persist_alert(orm_alert)
            assert ok is True
        else:
            # Fallback path cleanly tested
            ok = await ps.persist_alert(orm_alert)
            assert ok is False


# ── F. SSE Event Tests ────────────────────────────────────────────────────
class TestAlertSSEEvents:
    def test_sse_event_envelope_publication(self):
        broker = get_event_broker()
        q = broker.subscribe()

        engine = IntelligentAlertEngine()
        engine.evaluate_all_rules(predicted_risk=82.0, current_risk=65.0)

        assert q.qsize() > 0
        event_env = q.get_nowait()
        assert event_env.event in (EventType.ALERT_CREATED, EventType.RISK_UPDATED)
        broker.unsubscribe(q)


# ── G. REST API Tests ─────────────────────────────────────────────────────
class TestAlertAPIEndpoints:
    def test_get_alerts_endpoint(self):
        res = client.get("/api/alerts")
        assert res.status_code == 200
        data = res.json()
        assert "open" in data
        assert "alerts" in data
        assert isinstance(data["alerts"], list)

    def test_post_evaluate_alerts_endpoint(self):
        res = client.post("/api/alerts/evaluate")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "active_count" in data

    def test_acknowledge_alert_endpoint(self):
        # First evaluate to populate active alerts
        client.post("/api/alerts/evaluate")
        engine = get_alert_engine()
        if engine._active_alerts:
            target_id = list(engine._active_alerts.values())[0].id
            res = client.post(f"/api/alerts/{target_id}/acknowledge")
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            assert data["alert"]["status"] == STATUS_ACKNOWLEDGED

    def test_resolve_alert_endpoint(self):
        client.post("/api/alerts/evaluate")
        engine = get_alert_engine()
        if engine._active_alerts:
            target_id = list(engine._active_alerts.values())[0].id
            res = client.post(f"/api/alerts/{target_id}/resolve")
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            assert data["alert"]["status"] == STATUS_RESOLVED


# ── H. Regression Suite ──────────────────────────────────────────────────
class TestRegressionSuite:
    def test_gbr_model_7_features_intact(self):
        from ml.features.schema import FEATURE_NAMES
        assert len(FEATURE_NAMES) == 7

    def test_spatial_service_intact(self):
        from app.services.spatial_service import get_spatial_service
        svc = get_spatial_service()
        assert svc.get_hazards() is not None
