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
        from app.hazards.types import HazardType

        if not observation.hazard_type:
            observation.hazard_type = "flood"
        else:
            if isinstance(observation.hazard_type, HazardType):
                observation.hazard_type = observation.hazard_type.value
            elif isinstance(observation.hazard_type, str):
                try:
                    observation.hazard_type = HazardType(observation.hazard_type.lower()).value
                except ValueError as exc:
                    raise ValueError(f"Unknown or unsupported hazard type: '{observation.hazard_type}'") from exc

        self.session.add(observation)
        await self.session.flush()
        return observation

    async def get_by_fingerprint(self, fingerprint: str) -> Optional[TelemetryObservation]:
        """Fetch telemetry observation by unique fingerprint hash."""
        stmt = (
            select(TelemetryObservation)
            .where(TelemetryObservation.fingerprint == fingerprint)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_latest(
        self, incident_id: Optional[str] = None
    ) -> Optional[TelemetryObservation]:
        """Fetch the most recent telemetry observation."""
        return await self.get_latest_observation(incident_id=incident_id)

    async def get_latest_observation(
        self,
        incident_id: Optional[str] = None,
        hazard_type: Optional[str] = None,
        before_dt: Optional[datetime] = None,
    ) -> Optional[TelemetryObservation]:
        """Fetch the most recent telemetry observation by incident_id, optional hazard_type, and optional before_dt cutoff."""
        stmt = select(TelemetryObservation)
        if incident_id:
            stmt = stmt.where(TelemetryObservation.incident_id == incident_id)
        if hazard_type:
            stmt = stmt.where(TelemetryObservation.hazard_type == hazard_type)
        if before_dt:
            stmt = stmt.where(TelemetryObservation.observed_at < before_dt)
        stmt = stmt.order_by(TelemetryObservation.observed_at.desc(), TelemetryObservation.id.desc()).limit(1)
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

    async def get_history_paginated(
        self,
        incident_id: str,
        params: Optional[PaginationParams] = None,
        hazard_type: Optional[str] = None,
    ) -> PageResult:
        """Fetch time-ordered telemetry observations using keyset pagination."""
        from app.db.pagination import apply_keyset_pagination, build_page_result, PaginationParams, PageResult

        p = params or PaginationParams()
        stmt = select(TelemetryObservation).where(
            TelemetryObservation.incident_id == incident_id
        )
        if hazard_type:
            stmt = stmt.where(TelemetryObservation.hazard_type == hazard_type)

        stmt = apply_keyset_pagination(
            stmt=stmt,
            timestamp_col=TelemetryObservation.observed_at,
            id_col=TelemetryObservation.id,
            params=p,
            id_is_uuid=True,
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return build_page_result(
            items=items,
            limit=p.limit,
            get_timestamp=lambda item: item.observed_at,
            get_id=lambda item: item.id,
        )
