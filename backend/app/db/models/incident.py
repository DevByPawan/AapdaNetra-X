"""AapdaNetra-X — Incident ORM Model

Maps the 'incidents' table storing disaster event metadata and location.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Incident(TimestampMixin, Base):
    """Active disaster incident with spatial location."""

    __tablename__ = "incidents"

    # ── Primary Key ──────────────────────────────────────────────────
    # Natural domain ID (e.g. "INC-2026-0909") — VARCHAR, not UUID.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # ── Core Fields ──────────────────────────────────────────────────
    incident_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sector: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)

    # ── Location ─────────────────────────────────────────────────────
    location_name: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geom = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=False,
    )

    # ── Relationships ────────────────────────────────────────────────
    telemetry_observations = relationship(
        "TelemetryObservation", back_populates="incident"
    )
    risk_predictions = relationship(
        "RiskPrediction", back_populates="incident"
    )
    simulations = relationship(
        "Simulation", back_populates="incident"
    )
    alerts = relationship(
        "Alert", back_populates="incident"
    )
    audit_events = relationship(
        "AuditEvent", back_populates="incident"
    )

    def __repr__(self) -> str:
        return f"<Incident id={self.id!r} type={self.incident_type!r} status={self.status!r}>"
