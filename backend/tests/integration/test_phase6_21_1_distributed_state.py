"""Phase 6.21.1 — Distributed State Foundation Integration Tests.

Verifies:
1. Migration 004 schema.
2. Durable Decision ORM CRUD.
3. Atomic Decision status transition.
4. Hazard isolation for durable decisions.
5. Durable telemetry fingerprint persistence.
6. PostgreSQL-enforced fingerprint uniqueness.
"""

from datetime import datetime, timezone
import uuid

import pytest
from geoalchemy2 import WKTElement
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Decision, Incident, TelemetryObservation
from app.db.repositories.decision import DecisionRepository
from app.hazards.types import HazardType


pytestmark = pytest.mark.postgis


def _make_incident_id() -> str:
    return f"INC-6.21.1-{uuid.uuid4().hex[:10]}"


def _make_decision_id() -> str:
    return f"dec-6.21.1-{uuid.uuid4().hex[:10]}"


def _make_telemetry(
    incident_id: str,
    fingerprint: str,
) -> TelemetryObservation:
    return TelemetryObservation(
        id=uuid.uuid4(),
        incident_id=incident_id,
        hazard_type=HazardType.FLOOD.value,
        data_mode="live",
        fallback_used=False,
        rainfall_intensity=45.0,
        rainfall_trend=2.0,
        water_level=5.5,
        water_level_trend=0.4,
        road_congestion=0.3,
        population_exposure=0.5,
        infrastructure_vulnerability=0.4,
        provenance={"source": "phase6.21.1-test"},
        provider_metadata={"sensor_id": "TEST-SENSOR"},
        fingerprint=fingerprint,
    )


async def _create_incident(
    session: AsyncSession,
    incident_id: str,
) -> Incident:
    incident = Incident(
        id=incident_id,
        incident_type="flood",
        status="active",
        started_at=datetime.now(timezone.utc),
        sector="Phase-6.21.1",
        severity="HIGH",
        location_name="Yamuna River Bank",
        latitude=28.6448,
        longitude=77.2167,
        geom=WKTElement("POINT(77.2167 28.6448)", srid=4326),
    )
    session.add(incident)
    await session.flush()
    return incident


