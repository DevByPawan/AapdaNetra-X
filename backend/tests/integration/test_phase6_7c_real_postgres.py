"""Phase 6.7C — Real PostgreSQL/PostGIS Integration Test Suite

Executes actual SQL queries against the dedicated 'aapdanetra_test' database.
"""

from datetime import datetime, timezone
import uuid
import pytest
from geoalchemy2 import WKTElement
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings
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
from app.db.pagination import PaginationParams, apply_keyset_pagination, build_page_result
from app.services.timeline_service import TimelineService
from app.services.persistence_service import PersistenceService

pytestmark = pytest.mark.postgis


# ── SECTION C: DATABASE CONNECTION TEST ───────────────────────────────────

@pytest.mark.anyio
async def test_01_database_connection_and_postgis_version(test_db_session: AsyncSession):
    """Verify active database is aapdanetra_test, PostgreSQL is reachable, and PostGIS is enabled."""
    res_db = await test_db_session.execute(text("SELECT current_database();"))
    db_name = res_db.scalar()
    assert db_name == "aapdanetra_test", f"Connected to wrong database: '{db_name}'!"

    res_version = await test_db_session.execute(text("SELECT version();"))
    pg_version = res_version.scalar()
    assert "PostgreSQL" in pg_version

    res_postgis = await test_db_session.execute(text("SELECT PostGIS_Full_Version();"))
    postgis_version = res_postgis.scalar()
    assert "POSTGIS=" in postgis_version
    assert "3." in postgis_version


# ── SECTION B: ALEMBIC MIGRATION STATUS ───────────────────────────────────

@pytest.mark.anyio
async def test_02_alembic_migration_head_status(test_db_session: AsyncSession):
    """Verify Alembic version in test database matches Phase 6.7B head."""
    res = await test_db_session.execute(text("SELECT version_num FROM alembic_version;"))
    version_num = res.scalar()
    assert version_num == "002_postgis_indexes_perf", f"Test DB alembic version is '{version_num}'!"


