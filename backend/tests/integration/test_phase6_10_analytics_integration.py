"""Phase 6.10 — Real PostgreSQL/PostGIS Integration Tests for Analytics

Executes real SQL aggregation queries (COUNT, AVG, MIN, MAX, GROUP BY) against dedicated aapdanetra_test database.
"""

from datetime import datetime, timezone, timedelta
import pytest
import uuid
from sqlalchemy import text

from app.db.repositories.analytics import AnalyticsRepository
from app.db.models import (
    Alert,
    AuditEvent,
    EvacuationRoute,
    Incident,
    RiskPrediction,
    Simulation,
    TelemetryObservation,
)


@pytest.mark.postgis
@pytest.mark.anyio
async def test_analytics_repository_empty_database(test_db_session):
    """Verify aggregation queries execute cleanly without SQL errors on empty tables."""
    repo = AnalyticsRepository(test_db_session)

    overview = await repo.get_overview()
    assert overview["total_incidents"] == 0
    assert overview["total_risk_predictions"] == 0
    assert overview["avg_system_risk"] is None
    assert overview["max_system_risk"] is None

    risk_stats = await repo.get_risk_analytics()
    assert risk_stats["total_predictions"] == 0
    assert risk_stats["min_risk"] is None
    assert risk_stats["max_risk"] is None
    assert risk_stats["avg_risk"] is None
    assert risk_stats["risk_trend"] == "INSUFFICIENT_DATA"
    assert risk_stats["risk_category_distribution"] == {}

    alert_stats = await repo.get_alert_analytics()
    assert alert_stats["total_alerts"] == 0
    assert alert_stats["severity_distribution"] == {}

    route_stats = await repo.get_route_analytics()
    assert route_stats["total_routes"] == 0
    assert route_stats["avg_safety_score"] is None

    sim_stats = await repo.get_simulation_analytics()
    assert sim_stats["total_simulations"] == 0
    assert sim_stats["avg_risk_delta"] is None

    telem_stats = await repo.get_telemetry_analytics()
    assert telem_stats["total_observations"] == 0
    assert telem_stats["rainfall_avg"] is None


