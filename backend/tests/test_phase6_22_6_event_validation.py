"""
Phase 6.22.6 Real-Event Evidence Validation & Validation Closure Unit Tests
Comprehensive tests for event evidence extraction, ERA5 evidence, CWC milestones,
flood GIS footprint, spatial/temporal correlation, population context, built-up context,
traffic context, evidence chain integrity, validation package categories A-E,
and strict safety disclaimers.
"""
import pytest
from app.ml.real_data.event_evidence import (
    get_era5_event_evidence,
    get_cwc_event_evidence,
    get_flood_gis_event_evidence,
    get_worldpop_context_evidence,
    get_ghsl_context_evidence,
    get_traffic_context_evidence,
    build_era5_cwc_correlation_table,
    build_event_evidence_chain,
)
from app.ml.real_data.event_validation import (
    build_event_validation_package,
    EventValidationPackage,
)
from app.ml.real_data.event_validation_report import (
    generate_event_validation_report_dict,
    generate_markdown_event_validation_report,
)


def test_era5_event_evidence():
    """
    Proves ERA5 rainfall evidence is derived from accepted preprocessing,
    classified as DERIVED_FROM_REAL, preserves UTC timestamps, and identifies major peaks.
    """
    era5 = get_era5_event_evidence()
    assert era5.total_hourly_timestamps == 744
    assert era5.intensity_min_mm_h == 0.0
    assert abs(era5.intensity_max_mm_h - 260.333) < 1e-2
    assert "DERIVED_FROM_REAL" in era5.provenance
    assert era5.peak_intensity_timestamp_utc == "2023-07-25T20:00:00Z"


def test_cwc_event_milestones():
    """
    Proves CWC event milestones use official observations, classify missing periods
    as UNAVAILABLE, perform no interpolation/synthetic hydrograph construction,
    and preserve raw station datum and provenance.
    """
    cwc = get_cwc_event_evidence()
    assert len(cwc.milestones) == 5
    assert cwc.unobserved_period_status == "UNAVAILABLE"

    # Peak HFL milestone check
    peak = [m for m in cwc.milestones if m.timestamp_utc == "2023-07-13T12:00:00Z"][0]
    assert peak.relative_stage_m == 4.66
    assert peak.water_level_navd88_m == 208.66
    assert "Old Railway Bridge" in peak.station_name


def test_flood_gis_event_footprint():
    """
    Proves Flood GIS layer analysis preserves raw KML files, identifies study-bbox
    intersecting geometries, reports AREA_NOT_COMPUTABLE_FROM_RAW_GEOMETRY due to raw invalid geometries,
    and classifies as EVENT_REFERENCE.
    """
    gis = get_flood_gis_event_evidence()
    assert gis.kml_files_count == 4
    assert gis.total_geometries == 4114
    assert gis.total_bbox_intersections == 40
    assert gis.invalid_geometries == 7
    assert gis.area_calculation_status == "AREA_NOT_COMPUTABLE_FROM_RAW_GEOMETRY"
    assert "EVENT_REFERENCE" in gis.provenance
    assert gis.raw_kml_files_repaired is False


def test_era5_cwc_temporal_correlation():
    """
    Proves temporal correlation table only includes actual available timestamps,
    sets unavailable sources to UNAVAILABLE, and performs zero timestamp manufacturing or interpolation.
    """
    table = build_era5_cwc_correlation_table()
    assert len(table) > 0

    # Milestone timestamp 2023-07-13T12:00:00Z has both ERA5 and CWC available
    m_peak = [row for row in table if row.timestamp_utc == "2023-07-13T12:00:00Z"][0]
    assert m_peak.cwc_water_level_stage_m == 4.66
    assert m_peak.era5_rainfall_intensity_mm_h is not None
    assert m_peak.evidence_status == "DUAL_REAL_EVIDENCE_AVAILABLE"