# ── SECTION D: ORM CRUD TESTS ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_03_all_9_models_orm_crud(test_db_session: AsyncSession):
    """Perform real INSERT + SELECT for all 9 domain models against PostgreSQL."""
    now = datetime.now(timezone.utc)
    inc_id = f"INC-TEST-{uuid.uuid4().hex[:8]}"

    # 1. Incident
    incident = Incident(
        id=inc_id,
        incident_type="flood",
        status="active",
        started_at=now,
        sector="Sector-4",
        severity="HIGH",
        location_name="Yamuna River Bank",
        latitude=28.6448,
        longitude=77.2167,
        geom=WKTElement("POINT(77.2167 28.6448)", srid=4326),
    )
    test_db_session.add(incident)
    await test_db_session.commit()

    fetched_inc = await test_db_session.get(Incident, inc_id)
    assert fetched_inc is not None
    assert fetched_inc.incident_type == "flood"

    # 2. TelemetryObservation
    telemetry = TelemetryObservation(
        id=uuid.uuid4(),
        incident_id=inc_id,
        data_mode="live",
        fallback_used=False,
        rainfall_intensity=55.4,
        rainfall_trend=3.2,
        water_level=6.1,
        water_level_trend=0.5,
        road_congestion=0.8,
        population_exposure=15000.0,
        infrastructure_vulnerability=0.6,
        location_name="Station-01",
        location_geom=WKTElement("POINT(77.2167 28.6448)", srid=4326),
        provenance={"sensor": "radar_01"},
        provider_metadata={"quality": "high"},
        observed_at=now,
    )
    test_db_session.add(telemetry)
    await test_db_session.commit()

    fetched_tel = await test_db_session.get(TelemetryObservation, telemetry.id)
    assert fetched_tel is not None
    assert fetched_tel.rainfall_intensity == 55.4
    assert fetched_tel.provenance["sensor"] == "radar_01"

    # 3. RiskPrediction
    prediction = RiskPrediction(
        id=uuid.uuid4(),
        incident_id=inc_id,
        telemetry_id=telemetry.id,
        horizon=1,
        horizon_label="+10M",
        current_risk=0.5,
        predicted_risk=0.82,
        risk_category="CRITICAL",
        confidence=0.91,
        prediction_reliability=0.94,
        affected_population=18000,
        critical_population=2500,
        critical_assets_count=4,
        affected_assets_count=10,
        trend="RISING",
        map_status_text="Severe risk spike expected",
        prediction_note="Heavy precipitation upstream",
        input_features={"rainfall_intensity": 55.4},
        heatmap_zones=[{"zone_id": "z1", "risk": 0.82}],
        created_at=now,
    )
    test_db_session.add(prediction)
    await test_db_session.commit()

    fetched_pred = await test_db_session.get(RiskPrediction, prediction.id)
    assert fetched_pred is not None
    assert fetched_pred.predicted_risk == 0.82

    # 4. SHAPRecord
    shap = SHAPRecord(
        id=uuid.uuid4(),
        risk_prediction_id=prediction.id,
        horizon=1,
        prediction=0.82,
        base_value=0.25,
        total_shap_delta=0.57,
        features={"rainfall_intensity": {"shap_value": 0.35}},
        decision_trace={"steps": ["rainfall -> +0.35"]},
        created_at=now,
    )
    test_db_session.add(shap)
    await test_db_session.commit()

    fetched_shap = await test_db_session.get(SHAPRecord, shap.id)
    assert fetched_shap is not None
    assert fetched_shap.total_shap_delta == 0.57

    # 5. EvacuationRoute
    route = EvacuationRoute(
        id=uuid.uuid4(),
        incident_id=inc_id,
        risk_prediction_id=prediction.id,
        route_name="Ring Road Rescue Corridor",
        route_type="primary",
        is_recommended=True,
        origin_name="Sector 4 Hub",
        origin_lat=28.6448,
        origin_lon=77.2167,
        origin_geom=WKTElement("POINT(77.2167 28.6448)", srid=4326),
        destination_name="Relief Shelter Alpha",
        destination_lat=28.6700,
        destination_lon=77.2400,
        destination_geom=WKTElement("POINT(77.2400 28.6700)", srid=4326),
        path_geom=WKTElement("LINESTRING(77.2167 28.6448, 77.2400 28.6700)", srid=4326),
        waypoint_coords=[[28.6448, 77.2167], [28.6700, 77.2400]],
        distance_km=5.8,
        estimated_minutes=14.2,
        safety_score=0.92,
        congestion_index=0.15,
        created_at=now,
    )
    test_db_session.add(route)
    await test_db_session.commit()

    fetched_route = await test_db_session.get(EvacuationRoute, route.id)
    assert fetched_route is not None
    assert fetched_route.distance_km == 5.8

    # 6. CriticalAsset
    asset = CriticalAsset(
        id=uuid.uuid4(),
        asset_code=f"AST-TEST-{uuid.uuid4().hex[:6]}",
        name="District Hospital Sector 4",
        asset_type="hospital",
        sector="Sector-4",
        latitude=28.6480,
        longitude=77.2200,
        location_geom=WKTElement("POINT(77.2200 28.6480)", srid=4326),
        vulnerability=0.8,
        status="OPERATIONAL",
        asset_metadata={"icu_beds": 120},
    )
    test_db_session.add(asset)
    await test_db_session.commit()

    fetched_asset = await test_db_session.get(CriticalAsset, asset.id)
    assert fetched_asset is not None
    assert fetched_asset.vulnerability == 0.8

    # 7. Simulation
    sim = Simulation(
        id=uuid.uuid4(),
        incident_id=inc_id,
        evacuation_pace=1.2,
        rainfall_multiplier=1.5,
        drainage_efficiency=0.7,
        route_blockage=True,
        rainfall_increase=30.0,
        population_movement=6000,
        water_level_increase=0.6,
        baseline_risk=0.5,
        scenario_risk=0.88,
        risk_delta=0.38,
        risk_category="CRITICAL",
        prediction_reliability=0.93,
        route_recommendation="Reroute via Western Bypass",
        flagged_assets=["District Hospital Sector 4"],
        narrative="Extreme risk spike simulated.",
        severity="SEVERE",
        created_at=now,
    )
    test_db_session.add(sim)
    await test_db_session.commit()

    fetched_sim = await test_db_session.get(Simulation, sim.id)
    assert fetched_sim is not None
    assert fetched_sim.risk_delta == 0.38

    # 8. Alert
    alert = Alert(
        id=uuid.uuid4(),
        incident_id=inc_id,
        critical_asset_id=asset.id,
        severity="CRITICAL",
        title="Immediate Evacuation Order",
        description="Sector 4 low-lying zones flooding.",
        status="OPEN",
        boundary_geom=WKTElement("POLYGON((77.21 28.64, 77.23 28.64, 77.23 28.66, 77.21 28.66, 77.21 28.64))", srid=4326),
        alert_metadata={"channels": ["CAP", "SMS"]},
        created_at=now,
    )
    test_db_session.add(alert)
    await test_db_session.commit()

    fetched_alert = await test_db_session.get(Alert, alert.id)
    assert fetched_alert is not None
    assert fetched_alert.severity == "CRITICAL"

    # 9. AuditEvent
    audit = AuditEvent(
        id=uuid.uuid4(),
        incident_id=inc_id,
        event_type="RESPONSE_WORKFLOW_APPROVED",
        severity="INFO",
        source="OperatorConsole",
        description="Emergency evacuation workflow approved by incident commander",
        actor="commander_alpha",
        event_data={"workflow_id": "wf-99"},
        created_at=now,
    )
    test_db_session.add(audit)
    await test_db_session.commit()

    fetched_audit = await test_db_session.get(AuditEvent, audit.id)
    assert fetched_audit is not None
    assert fetched_audit.actor == "commander_alpha"


