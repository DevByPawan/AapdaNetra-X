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

    async def list_incidents_paginated(
        self,
        params: Optional[PaginationParams] = None,
        status: Optional[str] = None,
    ) -> PageResult:
        """List incidents using keyset pagination and optional status filter."""
        from app.db.pagination import apply_keyset_pagination, build_page_result, PaginationParams, PageResult

        p = params or PaginationParams()
        stmt = select(Incident)
        if status:
            stmt = stmt.where(Incident.status == status)

        stmt = apply_keyset_pagination(
            stmt=stmt,
            timestamp_col=Incident.started_at,
            id_col=Incident.id,
            params=p,
            id_is_uuid=False,
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return build_page_result(
            items=items,
            limit=p.limit,
            get_timestamp=lambda item: item.started_at,
            get_id=lambda item: item.id,
        )
