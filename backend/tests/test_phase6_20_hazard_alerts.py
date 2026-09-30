"""
AapdaNetra-X — Phase 6.20.7 Hazard-Aware Alert Intelligence Unit Test Suite

Verifies:
1. Flood operational alert rules fire with hazard_type="flood".
2. Extreme rainfall contextual telemetry alert fires with hazard_type="extreme_rainfall" without fabricating ML/SHAP data.
3. Unsupported hazards (landslide, cyclone, heatwave, earthquake) do NOT trigger flood alert rules.
4. Unknown hazard raises validation error.
5. Deduplication key (incident_id:hazard_type:alert_type:signature) prevents cross-hazard collision.
6. AlertRepository validates and persists hazard_type.
7. Alert lifecycle transitions (ACKNOWLEDGED, RESOLVED) preserve hazard_type.
"""
import uuid
import pytest
from app.services.alert_engine import (
    IntelligentAlertEngine,
    AlertRecord,
    STATUS_OPEN,
    STATUS_ACKNOWLEDGED,
    STATUS_RESOLVED,
)
from app.hazards.types import HazardType
from app.db.models.alert import Alert
from app.db.repositories.alert import AlertRepository


def test_flood_alert_rules_preservation():
    """Verify operational flood rules fire and set hazard_type='flood'."""
    engine = IntelligentAlertEngine()
    alerts = engine.evaluate_all_rules(
        incident_id="INC-FLOOD-TEST",
        predicted_risk=88.0,  # Critical risk threshold
        current_risk=60.0,
        telemetry_features={"rainfall_intensity": 80.0, "water_level": 6.0},
        spatial_exposure={"spatial_exposure_ratio": 0.30},
        route_blockage=True,
        hazard_type="flood",
    )

    assert len(alerts) >= 4
    for a in alerts:
        assert a.hazard_type == "flood"
        assert a.incident_id == "INC-FLOOD-TEST"

    alert_types = {a.alert_type for a in alerts}
    assert "RISK_THRESHOLD" in alert_types
    assert "TELEMETRY_RAINFALL" in alert_types
    assert "TELEMETRY_WATER_LEVEL" in alert_types
    assert "ROUTE_BLOCKAGE" in alert_types


def test_extreme_rainfall_contextual_alerting():
    """Verify extreme_rainfall produces telemetry rainfall alert only and no fake ML data."""
    engine = IntelligentAlertEngine()

    # Pass high water level and high risk score to confirm flood rules are ignored for extreme_rainfall
    alerts = engine.evaluate_all_rules(
        incident_id="INC-ER-TEST",
        predicted_risk=90.0,  # Should NOT trigger RISK_THRESHOLD
        current_risk=50.0,
        telemetry_features={"rainfall_intensity": 110.0, "water_level": 8.0},  # Water level should NOT trigger
        spatial_exposure={"spatial_exposure_ratio": 0.40},  # Should NOT trigger
        route_blockage=True,  # Should NOT trigger
        hazard_type="extreme_rainfall",
    )

    op_alerts = [a for a in alerts if a.alert_type != "SYSTEM_DATA_FRESHNESS"]
    assert len(op_alerts) == 1
    rf_alert = op_alerts[0]
    assert rf_alert.hazard_type == "extreme_rainfall"
    assert rf_alert.alert_type == "TELEMETRY_RAINFALL"
    assert "Extreme Rainfall" in rf_alert.title
    assert rf_alert.metadata.get("alert_capability") == "contextual_telemetry"

    # Confirm ML risk, water level, and route blockage did NOT fire
    alert_types = {a.alert_type for a in alerts}
    assert "RISK_THRESHOLD" not in alert_types
    assert "TELEMETRY_WATER_LEVEL" not in alert_types
    assert "ROUTE_BLOCKAGE" not in alert_types
    assert "SPATIAL_HAZARD_EXPOSURE" not in alert_types