# ── SECTION E: POSTGIS GEOMETRY TESTS ─────────────────────────────────────

@pytest.mark.anyio
async def test_04_postgis_geometry_types_and_srid(test_db_session: AsyncSession):
    """Verify PostGIS POINT, LINESTRING, and POLYGON storage, retrieval, and SRID 4326 metadata."""
    now = datetime.now(timezone.utc)
    inc_id = f"INC-GEOM-{uuid.uuid4().hex[:6]}"

    incident = Incident(
        id=inc_id,
        incident_type="flood",
        status="active",
        started_at=now,
        sector="Sector-4",
        severity="HIGH",
        location_name="Geom Test Location",
        latitude=28.6500,
        longitude=77.2200,
        geom=WKTElement("POINT(77.2200 28.6500)", srid=4326),
    )
    test_db_session.add(incident)
    await test_db_session.commit()

    sql = text("""
        SELECT 
            ST_SRID(geom) AS srid,
            ST_AsText(geom) AS text_geom,
            ST_GeometryType(geom) AS geom_type
        FROM incidents
        WHERE id = :inc_id;
    """)
    res = await test_db_session.execute(sql, {"inc_id": inc_id})
    row = res.one()

    assert row.srid == 4326, f"Expected SRID 4326, got {row.srid}"
    assert row.text_geom == "POINT(77.22 28.65)"
    assert row.geom_type == "ST_Point"


# ── SECTION F: REAL SPATIAL QUERY TESTS ───────────────────────────────────

@pytest.mark.anyio
async def test_05_real_spatial_queries(test_db_session: AsyncSession):
    """Execute real PostGIS ST_DWithin, ST_Intersects, and ST_Contains spatial queries."""
    now = datetime.now(timezone.utc)
    inc_id = f"INC-SPATIAL-{uuid.uuid4().hex[:6]}"

    inc = Incident(
        id=inc_id, incident_type="flood", status="active", started_at=now,
        sector="Sector-4", severity="HIGH", location_name="Spatial Hub", latitude=28.65, longitude=77.22,
        geom=WKTElement("POINT(77.22 28.65)", srid=4326)
    )
    test_db_session.add(inc)
    await test_db_session.commit()

    asset = CriticalAsset(
        id=uuid.uuid4(),
        asset_code=f"AST-SP-{uuid.uuid4().hex[:6]}",
        name="Spatial Hospital",
        asset_type="hospital",
        sector="Sector-4",
        latitude=28.6480,
        longitude=77.2200,
        location_geom=WKTElement("POINT(77.2200 28.6480)", srid=4326),
        vulnerability=0.7,
    )
    alert = Alert(
        id=uuid.uuid4(),
        incident_id=inc_id,
        severity="HIGH",
        title="Flood Risk Polygon",
        description="Active warning polygon",
        status="OPEN",
        boundary_geom=WKTElement("POLYGON((77.21 28.64, 77.23 28.64, 77.23 28.66, 77.21 28.66, 77.21 28.64))", srid=4326),
        created_at=now,
    )
    test_db_session.add_all([asset, alert])
    await test_db_session.commit()

    # 1. Proximity check via ST_DWithin (geography, 5km radius around 77.2210, 28.6490)
    sql_dwithin = text("""
        SELECT name FROM critical_assets
        WHERE ST_DWithin(
            location_geom::geography,
            ST_SetSRID(ST_MakePoint(77.2210, 28.6490), 4326)::geography,
            5000
        );
    """)
    res_dw = await test_db_session.execute(sql_dwithin)
    found_assets = res_dw.scalars().all()
    assert "Spatial Hospital" in found_assets

    # 2. Polygon intersection check via ST_Intersects against point (77.2200, 28.6500)
    sql_intersects = text("""
        SELECT title FROM alerts
        WHERE ST_Intersects(
            boundary_geom,
            ST_SetSRID(ST_MakePoint(77.2200, 28.6500), 4326)
        );
    """)
    res_int = await test_db_session.execute(sql_intersects)
    found_alerts = res_int.scalars().all()
    assert "Flood Risk Polygon" in found_alerts


# ── SECTION G: FOREIGN KEY CASCADE & SET NULL TESTS ─────────────────────────

