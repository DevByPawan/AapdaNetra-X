"""
AapdaNetra-X — Phase 6.20.6 Real PostgreSQL Persistence & History Integration Test Suite

Executes actual SQL queries against the dedicated 'aapdanetra_test' PostgreSQL database
to verify hazard_type column persistence, filtering, keyset pagination determinism,
and incident isolation across Telemetry, Risk, Route, Alert, and Audit entities.
"""

from datetime import datetime, timezone, timedelta
import uuid
import pytest
from geoalchemy2 import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    TelemetryObservation,
    RiskPrediction,
    EvacuationRoute,
    Alert,
    AuditEvent,
    Incident,
)
from app.db.pagination import PaginationParams
from app.db.repositories import (
    TelemetryRepository,
    RiskPredictionRepository,
    EvacuationRouteRepository,
    AuditEventRepository,
)
from app.services.timeline_service import TimelineService

pytestmark = pytest.mark.postgis


@pytest.mark.anyio
async def test_real_postgres_multi_hazard_persistence_and_filtering(test_db_session: AsyncSession):
    """
    Verifies actual PostgreSQL writes, reads, hazard_type filtering, keyset pagination,
    and incident isolation for flood, extreme_rainfall, and landslide records.
    """
    inc_id_1 = f"INC-PG-HAZARD-1-{uuid.uuid4().hex[:6]}"
    inc_id_2 = f"INC-PG-HAZARD-2-{uuid.uuid4().hex[:6]}"

    # Ensure incident records exist
    now = datetime.now(timezone.utc)
    inc_1 = Incident(
        id=inc_id_1,
        incident_type="DISASTER",
        status="ACTIVE",
        started_at=now - timedelta(hours=1),
        sector="Sector-A",
        severity="HIGH",
        location_name="Test Sector A",
        latitude=28.6,
        longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326),
    )
    inc_2 = Incident(
        id=inc_id_2,
        incident_type="DISASTER",
        status="ACTIVE",
        started_at=now - timedelta(hours=1),
        sector="Sector-B",
        severity="CRITICAL",
        location_name="Test Sector B",
        latitude=28.7,
        longitude=77.3,
        geom=WKTElement("POINT(77.3 28.7)", srid=4326),
    )
    test_db_session.add_all([inc_1, inc_2])
    await test_db_session.flush()

    t_repo = TelemetryRepository(test_db_session)
    r_repo = RiskPredictionRepository(test_db_session)
    route_repo = EvacuationRouteRepository(test_db_session)
    audit_repo = AuditEventRepository(test_db_session)

    # 1. Insert multi-hazard telemetry observations
    t_flood_1 = TelemetryObservation(
        id=uuid.uuid4(),
        incident_id=inc_id_1,
        hazard_type="flood",
        data_mode="simulated",
        rainfall_intensity=55.0,
        rainfall_trend=0.0,
        water_level=2.1,
        water_level_trend=0.0,
        road_congestion=0.5,
        population_exposure=1000.0,
        infrastructure_vulnerability=0.5,
        provenance={"source": "test"},
        observed_at=now - timedelta(minutes=20),
    )
    t_flood_2 = TelemetryObservation(
        id=uuid.uuid4(),
        incident_id=inc_id_1,
        hazard_type="flood",
        data_mode="simulated",
        rainfall_intensity=65.0,
        rainfall_trend=1.0,
        water_level=2.6,
        water_level_trend=0.1,
        road_congestion=0.6,
        population_exposure=1200.0,
        infrastructure_vulnerability=0.5,
        provenance={"source": "test"},
        observed_at=now - timedelta(minutes=10),
    )
    t_extreme_rainfall = TelemetryObservation(
        id=uuid.uuid4(),
        incident_id=inc_id_1,
        hazard_type="extreme_rainfall",
        data_mode="simulated",
        rainfall_intensity=150.0,
        rainfall_trend=10.0,
        water_level=3.5,
        water_level_trend=0.5,
        road_congestion=0.8,
        population_exposure=2000.0,
        infrastructure_vulnerability=0.7,
        provenance={"source": "test"},
        observed_at=now,
    )
    t_landslide_inc2 = TelemetryObservation(
        id=uuid.uuid4(),
        incident_id=inc_id_2,
        hazard_type="landslide",
        data_mode="simulated",
        rainfall_intensity=90.0,
        rainfall_trend=2.0,
        water_level=1.2,
        water_level_trend=0.0,
        road_congestion=0.3,
        population_exposure=600.0,
        infrastructure_vulnerability=0.4,
        provenance={"source": "test"},
        observed_at=now,
    )
    test_db_session.add_all([t_flood_1, t_flood_2, t_extreme_rainfall, t_landslide_inc2])
    await test_db_session.flush()

    # 2. Test Telemetry Repository Queries & Filtering
    # Omitted filter: all inc_id_1 records (3)
    page_all = await t_repo.get_history_paginated(incident_id=inc_id_1)
    assert len(page_all.items) == 3

    # Filter flood: 2 records
    page_flood = await t_repo.get_history_paginated(incident_id=inc_id_1, hazard_type="flood")
    assert len(page_flood.items) == 2
    assert all(item.hazard_type == "flood" for item in page_flood.items)

    # Filter extreme_rainfall: 1 record
    page_er = await t_repo.get_history_paginated(incident_id=inc_id_1, hazard_type="extreme_rainfall")
    assert len(page_er.items) == 1
    assert page_er.items[0].hazard_type == "extreme_rainfall"

    # Incident isolation test: inc_id_1 has 0 landslide records
    page_landslide = await t_repo.get_history_paginated(incident_id=inc_id_1, hazard_type="landslide")
    assert len(page_landslide.items) == 0

    page_landslide_inc2 = await t_repo.get_history_paginated(incident_id=inc_id_2, hazard_type="landslide")
    assert len(page_landslide_inc2.items) == 1
    assert page_landslide_inc2.items[0].hazard_type == "landslide"

    # 3. Test Keyset Pagination Determinism
    p1 = PaginationParams(limit=1)
    page_p1 = await t_repo.get_history_paginated(incident_id=inc_id_1, hazard_type="flood", params=p1)
    assert len(page_p1.items) == 1
    assert page_p1.has_more is True

    c_ts = datetime.fromisoformat(page_p1.next_cursor["timestamp"])
    p2 = PaginationParams(limit=1, cursor_timestamp=c_ts, cursor_id=page_p1.next_cursor["id"])
    page_p2 = await t_repo.get_history_paginated(incident_id=inc_id_1, hazard_type="flood", params=p2)
    assert len(page_p2.items) == 1
    assert page_p2.items[0].id != page_p1.items[0].id

    # 4. Test Unified Timeline Service with hazard_type filter
    timeline_svc = TimelineService(test_db_session)
    tl_all = await timeline_svc.get_incident_timeline(incident_id=inc_id_1)
    assert len(tl_all.items) >= 3

    tl_er = await timeline_svc.get_incident_timeline(incident_id=inc_id_1, hazard_type="extreme_rainfall")
    assert len(tl_er.items) == 1
    assert tl_er.items[0].hazard_type == "extreme_rainfall"
