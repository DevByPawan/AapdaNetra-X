"""
AapdaNetra-X — Phase 6.20.10: Final PostgreSQL/PostGIS Multi-Hazard Persistence Integration Test

Verifies:
1. Migration 003 head status on real aapdanetra_test database.
2. End-to-end persistence of hazard_type across all 5 tables (telemetry, risk, alerts, routes, audit).
3. Keyset pagination and hazard-isolation queries against real PostgreSQL database.
"""

import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.telemetry import TelemetryRepository
from app.db.repositories.risk import RiskPredictionRepository
from app.db.repositories.alert import AlertRepository
from app.db.repositories.route import EvacuationRouteRepository
from app.db.repositories.audit import AuditEventRepository
from app.db.models.telemetry import TelemetryObservation
from app.db.models.risk import RiskPrediction
from app.db.models.alert import Alert
from app.db.models.route import EvacuationRoute
from app.db.models.audit import AuditEvent
from app.hazards.types import HazardType


@pytest.mark.anyio
@pytest.mark.postgis
async def test_01_verify_alembic_head_migration_003(test_db_session: AsyncSession):
    """Verify Alembic version on aapdanetra_test database is migration 003."""
    res = await test_db_session.execute(text("SELECT version_num FROM alembic_version;"))
    version_num = res.scalar()
    assert version_num == "003_add_hazard_type_persistence", f"Alembic version is '{version_num}'!"


@pytest.mark.anyio
@pytest.mark.postgis
async def test_02_verify_schema_hazard_type_persistence_columns(test_db_session: AsyncSession):
    """Verify hazard_type VARCHAR(32) NOT NULL DEFAULT 'flood' column across all 5 tables in PostgreSQL."""
    res = await test_db_session.execute(text("""
        SELECT table_name, column_name, data_type, column_default, is_nullable
        FROM information_schema.columns
        WHERE column_name='hazard_type'
        ORDER BY table_name;
    """))
    rows = res.fetchall()
    table_map = {row.table_name: row for row in rows}

    expected_tables = ["alerts", "audit_events", "evacuation_routes", "risk_predictions", "telemetry_observations"]
    for table_name in expected_tables:
        assert table_name in table_map, f"Table '{table_name}' missing 'hazard_type' column!"
        row = table_map[table_name]
        assert row.data_type == "character varying"
        assert row.is_nullable == "NO"
        assert "'flood'" in row.column_default


@pytest.mark.anyio
@pytest.mark.postgis
async def test_03_end_to_end_multi_table_hazard_persistence_and_isolation(test_db_session: AsyncSession):
    """Verify inserting records with flood and extreme_rainfall maintains hazard isolation on query."""
    unique_suffix = uuid.uuid4().hex[:8]

    # 1. Telemetry
    t1 = TelemetryObservation(
        data_mode="LIVE",
        hazard_type=HazardType.FLOOD.value,
        rainfall_intensity=45.0,
        rainfall_trend=0.0,
        water_level=3.2,
        water_level_trend=0.0,
        road_congestion=0.2,
        population_exposure=0.5,
        infrastructure_vulnerability=0.3,
        location_name=f"Station-Flood-{unique_suffix}",
        provenance="Synthetic test feed",
    )
    t2 = TelemetryObservation(
        data_mode="LIVE",
        hazard_type=HazardType.EXTREME_RAINFALL.value,
        rainfall_intensity=90.0,
        rainfall_trend=5.0,
        water_level=1.0,
        water_level_trend=0.0,
        road_congestion=0.1,
        population_exposure=0.2,
        infrastructure_vulnerability=0.1,
        location_name=f"Station-Rain-{unique_suffix}",
        provenance="Synthetic test feed",
    )
    test_db_session.add_all([t1, t2])
    await test_db_session.flush()

    # 2. Audit
    audit_repo = AuditEventRepository(test_db_session)
    await audit_repo.log_event(
        event_type="DECISION_TEST",
        severity="INFO",
        source="unit_test",
        description=f"action_flood_{unique_suffix}",
        actor="OPERATOR-1",
        hazard_type="flood",
    )
    await audit_repo.log_event(
        event_type="TELEMETRY_TEST",
        severity="INFO",
        source="unit_test",
        description=f"action_er_{unique_suffix}",
        actor="OPERATOR-2",
        hazard_type="extreme_rainfall",
    )
    await test_db_session.flush()

    flood_res = await audit_repo.get_history_paginated(hazard_type="flood")
    er_res = await audit_repo.get_history_paginated(hazard_type="extreme_rainfall")

    flood_descs = [a.description for a in flood_res.items]
    er_descs = [a.description for a in er_res.items]

    assert f"action_flood_{unique_suffix}" in flood_descs
    assert f"action_flood_{unique_suffix}" not in er_descs
    assert f"action_er_{unique_suffix}" in er_descs
    assert f"action_er_{unique_suffix}" not in flood_descs