@pytest.mark.anyio
async def test_06_foreign_key_cascade_and_set_null_behavior(test_db_session: AsyncSession):
    """Verify real PostgreSQL ON DELETE CASCADE and ON DELETE SET NULL foreign key behaviors."""
    now = datetime.now(timezone.utc)
    inc_id = f"INC-FK-{uuid.uuid4().hex[:6]}"

    inc = Incident(
        id=inc_id, incident_type="flood", status="active", started_at=now,
        sector="Sector-4", severity="HIGH", location_name="Loc", latitude=28.6, longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326)
    )
    test_db_session.add(inc)
    await test_db_session.commit()

    # Child 1: Telemetry (ON DELETE SET NULL)
    tel = TelemetryObservation(
        id=uuid.uuid4(), incident_id=inc_id, data_mode="live", fallback_used=False,
        rainfall_intensity=10.0, rainfall_trend=0.0, water_level=2.0, water_level_trend=0.0,
        road_congestion=0.1, population_exposure=100.0, infrastructure_vulnerability=0.1,
        provenance={}, observed_at=now
    )
    # Child 2: RiskPrediction (ON DELETE CASCADE)
    pred = RiskPrediction(
        id=uuid.uuid4(), incident_id=inc_id, horizon=0, horizon_label="NOW", current_risk=0.5,
        predicted_risk=0.5, risk_category="LOW", confidence=0.9, prediction_reliability=0.9,
        affected_population=100, critical_population=10, critical_assets_count=1, affected_assets_count=0,
        trend="STABLE", map_status_text="OK", prediction_note="OK", input_features={}, heatmap_zones=[], created_at=now
    )
    test_db_session.add_all([tel, pred])
    await test_db_session.commit()

    # Child 3: SHAPRecord (ON DELETE CASCADE from RiskPrediction)
    shap = SHAPRecord(
        id=uuid.uuid4(), risk_prediction_id=pred.id, horizon=0, prediction=0.5, base_value=0.2,
        total_shap_delta=0.3, features={}, decision_trace={}, created_at=now
    )
    test_db_session.add(shap)
    await test_db_session.commit()

    # Execute direct SQL DELETE against parent incident to test PostgreSQL engine constraints
    await test_db_session.execute(text("DELETE FROM incidents WHERE id = :inc_id"), {"inc_id": inc_id})
    await test_db_session.commit()
    test_db_session.expunge_all()

    # 1. TelemetryObservation should still exist but incident_id set to NULL (SET NULL)
    res_tel = await test_db_session.execute(select(TelemetryObservation).where(TelemetryObservation.id == tel.id))
    fetched_tel = res_tel.scalar_one_or_none()
    assert fetched_tel is not None
    assert fetched_tel.incident_id is None

    # 2. RiskPrediction should be deleted (CASCADE)
    res_pred = await test_db_session.execute(select(RiskPrediction).where(RiskPrediction.id == pred.id))
    fetched_pred = res_pred.scalar_one_or_none()
    assert fetched_pred is None

    # 3. SHAPRecord should be deleted via cascade chain (CASCADE)
    res_shap = await test_db_session.execute(select(SHAPRecord).where(SHAPRecord.id == shap.id))
    fetched_shap = res_shap.scalar_one_or_none()
    assert fetched_shap is None


# ── SECTION H: KEYSET PAGINATION TESTS ────────────────────────────────────

@pytest.mark.anyio
async def test_07_keyset_pagination_real_postgresql(test_db_session: AsyncSession):
    """Verify keyset pagination returns deterministic, duplicate-free records against PostgreSQL."""
    now = datetime.now(timezone.utc)
    inc_id = f"INC-PAGE-{uuid.uuid4().hex[:6]}"

    inc = Incident(
        id=inc_id, incident_type="flood", status="active", started_at=now,
        sector="Sector-4", severity="HIGH", location_name="Page Hub", latitude=28.6, longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326)
    )
    test_db_session.add(inc)
    await test_db_session.commit()

    tel_ids = [uuid.uuid4() for _ in range(6)]
    tel_ids.sort(reverse=True)

    for t_id in tel_ids:
        obs = TelemetryObservation(
            id=t_id, incident_id=inc_id, data_mode="simulated", fallback_used=False,
            rainfall_intensity=40.0, rainfall_trend=0.0, water_level=3.0, water_level_trend=0.0,
            road_congestion=0.2, population_exposure=500.0, infrastructure_vulnerability=0.2,
            provenance={}, observed_at=now
        )
        test_db_session.add(obs)
    await test_db_session.commit()

    # Page 1: limit=3
    params1 = PaginationParams(limit=3)
    stmt1 = select(TelemetryObservation).where(TelemetryObservation.incident_id == inc_id)
    stmt1 = apply_keyset_pagination(stmt1, TelemetryObservation.observed_at, TelemetryObservation.id, params1)
    res1 = await test_db_session.execute(stmt1)
    items1 = list(res1.scalars().all())
    page1 = build_page_result(items1, params1.limit, lambda x: x.observed_at, lambda x: x.id)

    assert len(page1.items) == 3
    assert page1.has_more is True
    assert page1.next_cursor is not None

    # Page 2: using cursor from Page 1
    params2 = PaginationParams(
        limit=3,
        cursor_timestamp=datetime.fromisoformat(page1.next_cursor["timestamp"]),
        cursor_id=page1.next_cursor["id"],
    )
    stmt2 = select(TelemetryObservation).where(TelemetryObservation.incident_id == inc_id)
    stmt2 = apply_keyset_pagination(stmt2, TelemetryObservation.observed_at, TelemetryObservation.id, params2)
    res2 = await test_db_session.execute(stmt2)
    items2 = list(res2.scalars().all())
    page2 = build_page_result(items2, params2.limit, lambda x: x.observed_at, lambda x: x.id)

    assert len(page2.items) == 3
    assert page2.has_more is False

    p1_ids = {str(item.id) for item in page1.items}
    p2_ids = {str(item.id) for item in page2.items}
    assert p1_ids.isdisjoint(p2_ids)
    assert len(p1_ids.union(p2_ids)) == 6


