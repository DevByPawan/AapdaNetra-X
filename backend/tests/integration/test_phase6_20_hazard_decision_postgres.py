"""
AapdaNetra-X — Phase 6.20.9 Real PostgreSQL Decision Audit Integration Test Suite

Executes actual SQL queries against the dedicated 'aapdanetra_test' PostgreSQL database
to verify AuditEvent table writes, reads, hazard_type column persistence, and incident isolation for decisions.
"""

from datetime import datetime, timezone, timedelta
import uuid
import pytest
from geoalchemy2 import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import AuditEvent, Incident
from app.db.repositories.audit import AuditEventRepository
from app.services.decision_service import compute_emergency_decision, transition_decision, STATE_APPROVED

pytestmark = pytest.mark.postgis


@pytest.mark.anyio
async def test_real_postgres_flood_decision_audit_persistence(test_db_session: AsyncSession):
    """
    Verifies actual PostgreSQL writes, reads, hazard_type column persistence,
    and history filtering for Decision AuditEvent records.
    """
    inc_id = f"INC-PG-DEC-{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc)

    # 1. Create incident record
    inc = Incident(
        id=inc_id,
        incident_type="DISASTER",
        status="ACTIVE",
        started_at=now - timedelta(hours=1),
        sector="Sector-Decision",
        severity="HIGH",
        location_name="Test Decision Sector",
        latitude=28.6,
        longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326),
    )
    test_db_session.add(inc)
    await test_db_session.flush()

    audit_repo = AuditEventRepository(test_db_session)

    # 2. Persist real flood decision approval audit event
    saved_audit = await audit_repo.log_event(
        event_type="DECISION_APPROVED",
        severity="INFO",
        source="DecisionRouter",
        description="Emergency flood response plan approved by OPERATOR-01",
        actor="OPERATOR-01",
        event_data={"decision_id": "dec-test-flood-123", "status": "APPROVED"},
        incident_id=inc_id,
        hazard_type="flood",
    )
    assert saved_audit.hazard_type == "flood"


    # 3. Read back from database
    stmt = select(AuditEvent).where(AuditEvent.incident_id == inc_id)
    res = await test_db_session.execute(stmt)
    events_in_db = list(res.scalars().all())
    assert len(events_in_db) == 1
    assert events_in_db[0].hazard_type == "flood"
    assert events_in_db[0].event_type == "DECISION_APPROVED"

    # 4. Verify history pagination with hazard_type filter
    page_flood = await audit_repo.get_history_paginated(incident_id=inc_id, hazard_type="flood")
    assert len(page_flood.items) == 1
    assert page_flood.items[0].hazard_type == "flood"

    page_er = await audit_repo.get_history_paginated(incident_id=inc_id, hazard_type="extreme_rainfall")
    assert len(page_er.items) == 0
