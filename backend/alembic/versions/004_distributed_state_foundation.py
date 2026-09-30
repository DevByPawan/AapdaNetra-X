"""Phase 6.21.1 — Distributed State Foundation Migration

Revision ID: 004_distributed_state_foundation
Revises: 003_add_hazard_type_persistence
Create Date: 2026-09-30 05:30:00.000000

Creates durable decisions table, indexes, and partial unique index on telemetry fingerprint.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "004_distributed_state_foundation"
down_revision: Union[str, None] = "003_add_hazard_type_persistence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create decisions table
    op.create_table(
        "decisions",
        sa.Column(
            "id",
            sa.String(length=64),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            sa.String(length=64),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "hazard_type",
            sa.String(length=32),
            nullable=False,
            server_default="flood",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="RECOMMENDED",
        ),
        sa.Column(
            "priority",
            sa.String(length=32),
            nullable=False,
            server_default="LOW",
        ),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # 2. Indexes on decisions table
    op.create_index(
        "idx_decisions_incident_hazard_created",
        "decisions",
        ["incident_id", "hazard_type", sa.text("created_at DESC")],
    )
    op.create_index("idx_decisions_status", "decisions", ["status"])

    # 3. Add fingerprint column to telemetry_observations
    op.add_column(
        "telemetry_observations",
        sa.Column("fingerprint", sa.String(length=64), nullable=True),
    )

    # 4. Create partial unique index on telemetry_observations (fingerprint) WHERE fingerprint IS NOT NULL
    op.create_index(
        "idx_telemetry_fingerprint_unique",
        "telemetry_observations",
        ["fingerprint"],
        unique=True,
        postgresql_where=sa.text("fingerprint IS NOT NULL"),
    )


def downgrade() -> None:
    # 1. Drop partial unique index and column on telemetry_observations
    op.drop_index(
        "idx_telemetry_fingerprint_unique",
        table_name="telemetry_observations",
        postgresql_where=sa.text("fingerprint IS NOT NULL"),
    )
    op.drop_column("telemetry_observations", "fingerprint")

    # 2. Drop indexes and table decisions
    op.drop_index("idx_decisions_status", table_name="decisions")
    op.drop_index("idx_decisions_incident_hazard_created", table_name="decisions")
    op.drop_table("decisions")