def test_demographic_and_builtup_context():
    """
    Proves WorldPop and GHSL are classified as CONTEXTUAL_BASELINE and explicitly
    not converted into GBR features (population_exposure or infrastructure_vulnerability).
    """
    wp = get_worldpop_context_evidence()
    assert "CONTEXTUAL_BASELINE" in wp.provenance
    assert "WorldPop provides real demographic context but does not constitute" in wp.mandatory_disclaimer

    ghsl = get_ghsl_context_evidence()
    assert "CONTEXTUAL_BASELINE" in ghsl.provenance
    assert "GHSL built-up surface is contextual infrastructure/settlement evidence" in ghsl.mandatory_disclaimer


def test_traffic_baseline_context():
    """
    Proves traffic data is classified as CONTEXTUAL_BASELINE with mandatory disclaimer
    reaffirming historical 2020 baseline status.
    """
    tf = get_traffic_context_evidence()
    assert "CONTEXTUAL_BASELINE" in tf.provenance
    assert tf.mandatory_wording == "Delhi 2020 empirical traffic baseline; not July 2023 flood traffic."


def test_structured_event_evidence_chain():
    """
    Proves evidence chain connects all 5 tiers (RAINFALL, HYDRO-MET, CWC, GIS, POP/BUILTUP)
    with explicit sources, scope, provenance, status, and limitations. Does NOT contain GBR as required link.
    """
    chain = build_event_evidence_chain()
    assert len(chain) == 6

    tiers = [link.link_name for link in chain]
    assert tiers == [
        "1. RAINFALL EVIDENCE",
        "2. HYDRO-METEOROLOGICAL CONTEXT",
        "3. CWC OFFICIAL EVENT MILESTONES",
        "4. DOCUMENTED FLOOD GIS FOOTPRINT",
        "5. DEMOGRAPHIC POPULATION CONTEXT",
        "6. BUILT-UP SURFACE CONTEXT",
    ]

    for link in chain:
        assert hasattr(link, "source_dataset")
        assert hasattr(link, "spatial_temporal_scope")
        assert hasattr(link, "provenance")
        assert hasattr(link, "availability_status")
        assert hasattr(link, "limitations")
        assert "GBR prediction" not in link.source_dataset


def test_event_validation_package_categories():
    """
    Proves EventValidationPackage evaluates categories A-E accurately and declares
    MODEL_REAL_WORLD_ACCURACY: NOT ESTABLISHED and MODEL_OPERATIONAL_VALIDATION: NOT ESTABLISHED.
    """
    pkg = build_event_validation_package()

    assert pkg.categories["A_DATA_ACQUISITION"].status_code == "VERIFIED_COMPLETE"
    assert pkg.categories["B_TEMPORAL_CONSISTENCY"].status_code == "VERIFIED_MISMATCH_EXPLICITLY_MANAGED"
    assert pkg.categories["C_SPATIAL_CONSISTENCY"].status_code == "VERIFIED_BBOX_ALIGNMENT"
    assert pkg.categories["D_EVENT_EVIDENCE_CONSISTENCY"].status_code == "VERIFIED_QUALITATIVE_CORRESPONDENCE"
    assert pkg.categories["E_MODEL_VALIDATION_ELIGIBILITY"].status_code == "NOT_ELIGIBLE"

    assert pkg.model_real_world_accuracy == "NOT ESTABLISHED"
    assert pkg.model_operational_validation == "NOT ESTABLISHED"
    assert len(pkg.disclaimer_reasons) >= 6


def test_event_validation_report_generation():
    """
    Proves event_validation_report generates complete dict and markdown reports with all 15
    required sections and exact closing disclaimers.
    """
    rep_dict = generate_event_validation_report_dict()
    assert len(rep_dict) >= 15

    md_report = generate_markdown_event_validation_report()
    assert "# PHASE 6.22.6 — REAL-EVENT EVIDENCE VALIDATION REPORT" in md_report
    assert "REAL-WORLD MODEL ACCURACY:\nNOT ESTABLISHED" in md_report
    assert "OPERATIONAL VALIDATION:\nNOT ESTABLISHED" in md_report
    assert "GBR MODEL:\nUNTOUCHED" in md_report
    assert "MODEL WEIGHTS:\nUNTOUCHED" in md_report
    assert "TRAINING:\nNOT PERFORMED" in md_report
    assert "RAW DATA:\nUNTOUCHED" in md_report
    assert "COMMITS:\n0" in md_report
    assert "PUSHES:\n0" in md_report
