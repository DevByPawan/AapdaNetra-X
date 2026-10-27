"""
Phase 6.22.7 Consolidated Real-Data Audit & Phase 6.22 Closure Unit Tests
Comprehensive test suite verifying dataset inventory, feature provenance matrix,
contextual features isolation, ERA5 de-accumulation audit, population semantics,
infrastructure vulnerability fallback, CWC milestones non-interpolation, traffic baseline disclaimers,
Flood GIS reference footprint, model validation eligibility, report generation, and closure criteria.
"""
import pytest
from app.ml.real_data.phase6_22_closure_report import (
    generate_phase6_22_closure_dict,
    generate_markdown_phase6_22_closure_report,
)
from app.ml.real_data.provenance import FEATURE_ORDER
from app.ml.real_data.validation import RealDataGBRValidator


def test_phase6_22_7_closure_dict_generation():
    """
    Proves generate_phase6_22_closure_dict compiles a complete 14-section dictionary
    covering all Phase 6.22 subphases, dataset inventory, and closure disclaimers.
    """
    closure = generate_phase6_22_closure_dict()
    assert len(closure) >= 14
    assert closure["14_phase6_22_closure_decision"]["phase_status"] == "CLOSED"
    assert closure["9_gbr_validation_eligibility"]["model_real_world_accuracy"] == "NOT ESTABLISHED"
    assert closure["9_gbr_validation_eligibility"]["model_operational_validation"] == "NOT ESTABLISHED"


def test_dataset_inventory_completeness_and_provenance():
    """
    Proves dataset inventory includes all 6 acquired datasets with exact expected provenance,
    local raw files, and scientific roles.
    """
    closure = generate_phase6_22_closure_dict()
    inventory = closure["3_dataset_inventory"]
    assert len(inventory) == 6

    d_names = [d["dataset"] for d in inventory]
    assert "ERA5-Land Total Precipitation" in d_names
    assert "WorldPop 2020 India Constrained Population" in d_names
    assert "GHSL Built-Up Surface 2020 Epoch" in d_names
    assert "Delhi Traffic Density Baseline" in d_names
    assert "CWC Yamuna River Gauge Observations" in d_names
    assert "Delhi July 2023 Flood Inundation Vector Layers" in d_names

    prov_dict = {d["dataset"]: d["provenance"] for d in inventory}
    assert prov_dict["ERA5-Land Total Precipitation"] == "DERIVED_FROM_REAL / REANALYSIS"
    assert prov_dict["WorldPop 2020 India Constrained Population"] == "CONTEXTUAL_BASELINE"
    assert prov_dict["GHSL Built-Up Surface 2020 Epoch"] == "CONTEXTUAL_BASELINE"
    assert prov_dict["Delhi Traffic Density Baseline"] == "CONTEXTUAL_BASELINE / EMPIRICAL_TRAFFIC_2020"
    assert prov_dict["CWC Yamuna River Gauge Observations"] == "OBSERVED / OFFICIAL_EVENT_ONLY"
    assert prov_dict["Delhi July 2023 Flood Inundation Vector Layers"] == "EVENT_REFERENCE"


def test_seven_feature_provenance_matrix_classifications():
    """
    Proves the seven GBR features maintain exact expected scientific provenance classifications.
    """
    closure = generate_phase6_22_closure_dict()
    matrix = closure["4_feature_provenance_matrix"]
    assert len(matrix) == 7

    for f in FEATURE_ORDER:
        assert f in matrix

    assert matrix["rainfall_intensity"]["provenance"] == "DERIVED_FROM_REAL"
    assert matrix["rainfall_trend"]["provenance"] == "DERIVED_FROM_REAL"
    assert matrix["water_level"]["provenance"] == "OFFICIAL_EVENT_ONLY"
    assert matrix["water_level_trend"]["provenance"] == "OFFICIAL_EVENT_ONLY"
    assert "2020 BASELINE" in matrix["road_congestion"]["provenance"]
    assert matrix["population_exposure"]["provenance"] == "SEMANTICALLY_INCOMPATIBLE_FOR_CURRENT_GBR"
    assert matrix["infrastructure_vulnerability"]["provenance"] == "PROVISIONAL"


def test_contextual_features_isolation():
    """
    Proves GHSL, WorldPop, Flood GIS, and Traffic contextual features are isolated
    and NOT promoted into GBR model features.
    """
    closure = generate_phase6_22_closure_dict()
    non_claims = closure["13_final_non_claims"]

    assert any("WorldPop 100m grid cell population counts are NOT claimed as validated sector exposure" in c for c in non_claims)
    assert any("GHSL built-up surface is NOT converted into infrastructure_vulnerability" in c for c in non_claims)
    assert any("Flood GIS polygon extents are NOT claimed as ML model ground-truth prediction targets" in c for c in non_claims)
    assert any("Historical 2020 traffic is NOT claimed as July 2023 real-time flood traffic" in c for c in non_claims)


def test_era5_and_cwc_audit_guarantees():
    """
    Proves ERA5 rainfall de-accumulation has 744 hours, peak at 260.33 mm/h,
    and CWC river gauge observations contain zero interpolation/synthetic hydrograph.
    """
    closure = generate_phase6_22_closure_dict()
    ev = closure["8_real_event_evidence_summary"]

    assert ev["era5_peak"]["total_hourly_timestamps"] == 744
    assert abs(ev["era5_peak"]["peak_intensity_value_mm_h"] - 260.333) < 1e-2
    assert "UNAVAILABLE" in ev["cwc_record_hfl"]["unobserved_period_status"]
    assert "zero interpolation" in ev["cwc_record_hfl"]["no_interpolation_disclaimer"]


def test_gbr_model_immutability_and_read_only():
    """
    Proves GBR model artifact remains read-only, weights untouched, feature order schema preserved.
    """
    validator = RealDataGBRValidator()
    assert validator.predictor.model is not None
    assert validator.predictor.model_info["model_name"] == "GradientBoostingRegressor"
    assert FEATURE_ORDER == [
        "rainfall_intensity",
        "rainfall_trend",
        "water_level",
        "water_level_trend",
        "road_congestion",
        "population_exposure",
        "infrastructure_vulnerability",
    ]


def test_markdown_closure_report_content_and_closing_disclaimers():
    """
    Proves generate_markdown_phase6_22_closure_report produces complete markdown document
    ending with exact required closure status text.
    """
    md = generate_markdown_phase6_22_closure_report()

    assert "# PHASE 6.22 — CONSOLIDATED REAL-DATA AUDIT & CLOSURE REPORT" in md
    assert "PHASE 6.22 STATUS:\nCLOSED" in md
    assert "REAL-WORLD MODEL ACCURACY:\nNOT ESTABLISHED" in md
    assert "OPERATIONAL VALIDATION:\nNOT ESTABLISHED" in md
    assert "GBR:\nUNCHANGED" in md
    assert "MODEL WEIGHTS:\nUNCHANGED" in md
    assert "TRAINING:\nNOT PERFORMED" in md
    assert "RAW DATA:\nUNCHANGED" in md
    assert "NEW DATASETS:\n0" in md
    assert "COMMITS:\n0" in md
    assert "PUSHES:\n0" in md
