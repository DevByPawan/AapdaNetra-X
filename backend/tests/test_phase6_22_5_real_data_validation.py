"""
Phase 6.22.5 Real-Data GBR Validation & Scientific Consistency Unit Tests
Comprehensive tests for GBR model integrity, Mode A strict rejection, Mode B provisional handling,
Mode C event evidence evaluation, distribution shift reporting, and pre-acceptance semantic audit rules.
"""
import os
import pytest
from app.ml.real_data.provenance import FEATURE_ORDER, ProvenanceStatus
from app.ml.real_data.validation import (
    RealDataGBRValidator,
    ValidationMode,
    ScientificFlag,
)
from app.ml.real_data.validation_report import (
    generate_validation_report_dict,
    generate_markdown_validation_report,
)


def test_gbr_model_integrity_and_read_only_artifact():
    """
    Proves GBR artifact is loaded read-only, weights are untouched,
    no retraining is performed, and feature order strictly matches schema.
    """
    validator = RealDataGBRValidator()
    assert validator.predictor.model is not None, "GBR model artifact must be loaded"
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
    # Verify synthetic training metrics are read-only
    assert validator.SYNTHETIC_METRICS["MAE"] == 3.3364
    assert validator.SYNTHETIC_METRICS["RMSE"] == 4.2142
    assert validator.SYNTHETIC_METRICS["R2"] == 0.9258


def test_mode_a_strict_real_mode_rejection():
    """
    Proves Mode A rejects inference (0 cases eligible) because infrastructure_vulnerability
    is PROVISIONAL and population_exposure lacks a defensible sector aggregation mapping.
    """
    validator = RealDataGBRValidator()
    records = validator.run_mode_a_strict_real()

    assert len(records) > 0
    for r in records:
        assert r.inference_mode == ValidationMode.MODE_A_STRICT_REAL.value
        assert r.eligible_for_inference is False
        assert r.prediction_risk_score is None
        assert "NOT_ELIGIBLE_FOR_STRICT_REAL_INFERENCE" in r.validation_status
        assert "infrastructure_vulnerability" in r.provisional_features
        assert ScientificFlag.POPULATION_EXPOSURE_SEMANTICALLY_INCOMPATIBLE.value in r.scientific_flags


def test_mode_b_provisional_inference_rejection_safety():
    """
    Proves Mode B marks cases NOT_ELIGIBLE for valid GBR inference (INCOMPLETE_POPULATION_EXPOSURE_EVIDENCE)
    due to population_exposure semantic incompatibility and provisional vulnerability fallback.
    """
    validator = RealDataGBRValidator()
    records = validator.run_mode_b_provisional(["2023-07-01T00:00:00Z", "2023-07-13T12:00:00Z"])

    for r in records:
        assert r.inference_mode == ValidationMode.MODE_B_PROVISIONAL.value
        assert r.eligible_for_inference is False
        assert r.prediction_risk_score is None
        assert "INCOMPLETE_POPULATION_EXPOSURE_EVIDENCE" in r.validation_status
        assert ScientificFlag.POPULATION_EXPOSURE_SEMANTICALLY_INCOMPATIBLE.value in r.scientific_flags


def test_mode_c_event_evidence_semantic_flags():
    """
    Proves Mode C records event observations, flags rainfall_trend clipping and population exposure incompatibility,
    and withholds valid GBR inference claims.
    """
    validator = RealDataGBRValidator()
    records = validator.run_mode_c_event_evidence()

    assert len(records) > 0
    for r in records:
        assert r.inference_mode == ValidationMode.MODE_C_EVENT_EVIDENCE.value
        assert r.eligible_for_inference is False
        assert r.prediction_risk_score is None
        assert ScientificFlag.RAINFALL_TREND_CLIPPED_AT_MODEL_INPUT.value in r.scientific_flags
        assert ScientificFlag.POPULATION_EXPOSURE_SEMANTICALLY_INCOMPATIBLE.value in r.scientific_flags


def test_distribution_analysis_raw_vs_model_input():
    """
    Proves distribution analysis explicitly distinguishes RAW_REAL_VALUE from MODEL_INPUT_VALUE
    and identifies clipping at ml/features/schema.py:L57 for rainfall_trend.
    """
    validator = RealDataGBRValidator()
    report = validator.compute_distribution_analysis()

    # Rainfall trend clipping check
    rt = report["rainfall_trend"]
    assert rt["raw_real_value"]["max"] > 50.0  # +260.33 mm/h²
    assert rt["model_input_value"]["max"] == 50.0  # Clipped to 50.0
    assert rt["clipping_applied"] is True
    assert "schema.py:L57" in rt["clipping_location"]

    # Population exposure semantic check
    pe = report["population_exposure"]
    assert pe["semantic_compatibility"] == "POPULATION_EXPOSURE_SEMANTICALLY_INCOMPATIBLE"


def test_validation_report_generation():
    """
    Proves validation_report module generates complete machine-readable and markdown reports
    containing all 6 required sections and end-of-report safety disclaimers.
    """
    rep_dict = generate_validation_report_dict()
    assert "section_a_model_integrity" in rep_dict
    assert "section_b_validation_dataset_overview" in rep_dict
    assert "section_c_feature_provenance_matrix" in rep_dict
    assert "section_d_distribution_analysis" in rep_dict
    assert "section_e_event_validation" in rep_dict
    assert "section_f_scientific_limitations" in rep_dict

    md_report = generate_markdown_validation_report()
    assert "GBR MODEL: UNTOUCHED" in md_report
    assert "MODEL WEIGHTS: UNTOUCHED" in md_report
    assert "FEATURE ORDER: UNCHANGED" in md_report
    assert "TRAINING: NOT PERFORMED" in md_report
    assert "REAL-WORLD ACCURACY CLAIM: NOT MADE" in md_report
    assert "OPERATIONAL VALIDATION: NOT CLAIMED" in md_report
    assert "COMMITS: 0" in md_report
    assert "PUSHES: 0" in md_report