@pytest.mark.postgis
@pytest.mark.anyio
async def test_analytics_repository_real_aggregations(test_db_session):
    """Verify COUNT, AVG, MIN, MAX, GROUP BY calculations against real PostgreSQL tables."""
    t0 = datetime.now(timezone.utc) - timedelta(hours=2)
    t1 = datetime.now(timezone.utc) - timedelta(hours=1)
    t2 = datetime.now(timezone.utc)

    # 1. Insert Incident
    inc = Incident(
        id="INC-2026-POSTGIS",
        incident_type="FLOOD",
        status="ACTIVE",
        started_at=t0,
        sector="NORTH",
        severity="CRITICAL",
        location_name="Rishikesh",
        latitude=30.0869,
        longitude=78.2676,
        geom="SRID=4326;POINT(78.2676 30.0869)",
    )
    test_db_session.add(inc)

    # 2. Insert Telemetry Observations
    telem1 = TelemetryObservation(
        id=uuid.uuid4(),
        incident_id="INC-2026-POSTGIS",
        data_mode="simulated",
        fallback_used=False,
        rainfall_intensity=50.0,
        rainfall_trend=1.2,
        water_level=2.5,
        water_level_trend=0.5,
        road_congestion=0.4,
        population_exposure=1500.0,
        infrastructure_vulnerability=0.6,
        provenance={"source": "test_sensor_1"},
        observed_at=t0,
    )
    telem2 = TelemetryObservation(
        id=uuid.uuid4(),
        incident_id="INC-2026-POSTGIS",
        data_mode="hybrid",
        fallback_used=True,
        rainfall_intensity=100.0,
        rainfall_trend=2.0,
        water_level=4.5,
        water_level_trend=1.0,
        road_congestion=0.8,
        population_exposure=2500.0,
        infrastructure_vulnerability=0.8,
        provenance={"source": "test_sensor_2"},
        observed_at=t1,
    )
    test_db_session.add_all([telem1, telem2])

    # 3. Insert Risk Predictions
    risk1 = RiskPrediction(
        id=uuid.uuid4(),
        incident_id="INC-2026-POSTGIS",
        horizon=0,
        horizon_label="NOW",
        current_risk=0.40,
        predicted_risk=0.40,
        risk_category="MODERATE",
        confidence=0.90,
        prediction_reliability=0.95,
        affected_population=1500,
        critical_population=200,
        critical_assets_count=5,
        affected_assets_count=10,
        trend="STABLE",
        map_status_text="Moderate risk",
        prediction_note="Baseline",
        input_features={},
        heatmap_zones=[],
        created_at=t0,
    )
    risk2 = RiskPrediction(
        id=uuid.uuid4(),
        incident_id="INC-2026-POSTGIS",
        horizon=1,
        horizon_label="+10M",
        current_risk=0.40,
        predicted_risk=0.80,
        risk_category="HIGH",
        confidence=0.88,
        prediction_reliability=0.90,
        affected_population=2500,
        critical_population=500,
        critical_assets_count=8,
        affected_assets_count=18,
        trend="RISING",
        map_status_text="High risk escalation",
        prediction_note="Escalating",
        input_features={},
        heatmap_zones=[],
        created_at=t2,
    )
    test_db_session.add_all([risk1, risk2])

    # 4. Insert Alerts
    alert1 = Alert(
        id=uuid.uuid4(),
        incident_id="INC-2026-POSTGIS",
        severity="WARNING",
        title="Flash Flood Warning",
        description="Water levels rising rapidly",
        status="OPEN",
        created_at=t1,
    )
    alert2 = Alert(
        id=uuid.uuid4(),
        incident_id="INC-2026-POSTGIS",
        severity="CRITICAL",
        title="Evacuation Order",
        description="Immediate evacuation required",
        status="OPEN",
        created_at=t2,
    )
    test_db_session.add_all([alert1, alert2])

    # 5. Insert Evacuation Route
    route1 = EvacuationRoute(
        id=uuid.uuid4(),
        incident_id="INC-2026-POSTGIS",
        route_name="Primary Route A",
        route_type="primary",
        is_recommended=True,
        origin_name="Rishikesh Center",
        origin_lat=30.0869,
        origin_lon=78.2676,
        destination_name="Safe Camp North",
        destination_lat=30.1200,
        destination_lon=78.3000,
        waypoint_coords=[],
        distance_km=8.5,
        estimated_minutes=15.0,
        safety_score=0.85,
        congestion_index=0.2,
        created_at=t1,
    )
    test_db_session.add(route1)

    # 6. Insert Simulation
    sim1 = Simulation(
        id=uuid.uuid4(),
        incident_id="INC-2026-POSTGIS",
        evacuation_pace=1.2,
        rainfall_multiplier=1.5,
        drainage_efficiency=0.8,
        route_blockage=False,
        baseline_risk=0.40,
        scenario_risk=0.75,
        risk_delta=0.35,
        risk_category="HIGH",
        prediction_reliability=0.92,
        route_recommendation="Use Route A",
        flagged_assets=[],
        narrative="Heavy rain scenario",
        severity="HIGH",
        created_at=t1,
    )
    test_db_session.add(sim1)

    await test_db_session.commit()

    repo = AnalyticsRepository(test_db_session)

    # Overview assertion
    overview = await repo.get_overview()
    assert overview["total_incidents"] == 1
    assert overview["active_incidents"] == 1
    assert overview["total_telemetry_observations"] == 2
    assert overview["total_risk_predictions"] == 2
    assert overview["total_alerts"] == 2
    assert overview["total_evacuation_routes"] == 1
    assert overview["total_simulations"] == 1
    assert overview["avg_system_risk"] == 0.60
    assert overview["max_system_risk"] == 0.80

    # Incident-specific analytics assertion
    inc_analytics = await repo.get_incident_analytics("INC-2026-POSTGIS")
    assert inc_analytics is not None
    assert inc_analytics["incident_id"] == "INC-2026-POSTGIS"
    assert inc_analytics["telemetry_count"] == 2
    assert inc_analytics["risk_prediction_count"] == 2
    assert inc_analytics["route_count"] == 1
    assert inc_analytics["alert_count"] == 2
    assert inc_analytics["simulation_count"] == 1
    assert inc_analytics["latest_risk"] == 0.80
    assert inc_analytics["max_observed_risk"] == 0.80
    assert inc_analytics["avg_observed_risk"] == 0.60

    # Risk analytics assertion
    risk_analytics = await repo.get_risk_analytics(incident_id="INC-2026-POSTGIS")
    assert risk_analytics["total_predictions"] == 2
    assert risk_analytics["min_risk"] == 0.40
    assert risk_analytics["max_risk"] == 0.80
    assert risk_analytics["avg_risk"] == 0.60
    assert risk_analytics["latest_risk"] == 0.80
    assert risk_analytics["earliest_risk"] == 0.40
    assert risk_analytics["risk_trend"] == "INCREASING"
    assert risk_analytics["risk_category_distribution"] == {"MODERATE": 1, "HIGH": 1}

    # Telemetry analytics assertion
    telem_analytics = await repo.get_telemetry_analytics(incident_id="INC-2026-POSTGIS")
    assert telem_analytics["total_observations"] == 2
    assert telem_analytics["rainfall_min"] == 50.0
    assert telem_analytics["rainfall_max"] == 100.0
    assert telem_analytics["rainfall_avg"] == 75.0
    assert telem_analytics["water_level_avg"] == 3.5
    assert telem_analytics["data_mode_distribution"] == {"simulated": 1, "hybrid": 1}
    assert telem_analytics["fallback_used_count"] == 1

    # Time range filtering assertion
    t_filter_risk = await repo.get_risk_analytics(from_time=t2)
    assert t_filter_risk["total_predictions"] == 1
    assert t_filter_risk["min_risk"] == 0.80
    assert t_filter_risk["latest_risk"] == 0.80
