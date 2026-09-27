"""AapdaNetra-X — Telemetry Repository

Data access layer for TelemetryObservation ORM model, strictly enforcing
the frozen 7-feature ML schema and provenance metadata.
"""

from __future__ import annotations

import uuid
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.telemetry import TelemetryObservation
from app.db.repositories.base import BaseRepository


class TelemetryRepository(BaseRepository[TelemetryObservation]):
    """Repository managing time-series hydro-meteorological sensor observations."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TelemetryObservation, session)

    async def create_observation(
        self, observation: TelemetryObservation
    ) -> TelemetryObservation:
        """Persist a new telemetry snapshot with all 7 ML features and flush."""
        self.session.add(observation)
        await self.session.flush()
        return observation

    async def get_latest(
        self, incident_id: Optional[str] = None
    ) -> Optional[TelemetryObservation]:
        """Fetch the most recent telemetry observation."""
        stmt = select(TelemetryObservation)
        if incident_id:
            stmt = stmt.where(TelemetryObservation.incident_id == incident_id)
        stmt = stmt.order_by(TelemetryObservation.observed_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_history_by_incident(
        self, incident_id: str, limit: int = 50
    ) -> List[TelemetryObservation]:
        """Fetch time-ordered telemetry observations for an incident."""
        stmt = (
            select(TelemetryObservation)
            .where(TelemetryObservation.incident_id == incident_id)
            .order_by(TelemetryObservation.observed_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
