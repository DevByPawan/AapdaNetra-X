"""AapdaNetra-X — Base Repository

Provides common async SQLAlchemy 2.x operations and session management.
Repository methods do not commit transactions directly; transaction boundaries
are managed by caller services or multi-repository unit-of-work contexts.
"""

from __future__ import annotations

from typing import Generic, Type, TypeVar, Optional, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic async repository base supporting caller-managed transactions."""

    def __init__(self, model: Type[ModelType], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get_by_id(self, id_val: Any) -> Optional[ModelType]:
        """Fetch a record by primary key."""
        result = await self.session.get(self.model, id_val)
        return result

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[ModelType]:
        """Fetch records with pagination."""
        stmt = select(self.model).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add(self, instance: ModelType) -> ModelType:
        """Add an instance to the session and flush to assign generated IDs."""
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def flush(self) -> None:
        """Flush pending changes to the database within current transaction."""
        await self.session.flush()
