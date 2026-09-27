"""Initial Phase 6.5B PostgreSQL/PostGIS Schema Migration

Revision ID: 001_initial_phase_6_5b
Revises: 
Create Date: 2026-09-27 08:30:00.000000

Creates core tables (9 tables total):
  1. incidents
  2. telemetry_observations
  3. risk_predictions
  4. shap_records
  5. evacuation_routes
  6. critical_assets
  7. simulations
  8. alerts
  9. audit_events
"""

from typing import Sequence, Union

from alembic import op
import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_phase_6_5b"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. Ensure PostGIS extension exists
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

    # 1. incidents table
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("incident_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sector", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("location_name", sa.String(length=255), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. telemetry_observations table
    op.create_table(
        "telemetry_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", sa.String(length=64), nullable=True),
        sa.Column("data_mode", sa.String(length=32), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rainfall_intensity", sa.Float(), nullable=False),
        sa.Column("rainfall_trend", sa.Float(), nullable=False),
        sa.Column("water_level", sa.Float(), nullable=False),
        sa.Column("water_level_trend", sa.Float(), nullable=False),
        sa.Column("road_congestion", sa.Float(), nullable=False),
        sa.Column("population_exposure", sa.Float(), nullable=False),
        sa.Column("infrastructure_vulnerability", sa.Float(), nullable=False),
        sa.Column("location_name", sa.String(length=255), nullable=True),
        sa.Column(
            "location_geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 3. risk_predictions table
    op.create_table(
        "risk_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", sa.String(length=64), nullable=False),
        sa.Column("telemetry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("horizon_label", sa.String(length=32), nullable=False),
        sa.Column("current_risk", sa.Float(), nullable=False),
        sa.Column("predicted_risk", sa.Float(), nullable=False),
        sa.Column("risk_category", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("prediction_reliability", sa.Float(), nullable=False),
        sa.Column("affected_population", sa.Integer(), nullable=False),
        sa.Column("critical_population", sa.Integer(), nullable=False),
        sa.Column("critical_assets_count", sa.Integer(), nullable=False),
        sa.Column("affected_assets_count", sa.Integer(), nullable=False),
        sa.Column("trend", sa.String(length=64), nullable=False),
        sa.Column("map_status_text", sa.Text(), nullable=False),
        sa.Column("prediction_note", sa.Text(), nullable=False),
        sa.Column("input_features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("heatmap_zones", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["telemetry_id"], ["telemetry_observations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 4. shap_records table
    op.create_table(
        "shap_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_prediction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("prediction", sa.Float(), nullable=False),
        sa.Column("base_value", sa.Float(), nullable=False),
        sa.Column("total_shap_delta", sa.Float(), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decision_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["risk_prediction_id"], ["risk_predictions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("risk_prediction_id"),
    )

    # 5. evacuation_routes table
    op.create_table(
        "evacuation_routes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", sa.String(length=64), nullable=False),
        sa.Column("risk_prediction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("route_name", sa.String(length=128), nullable=False),
        sa.Column("route_type", sa.String(length=32), nullable=False, server_default="primary"),
        sa.Column("is_recommended", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("origin_name", sa.String(length=255), nullable=False),
        sa.Column("origin_lat", sa.Float(), nullable=False),
        sa.Column("origin_lon", sa.Float(), nullable=False),
        sa.Column(
            "origin_geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("destination_name", sa.String(length=255), nullable=False),
        sa.Column("destination_lat", sa.Float(), nullable=False),
        sa.Column("destination_lon", sa.Float(), nullable=False),
        sa.Column(
            "destination_geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column(
            "path_geom",
            geoalchemy2.types.Geometry(
                geometry_type="LINESTRING",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("waypoint_coords", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column("estimated_minutes", sa.Float(), nullable=False),
        sa.Column("safety_score", sa.Float(), nullable=False),
        sa.Column("congestion_index", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("risk_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["risk_prediction_id"], ["risk_predictions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 6. critical_assets table
    op.create_table(
        "critical_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_type", sa.String(length=64), nullable=False),
        sa.Column("sector", sa.String(length=32), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "location_geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.Column("vulnerability", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPERATIONAL"),
        sa.Column("asset_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_code"),
    )
    op.create_index(op.f("ix_critical_assets_asset_code"), "critical_assets", ["asset_code"], unique=True)

    # 7. simulations table
    op.create_table(
        "simulations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", sa.String(length=64), nullable=False),
        sa.Column("evacuation_pace", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("rainfall_multiplier", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("drainage_efficiency", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("route_blockage", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rainfall_increase", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("population_movement", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("water_level_increase", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("baseline_risk", sa.Float(), nullable=False),
        sa.Column("scenario_risk", sa.Float(), nullable=False),
        sa.Column("risk_delta", sa.Float(), nullable=False),
        sa.Column("risk_category", sa.String(length=32), nullable=False),
        sa.Column("prediction_reliability", sa.Float(), nullable=False, server_default="0.95"),
        sa.Column("route_recommendation", sa.String(length=255), nullable=False),
        sa.Column("flagged_assets", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 8. alerts table
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", sa.String(length=64), nullable=False),
        sa.Column("critical_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column(
            "boundary_geom",
            geoalchemy2.types.Geometry(
                geometry_type="POLYGON",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("alert_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["critical_asset_id"], ["critical_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 9. audit_events table
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default="INFO"),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("event_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("alerts")
    op.drop_table("simulations")
    op.drop_index(op.f("ix_critical_assets_asset_code"), table_name="critical_assets")
    op.drop_table("critical_assets")
    op.drop_table("evacuation_routes")
    op.drop_table("shap_records")
    op.drop_table("risk_predictions")
    op.drop_table("telemetry_observations")
    op.drop_table("incidents")
