"""AapdaNetra-X — SHAP Record ORM Model

Maps the 'shap_records' table storing SHAP TreeExplainer feature
attribution breakdowns. One-to-one relationship with risk_predictions.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SHAPRecord(Base):
    """SHAP feature attribution snapshot tied 1:1 to a RiskPrediction."""

    __tablename__ = "shap_records"

    # ── Primary Key ──────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Foreign Keys ─────────────────────────────────────────────────
    risk_prediction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("risk_predictions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # ── Core SHAP Values ─────────────────────────────────────────────
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    prediction: Mapped[float] = mapped_column(Float, nullable=False)
    base_value: Mapped[float] = mapped_column(Float, nullable=False)
    total_shap_delta: Mapped[float] = mapped_column(Float, nullable=False)

    # ── Structured Feature Attribution Data ──────────────────────────
    features = mapped_column(JSONB, nullable=False)
    decision_trace = mapped_column(JSONB, nullable=False)

    # ── Timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationships ────────────────────────────────────────────────
    risk_prediction = relationship(
        "RiskPrediction", back_populates="shap_record"
    )

    def __repr__(self) -> str:
        return (
            f"<SHAPRecord id={self.id!r} prediction={self.prediction} "
            f"base_value={self.base_value}>"
        )
