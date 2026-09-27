"""AapdaNetra-X — Incident Repository

Data access layer for Incident ORM model.
"""

from __future__ import annotations

from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.incident import Incident
from app.db.repositories.base import BaseRepository


class IncidentRepository(BaseRepository[Incident]):
    """Repository managing disaster incident records."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Incident, session)

    async def get_by_id(self, incident_id: str) -> Optional[Incident]:
        """Fetch incident by string ID (e.g. 'INC-2026-0927')."""
        return await self.session.get(Incident, incident_id)

    async def get_active_incident(self) -> Optional[Incident]:
        """Fetch current active incident if available."""
        stmt = (
            select(Incident)
            .where(Incident.status == "ACTIVE")
            .order_by(Incident.started_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def save(self, incident: Incident) -> Incident:
        """Add or merge an incident record and flush."""
        merged = await self.session.merge(incident)
        await self.session.flush()
        return merged

    async def list_incidents(self, limit: int = 20) -> List[Incident]:
        """List recent incidents ordered by start time."""
        stmt = select(Incident).order_by(Incident.started_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
