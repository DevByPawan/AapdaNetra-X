"""AapdaNetra-X — Audit Event ORM Model

Maps the 'audit_events' table storing system events, telemetry state changes,
risk alerts, and user/operator action audit trails.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AuditEvent(Base):
    """Immutable audit trail log entry for system and decision support events."""

    __tablename__ = "audit_events"

    # ── Primary Key ──────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Foreign Keys ─────────────────────────────────────────────────
    incident_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Event Details ────────────────────────────────────────────────
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="INFO")
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # ── Structured Data ──────────────────────────────────────────────
    event_data = mapped_column(JSONB, nullable=True)

    # ── Timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationships ────────────────────────────────────────────────
    incident = relationship("Incident", back_populates="audit_events")

    def __repr__(self) -> str:
        return (
            f"<AuditEvent id={self.id!r} type={self.event_type!r} "
            f"severity={self.severity!r}>"
        )
