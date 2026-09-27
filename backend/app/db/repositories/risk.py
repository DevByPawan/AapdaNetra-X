"""AapdaNetra-X — Risk Prediction Repository

Data access layer for RiskPrediction ORM model storing ML GradientBoostingRegressor output.
"""

from __future__ import annotations

import uuid
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.risk import RiskPrediction
from app.db.repositories.base import BaseRepository


class RiskPredictionRepository(BaseRepository[RiskPrediction]):
    """Repository managing ML risk predictions per temporal horizon."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(RiskPrediction, session)

    async def save_prediction(self, prediction: RiskPrediction) -> RiskPrediction:
        """Save a new risk prediction record and flush."""
        self.session.add(prediction)
        await self.session.flush()
        return prediction

    async def get_latest_by_horizon(
        self, incident_id: str, horizon: int
    ) -> Optional[RiskPrediction]:
        """Fetch latest prediction for a specific incident and horizon index (0..3)."""
        stmt = (
            select(RiskPrediction)
            .where(
                RiskPrediction.incident_id == incident_id,
                RiskPrediction.horizon == horizon,
            )
            .order_by(RiskPrediction.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_history(
        self, incident_id: str, limit: int = 50
    ) -> List[RiskPrediction]:
        """Fetch historical risk predictions for an incident."""
        stmt = (
            select(RiskPrediction)
            .where(RiskPrediction.incident_id == incident_id)
            .order_by(RiskPrediction.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
