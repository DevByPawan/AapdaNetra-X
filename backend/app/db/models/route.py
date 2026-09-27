"""AapdaNetra-X — Evacuation Route ORM Model

Maps the 'evacuation_routes' table storing spatial route geometries,
waypoints, distance, estimated travel time, and safety scores.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EvacuationRoute(Base):
    """Evacuation route between origin and destination with PostGIS LineString."""

    __tablename__ = "evacuation_routes"

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
    risk_prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("risk_predictions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Route Metadata ───────────────────────────────────────────────
    route_name: Mapped[str] = mapped_column(String(128), nullable=False)
    route_type: Mapped[str] = mapped_column(String(32), nullable=False, default="primary")
    is_recommended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── Origin & Destination Details ────────────────────────────────
    origin_name: Mapped[str] = mapped_column(String(255), nullable=False)
    origin_lat: Mapped[float] = mapped_column(Float, nullable=False)
    origin_lon: Mapped[float] = mapped_column(Float, nullable=False)
    origin_geom = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True,
    )

    destination_name: Mapped[str] = mapped_column(String(255), nullable=False)
    destination_lat: Mapped[float] = mapped_column(Float, nullable=False)
    destination_lon: Mapped[float] = mapped_column(Float, nullable=False)
    destination_geom = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True,
    )

    # ── Path & Spatial Geometry ──────────────────────────────────────
    path_geom = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326),
        nullable=True,
    )
    waypoint_coords = mapped_column(JSONB, nullable=False)

    # ── Dynamic Attributes ───────────────────────────────────────────
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    safety_score: Mapped[float] = mapped_column(Float, nullable=False)
    congestion_index: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    risk_summary = mapped_column(JSONB, nullable=True)

    # ── Timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationships ────────────────────────────────────────────────
    incident = relationship("Incident")
    risk_prediction = relationship(
        "RiskPrediction", back_populates="evacuation_routes"
    )

    def __repr__(self) -> str:
        return (
            f"<EvacuationRoute id={self.id!r} name={self.route_name!r} "
            f"distance={self.distance_km}km score={self.safety_score}>"
        )
