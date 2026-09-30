"""
AapdaNetra-X — Phase 6.20.7 Real PostgreSQL Alert Persistence & Intelligence Integration Test Suite

Executes actual SQL queries against the dedicated 'aapdanetra_test' PostgreSQL database
to verify Alert table writes, reads, hazard_type column persistence, deduplication,
and lifecycle state transitions across flood, extreme_rainfall, and unsupported hazard types.
"""

from datetime import datetime, timezone, timedelta
import uuid
import pytest
from geoalchemy2 import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import Alert, Incident
from app.db.repositories.alert import AlertRepository
from app.services.alert_engine import IntelligentAlertEngine, STATUS_OPEN, STATUS_ACKNOWLEDGED, STATUS_RESOLVED

pytestmark = pytest.mark.postgis


@pytest.mark.anyio
async def test_real_postgres_hazard_alert_persistence_and_lifecycle(test_db_session: AsyncSession):
    """
    Verifies actual PostgreSQL writes, reads, hazard_type column persistence,
    validation, and status transitions for Alert ORM records.
    """
    inc_id = f"INC-PG-ALT-{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc)

    # 1. Create incident record
    inc = Incident(
        id=inc_id,
        incident_type="DISASTER",
        status="ACTIVE",
        started_at=now - timedelta(hours=1),
        sector="Sector-Alert",
        severity="HIGH",
        location_name="Test Alert Sector",
        latitude=28.6,
        longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326),
    )
    test_db_session.add(inc)
    await test_db_session.flush()

    repo = AlertRepository(test_db_session)

    # 2. Persist explicit flood alert row
    flood_alert = Alert(
        id=uuid.uuid4(),
        incident_id=inc_id,
        severity="HIGH",
        title="Flood Inundation Warning",
        description="High water level observed.",
        status="OPEN",
        hazard_type="flood",
        alert_metadata={"water_level": 6.5},
    )
    saved_flood = await repo.save_alert(flood_alert)
    assert saved_flood.hazard_type == "flood"

    # 3. Persist explicit extreme_rainfall alert row
    er_alert = Alert(
        id=uuid.uuid4(),
        incident_id=inc_id,
        severity="WARNING",
        title="Extreme Rainfall Telemetry Notice",
        description="Heavy rainfall intensity observed.",
        status="OPEN",
        hazard_type="extreme_rainfall",
        alert_metadata={"rainfall_intensity": 105.0},
    )
    saved_er = await repo.save_alert(er_alert)
    assert saved_er.hazard_type == "extreme_rainfall"

    # 4. Verify DB reads by status and hazard_type
    active_alerts = await repo.get_active_alerts(incident_id=inc_id)
    assert len(active_alerts) == 2
    hazards_in_db = {a.hazard_type for a in active_alerts}
    assert "flood" in hazards_in_db
    assert "extreme_rainfall" in hazards_in_db

    # 5. Verify status update lifecycle in PostgreSQL
    updated = await repo.update_status(saved_er.id, "ACKNOWLEDGED")
    assert updated is not None
    assert updated.status == "ACKNOWLEDGED"

    # Query DB directly to verify persistence of status update
    stmt = select(Alert).where(Alert.id == saved_er.id)
    res = await test_db_session.execute(stmt)
    db_row = res.scalar_one()
    assert db_row.status == "ACKNOWLEDGED"
    assert db_row.hazard_type == "extreme_rainfall"


@pytest.mark.anyio
async def test_alert_repository_invalid_hazard_rejection(test_db_session: AsyncSession):
    """Verify AlertRepository rejects unknown or invalid hazard_type strings on save."""
    inc_id = f"INC-PG-ALT-REJ-{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc)
    inc = Incident(
        id=inc_id,
        incident_type="DISASTER",
        status="ACTIVE",
        started_at=now - timedelta(hours=1),
        sector="Sector-Rej",
        severity="HIGH",
        location_name="Test Sector Rej",
        latitude=28.6,
        longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326),
    )
    test_db_session.add(inc)
    await test_db_session.flush()

    repo = AlertRepository(test_db_session)
    alert_bad = Alert(
        id=uuid.uuid4(),
        incident_id=inc_id,
        severity="HIGH",
        title="Invalid Hazard Alert",
        description="Invalid hazard",
        status="OPEN",
        hazard_type="alien_invasion",
    )
    with pytest.raises(ValueError, match="Unknown or unsupported hazard type"):
        await repo.save_alert(alert_bad)
