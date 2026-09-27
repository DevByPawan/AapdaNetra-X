"""AapdaNetra-X — Critical Asset Repository

Data access layer for CriticalAsset ORM model.
"""

from __future__ import annotations

import uuid
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset import CriticalAsset
from app.db.repositories.base import BaseRepository


class CriticalAssetRepository(BaseRepository[CriticalAsset]):
    """Repository managing critical infrastructure assets and spatial locations."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(CriticalAsset, session)

    async def save_asset(self, asset: CriticalAsset) -> CriticalAsset:
        """Add or update a critical asset record and flush."""
        merged = await self.session.merge(asset)
        await self.session.flush()
        return merged

    async def get_by_code(self, asset_code: str) -> Optional[CriticalAsset]:
        """Fetch critical asset by unique asset_code."""
        stmt = select(CriticalAsset).where(CriticalAsset.asset_code == asset_code)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all_assets(self, limit: int = 100) -> List[CriticalAsset]:
        """Fetch all critical assets up to limit."""
        stmt = select(CriticalAsset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_sector(self, sector: str) -> List[CriticalAsset]:
        """Fetch critical assets belonging to a specific sector."""
        stmt = select(CriticalAsset).where(CriticalAsset.sector == sector)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