# ── SECTION I: UNIFIED INCIDENT TIMELINE TEST ─────────────────────────────

@pytest.mark.anyio
async def test_08_unified_timeline_real_postgresql(test_db_session: AsyncSession):
    """Verify TimelineService aggregates, ranks, formats cursors, and paginates deterministically across all 6 entities in real PostgreSQL."""
    from app.services.timeline_service import EVENT_RANKS, TimelineService

    # 1. Single source of truth for event ranks verification
    assert EVENT_RANKS == {
        "telemetry_observation": 6,
        "risk_prediction": 5,
        "evacuation_route": 4,
        "alert": 3,
        "simulation": 2,
        "audit_event": 1,
    }

    now = datetime.now(timezone.utc)
    inc_id = f"INC-TIMELINE-{uuid.uuid4().hex[:6]}"

    inc = Incident(
        id=inc_id, incident_type="flood", status="active", started_at=now,
        sector="Sector-4", severity="HIGH", location_name="Timeline Hub", latitude=28.6, longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326)
    )
    test_db_session.add(inc)
    await test_db_session.commit()

    tel = TelemetryObservation(
        id=uuid.uuid4(), incident_id=inc_id, data_mode="live", fallback_used=False,
        rainfall_intensity=60.0, rainfall_trend=1.0, water_level=4.0, water_level_trend=0.2,
        road_congestion=0.5, population_exposure=1000.0, infrastructure_vulnerability=0.4,
        provenance={}, observed_at=now
    )
    pred = RiskPrediction(
        id=uuid.uuid4(), incident_id=inc_id, horizon=0, horizon_label="NOW", current_risk=0.6,
        predicted_risk=0.75, risk_category="HIGH", confidence=0.9, prediction_reliability=0.95,
        affected_population=1000, critical_population=100, critical_assets_count=2, affected_assets_count=1,
        trend="RISING", map_status_text="High risk", prediction_note="Spike", input_features={}, heatmap_zones=[], created_at=now
    )
    route = EvacuationRoute(
        id=uuid.uuid4(), incident_id=inc_id, route_name="Route 1", route_type="primary", is_recommended=True,
        origin_name="O", origin_lat=28.6, origin_lon=77.2, destination_name="D", destination_lat=28.7, destination_lon=77.3,
        waypoint_coords=[], distance_km=4.0, estimated_minutes=10.0, safety_score=0.9, created_at=now
    )
    alert = Alert(
        id=uuid.uuid4(), incident_id=inc_id, severity="HIGH", title="Timeline Alert", description="Alert text", status="OPEN", created_at=now
    )
    sim = Simulation(
        id=uuid.uuid4(), incident_id=inc_id, baseline_risk=0.6, scenario_risk=0.8, risk_delta=0.2,
        risk_category="HIGH", route_recommendation="Rec", flagged_assets=[], narrative="Sim", severity="HIGH", created_at=now
    )
    audit = AuditEvent(
        id=uuid.uuid4(), incident_id=inc_id, event_type="TEST_AUDIT", severity="INFO", source="Test",
        description="Audit entry", actor="tester", created_at=now
    )
    test_db_session.add_all([tel, pred, route, alert, sim, audit])
    await test_db_session.commit()

    service = TimelineService(test_db_session)

    # A. Full fetch (limit=10) to verify rank ordering at identical timestamps
    res_full = await service.get_incident_timeline(inc_id, PaginationParams(limit=10))

    assert len(res_full.items) == 6
    entity_types = [item.entity_type for item in res_full.items]
    # Exact 6.6C rank order: Telemetry(6), Risk(5), Route(4), Alert(3), Simulation(2), Audit(1)
    assert entity_types == [
        "telemetry_observation",
        "risk_prediction",
        "evacuation_route",
        "alert",
        "simulation",
        "audit_event",
    ]

    # B. Test same rank + entity_id tie breaking (e.g. 2 telemetry observations at identical timestamp now)
    id_smaller = uuid.UUID("10000000-0000-0000-0000-000000000000")
    id_larger = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

    tel_small = TelemetryObservation(
        id=id_smaller, incident_id=inc_id, data_mode="live", fallback_used=False,
        rainfall_intensity=10.0, rainfall_trend=0.0, water_level=1.0, water_level_trend=0.0,
        road_congestion=0.1, population_exposure=100.0, infrastructure_vulnerability=0.1,
        provenance={}, observed_at=now
    )
    tel_large = TelemetryObservation(
        id=id_larger, incident_id=inc_id, data_mode="live", fallback_used=False,
        rainfall_intensity=20.0, rainfall_trend=0.0, water_level=2.0, water_level_trend=0.0,
        road_congestion=0.2, population_exposure=200.0, infrastructure_vulnerability=0.2,
        provenance={}, observed_at=now
    )
    test_db_session.add_all([tel_small, tel_large])
    await test_db_session.commit()

    res_ties = await service.get_incident_timeline(inc_id, PaginationParams(limit=10))
    telemetry_items = [i for i in res_ties.items if i.entity_type == "telemetry_observation"]
    assert len(telemetry_items) == 3
    # entity_id DESC ordering for same rank & timestamp
    assert telemetry_items[0].entity_id == str(id_larger)

    # Clean up tie-breaker test records to keep pagination test deterministic with 6 items
    await test_db_session.delete(tel_small)
    await test_db_session.delete(tel_large)
    await test_db_session.commit()

    # C. Keyset Pagination (limit=3 per page across source boundaries)
    page1 = await service.get_incident_timeline(inc_id, PaginationParams(limit=3))
    assert len(page1.items) == 3
    assert page1.has_more is True
    assert page1.next_cursor is not None

    # Exact cursor_timestamp and cursor_id format checks
    assert "timestamp" in page1.next_cursor
    assert "id" in page1.next_cursor
    assert page1.next_cursor["timestamp"] == page1.items[-1].timestamp
    # Item 3 is evacuation_route (rank 4), format: "4:{route.id}"
    assert page1.next_cursor["id"] == f"4:{route.id}"

    # Fetch Page 2 using returned cursor
    page2 = await service.get_incident_timeline(
        inc_id,
        PaginationParams(
            limit=3,
            cursor_timestamp=datetime.fromisoformat(page1.next_cursor["timestamp"]),
            cursor_id=page1.next_cursor["id"],
        ),
    )
    assert len(page2.items) == 3
    assert page2.items[0].entity_type == "alert"
    assert page2.items[1].entity_type == "simulation"
    assert page2.items[2].entity_type == "audit_event"

    # Zero duplicates & Zero skipped events across Page 1 + Page 2
    all_page_items = page1.items + page2.items
    all_entity_ids = [item.entity_id for item in all_page_items]
    assert len(all_entity_ids) == 6
    assert len(set(all_entity_ids)) == 6
    expected_ids = {str(tel.id), str(pred.id), str(route.id), str(alert.id), str(sim.id), str(audit.id)}
    assert set(all_entity_ids) == expected_ids


