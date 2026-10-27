"""
Phase 6.22.4 Real-Data Spatial/Temporal Alignment & Quality Validation Unit Tests
Comprehensive tests for spatial alignment matrix, temporal alignment matrix,
7-feature provenance schema, raw dataset immutability, quality checks, and mismatch representations.
"""
import os
import pytest
from app.ml.real_data.provenance import (
    FEATURE_ORDER,
    ProvenanceStatus,
    resolve_data_path,
)
from app.ml.real_data.spatial_alignment import (
    DELHI_STUDY_BBOX,
    build_spatial_alignment_matrix,
    get_era5_spatial_spec,
    get_worldpop_spatial_spec,
    get_ghsl_spatial_spec,
    get_traffic_spatial_spec,
    get_cwc_spatial_spec,
    get_flood_gis_spatial_spec,
)
from app.ml.real_data.temporal_alignment import (
    REFERENCE_STUDY_WINDOW,
    build_temporal_alignment_matrix,
    get_era5_temporal_spec,
    get_worldpop_temporal_spec,
    get_ghsl_temporal_spec,
    get_traffic_temporal_spec,
    get_cwc_temporal_spec,
    get_flood_gis_temporal_spec,
)
from app.ml.real_data.quality import (
    run_all_quality_checks,
    check_raw_files_immutability,
    check_era5_quality,
    check_worldpop_quality,
    check_ghsl_quality,
    check_traffic_quality,
    check_cwc_quality,
    check_feature_assembler_provenance,
    check_spatial_and_temporal_matrices,
)
from app.ml.real_data.alignment import (
    build_real_data_alignment_summary,
    get_feature_provenance_matrix,
)


# ── 1. Spatial Alignment Matrix Tests ─────────────────────────────────────

def test_spatial_alignment_study_bbox_and_specs():
    """
    Proves all 6 datasets intersect the exact Delhi study bbox [77.19-77.26E, 28.61-28.67N]
    and preserve their native resolutions/CRS.
    """
    matrix = build_spatial_alignment_matrix()
    assert matrix.study_bbox == DELHI_STUDY_BBOX
    assert len(matrix.datasets) == 6

    # ERA5 native resolution and grid check
    era5_spec = matrix.datasets["era5"]
    assert era5_spec.intersects_bbox is True
    assert "0.1°" in era5_spec.native_resolution
    assert "EPSG:4326" in era5_spec.crs
    assert "no 100m upsampling" in era5_spec.aggregation_status.lower()

    # WorldPop native resolution and window check
    wp_spec = matrix.datasets["worldpop"]
    assert wp_spec.intersects_bbox is True
    assert "3 arc-seconds" in wp_spec.native_resolution
    assert "EPSG:4326" in wp_spec.crs
    assert wp_spec.details["total_population_sum"] > 1000000.0

    # GHSL native resolution check
    ghsl_spec = matrix.datasets["ghsl"]
    assert ghsl_spec.intersects_bbox is True
    assert "3 arc-seconds" in ghsl_spec.native_resolution
    assert ghsl_spec.details["mapped_to_infrastructure_vulnerability"] is False

    # Traffic spatial check
    tr_spec = matrix.datasets["traffic"]
    assert tr_spec.intersects_bbox is True
    assert tr_spec.details["intersections_count"] == 3

    # CWC gauge station point location check
    cwc_spec = matrix.datasets["cwc"]
    assert cwc_spec.intersects_bbox is True
    assert "#011-MDNDEL" in cwc_spec.details["station_code"]

    # Flood GIS KML extent check
    gis_spec = matrix.datasets["flood_gis"]
    assert gis_spec.intersects_bbox is True
    assert gis_spec.details["kml_files_count"] == 4
    assert gis_spec.details["total_bbox_intersections"] > 0
    assert "SPATIAL_EVENT_VALIDATION" in gis_spec.aggregation_status


# ── 2. Temporal Alignment Matrix Tests ────────────────────────────────────

