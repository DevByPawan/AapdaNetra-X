"""AapdaNetra-X — SHAP Record Repository

Data access layer for SHAPRecord ORM model storing feature attributions (1:1 with RiskPrediction).
"""

from __future__ import annotations

import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.shap import SHAPRecord
from app.db.repositories.base import BaseRepository


class SHAPRecordRepository(BaseRepository[SHAPRecord]):
    """Repository managing SHAP TreeExplainer feature attribution records."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(SHAPRecord, session)

    async def save_shap_record(self, shap_record: SHAPRecord) -> SHAPRecord:
        """Save a SHAP record tied 1:1 to a RiskPrediction and flush."""
        self.session.add(shap_record)
        await self.session.flush()
        return shap_record

    async def get_by_prediction_id(
        self, risk_prediction_id: uuid.UUID
    ) -> Optional[SHAPRecord]:
        """Fetch SHAP record by associated RiskPrediction ID."""
        stmt = select(SHAPRecord).where(
            SHAPRecord.risk_prediction_id == risk_prediction_id
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