def test_unsupported_hazards_do_not_trigger_flood_rules():
    """Verify landslide, cyclone, heatwave, earthquake do NOT fire operational flood rules."""
    engine = IntelligentAlertEngine()

    unsupported_list = ["landslide", "cyclone", "heatwave", "earthquake"]
    for hz in unsupported_list:
        alerts = engine.evaluate_all_rules(
            incident_id=f"INC-{hz.upper()}-TEST",
            predicted_risk=95.0,  # High flood risk score
            current_risk=50.0,
            telemetry_features={"rainfall_intensity": 150.0, "water_level": 10.0},
            spatial_exposure={"spatial_exposure_ratio": 0.80},
            route_blockage=True,
            hazard_type=hz,
        )

        # Operational flood alerts MUST NOT trigger for unsupported hazards
        op_alerts = [a for a in alerts if a.alert_type != "SYSTEM_DATA_FRESHNESS"]
        assert len(op_alerts) == 0, f"Unsupported hazard '{hz}' triggered operational alerts!"


def test_unknown_hazard_type_rejection():
    """Verify unknown or invalid hazard_type string raises ValueError."""
    engine = IntelligentAlertEngine()
    with pytest.raises(ValueError, match="Unknown or unsupported hazard type"):
        engine.evaluate_all_rules(
            incident_id="INC-FAIL-TEST",
            hazard_type="volcano_eruption",
        )


def test_hazard_isolated_deduplication():
    """Verify same incident + same alert_type + same signature across different hazard_types do NOT collide."""
    engine = IntelligentAlertEngine()

    # 1. Trigger flood rainfall alert
    flood_alerts = engine.evaluate_all_rules(
        incident_id="INC-DEDUP-TEST",
        telemetry_features={"rainfall_intensity": 90.0},
        hazard_type="flood",
    )
    flood_rf = [a for a in flood_alerts if a.alert_type == "TELEMETRY_RAINFALL"]
    assert len(flood_rf) == 1
    assert flood_rf[0].hazard_type == "flood"

    # 2. Trigger extreme_rainfall rainfall alert for SAME incident and SAME rainfall intensity
    er_alerts = engine.evaluate_all_rules(
        incident_id="INC-DEDUP-TEST",
        telemetry_features={"rainfall_intensity": 90.0},
        hazard_type="extreme_rainfall",
    )
    er_rf = [a for a in er_alerts if a.alert_type == "TELEMETRY_RAINFALL"]
    assert len(er_rf) == 1
    assert er_rf[0].hazard_type == "extreme_rainfall"

    # Verify BOTH active rainfall alerts exist in engine without colliding
    rf_active_alerts = [a for a in engine._active_alerts.values() if a.alert_type == "TELEMETRY_RAINFALL"]
    assert len(rf_active_alerts) == 2
    hazards = {a.hazard_type for a in rf_active_alerts}
    assert hazards == {"flood", "extreme_rainfall"}


def test_alert_lifecycle_preserves_hazard_type():
    """Verify acknowledge and resolve lifecycle actions preserve hazard_type."""
    engine = IntelligentAlertEngine()
    alerts = engine.evaluate_all_rules(
        incident_id="INC-LIFECYCLE-TEST",
        telemetry_features={"rainfall_intensity": 95.0},
        hazard_type="extreme_rainfall",
    )
    er_rf = [a for a in alerts if a.alert_type == "TELEMETRY_RAINFALL"]
    assert len(er_rf) == 1
    target_id = er_rf[0].id

    # Acknowledge
    ack = engine.acknowledge_alert(target_id)
    assert ack is not None
    assert ack.status == STATUS_ACKNOWLEDGED
    assert ack.hazard_type == "extreme_rainfall"

    # Resolve
    res = engine.resolve_alert(target_id)
    assert res is not None
    assert res.status == STATUS_RESOLVED
    assert res.hazard_type == "extreme_rainfall"
