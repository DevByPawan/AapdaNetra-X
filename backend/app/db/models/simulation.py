"""AapdaNetra-X — Simulation ORM Model

Maps the 'simulations' table storing What-If scenario inputs, baseline risks,
simulated scenario risks, risk deltas, flagged assets, and narratives.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Simulation(TimestampMixin, Base):
    """What-If disaster risk simulation run result tied to an Incident."""

    __tablename__ = "simulations"

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

    # ── What-If Input Parameters ─────────────────────────────────────
    evacuation_pace: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    rainfall_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    drainage_efficiency: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    route_blockage: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rainfall_increase: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    population_movement: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    water_level_increase: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # ── Simulation Output Metrics ────────────────────────────────────
    baseline_risk: Mapped[float] = mapped_column(Float, nullable=False)
    scenario_risk: Mapped[float] = mapped_column(Float, nullable=False)
    risk_delta: Mapped[float] = mapped_column(Float, nullable=False)
    risk_category: Mapped[str] = mapped_column(String(32), nullable=False)
    prediction_reliability: Mapped[float] = mapped_column(Float, nullable=False, default=0.95)

    # ── Operational Guidance & Findings ──────────────────────────────
    route_recommendation: Mapped[str] = mapped_column(String(255), nullable=False)
    flagged_assets = mapped_column(JSONB, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)

    # ── Relationships ────────────────────────────────────────────────
    incident = relationship("Incident", back_populates="simulations")

    def __repr__(self) -> str:
        return (
            f"<Simulation id={self.id!r} incident_id={self.incident_id!r} "
            f"baseline={self.baseline_risk} scenario={self.scenario_risk}>"
        )
