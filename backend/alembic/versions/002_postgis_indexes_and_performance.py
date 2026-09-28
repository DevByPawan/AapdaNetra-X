"""Phase 6.7B — PostGIS Spatial, Foreign Key, and Keyset Pagination Indexes

Revision ID: 002_postgis_indexes_perf
Revises: 001_initial_phase_6_5b
Create Date: 2026-09-27 10:15:00.000000

Creates optimal indexes across domain entities (14 new indexes total):
  1. Spatial GIST indexes (5 geometry columns)
  2. Foreign Key B-tree indexes (3 non-leading FK relationships)
  3. Keyset & History Composite B-tree indexes (6 entity tables, serving both pagination and incident_id FK lookups)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002_postgis_indexes_perf"
down_revision: Union[str, None] = "001_initial_phase_6_5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Spatial GIST Indexes (5 indexes) ──────────────────────────────
    op.create_index(
        "ix_incidents_geom",
        "incidents",
        ["geom"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_telemetry_location_geom",
        "telemetry_observations",
        ["location_geom"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_routes_path_geom",
        "evacuation_routes",
        ["path_geom"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_assets_location_geom",
        "critical_assets",
        ["location_geom"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_alerts_boundary_geom",
        "alerts",
        ["boundary_geom"],
        unique=False,
        postgresql_using="gist",
    )

    # ── 2. Standalone Non-Leading Foreign Key B-Tree Indexes (3 indexes) ─
    # Note: FKs on incident_id are covered by the composite pagination indexes below.
    op.create_index(
        "ix_risk_predictions_telemetry_id",
        "risk_predictions",
        ["telemetry_id"],
        unique=False,
    )
    op.create_index(
        "ix_evacuation_routes_risk_prediction_id",
        "evacuation_routes",
        ["risk_prediction_id"],
        unique=False,
    )
    op.create_index(
        "ix_alerts_critical_asset_id",
        "alerts",
        ["critical_asset_id"],
        unique=False,
    )

    # ── 3. Keyset / History Composite B-Tree Indexes (6 indexes) ─────────
    op.create_index(
        "ix_telemetry_pagination",
        "telemetry_observations",
        ["incident_id", sa.text("observed_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_risk_pagination",
        "risk_predictions",
        ["incident_id", sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_routes_pagination",
        "evacuation_routes",
        ["incident_id", sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_alerts_pagination",
        "alerts",
        ["incident_id", sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_simulations_pagination",
        "simulations",
        ["incident_id", sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_audit_pagination",
        "audit_events",
        ["incident_id", sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
    )


def downgrade() -> None:
    # ── 3. Drop Keyset / History Composite Indexes ─────────────────────
    op.drop_index("ix_audit_pagination", table_name="audit_events")
    op.drop_index("ix_simulations_pagination", table_name="simulations")
    op.drop_index("ix_alerts_pagination", table_name="alerts")
    op.drop_index("ix_routes_pagination", table_name="evacuation_routes")
    op.drop_index("ix_risk_pagination", table_name="risk_predictions")
    op.drop_index("ix_telemetry_pagination", table_name="telemetry_observations")

    # ── 2. Drop Standalone Foreign Key Indexes ──────────────────────────
    op.drop_index("ix_alerts_critical_asset_id", table_name="alerts")
    op.drop_index("ix_evacuation_routes_risk_prediction_id", table_name="evacuation_routes")
    op.drop_index("ix_risk_predictions_telemetry_id", table_name="risk_predictions")

    # ── 1. Drop Spatial GIST Indexes ────────────────────────────────────
    op.drop_index("ix_alerts_boundary_geom", table_name="alerts")
    op.drop_index("ix_assets_location_geom", table_name="critical_assets")
    op.drop_index("ix_routes_path_geom", table_name="evacuation_routes")
    op.drop_index("ix_telemetry_location_geom", table_name="telemetry_observations")
    op.drop_index("ix_incidents_geom", table_name="incidents")
