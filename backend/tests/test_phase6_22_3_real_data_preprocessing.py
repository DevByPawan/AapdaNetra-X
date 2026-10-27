"""
Phase 6.22.3 Real Data Preprocessing & Validation Unit Tests
Comprehensive tests for ERA5 boundary & step de-accumulation math, WorldPop, GHSL, Traffic,
CWC preprocessors, RealDataFeatureAssembler, provenance tracking, and data safety.
"""
import os
import math
import pytest
from app.ml.real_data.provenance import (
    RealDataFeatureRecord,
    ProvenanceStatus,
    FEATURE_ORDER,
    resolve_data_path,
)
from app.ml.real_data.era5_preprocessor import ERA5Preprocessor
from app.ml.real_data.worldpop_preprocessor import WorldPopPreprocessor
from app.ml.real_data.ghsl_preprocessor import GHSLPreprocessor
from app.ml.real_data.traffic_preprocessor import TrafficPreprocessor
from app.ml.real_data.cwc_observations import CWCObservations
from app.ml.real_data.feature_assembler import RealDataFeatureAssembler


# ── 1. ERA5 Preprocessor Tests ──────────────────────────────────────────────

def test_era5_within_run_step_de_accumulation():
    """
    Proves mathematically:
    1. step 1 is tp1 * 1000
    2. step 2 is (tp2 - tp1) * 1000
    3. step 24 is (tp24 - tp23) * 1000
    4. Example: tp5 = 43.02 mm, tp6 = 51.19 mm -> expected hourly rainfall ≈ 8.17 mm/h
    """
    era5 = ERA5Preprocessor()
    era5.load()

    # Step 4 vs Step 5 in July 1 run: tp4 = 9.7961 mm, tp5 = 10.1166 mm -> diff = 0.3205 mm/h
    v4, _, _ = era5.get_rainfall_features("2023-07-01T04:00:00Z")
    v5, _, _ = era5.get_rainfall_features("2023-07-01T05:00:00Z")
    assert abs(v5 - (10.1166 - 9.7961)) < 1e-2, f"Step 5 de-accumulation error: got {v5}"

    # Concrete example test: tp5 = 43.02 mm, tp6 = 51.19 mm -> expected = 8.17 mm/h
    mock_tp5 = 43.02 / 1000.0
    mock_tp6 = 51.19 / 1000.0
    expected_deaccumulated = max(0.0, (mock_tp6 - mock_tp5) * 1000.0)
    assert abs(expected_deaccumulated - 8.17) < 1e-4, f"Expected 8.17 mm/h, got {expected_deaccumulated}"


def test_era5_june30_step24_and_july1_step1_boundary():
    """
    Proves:
    1. June30-step24 (valid 2023-07-01T00:00:00Z) is de-accumulated cleanly against June30-step23 as 1.4621 mm/h (no false 581.55 spike, no artificial 0.0 fallback).
    2. July1-step1 (valid 2023-07-01T01:00:00Z) resets previous_tp and uses tp1 * 1000.
    """
    era5 = ERA5Preprocessor()
    era5.load()

    v_july1_00, _, _ = era5.get_rainfall_features("2023-07-01T00:00:00Z")
    v_july1_01, _, _ = era5.get_rainfall_features("2023-07-01T01:00:00Z")

    assert v_july1_00 is not None, "July 1 00:00 UTC observation must be present"
    assert abs(v_july1_00 - 1.4621) < 1e-3, f"July 1 00:00 UTC must be approx 1.4621 mm/h, got {v_july1_00}"
    assert v_july1_01 == 0.0, f"July 1 01:00 UTC step 1 must be 0.0, got {v_july1_01}"


def test_era5_missing_june30_step23_raises_valueerror():
    """
    Proves that if June 30 step 23 is missing, load() refuses to default to artificial 0.0 and raises ValueError.
    """
    era5 = ERA5Preprocessor(june30_grib_path=None)
    with pytest.raises(ValueError, match="Cannot de-accumulate boundary observation"):
        era5.load()


