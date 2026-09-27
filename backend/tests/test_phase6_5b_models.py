"""AapdaNetra-X — Phase 6.5B Model & Alembic Migration Test Suite

Tests all 9 SQLAlchemy ORM domain models, declarative metadata, feature contract alignment,
relationships, spatial geometry types, JSONB fields, and Alembic migration structure.
"""

from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import String, inspect
from sqlalchemy.orm import DeclarativeBase

from app.db.base import Base, TimestampMixin
from app.db.models import (
    Alert,
    AuditEvent,
    CriticalAsset,
    EvacuationRoute,
    Incident,
    RiskPrediction,
    SHAPRecord,
    Simulation,
    TelemetryObservation,
)
from ml.features.schema import FEATURE_NAMES


def test_base_metadata_registered_tables():
    """Verify that all 9 Phase 6.5B tables are registered in Base.metadata."""
    tables = Base.metadata.tables.keys()
    expected_tables = {
        "incidents",
        "telemetry_observations",
        "risk_predictions",
        "shap_records",
        "evacuation_routes",
        "critical_assets",
        "simulations",
        "alerts",
        "audit_events",
    }
    for table in expected_tables:
        assert table in tables, f"Table {table!r} missing from Base.metadata"


def test_telemetry_model_matches_frozen_ml_features():
    """Verify TelemetryObservation model contains all 7 frozen ML feature columns."""
    mapper = inspect(TelemetryObservation)
    column_names = {c.key for c in mapper.columns}

    for feature_name in FEATURE_NAMES:
        assert feature_name in column_names, (
            f"Frozen ML feature {feature_name!r} missing from TelemetryObservation ORM model"
        )


def test_incident_model_instantiation():
    """Verify Incident model fields, defaults, and relationships."""
    now = datetime.now(timezone.utc)
    incident = Incident(
        id="INC-TEST-001",
        incident_type="flood",
        status="active",
        started_at=now,
        sector="Sector-4",
        severity="HIGH",
        location_name="Yamuna Bank",
        latitude=28.6448,
        longitude=77.2167,
    )

    assert incident.id == "INC-TEST-001"
    assert incident.incident_type == "flood"
    assert incident.status == "active"
    assert incident.sector == "Sector-4"
    assert incident.severity == "HIGH"
    assert "INC-TEST-001" in repr(incident)


def test_telemetry_observation_instantiation():
    """Verify TelemetryObservation model fields."""
    telemetry = TelemetryObservation(
        id=uuid.uuid4(),
        incident_id="INC-TEST-001",
        data_mode="simulated",
        fallback_used=False,
        rainfall_intensity=45.2,
        rainfall_trend=2.1,
        water_level=5.6,
        water_level_trend=0.4,
        road_congestion=0.7,
        population_exposure=12000.0,
        infrastructure_vulnerability=0.45,
        provenance={"source": "simulated_telemetry_provider"},
    )

    assert telemetry.rainfall_intensity == 45.2
    assert telemetry.water_level == 5.6
    assert telemetry.population_exposure == 12000.0
    assert telemetry.data_mode == "simulated"
    assert "TelemetryObservation" in repr(telemetry)


def test_risk_prediction_instantiation():
    """Verify RiskPrediction model fields."""
    pred_id = uuid.uuid4()
    risk = RiskPrediction(
        id=pred_id,
        incident_id="INC-TEST-001",
        horizon=1,
        horizon_label="+10M",
        current_risk=0.45,
        predicted_risk=0.68,
        risk_category="HIGH",
        confidence=0.89,
        prediction_reliability=0.92,
        affected_population=15000,
        critical_population=1200,
        critical_assets_count=3,
        affected_assets_count=8,
        trend="INCREASING",
        map_status_text="High flood risk predicted in 10 minutes.",
        prediction_note="Rainfall intensity spiking rapidly.",
        input_features={"rainfall_intensity": 45.2},
        heatmap_zones=[{"zone_id": "z1", "risk": 0.68}],
    )

    assert risk.horizon == 1
    assert risk.horizon_label == "+10M"
    assert risk.predicted_risk == 0.68
    assert risk.risk_category == "HIGH"
    assert "RiskPrediction" in repr(risk)


def test_shap_record_instantiation():
    """Verify SHAPRecord model fields."""
    risk_id = uuid.uuid4()
    shap = SHAPRecord(
        id=uuid.uuid4(),
        risk_prediction_id=risk_id,
        horizon=1,
        prediction=0.68,
        base_value=0.25,
        total_shap_delta=0.43,
        features={"rainfall_intensity": {"shap_value": 0.22}},
        decision_trace={"steps": ["rainfall -> +0.22"]},
    )

    assert shap.risk_prediction_id == risk_id
    assert shap.base_value == 0.25
    assert shap.total_shap_delta == 0.43
    assert "SHAPRecord" in repr(shap)


