"""AapdaNetra-X — Risk Prediction ORM Model

Maps the 'risk_predictions' table storing ML GradientBoostingRegressor
prediction results for each temporal horizon index (0=NOW through 3=+30M).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RiskPrediction(Base):
    """ML risk assessment result for a specific incident + horizon."""

    __tablename__ = "risk_predictions"

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
    telemetry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("telemetry_observations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Horizon ──────────────────────────────────────────────────────
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    horizon_label: Mapped[str] = mapped_column(String(32), nullable=False)
    hazard_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="flood", default="flood"
    )

    # ── Prediction Results ───────────────────────────────────────────
    current_risk: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_risk: Mapped[float] = mapped_column(Float, nullable=False)
    risk_category: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    prediction_reliability: Mapped[float] = mapped_column(Float, nullable=False)

    # ── Population & Asset Impact ────────────────────────────────────
    affected_population: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_population: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_assets_count: Mapped[int] = mapped_column(Integer, nullable=False)
    affected_assets_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Descriptive ──────────────────────────────────────────────────
    trend: Mapped[str] = mapped_column(String(64), nullable=False)
    map_status_text: Mapped[str] = mapped_column(Text, nullable=False)
    prediction_note: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Structured Data ──────────────────────────────────────────────
    input_features = mapped_column(JSONB, nullable=False)
    heatmap_zones = mapped_column(JSONB, nullable=False)

    # ── Timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationships ────────────────────────────────────────────────
    incident = relationship("Incident", back_populates="risk_predictions")
    telemetry = relationship(
        "TelemetryObservation", back_populates="risk_predictions"
    )
    shap_record = relationship(
        "SHAPRecord", back_populates="risk_prediction", uselist=False
    )
    evacuation_routes = relationship(
        "EvacuationRoute", back_populates="risk_prediction"
    )

    def __repr__(self) -> str:
        return (
            f"<RiskPrediction id={self.id!r} horizon={self.horizon} "
            f"risk={self.predicted_risk}>"
        )