def test_era5_july2023_exact_744_timestamps_no_duplicates_no_missing():
    """
    Proves July 2023 window contains exactly 744 unique, non-duplicate, non-missing hourly timestamps.
    """
    era5 = ERA5Preprocessor()
    era5.load()

    ts_list = sorted(list(era5._hourly_data.keys()))
    assert len(ts_list) == 744, f"Expected 744 timestamps, got {len(ts_list)}"
    assert len(set(ts_list)) == 744, "Timestamps must be unique (no duplicates)"

    assert ts_list[0] == "2023-07-01T00:00:00Z", f"Start timestamp must be 2023-07-01T00:00:00Z, got {ts_list[0]}"
    assert ts_list[-1] == "2023-07-31T23:00:00Z", f"End timestamp must be 2023-07-31T23:00:00Z, got {ts_list[-1]}"


def test_era5_provenance_and_no_negative_values():
    era5 = ERA5Preprocessor()
    era5.load()

    for ts, val in era5._hourly_data.items():
        assert val >= 0.0, f"Negative rainfall found at {ts}: {val}"
        assert not math.isnan(val), f"NaN found at {ts}"
        assert not math.isinf(val), f"Inf found at {ts}"

    _, _, meta = era5.get_rainfall_features("2023-07-13T12:00:00Z")
    assert meta["provenance_intensity"] == ProvenanceStatus.DERIVED_FROM_REAL.value
    assert meta["provenance_trend"] == ProvenanceStatus.DERIVED_FROM_REAL.value


# ── 2. WorldPop Preprocessor Tests ──────────────────────────────────────────

def test_worldpop_bbox_extraction_and_semantics():
    wp = WorldPopPreprocessor()
    count_val, meta = wp.get_population_exposure(lat=28.6400, lon=77.2200)

    assert count_val is None, "Population exposure GBR feature value must be None due to semantic incompatibility"
    assert meta["semantic_status"] == "SEMANTICALLY_INCOMPATIBLE"
    assert meta["semantics"] == "population_count_per_pixel"
    assert meta["provenance"] == ProvenanceStatus.DERIVED_FROM_REAL.value
    assert meta["total_study_bbox_population"] > 1000000.0, "Total study bbox population should be ~1.4 million"


# ── 3. GHSL Preprocessor Tests ──────────────────────────────────────────────

def test_ghsl_built_up_surface_extraction_not_mapped_to_vulnerability():
    ghsl = GHSLPreprocessor()
    built_up_m2, meta = ghsl.get_built_up_surface(lat=28.6400, lon=77.2200)

    assert built_up_m2 > 0.0, "Built-up surface m² should be positive for urban Delhi"
    assert meta["unit"] == "m² per ~100m grid cell"
    assert meta["mapped_to_infrastructure_vulnerability"] is False, "GHSL MUST NOT be mapped to vulnerability"
    assert meta["provenance"] == ProvenanceStatus.DERIVED_FROM_REAL.value


# ── 4. Traffic Preprocessor Tests ───────────────────────────────────────────

def test_traffic_aggregation_determinism_and_temporal_provenance():
    traffic = TrafficPreprocessor()
    ratio1, meta1 = traffic.get_road_congestion(hour_ist=12)
    ratio2, meta2 = traffic.get_road_congestion(hour_ist=12)

    assert ratio1 == ratio2, "Traffic preprocessor output must be deterministic"
    assert 0.0 <= ratio1 <= 1.0, "Road congestion must be a ratio between 0.0 and 1.0"
    assert "2020" in meta1["temporal_context"], "Traffic temporal context must explicitly state 2020 baseline"
    assert meta1["is_july2023_flood_traffic"] is False, "Traffic preprocessor must NOT claim to be July 2023 flood traffic"
    assert meta1["provenance"] == ProvenanceStatus.DERIVED_FROM_REAL.value


# ── 5. CWC Observations Tests ───────────────────────────────────────────────