@pytest.mark.anyio
async def test_01_migration_004_schema(test_db_session: AsyncSession):
    """Verify migration 004 created decisions and telemetry fingerprint."""
    version = await test_db_session.execute(
        text("SELECT version_num FROM alembic_version;")
    )
    assert version.scalar() == "004_distributed_state_foundation"

    decisions_table = await test_db_session.execute(
        text(
            """
            SELECT column_name, data_type, character_maximum_length, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'decisions'
            ORDER BY ordinal_position;
            """
        )
    )
    decision_columns = {
        row.column_name: row
        for row in decisions_table.fetchall()
    }

    assert "id" in decision_columns
    assert decision_columns["id"].data_type == "character varying"
    assert decision_columns["id"].character_maximum_length == 64
    assert decision_columns["id"].is_nullable == "NO"

    assert "incident_id" in decision_columns
    assert decision_columns["incident_id"].is_nullable == "NO"

    assert "hazard_type" in decision_columns
    assert "status" in decision_columns
    assert "priority" in decision_columns
    assert "payload" in decision_columns

    telemetry_columns = await test_db_session.execute(
        text(
            """
            SELECT data_type, character_maximum_length, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'telemetry_observations'
              AND column_name = 'fingerprint';
            """
        )
    )
    fingerprint_column = telemetry_columns.fetchone()

    assert fingerprint_column is not None
    assert fingerprint_column.data_type == "character varying"
    assert fingerprint_column.character_maximum_length == 64
    assert fingerprint_column.is_nullable == "YES"

    indexes = await test_db_session.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'telemetry_observations'
              AND indexname = 'idx_telemetry_fingerprint_unique';
            """
        )
    )
    fingerprint_index = indexes.fetchone()

    assert fingerprint_index is not None
    assert "UNIQUE INDEX" in fingerprint_index.indexdef
    assert "fingerprint" in fingerprint_index.indexdef
    assert "fingerprint IS NOT NULL" in fingerprint_index.indexdef


@pytest.mark.anyio
async def test_02_decision_crud_and_latest(
    test_db_session: AsyncSession,
):
    """Verify durable Decision insert, fetch, and latest lookup."""
    incident_id = _make_incident_id()
    await _create_incident(test_db_session, incident_id)

    decision = Decision(
        id=_make_decision_id(),
        incident_id=incident_id,
        hazard_type=HazardType.FLOOD.value,
        status="RECOMMENDED",
        priority="HIGH",
        risk_score=82.5,
        payload={
            "action": "Prepare evacuation corridor",
            "source": "phase6.21.1-test",
        },
    )

    repository = DecisionRepository(test_db_session)

    saved = await repository.save_decision(decision)
    assert saved.id == decision.id
    assert saved.hazard_type == HazardType.FLOOD.value
    assert saved.status == "RECOMMENDED"

    fetched = await repository.get_by_id(decision.id)
    assert fetched is not None
    assert fetched.id == decision.id
    assert fetched.incident_id == incident_id
    assert fetched.payload["action"] == "Prepare evacuation corridor"

    latest = await repository.get_latest_active_decision(
        incident_id=incident_id,
        hazard_type=HazardType.FLOOD.value,
    )
    assert latest is not None
    assert latest.id == decision.id


@pytest.mark.anyio
async def test_03_decision_atomic_status_transition(
    test_db_session: AsyncSession,
):
    """Verify expected-status transition is atomic and stale transitions fail."""
    incident_id = _make_incident_id()
    await _create_incident(test_db_session, incident_id)

    decision = Decision(
        id=_make_decision_id(),
        incident_id=incident_id,
        hazard_type=HazardType.FLOOD.value,
        status="RECOMMENDED",
        priority="HIGH",
        risk_score=88.0,
        payload={"action": "Evacuate exposed sector"},
    )

    repository = DecisionRepository(test_db_session)
    await repository.save_decision(decision)

    approved = await repository.transition_status(
        decision_id=decision.id,
        expected_status="RECOMMENDED",
        new_status="APPROVED",
    )

    assert approved is not None
    assert approved.status == "APPROVED"

    stale_transition = await repository.transition_status(
        decision_id=decision.id,
        expected_status="RECOMMENDED",
        new_status="REJECTED",
    )

    assert stale_transition is None

    persisted = await repository.get_by_id(decision.id)
    assert persisted is not None
    assert persisted.status == "APPROVED"


@pytest.mark.anyio
async def test_04_decision_hazard_isolation(
    test_db_session: AsyncSession,
):
    """Verify decisions remain isolated by hazard_type."""
    incident_id = _make_incident_id()
    await _create_incident(test_db_session, incident_id)

    flood_decision = Decision(
        id=_make_decision_id(),
        incident_id=incident_id,
        hazard_type=HazardType.FLOOD.value,
        status="RECOMMENDED",
        priority="HIGH",
        risk_score=80.0,
        payload={"hazard": "flood"},
    )

    rainfall_decision = Decision(
        id=_make_decision_id(),
        incident_id=incident_id,
        hazard_type=HazardType.EXTREME_RAINFALL.value,
        status="UNAVAILABLE",
        priority="LOW",
        risk_score=None,
        payload={"hazard": "extreme_rainfall"},
    )

    repository = DecisionRepository(test_db_session)

    await repository.save_decision(flood_decision)
    await repository.save_decision(rainfall_decision)

    flood_latest = await repository.get_latest_active_decision(
        incident_id,
        HazardType.FLOOD.value,
    )
    rainfall_latest = await repository.get_latest_active_decision(
        incident_id,
        HazardType.EXTREME_RAINFALL.value,
    )

    assert flood_latest is not None
    assert rainfall_latest is not None

    assert flood_latest.id == flood_decision.id
    assert flood_latest.hazard_type == HazardType.FLOOD.value

    assert rainfall_latest.id == rainfall_decision.id
    assert rainfall_latest.hazard_type == HazardType.EXTREME_RAINFALL.value


@pytest.mark.anyio
async def test_05_telemetry_fingerprint_persistence(
    test_db_session: AsyncSession,
):
    """Verify a telemetry fingerprint survives a real PostgreSQL round trip."""
    incident_id = _make_incident_id()
    await _create_incident(test_db_session, incident_id)

    fingerprint = "a" * 64

    telemetry = _make_telemetry(
        incident_id=incident_id,
        fingerprint=fingerprint,
    )

    test_db_session.add(telemetry)
    await test_db_session.commit()

    fetched = await test_db_session.get(
        TelemetryObservation,
        telemetry.id,
    )

    assert fetched is not None
    assert fetched.fingerprint == fingerprint


@pytest.mark.anyio
async def test_06_telemetry_fingerprint_unique_constraint(
    test_db_session: AsyncSession,
):
    """Verify PostgreSQL rejects duplicate non-null telemetry fingerprints."""
    incident_id = _make_incident_id()
    await _create_incident(test_db_session, incident_id)

    fingerprint = "b" * 64

    first = _make_telemetry(
        incident_id=incident_id,
        fingerprint=fingerprint,
    )
    test_db_session.add(first)
    await test_db_session.commit()

    second = _make_telemetry(
        incident_id=incident_id,
        fingerprint=fingerprint,
    )
    test_db_session.add(second)

    with pytest.raises(IntegrityError):
        await test_db_session.flush()

    await test_db_session.rollback()

    stored_count = await test_db_session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM telemetry_observations
            WHERE fingerprint = :fingerprint;
            """
        ),
        {"fingerprint": fingerprint},
    )

    assert stored_count.scalar() == 1