"""
AapdaNetra-X — Phase 6.20.8 Real PostgreSQL Evacuation Route Integration Test Suite

Executes actual SQL queries against the dedicated 'aapdanetra_test' PostgreSQL database
to verify EvacuationRoute table writes, reads, hazard_type column persistence, and pagination.
"""

from datetime import datetime, timezone, timedelta
import uuid
import pytest
from geoalchemy2 import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import EvacuationRoute, Incident
from app.db.repositories.route import EvacuationRouteRepository

pytestmark = pytest.mark.postgis


@pytest.mark.anyio
async def test_real_postgres_hazard_evacuation_route_persistence(test_db_session: AsyncSession):
    """
    Verifies actual PostgreSQL writes, reads, hazard_type column persistence,
    and history pagination filtering for EvacuationRoute ORM records.
    """
    inc_id = f"INC-PG-ROUTE-{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc)

    # 1. Create incident record
    inc = Incident(
        id=inc_id,
        incident_type="DISASTER",
        status="ACTIVE",
        started_at=now - timedelta(hours=1),
        sector="Sector-Route",
        severity="HIGH",
        location_name="Test Route Sector",
        latitude=28.6,
        longitude=77.2,
        geom=WKTElement("POINT(77.2 28.6)", srid=4326),
    )
    test_db_session.add(inc)
    await test_db_session.flush()

    repo = EvacuationRouteRepository(test_db_session)

    # 2. Persist real flood evacuation route
    flood_route = EvacuationRoute(
        id=uuid.uuid4(),
        incident_id=inc_id,
        route_name="Route Alpha (Primary Evacuation)",
        origin_name="Sector-Route Origin",
        origin_lat=28.6,
        origin_lon=77.2,
        destination_name="Sector-Route Shelter",
        destination_lat=28.7,
        destination_lon=77.3,
        waypoint_coords=[{"lat": 28.6, "lng": 77.2}, {"lat": 28.7, "lng": 77.3}],
        distance_km=12.5,
        estimated_minutes=25.0,
        safety_score=0.85,
        is_recommended=True,
        hazard_type="flood",
        path_geom=WKTElement("LINESTRING(77.2 28.6, 77.25 28.65, 77.3 28.7)", srid=4326),
        risk_summary={"water_level": 2.5},
    )
    saved_route = await repo.save_route(flood_route)
    assert saved_route.hazard_type == "flood"

    # 3. Read back from database
    routes_in_db = await repo.get_routes_by_incident(incident_id=inc_id)
    assert len(routes_in_db) == 1
    assert routes_in_db[0].hazard_type == "flood"
    assert routes_in_db[0].is_recommended is True

    # 4. Verify history pagination with hazard_type filter
    page_flood = await repo.get_history_paginated(incident_id=inc_id, hazard_type="flood")
    assert len(page_flood.items) == 1
    assert page_flood.items[0].hazard_type == "flood"

    page_er = await repo.get_history_paginated(incident_id=inc_id, hazard_type="extreme_rainfall")
    assert len(page_er.items) == 0


@pytest.mark.anyio
async def test_alert_repository_invalid_hazard_route_rejection(test_db_session: AsyncSession):
    """Verify EvacuationRouteRepository rejects invalid hazard_type strings on save."""
    inc_id = f"INC-PG-RREJ-{uuid.uuid4().hex[:6]}"
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

    repo = EvacuationRouteRepository(test_db_session)
    route_bad = EvacuationRoute(
        id=uuid.uuid4(),
        incident_id=inc_id,
        route_name="Bad Route",
        origin_name="Origin",
        origin_lat=28.6,
        origin_lon=77.2,
        destination_name="Destination",
        destination_lat=28.7,
        destination_lon=77.3,
        waypoint_coords=[],
        distance_km=5.0,
        estimated_minutes=10.0,
        safety_score=0.5,
        hazard_type="space_debris",
    )
    with pytest.raises(ValueError, match="Unknown or unsupported hazard type"):
        await repo.save_route(route_bad)