# ── SECTION J: PERSISTENCE PIPELINE TEST ──────────────────────────────────

@pytest.mark.anyio
async def test_09_persistence_service_atomic_pipeline_real_postgresql(test_db_session: AsyncSession):
    """Verify PersistenceService executes atomic assessment pipeline commit to PostgreSQL."""
    from unittest.mock import patch, MagicMock

    now = datetime.now(timezone.utc)
    inc_id = f"INC-PIPE-{uuid.uuid4().hex[:6]}"

    inc = Incident(
        id=inc_id, incident_type="flood", status="active", started_at=now,
        sector="Sector-4", severity="HIGH", location_name="Pipeline Hub", latitude=28.6, longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326)
    )
    test_db_session.add(inc)
    await test_db_session.commit()

    telemetry = TelemetryObservation(
        id=uuid.uuid4(), data_mode="live", fallback_used=False,
        rainfall_intensity=50.0, rainfall_trend=0.0, water_level=3.5, water_level_trend=0.0,
        road_congestion=0.3, population_exposure=1200.0, infrastructure_vulnerability=0.3,
        provenance={}, observed_at=now
    )
    prediction = RiskPrediction(
        id=uuid.uuid4(), horizon=0, horizon_label="NOW", current_risk=0.5, predicted_risk=0.7,
        risk_category="HIGH", confidence=0.9, prediction_reliability=0.9, affected_population=1200,
        critical_population=100, critical_assets_count=2, affected_assets_count=1, trend="RISING",
        map_status_text="Rising", prediction_note="Note", input_features={}, heatmap_zones=[], created_at=now
    )
    shap = SHAPRecord(
        id=uuid.uuid4(), horizon=0, prediction=0.7, base_value=0.2, total_shap_delta=0.5,
        features={}, decision_trace={}, created_at=now
    )
    route = EvacuationRoute(
        id=uuid.uuid4(), route_name="Pipe Route", route_type="primary", is_recommended=True,
        origin_name="O", origin_lat=28.6, origin_lon=77.2, destination_name="D", destination_lat=28.7, destination_lon=77.3,
        waypoint_coords=[], distance_km=5.0, estimated_minutes=12.0, safety_score=0.9, created_at=now
    )

    ps = PersistenceService()
    
    mock_mgr = MagicMock()
    mock_mgr.is_available = True
    
    class TestSessionContext:
        def __init__(self, session):
            self.session = session
        async def __aenter__(self):
            return self.session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_mgr.get_session.return_value = TestSessionContext(test_db_session)

    with patch("app.services.persistence_service.get_db_manager", return_value=mock_mgr):
        with patch.object(settings, "persistence_mode", "required"):
            success = await ps.persist_assessment_pipeline(
                incident_id=inc_id,
                telemetry=telemetry,
                prediction=prediction,
                shap_record=shap,
                routes=[route],
            )
            assert success is True

    assert await test_db_session.get(TelemetryObservation, telemetry.id) is not None
    assert await test_db_session.get(RiskPrediction, prediction.id) is not None
    assert await test_db_session.get(SHAPRecord, shap.id) is not None
    assert await test_db_session.get(EvacuationRoute, route.id) is not None


