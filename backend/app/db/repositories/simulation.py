"""AapdaNetra-X — Simulation Repository

Data access layer for Simulation ORM model storing What-If disaster scenario runs.
"""

from __future__ import annotations

import uuid
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.simulation import Simulation
from app.db.repositories.base import BaseRepository


class SimulationRepository(BaseRepository[Simulation]):
    """Repository managing What-If counterfactual disaster simulation records."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Simulation, session)

    async def save_simulation(self, simulation: Simulation) -> Simulation:
        """Save a new simulation run record and flush."""
        self.session.add(simulation)
        await self.session.flush()
        return simulation

    async def get_history_by_incident(
        self, incident_id: str, limit: int = 20
    ) -> List[Simulation]:
        """Fetch simulation history for a given incident."""
        stmt = (
            select(Simulation)
            .where(Simulation.incident_id == incident_id)
            .order_by(Simulation.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
