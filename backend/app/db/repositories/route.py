"""AapdaNetra-X — Evacuation Route Repository

Data access layer for EvacuationRoute ORM model storing NetworkX risk-optimized routes.
"""

from __future__ import annotations

import uuid
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.route import EvacuationRoute
from app.db.repositories.base import BaseRepository


class EvacuationRouteRepository(BaseRepository[EvacuationRoute]):
    """Repository managing spatial evacuation route options and geometries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(EvacuationRoute, session)

    async def save_route(self, route: EvacuationRoute) -> EvacuationRoute:
        """Save a single evacuation route record and flush."""
        self.session.add(route)
        await self.session.flush()
        return route

    async def save_routes(self, routes: List[EvacuationRoute]) -> List[EvacuationRoute]:
        """Save multiple evacuation routes atomically and flush."""
        self.session.add_all(routes)
        await self.session.flush()
        return routes

    async def get_routes_by_incident(
        self, incident_id: str, limit: int = 20
    ) -> List[EvacuationRoute]:
        """Fetch evacuation routes associated with an incident."""
        stmt = (
            select(EvacuationRoute)
            .where(EvacuationRoute.incident_id == incident_id)
            .order_by(EvacuationRoute.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recommended_route(
        self, incident_id: str
    ) -> Optional[EvacuationRoute]:
        """Fetch the latest recommended evacuation route for an incident."""
        stmt = (
            select(EvacuationRoute)
            .where(
                EvacuationRoute.incident_id == incident_id,
                EvacuationRoute.is_recommended == True,  # noqa: E712
            )
            .order_by(EvacuationRoute.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_history_paginated(
        self,
        incident_id: str,
        params: Optional[PaginationParams] = None,
    ) -> PageResult:
        """Fetch historical evacuation routes using keyset pagination."""
        from app.db.pagination import apply_keyset_pagination, build_page_result, PaginationParams, PageResult

        p = params or PaginationParams()
        stmt = select(EvacuationRoute).where(EvacuationRoute.incident_id == incident_id)

        stmt = apply_keyset_pagination(
            stmt=stmt,
            timestamp_col=EvacuationRoute.created_at,
            id_col=EvacuationRoute.id,
            params=p,
            id_is_uuid=True,
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return build_page_result(
            items=items,
            limit=p.limit,
            get_timestamp=lambda item: item.created_at,
            get_id=lambda item: item.id,
        )
