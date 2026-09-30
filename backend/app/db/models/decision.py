"""AapdaNetra-X — Emergency Decision Support ORM Model

Maps the 'decisions' table storing active emergency decision support recommendations
and lifecycle status transitions (RECOMMENDED -> APPROVED / REJECTED / SUPERSEDED / UNAVAILABLE).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Decision(Base):
    """Active emergency decision recommendation and state model."""

    __tablename__ = "decisions"

    # ── Primary Key ──────────────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        String(64), primary_key=True
    )

    # ── Foreign Keys ─────────────────────────────────────────────────
    incident_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Hazard & Status ──────────────────────────────────────────────
    hazard_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="flood", default="flood"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="RECOMMENDED", default="RECOMMENDED"
    )
    priority: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="LOW", default="LOW"
    )
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Recommendation Payload ───────────────────────────────────────
    payload = mapped_column(JSONB, nullable=False, server_default="{}")

    # ── Timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ── Relationships ────────────────────────────────────────────────
    incident = relationship("Incident", back_populates="decisions")

    __table_args__ = (
        Index(
            "idx_decisions_incident_hazard_created",
            "incident_id",
            "hazard_type",
            text("created_at DESC"),
        ),
        Index("idx_decisions_status", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<Decision id={self.id!r} hazard={self.hazard_type!r} "
            f"status={self.status!r} priority={self.priority!r}>"
        )
