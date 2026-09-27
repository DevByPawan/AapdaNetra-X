"""AapdaNetra-X — Critical Asset ORM Model

Maps the 'critical_assets' table storing disaster critical infrastructure,
hospitals, emergency shelters, power stations, and vulnerability scores.
"""

from __future__ import annotations

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import Float, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class CriticalAsset(TimestampMixin, Base):
    """Critical infrastructure asset with PostGIS spatial point location."""

    __tablename__ = "critical_assets"

    # ── Primary Key ──────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Identifiers & Metadata ───────────────────────────────────────
    asset_code: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False)
    sector: Mapped[str] = mapped_column(String(32), nullable=False)

    # ── Location & Spatial ───────────────────────────────────────────
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    location_geom = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=False,
    )

    # ── Status & Vulnerability ───────────────────────────────────────
    vulnerability: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5
    )  # Bounded [0.0, 1.0]
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="OPERATIONAL"
    )

    # ── Structured Attributes ────────────────────────────────────────
    asset_metadata = mapped_column(JSONB, nullable=True)

    # ── Relationships ────────────────────────────────────────────────
    alerts = relationship("Alert", back_populates="critical_asset")

    def __repr__(self) -> str:
        return (
            f"<CriticalAsset code={self.asset_code!r} name={self.name!r} "
            f"type={self.asset_type!r} status={self.status!r}>"
        )
