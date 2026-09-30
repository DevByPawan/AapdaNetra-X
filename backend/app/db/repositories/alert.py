"""AapdaNetra-X — Alert Repository

Data access layer for Alert ORM model.
"""

from __future__ import annotations

import uuid
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert
from app.db.repositories.base import BaseRepository


class AlertRepository(BaseRepository[Alert]):
    """Repository managing emergency warning alert records and spatial boundaries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Alert, session)

    async def save_alert(self, alert: Alert) -> Alert:
        """Save a new alert record and flush."""
        from app.hazards.types import HazardType

        if not alert.hazard_type:
            alert.hazard_type = "flood"
        else:
            if isinstance(alert.hazard_type, HazardType):
                alert.hazard_type = alert.hazard_type.value
            elif isinstance(alert.hazard_type, str):
                try:
                    alert.hazard_type = HazardType(alert.hazard_type.lower()).value
                except ValueError as exc:
                    raise ValueError(f"Unknown or unsupported hazard type: '{alert.hazard_type}'") from exc

        self.session.add(alert)
        await self.session.flush()
        return alert

    async def get_active_alerts(
        self, incident_id: Optional[str] = None
    ) -> List[Alert]:
        """Fetch open emergency alerts."""
        stmt = select(Alert).where(Alert.status == "OPEN")
        if incident_id:
            stmt = stmt.where(Alert.incident_id == incident_id)
        stmt = stmt.order_by(Alert.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(self, alert_id: uuid.UUID, status: str) -> Optional[Alert]:
        """Update status of an alert (e.g. 'OPEN', 'ACKNOWLEDGED', 'RESOLVED')."""
        alert = await self.get_by_id(alert_id)
        if alert:
            alert.status = status
            await self.session.flush()
        return alert
