"""AapdaNetra-X — Audit Event Repository

Data access layer for AuditEvent ORM model providing append-oriented audit log creation.
"""

from __future__ import annotations

import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditEvent
from app.db.repositories.base import BaseRepository


class AuditEventRepository(BaseRepository[AuditEvent]):
    """Repository managing append-only immutable system audit logs."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AuditEvent, session)

    async def log_event(
        self,
        event_type: str,
        severity: str,
        source: str,
        description: str,
        actor: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
        incident_id: Optional[str] = None,
        hazard_type: Optional[str] = None,
    ) -> AuditEvent:
        """Append a new audit event record and flush."""
        from app.hazards.types import HazardType

        if hazard_type is not None:
            if isinstance(hazard_type, HazardType):
                h_val = hazard_type.value
            elif isinstance(hazard_type, str):
                try:
                    h_val = HazardType(hazard_type.lower()).value
                except ValueError as exc:
                    raise ValueError(f"Unknown or unsupported hazard type: '{hazard_type}'") from exc
            else:
                raise ValueError(f"Unknown or unsupported hazard type: '{hazard_type}'")
        else:
            h_val = "flood"

        event = AuditEvent(
            id=uuid.uuid4(),
            incident_id=incident_id,
            event_type=event_type,
            severity=severity,
            source=source,
            description=description,
            actor=actor,
            event_data=event_data,
            hazard_type=h_val,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_incident(
        self, incident_id: str, limit: int = 50
    ) -> List[AuditEvent]:
        """Fetch audit events associated with a specific incident."""
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.incident_id == incident_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_events(self, limit: int = 50) -> List[AuditEvent]:
        """Fetch recent audit events across the platform."""
        stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_history_paginated(
        self,
        incident_id: Optional[str] = None,
        params: Optional[PaginationParams] = None,
        hazard_type: Optional[str] = None,
    ) -> PageResult:
        """Fetch audit events using keyset pagination."""
        from app.db.pagination import apply_keyset_pagination, build_page_result, PaginationParams, PageResult

        p = params or PaginationParams()
        stmt = select(AuditEvent)
        if incident_id:
            stmt = stmt.where(AuditEvent.incident_id == incident_id)

        if hazard_type:
            stmt = stmt.where(AuditEvent.hazard_type == hazard_type)

        stmt = apply_keyset_pagination(
            stmt=stmt,
            timestamp_col=AuditEvent.created_at,
            id_col=AuditEvent.id,
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