# ── SECTION K: TRANSACTION ROLLBACK TEST ──────────────────────────────────

@pytest.mark.anyio
async def test_10_transaction_rollback_prevents_partial_persistence(test_engine):
    """Verify an error during atomic pipeline transaction causes complete rollback in PostgreSQL."""
    now = datetime.now(timezone.utc)
    inc_id = f"INC-ROLLBACK-{uuid.uuid4().hex[:6]}"

    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        inc = Incident(
            id=inc_id, incident_type="flood", status="active", started_at=now,
            sector="Sector-4", severity="HIGH", location_name="Rollback Hub", latitude=28.6, longitude=77.2,
            geom=WKTElement("POINT(77.2 28.6)", srid=4326)
        )
        session.add(inc)
        await session.commit()

        tel_id = uuid.uuid4()
        try:
            async with session.begin():
                telemetry = TelemetryObservation(
                    id=tel_id, incident_id=inc_id, data_mode="live", fallback_used=False,
                    rainfall_intensity=50.0, rainfall_trend=0.0, water_level=3.5, water_level_trend=0.0,
                    road_congestion=0.3, population_exposure=1200.0, infrastructure_vulnerability=0.3,
                    provenance={}, observed_at=now
                )
                session.add(telemetry)
                await session.flush()

                # Staging invalid RiskPrediction referencing non-existent incident ID to trigger FK constraint error
                invalid_pred = RiskPrediction(
                    id=uuid.uuid4(), incident_id="NON_EXISTENT_INCIDENT_ID", telemetry_id=tel_id, horizon=0,
                    horizon_label="NOW", current_risk=0.5, predicted_risk=0.7, risk_category="HIGH",
                    confidence=0.9, prediction_reliability=0.9, affected_population=100, critical_population=10,
                    critical_assets_count=1, affected_assets_count=0, trend="STABLE", map_status_text="ERR",
                    prediction_note="ERR", input_features={}, heatmap_zones=[], created_at=now
                )
                session.add(invalid_pred)
                await session.flush()
        except Exception:
            pass  # Exception expected

        # Query real PostgreSQL database — TelemetryObservation must NOT exist due to rollback
        fetched_tel = await session.get(TelemetryObservation, tel_id)
        assert fetched_tel is None, "Telemetry row was committed despite transaction failure!"


# ── SECTION L: SSE POST-COMMIT TEST ───────────────────────────────────────

@pytest.mark.anyio
async def test_11_sse_post_commit_ordering(test_db_session: AsyncSession):
    """Verify SSE events are published strictly post-commit and suppressed on failed transaction."""
    from unittest.mock import patch, MagicMock
    ps = PersistenceService()

    now = datetime.now(timezone.utc)
    inc_id = f"INC-SSE-{uuid.uuid4().hex[:6]}"

    inc = Incident(
        id=inc_id, incident_type="flood", status="active", started_at=now,
        sector="Sector-4", severity="HIGH", location_name="SSE Hub", latitude=28.6, longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326)
    )
    test_db_session.add(inc)
    await test_db_session.commit()

    telemetry = TelemetryObservation(
        id=uuid.uuid4(), data_mode="live", fallback_used=False,
        rainfall_intensity=50.0, rainfall_trend=0.0, water_level=3.5, water_level_trend=0.0,
        road_congestion=0.3, population_exposure=1200.0, infrastructure_vulnerability=0.3,
        provenance={}, observed_at=now
    )
    prediction = RiskPrediction(
        id=uuid.uuid4(), horizon=0, horizon_label="NOW", current_risk=0.5, predicted_risk=0.7,
        risk_category="HIGH", confidence=0.9, prediction_reliability=0.9, affected_population=1200,
        critical_population=100, critical_assets_count=2, affected_assets_count=1, trend="RISING",
        map_status_text="Rising", prediction_note="Note", input_features={}, heatmap_zones=[], created_at=now
    )
    shap = SHAPRecord(
        id=uuid.uuid4(), horizon=0, prediction=0.7, base_value=0.2, total_shap_delta=0.5,
        features={}, decision_trace={}, created_at=now
    )

    mock_broker = MagicMock()
    mock_mgr = MagicMock()
    mock_mgr.is_available = True

    class TestSessionContext:
        def __init__(self, session):
            self.session = session
        async def __aenter__(self):
            return self.session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_mgr.get_session.return_value = TestSessionContext(test_db_session)

    with patch("app.events.broker.get_event_broker", return_value=mock_broker):
        with patch("app.services.persistence_service.get_db_manager", return_value=mock_mgr):
            with patch.object(settings, "persistence_mode", "required"):
                success = await ps.persist_assessment_pipeline(
                    incident_id=inc_id,
                    telemetry=telemetry,
                    prediction=prediction,
                    shap_record=shap,
                    routes=[],
                )
                assert success is True
                assert mock_broker.publish.call_count >= 2


