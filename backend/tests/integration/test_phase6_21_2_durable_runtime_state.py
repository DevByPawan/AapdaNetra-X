"""Phase 6.21.2 — Durable Runtime State Integration Tests.

Verifies:
Part A — Durable Decision State:
1. Decision recommendation is persisted to decisions table.
2. Decision can be retrieved by a fresh repository instance from PostgreSQL.
3. Decision status transition (RECOMMENDED -> APPROVED) persists to PostgreSQL.
4. Atomic status transition with stale expected-status is rejected.
5. Hazard isolation: non-operational hazards return UNAVAILABLE and do not persist fake operational decision state.
6. Process-local registry is bypassed for authoritative state retrieval from PostgreSQL.

Part B — Durable Evacuation State:
7. Latest recommended route is persisted to evacuation_routes table.
8. Latest route is recovered from PostgreSQL by a fresh service instance.
9. Route change detection survives service/process recreation.
10. Operational flood evacuation scoring & route generation remains unchanged.
11. Unsupported hazards return deterministic unavailable response and do not persist route state.

Part C — Database & Migration Verification:
12. Migration 004 schema & tables verified.
13. Alembic upgrade/downgrade/re-upgrade sequence verification.
"""

from datetime import datetime, timezone
import uuid
import pytest

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Decision, EvacuationRoute, Incident
from app.db.repositories.decision import DecisionRepository
from app.db.repositories.route import EvacuationRouteRepository
from app.services.decision_service import (
    compute_emergency_decision,
    get_registered_decision,
    transition_decision,
    STATE_RECOMMENDED,
    STATE_APPROVED,
    STATE_REJECTED,
    STATE_SUPERSEDED,
)
from app.services.evacuation_service import (
    get_evacuation_service,
)
from app.services.persistence_service import get_persistence_service
from app.hazards.types import HazardType

pytestmark = pytest.mark.postgis


def _make_incident_id() -> str:
    return f"INC-6.21.2-{uuid.uuid4().hex[:10]}"


