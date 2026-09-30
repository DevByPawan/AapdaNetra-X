"""AapdaNetra-X — Alert ORM Model

Maps the 'alerts' table storing active emergency warnings, risk notifications,
affected zones (spatial polygons), and critical asset linkages.
"""

from __future__ import annotations

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Alert(TimestampMixin, Base):
    """Emergency alert notification with optional affected zone spatial polygon."""

    __tablename__ = "alerts"

    # ── Primary Key ──────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Foreign Keys ─────────────────────────────────────────────────
    incident_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    critical_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("critical_assets.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Alert Details ────────────────────────────────────────────────
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="OPEN"
    )
    hazard_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="flood", default="flood"
    )

    # ── Spatial Boundary ─────────────────────────────────────────────
    boundary_geom = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326),
        nullable=True,
    )

    # ── Metadata ─────────────────────────────────────────────────────
    alert_metadata = mapped_column(JSONB, nullable=True)

    # ── Relationships ────────────────────────────────────────────────
    incident = relationship("Incident", back_populates="alerts")
    critical_asset = relationship("CriticalAsset", back_populates="alerts")

    def __repr__(self) -> str:
        return (
            f"<Alert id={self.id!r} severity={self.severity!r} "
            f"title={self.title!r} status={self.status!r}>"
        )