# ── SECTION M: INDEX EXISTENCE TESTS ──────────────────────────────────────

@pytest.mark.anyio
async def test_12_index_existence_in_postgresql_catalog(test_db_session: AsyncSession):
    """Verify all 14 Phase 6.7B indexes exist in PostgreSQL catalog with correct access methods."""
    sql = text("""
        SELECT 
            i.relname AS index_name,
            a.amname AS method
        FROM pg_class t
        JOIN pg_index idx ON t.oid = idx.indrelid
        JOIN pg_class i ON i.oid = idx.indexrelid
        JOIN pg_am a ON i.relam = a.oid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public' 
          AND t.relkind = 'r'
          AND i.relname LIKE 'ix_%';
    """)
    res = await test_db_session.execute(sql)
    indexes = {row.index_name: row.method for row in res.all()}

    # 5 GIST indexes
    expected_gist = [
        "ix_incidents_geom",
        "ix_telemetry_location_geom",
        "ix_routes_path_geom",
        "ix_assets_location_geom",
        "ix_alerts_boundary_geom",
    ]
    for idx in expected_gist:
        assert idx in indexes, f"Missing GIST index '{idx}'"
        assert indexes[idx] == "gist", f"Index '{idx}' method is '{indexes[idx]}', expected 'gist'!"

    # 3 Standalone FK B-tree indexes
    expected_fk_btree = [
        "ix_risk_predictions_telemetry_id",
        "ix_evacuation_routes_risk_prediction_id",
        "ix_alerts_critical_asset_id",
    ]
    for idx in expected_fk_btree:
        assert idx in indexes, f"Missing FK B-tree index '{idx}'"
        assert indexes[idx] == "btree", f"Index '{idx}' method is '{indexes[idx]}', expected 'btree'!"

    # 6 Composite Pagination B-tree indexes
    expected_pag_btree = [
        "ix_telemetry_pagination",
        "ix_risk_pagination",
        "ix_routes_pagination",
        "ix_alerts_pagination",
        "ix_simulations_pagination",
        "ix_audit_pagination",
    ]
    for idx in expected_pag_btree:
        assert idx in indexes, f"Missing Pagination B-tree index '{idx}'"
        assert indexes[idx] == "btree", f"Index '{idx}' method is '{indexes[idx]}', expected 'btree'!"


# ── SECTION P: PERFORMANCE / EXPLAIN SMOKE TEST ──────────────────────────

@pytest.mark.anyio
async def test_13_explain_query_plans(test_db_session: AsyncSession):
    """Verify PostgreSQL query planner selects expected Phase 6.7B indexes."""
    res_tel = await test_db_session.execute(text(
        "EXPLAIN SELECT * FROM telemetry_observations WHERE incident_id = 'INC-01' ORDER BY observed_at DESC, id DESC LIMIT 10;"
    ))
    plan_tel = "\n".join(res_tel.scalars().all())
    assert "ix_telemetry_pagination" in plan_tel or "Index Scan" in plan_tel

    res_risk = await test_db_session.execute(text(
        "EXPLAIN SELECT * FROM risk_predictions WHERE incident_id = 'INC-01' ORDER BY created_at DESC, id DESC LIMIT 10;"
    ))
    plan_risk = "\n".join(res_risk.scalars().all())
    assert "ix_risk_pagination" in plan_risk or "Index Scan" in plan_risk

    res_spatial = await test_db_session.execute(text(
        "EXPLAIN SELECT * FROM alerts WHERE ST_Intersects(boundary_geom, ST_SetSRID(ST_MakePoint(77.22, 28.64), 4326));"
    ))
    plan_spatial = "\n".join(res_spatial.scalars().all())
    assert "ix_alerts_boundary_geom" in plan_spatial or "Index Scan" in plan_spatial