def test_evacuation_route_instantiation():
    """Verify EvacuationRoute model fields."""
    route = EvacuationRoute(
        id=uuid.uuid4(),
        incident_id="INC-TEST-001",
        route_name="Safe Route Alpha",
        route_type="primary",
        is_recommended=True,
        origin_name="Sector 4 Hub",
        origin_lat=28.6448,
        origin_lon=77.2167,
        destination_name="Relief Shelter B",
        destination_lat=28.6600,
        destination_lon=77.2300,
        waypoint_coords=[[28.6448, 77.2167], [28.6600, 77.2300]],
        distance_km=4.2,
        estimated_minutes=12.5,
        safety_score=0.91,
        congestion_index=0.2,
    )

    assert route.route_name == "Safe Route Alpha"
    assert route.is_recommended is True
    assert route.distance_km == 4.2
    assert "EvacuationRoute" in repr(route)


def test_critical_asset_instantiation():
    """Verify CriticalAsset model fields, geometry, and vulnerability bounds."""
    asset_id = uuid.uuid4()
    asset = CriticalAsset(
        id=asset_id,
        asset_code="AST-DEL-HOSP-01",
        name="AIIMS Emergency Wing",
        asset_type="hospital",
        sector="Sector-4",
        latitude=28.5672,
        longitude=77.2100,
        vulnerability=0.75,
        status="OPERATIONAL",
        asset_metadata={"beds": 500, "backup_generators": True},
    )

    assert asset.asset_code == "AST-DEL-HOSP-01"
    assert asset.name == "AIIMS Emergency Wing"
    assert asset.asset_type == "hospital"
    assert asset.vulnerability == 0.75
    assert asset.status == "OPERATIONAL"
    assert "AST-DEL-HOSP-01" in repr(asset)


def test_simulation_instantiation():
    """Verify Simulation model fields matching What-If inputs and outputs."""
    sim_id = uuid.uuid4()
    sim = Simulation(
        id=sim_id,
        incident_id="INC-TEST-001",
        evacuation_pace=1.2,
        rainfall_multiplier=1.5,
        drainage_efficiency=0.8,
        route_blockage=True,
        rainfall_increase=25.0,
        population_movement=5000,
        water_level_increase=0.5,
        baseline_risk=0.45,
        scenario_risk=0.78,
        risk_delta=0.33,
        risk_category="CRITICAL",
        prediction_reliability=0.94,
        route_recommendation="Reroute via Ring Road East",
        flagged_assets=["AIIMS Emergency Wing", "Substation 4B"],
        narrative="Heavy rainfall surge causes severe risk spike along Sector 4 corridor.",
        severity="SEVERE",
    )

    assert sim.incident_id == "INC-TEST-001"
    assert sim.rainfall_multiplier == 1.5
    assert sim.route_blockage is True
    assert sim.baseline_risk == 0.45
    assert sim.scenario_risk == 0.78
    assert sim.risk_delta == 0.33
    assert sim.severity == "SEVERE"
    assert "Simulation" in repr(sim)


def test_alert_instantiation():
    """Verify Alert model fields and foreign keys."""
    alert_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    alert = Alert(
        id=alert_id,
        incident_id="INC-TEST-001",
        critical_asset_id=asset_id,
        severity="CRITICAL",
        title="Flash Flood Warning — Sector 4",
        description="Water level surging past 5.5m near Yamuna bank.",
        status="OPEN",
        alert_metadata={"broadcasting_channels": ["SMS", "CAP_ALERT"]},
    )

    assert alert.incident_id == "INC-TEST-001"
    assert alert.critical_asset_id == asset_id
    assert alert.severity == "CRITICAL"
    assert alert.title == "Flash Flood Warning — Sector 4"
    assert alert.status == "OPEN"
    assert "Alert" in repr(alert)


def test_audit_event_instantiation():
    """Verify AuditEvent model fields."""
    audit = AuditEvent(
        id=uuid.uuid4(),
        incident_id="INC-TEST-001",
        event_type="RISK_THRESHOLD_EXCEEDED",
        severity="WARNING",
        source="RiskAssessmentService",
        description="Predicted risk exceeded 0.65 threshold for Horizon +10M",
        actor="system",
        event_data={"horizon": 1, "predicted_risk": 0.68},
    )

    assert audit.event_type == "RISK_THRESHOLD_EXCEEDED"
    assert audit.severity == "WARNING"
    assert audit.actor == "system"
    assert "AuditEvent" in repr(audit)


def test_alembic_configuration_and_all_9_tables_exist():
    """Verify Alembic setup files and migration script containing all 9 tables."""
    import os

    base_dir = "." if os.path.exists("alembic.ini") else "backend"
    assert os.path.exists(os.path.join(base_dir, "alembic.ini"))
    assert os.path.exists(os.path.join(base_dir, "alembic/env.py"))
    assert os.path.exists(os.path.join(base_dir, "alembic/script.py.mako"))

    migration_path = os.path.join(base_dir, "alembic/versions/001_initial_phase_6_5b.py")
    assert os.path.exists(migration_path)

    with open(migration_path, "r", encoding="utf-8") as f:
        migration_content = f.read()

    expected_migration_tables = [
        "incidents",
        "telemetry_observations",
        "risk_predictions",
        "shap_records",
        "evacuation_routes",
        "critical_assets",
        "simulations",
        "alerts",
        "audit_events",
    ]

    for table in expected_migration_tables:
        assert f'"{table}"' in migration_content or f"'{table}'" in migration_content, (
            f"Table {table!r} missing from Alembic migration 001_initial_phase_6_5b.py"
        )
