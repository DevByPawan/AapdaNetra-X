"""AapdaNetra-X — Decision Support Repository

Data access layer for Decision ORM model storing active emergency decision recommendations
and lifecycle status transitions (RECOMMENDED -> APPROVED / REJECTED / SUPERSEDED / UNAVAILABLE).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.decision import Decision
from app.db.repositories.base import BaseRepository


class DecisionRepository(BaseRepository[Decision]):
    """Repository managing active emergency decision support recommendation state."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Decision, session)

    async def save_decision(self, decision: Decision) -> Decision:
        """Save a new decision recommendation record and flush."""
        from app.hazards.types import HazardType

        if not decision.hazard_type:
            decision.hazard_type = "flood"
        else:
            if isinstance(decision.hazard_type, HazardType):
                decision.hazard_type = decision.hazard_type.value
            elif isinstance(decision.hazard_type, str):
                try:
                    decision.hazard_type = HazardType(decision.hazard_type.lower()).value
                except ValueError as exc:
                    raise ValueError(f"Unknown or unsupported hazard type: '{decision.hazard_type}'") from exc

        self.session.add(decision)
        await self.session.flush()
        return decision

    async def get_by_id(self, decision_id: str) -> Optional[Decision]:
        """Fetch a decision record by its VARCHAR domain ID."""
        return await super().get_by_id(decision_id)

    async def get_latest_active_decision(
        self, incident_id: str, hazard_type: Optional[str] = None
    ) -> Optional[Decision]:
        """Fetch the most recent decision recommendation for an incident and optional hazard_type."""
        stmt = select(Decision).where(Decision.incident_id == incident_id)
        if hazard_type:
            stmt = stmt.where(Decision.hazard_type == hazard_type)
        stmt = stmt.order_by(Decision.created_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def supersede_previous_recommendations(
        self, incident_id: str, hazard_type: str, exclude_decision_id: Optional[str] = None
    ) -> int:
        """Update any existing RECOMMENDED decisions for this incident & hazard to SUPERSEDED."""
        stmt = (
            update(Decision)
            .where(
                Decision.incident_id == incident_id,
                Decision.hazard_type == hazard_type,
                Decision.status == "RECOMMENDED",
            )
        )
        if exclude_decision_id:
            stmt = stmt.where(Decision.id != exclude_decision_id)
        stmt = stmt.values(status="SUPERSEDED")
        res = await self.session.execute(stmt)
        await self.session.flush()
        return res.rowcount

    async def transition_status(
        self,
        decision_id: str,
        expected_status: str,
        new_status: str,
        reason: Optional[str] = None,
        responder_id: Optional[str] = None,
    ) -> Optional[Decision]:
        """
        Transition decision status atomically from expected_status to new_status.
        Returns the updated Decision object if successful, or None if current status does not match.
        """
        target_id = decision_id

        stmt = (
            update(Decision)
            .where(
                Decision.id == target_id,
                Decision.status == expected_status,
            )
            .values(status=new_status)
            .execution_options(synchronize_session="fetch")
        )
        res = await self.session.execute(stmt)
        if res.rowcount == 0:
            return None

        await self.session.flush()
        dec = await self.get_by_id(target_id)
        if dec and isinstance(dec.payload, dict):
            updated_payload = dict(dec.payload)
            updated_payload["status"] = new_status
            if responder_id:
                updated_payload["action_by"] = responder_id
            if reason:
                updated_payload["action_reason"] = reason
            dec.payload = updated_payload
            await self.session.flush()
        return dec