def test_temporal_alignment_matrices_and_mismatches():
    """
    Proves dataset temporal coverage mismatches are explicitly represented
    without forcing datasets onto a fake common date.
    """
    matrix = build_temporal_alignment_matrix()
    assert matrix.reference_study_window == REFERENCE_STUDY_WINDOW
    assert len(matrix.datasets) == 6

    era5 = matrix.datasets["era5"]
    assert era5.is_july2023_telemetry is True
    assert era5.details["total_hourly_timestamps"] == 744

    wp = matrix.datasets["worldpop"]
    assert wp.is_july2023_telemetry is False
    assert wp.source_year == 2020

    ghsl = matrix.datasets["ghsl"]
    assert ghsl.is_july2023_telemetry is False
    assert ghsl.source_year == 2020
    assert ghsl.details["mapped_to_infrastructure_vulnerability"] is False

    traffic = matrix.datasets["traffic"]
    assert traffic.is_july2023_telemetry is False
    assert traffic.source_year == 2020
    assert "Delhi 2020 empirical baseline" in traffic.temporal_context_label

    cwc = matrix.datasets["cwc"]
    assert cwc.is_july2023_telemetry is True
    assert cwc.details["continuous_timeline_created"] is False

    gis = matrix.datasets["flood_gis"]
    assert gis.is_july2023_telemetry is True
    assert gis.details["classification"] == "SPATIAL_EVENT_VALIDATION"


# ── 3. Feature Provenance Matrix Tests ────────────────────────────────────

def test_feature_provenance_matrix_and_ghsl_isolation():
    """
    Proves all 7 ML features have explicit typed provenance statuses,
    and GHSL built_up_surface_m2 is kept separate from infrastructure_vulnerability.
    """
    prov_matrix = get_feature_provenance_matrix()
    features = prov_matrix["features"]

    assert list(features.keys()) == FEATURE_ORDER

    assert features["rainfall_intensity"]["provenance_status"] == ProvenanceStatus.DERIVED_FROM_REAL.value
    assert features["water_level"]["provenance_status"] == ProvenanceStatus.OFFICIAL_EVENT_ONLY.value
    assert features["road_congestion"]["provenance_status"] == ProvenanceStatus.DERIVED_FROM_REAL.value
    assert features["population_exposure"]["provenance_status"] == ProvenanceStatus.DERIVED_FROM_REAL.value
    assert features["infrastructure_vulnerability"]["provenance_status"] == ProvenanceStatus.PROVISIONAL.value

    # Critical scientific check: GHSL MUST NOT be assigned to infrastructure_vulnerability
    extra = prov_matrix["extra_contextual_features"]
    assert "built_up_surface_m2" in extra
    assert extra["built_up_surface_m2"]["mapped_to_infrastructure_vulnerability"] is False


# ── 4. Quality Check Suite Tests ──────────────────────────────────────────

def test_quality_checks_all_pass():
    """
    Executes all 8 data quality checks and asserts 100% pass rate.
    """
    report = run_all_quality_checks()
    assert report.overall_passed is True, f"Quality check failures: {[c for c in report.check_results if not c.passed]}"
    assert report.passed_checks_count == report.total_checks
    assert report.failed_checks_count == 0


def test_raw_files_immutability_check():
    res = check_raw_files_immutability()
    assert res.passed is True
    assert len(res.details["missing"]) == 0


def test_era5_quality_check():
    res = check_era5_quality()
    assert res.passed is True
    assert res.details["total_timestamps"] == 744
    assert res.details["negative_values_count"] == 0
    assert res.details["nan_or_inf_count"] == 0
    assert abs(res.details["boundary_rainfall_july1_00"] - 1.4621) < 1e-3


def test_worldpop_quality_check():
    res = check_worldpop_quality()
    assert res.passed is True
    assert res.details["total_study_bbox_population"] > 1000000.0


def test_ghsl_quality_check():
    res = check_ghsl_quality()
    assert res.passed is True
    assert res.details["mapped_to_infrastructure_vulnerability"] is False


def test_traffic_quality_check():
    res = check_traffic_quality()
    assert res.passed is True
    assert res.details["is_july2023_flood_traffic"] is False
    assert "2020" in res.details["temporal_context"]


def test_cwc_quality_check():
    res = check_cwc_quality()
    assert res.passed is True
    assert res.details["peak_water_level_m"] == 4.66
    assert res.details["unobserved_water_level"] is None


# ── 5. Unified Alignment Summary Test ────────────────────────────────────

def test_unified_alignment_summary_output():
    """
    Proves build_real_data_alignment_summary produces a complete, isolated,
    deterministic machine-readable alignment structure.
    """
    summary = build_real_data_alignment_summary()
    assert summary["study_area_bbox"] == DELHI_STUDY_BBOX
    assert "spatial_alignment_matrix" in summary
    assert "temporal_alignment_matrix" in summary
    assert "feature_provenance_matrix" in summary
    assert summary["quality_validation_report"]["overall_passed"] is True
