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
        from app.hazards.types import HazardType

        if not prediction.hazard_type:
            prediction.hazard_type = "flood"
        else:
            if isinstance(prediction.hazard_type, HazardType):
                prediction.hazard_type = prediction.hazard_type.value
            elif isinstance(prediction.hazard_type, str):
                try:
                    prediction.hazard_type = HazardType(prediction.hazard_type.lower()).value
                except ValueError as exc:
                    raise ValueError(f"Unknown or unsupported hazard type: '{prediction.hazard_type}'") from exc

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

    async def get_history_paginated(
        self,
        incident_id: str,
        horizon: Optional[int] = None,
        params: Optional[PaginationParams] = None,
        hazard_type: Optional[str] = None,
    ) -> PageResult:
        """Fetch historical risk predictions using keyset pagination."""
        from app.db.pagination import apply_keyset_pagination, build_page_result, PaginationParams, PageResult

        p = params or PaginationParams()
        stmt = select(RiskPrediction).where(RiskPrediction.incident_id == incident_id)

        if horizon is not None:
            stmt = stmt.where(RiskPrediction.horizon == horizon)

        if hazard_type:
            stmt = stmt.where(RiskPrediction.hazard_type == hazard_type)

        stmt = apply_keyset_pagination(
            stmt=stmt,
            timestamp_col=RiskPrediction.created_at,
            id_col=RiskPrediction.id,
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
