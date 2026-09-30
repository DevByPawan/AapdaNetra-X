"""Phase 6.20.4 — Add hazard_type persistence column

Revision ID: 003_add_hazard_type_persistence
Revises: 002_postgis_indexes_perf
Create Date: 2026-09-30 00:00:00.000000

Adds non-nullable hazard_type VARCHAR(32) column with server_default 'flood' to:
  1. telemetry_observations
  2. risk_predictions
  3. alerts
  4. evacuation_routes
  5. audit_events
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003_add_hazard_type_persistence"
down_revision: Union[str, None] = "002_postgis_indexes_perf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. telemetry_observations
    op.add_column(
        "telemetry_observations",
        sa.Column(
            "hazard_type",
            sa.String(length=32),
            nullable=False,
            server_default="flood",
        ),
    )

    # 2. risk_predictions
    op.add_column(
        "risk_predictions",
        sa.Column(
            "hazard_type",
            sa.String(length=32),
            nullable=False,
            server_default="flood",
        ),
    )

    # 3. alerts
    op.add_column(
        "alerts",
        sa.Column(
            "hazard_type",
            sa.String(length=32),
            nullable=False,
            server_default="flood",
        ),
    )

    # 4. evacuation_routes
    op.add_column(
        "evacuation_routes",
        sa.Column(
            "hazard_type",
            sa.String(length=32),
            nullable=False,
            server_default="flood",
        ),
    )

    # 5. audit_events
    op.add_column(
        "audit_events",
        sa.Column(
            "hazard_type",
            sa.String(length=32),
            nullable=False,
            server_default="flood",
        ),
    )


def downgrade() -> None:
    op.drop_column("audit_events", "hazard_type")
    op.drop_column("evacuation_routes", "hazard_type")
    op.drop_column("alerts", "hazard_type")
    op.drop_column("risk_predictions", "hazard_type")
    op.drop_column("telemetry_observations", "hazard_type")