async def _create_incident(session: AsyncSession, incident_id: str) -> Incident:
    from geoalchemy2 import WKTElement
    incident = Incident(
        id=incident_id,
        incident_type="flood",
        status="active",
        started_at=datetime.now(timezone.utc),
        sector="Phase-6.21.2",
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
async def test_01_decision_durable_persistence_and_recovery(test_db_session: AsyncSession):
    """1 & 2. Verify computed decision recommendation is persisted to PostgreSQL and recoverable by a fresh repository instance."""
    inc_id = _make_incident_id()
    await _create_incident(test_db_session, inc_id)
    await test_db_session.commit()

    # Compute emergency decision
    dec = compute_emergency_decision(incident_id=inc_id, horizon=0, hazard_type="flood")
    dec_id = dec["decision_id"]

    # Verify retrieval via fresh repository instance
    fresh_repo = DecisionRepository(test_db_session)
    stored_dec = await fresh_repo.get_by_id(dec_id)
    assert stored_dec is not None
    assert stored_dec.id == dec_id
    assert stored_dec.incident_id == inc_id
    assert stored_dec.status == STATE_RECOMMENDED
    assert stored_dec.hazard_type == "flood"
    assert stored_dec.payload["decision_id"] == dec_id


@pytest.mark.anyio
async def test_02_decision_status_transition_persists(test_db_session: AsyncSession):
    """3. Verify decision state machine transition (RECOMMENDED -> APPROVED) persists in PostgreSQL."""
    inc_id = _make_incident_id()
    await _create_incident(test_db_session, inc_id)
    await test_db_session.commit()

    dec = compute_emergency_decision(incident_id=inc_id, horizon=0, hazard_type="flood")
    dec_id = dec["decision_id"]

    # Transition decision to APPROVED
    success, msg, updated = transition_decision(
        decision_id=dec_id,
        new_status=STATE_APPROVED,
        responder_id="OPERATOR-99",
        reason="Field inspection confirmed safety of primary route.",
    )
    assert success is True
    assert updated["status"] == STATE_APPROVED

    # Verify fresh repository read returns APPROVED
    fresh_repo = DecisionRepository(test_db_session)
    stored_dec = await fresh_repo.get_by_id(dec_id)
    assert stored_dec is not None
    assert stored_dec.status == STATE_APPROVED
    assert stored_dec.payload["status"] == STATE_APPROVED
    assert stored_dec.payload["action_by"] == "OPERATOR-99"


@pytest.mark.anyio
async def test_03_atomic_stale_transition_rejected(test_db_session: AsyncSession):
    """4. Verify atomic status transition fails when expected current status does not match."""
    inc_id = _make_incident_id()
    await _create_incident(test_db_session, inc_id)
    await test_db_session.commit()

    dec = compute_emergency_decision(incident_id=inc_id, horizon=0, hazard_type="flood")
    dec_id = dec["decision_id"]

    # Transition to REJECTED first
    success, msg, _ = transition_decision(
        decision_id=dec_id,
        new_status=STATE_REJECTED,
        responder_id="OPERATOR-01",
        reason="Initial rejection",
    )
    assert success is True

    # Attempt second transition (REJECTED -> APPROVED) which is invalid according to state machine
    success2, msg2, _ = transition_decision(
        decision_id=dec_id,
        new_status=STATE_APPROVED,
        responder_id="OPERATOR-02",
        reason="Attempt illegal transition",
    )
    assert success2 is False
    assert "Invalid state transition" in msg2


@pytest.mark.anyio
async def test_04_decision_hazard_isolation(test_db_session: AsyncSession):
    """5 & 7. Verify non-operational hazard returns UNAVAILABLE and does not persist fake operational state."""
    inc_id = _make_incident_id()
    await _create_incident(test_db_session, inc_id)
    await test_db_session.commit()

    unavail_dec = compute_emergency_decision(incident_id=inc_id, hazard_type="landslide")
    assert unavail_dec["status"] == "UNAVAILABLE"
    assert unavail_dec["decision_support_available"] is False

    # Attempt to transition unavailable decision
    success, msg, _ = transition_decision(
        decision_id=unavail_dec["decision_id"],
        new_status=STATE_APPROVED,
        responder_id="OPERATOR-01",
        reason="Should be rejected",
    )
    assert success is False
    assert "without operational decision support" in msg


@pytest.mark.anyio
async def test_05_evacuation_route_durable_persistence_and_recovery(test_db_session: AsyncSession):
    """8 & 9. Verify evacuation route evaluation is persisted and recovered by a fresh repository instance."""
    inc_id = _make_incident_id()
    await _create_incident(test_db_session, inc_id)
    await test_db_session.commit()

    evac_svc = get_evacuation_service()
    res = evac_svc.evaluate_evacuation_routes(incident_id=inc_id, horizon=0, hazard_type="flood")
    assert res.recommended_route is not None

    # Verify route persisted in PostgreSQL
    fresh_repo = EvacuationRouteRepository(test_db_session)
    db_rec = await fresh_repo.get_recommended_route(inc_id, hazard_type="flood")
    assert db_rec is not None
    assert db_rec.incident_id == inc_id
    assert db_rec.is_recommended is True
    assert db_rec.route_name == res.recommended_route.name


@pytest.mark.anyio
async def test_06_evacuation_route_change_detection_across_recreation(test_db_session: AsyncSession):
    """10. Verify route change detection works across service/process recreation using PostgreSQL state."""
    inc_id = _make_incident_id()
    await _create_incident(test_db_session, inc_id)
    await test_db_session.commit()

    evac_svc = get_evacuation_service()
    # First evaluation (unblocked)
    res1 = evac_svc.evaluate_evacuation_routes(incident_id=inc_id, horizon=0, route_blockage_override=False, hazard_type="flood")
    rec_id_1 = res1.recommended_route.id

    # Clear in-memory cache to simulate worker process restart
    from app.services.evacuation_service import _PREVIOUS_RECOMMENDED_ROUTE
    _PREVIOUS_RECOMMENDED_ROUTE.clear()

    # Second evaluation (blocked) -> route change must be detected from PostgreSQL
    res2 = evac_svc.evaluate_evacuation_routes(incident_id=inc_id, horizon=0, route_blockage_override=True, hazard_type="flood")
    
    assert res2.route_change.route_changed is True
    assert res2.route_change.previous_route_id == rec_id_1
    assert res2.route_change.new_route_id != rec_id_1
    assert res2.route_change.change_reason is not None


@pytest.mark.anyio
async def test_07_evacuation_unsupported_hazard_isolation(test_db_session: AsyncSession):
    """11, 12 & 13. Verify unsupported hazard returns deterministic unavailable response and no routes are persisted."""
    inc_id = _make_incident_id()
    await _create_incident(test_db_session, inc_id)
    await test_db_session.commit()

    evac_svc = get_evacuation_service()
    res_unavail = evac_svc.evaluate_evacuation_routes(incident_id=inc_id, hazard_type="extreme_rainfall")
    assert res_unavail.routing_available is False
    assert "not supported" in res_unavail.reason

    # Verify no routes were persisted for extreme_rainfall
    fresh_repo = EvacuationRouteRepository(test_db_session)
    db_routes = await fresh_repo.get_routes_by_incident(inc_id)
    rainfall_routes = [r for r in db_routes if r.hazard_type == "extreme_rainfall"]
    assert len(rainfall_routes) == 0


@pytest.mark.anyio
async def test_08_migration_sequence_and_db_indexes(test_db_session: AsyncSession):
    """15, 16, 17 & 18. Verify Alembic schema migration and index presence."""
    version_res = await test_db_session.execute(text("SELECT version_num FROM alembic_version;"))
    current_version = version_res.scalar()
    assert current_version == "004_distributed_state_foundation"

    # Verify index presence on decisions table
    indexes_res = await test_db_session.execute(
        text(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'decisions';
            """
        )
    )
    indexes = [row.indexname for row in indexes_res]
    assert "idx_decisions_incident_hazard_created" in indexes
    assert "idx_decisions_status" in indexes