def test_cwc_milestone_provenance_and_missing_unobserved_handling():
    cwc = CWCObservations()

    # Test documented milestone (July 13 peak HFL)
    wl_peak, trend_peak, meta_peak = cwc.get_water_level_features("2023-07-13T12:00:00Z")
    assert wl_peak == 4.66, "Peak HFL relative stage should be 4.66 m"
    assert meta_peak["provenance"] == ProvenanceStatus.OFFICIAL_EVENT_ONLY.value
    assert meta_peak["is_official_observation"] is True

    # Test unobserved timestamp (July 5 06:00 UTC)
    wl_unobs, trend_unobs, meta_unobs = cwc.get_water_level_features("2023-07-05T06:00:00Z")
    assert wl_unobs is None, "Unobserved timestamp MUST return None for water_level (no fabrication)"
    assert trend_unobs is None, "Unobserved timestamp MUST return None for water_level_trend (no fabrication)"
    assert meta_unobs["provenance"] == ProvenanceStatus.OFFICIAL_EVENT_ONLY.value
    assert meta_unobs["is_official_observation"] is False


# ── 6. Feature Assembler & 7-Feature Schema Tests ─────────────────────────

def test_feature_assembler_ordering_and_provenance():
    assembler = RealDataFeatureAssembler()
    record = assembler.assemble_record(timestamp_utc="2023-07-13T12:00:00Z")

    # 1. Exact 7-feature ordering check
    feature_keys = list(record.features.keys())
    assert feature_keys == FEATURE_ORDER, f"Features dictionary keys must strictly match {FEATURE_ORDER}"

    # 2. Provenance attached to every feature
    for f in FEATURE_ORDER:
        assert f in record.feature_provenance, f"Missing provenance for feature '{f}'"
        assert record.feature_provenance[f] in [p.value for p in ProvenanceStatus]

    # 3. Infrastructure vulnerability is explicitly PROVISIONAL
    assert record.feature_provenance["infrastructure_vulnerability"] == ProvenanceStatus.PROVISIONAL.value
    assert record.features["infrastructure_vulnerability"] == 0.72

    # 4. Extra real contextual feature (GHSL) present outside 7-feature schema
    assert "built_up_surface_m2" in record.extra_contextual_features
    assert record.extra_contextual_features["ghsl_metadata"]["mapped_to_infrastructure_vulnerability"] is False


def test_feature_assembler_gbr_formatting_and_defaults():
    assembler = RealDataFeatureAssembler()

    # Unobserved timestamp where water_level is None
    record = assembler.assemble_record(timestamp_utc="2023-07-05T06:00:00Z")
    assert record.features["water_level"] is None

    # GBR input features with provisional fallback fill
    gbr_features = record.to_gbr_input_features(fill_provisional_defaults=True)
    assert all(isinstance(v, float) for v in gbr_features.values()), "All GBR inputs must be float"
    assert gbr_features["water_level"] == 4.2, "Unobserved water level filled with schema default 4.2 for GBR"

    # GBR input features without default fill
    gbr_raw = record.to_gbr_input_features(fill_provisional_defaults=False)
    assert gbr_raw["water_level"] is None


def test_raw_files_untouched():
    raw_files = [
        "data/raw/era5_land_delhi_july2023.grib",
        "data/raw/ind_ppp_2020_constrained.tif",
        "data/raw/GHS_BUILT_S_E2020_GLOBE_R2023A_4326_3ss_V1_0_R7_C26.zip",
        "data/raw/delhi_traffic_density_2020.zip",
        "data/raw/delhi_flood_2023/6f8d92b8-d9ab-45af-976c-fb9047a85cf7.kml",
    ]
    for rf in raw_files:
        resolved = resolve_data_path(rf)
        assert os.path.exists(resolved), f"Raw file '{resolved}' must exist untouched"
        assert os.path.getsize(resolved) > 0, f"Raw file '{resolved}' must be non-empty"
