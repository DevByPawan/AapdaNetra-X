"""AapdaNetra-X — Telemetry Observation ORM Model

Maps the 'telemetry_observations' table storing time-series
hydro-meteorological sensor readings and per-feature provenance.

The 7 feature columns mirror the frozen ML feature contract exactly:
  rainfall_intensity, rainfall_trend, water_level, water_level_trend,
  road_congestion, population_exposure, infrastructure_vulnerability
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TelemetryObservation(Base):
    """A single telemetry snapshot with all 7 ML features and provenance metadata."""

    __tablename__ = "telemetry_observations"

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

    # ── Data Mode & Fallback ─────────────────────────────────────────
    data_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    fallback_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # ── 7-Feature ML Contract (frozen) ───────────────────────────────
    rainfall_intensity: Mapped[float] = mapped_column(Float, nullable=False)
    rainfall_trend: Mapped[float] = mapped_column(Float, nullable=False)
    water_level: Mapped[float] = mapped_column(Float, nullable=False)
    water_level_trend: Mapped[float] = mapped_column(Float, nullable=False)
    road_congestion: Mapped[float] = mapped_column(Float, nullable=False)
    population_exposure: Mapped[float] = mapped_column(Float, nullable=False)
    infrastructure_vulnerability: Mapped[float] = mapped_column(
        Float, nullable=False
    )

    # ── Location (optional — sensor station position) ────────────────
    location_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    location_geom = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True,
    )

    # ── Provenance & Metadata ────────────────────────────────────────
    provenance = mapped_column(JSONB, nullable=False)
    provider_metadata = mapped_column(JSONB, nullable=True)

    # ── Timestamps ───────────────────────────────────────────────────
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationships ────────────────────────────────────────────────
    incident = relationship("Incident", back_populates="telemetry_observations")
    risk_predictions = relationship(
        "RiskPrediction", back_populates="telemetry"
    )

    def __repr__(self) -> str:
        return f"<TelemetryObservation id={self.id!r} mode={self.data_mode!r}>"
