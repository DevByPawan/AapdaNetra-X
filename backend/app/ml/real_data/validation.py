"""
AapdaNetra-X Real-Data GBR Validation & Scientific Consistency Harness
Evaluates the existing synthetic-trained GradientBoostingRegressor against real-data
evidence from Phase 6.22.3 and 6.22.4 without retraining, modifying weights, or altering
production pipeline code.

Pre-Acceptance Semantic Audit Alignment:
- ISSUE 1: Marks population_exposure as POPULATION_EXPOSURE_SEMANTICALLY_INCOMPATIBLE
  because no documented sector/zonal aggregation rule exists to convert ~100m WorldPop
  pixel counts (~250) or total study bbox population (1.42M) into sector headcount.
  Therefore, real-data cases are marked NOT_ELIGIBLE for GBR inference.
- ISSUE 2: Explicitly distinguishes RAW_REAL_VALUE (rainfall_trend up to +260.33 mm/h²)
  from MODEL_INPUT_VALUE (+50.0 mm/h² after schema.py:L57 clipping).
"""
import os
import math
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

from app.ml.real_data.provenance import (
    FEATURE_ORDER,
    ProvenanceStatus,
    RealDataFeatureRecord,
    resolve_data_path,
)
from app.ml.real_data.era5_preprocessor import ERA5Preprocessor
from app.ml.real_data.worldpop_preprocessor import WorldPopPreprocessor
from app.ml.real_data.ghsl_preprocessor import GHSLPreprocessor
from app.ml.real_data.traffic_preprocessor import TrafficPreprocessor
from app.ml.real_data.cwc_observations import CWCObservations
from app.ml.real_data.feature_assembler import RealDataFeatureAssembler
from app.ml.real_data.spatial_alignment import build_spatial_alignment_matrix, DELHI_STUDY_BBOX
from app.ml.real_data.temporal_alignment import build_temporal_alignment_matrix

# Import existing model predictor read-only
try:
    from ml.inference.predictor import get_predictor, RiskPredictor
    from ml.features.schema import FEATURE_SPECS, validate_and_clean_features
except ImportError:
    import sys
    ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    if ROOT_DIR not in sys.path:
        sys.path.insert(0, ROOT_DIR)
    from ml.inference.predictor import get_predictor, RiskPredictor
    from ml.features.schema import FEATURE_SPECS, validate_and_clean_features


# Scientific Risk Flags
class ScientificFlag(str, Enum):
    REAL_DATA_COMPLETE = "REAL_DATA_COMPLETE"
    REAL_DATA_INCOMPLETE = "REAL_DATA_INCOMPLETE"
    PROVISIONAL_INPUT_USED = "PROVISIONAL_INPUT_USED"
    TEMPORAL_MISMATCH = "TEMPORAL_MISMATCH"
    SPATIAL_MISMATCH = "SPATIAL_MISMATCH"
    DISTRIBUTION_SHIFT = "DISTRIBUTION_SHIFT"
    NO_GROUND_TRUTH = "NO_GROUND_TRUTH"
    NOT_OPERATIONALLY_VALIDATED = "NOT_OPERATIONALLY_VALIDATED"
    POPULATION_EXPOSURE_SEMANTICALLY_INCOMPATIBLE = "POPULATION_EXPOSURE_SEMANTICALLY_INCOMPATIBLE"
    RAINFALL_TREND_CLIPPED_AT_MODEL_INPUT = "RAINFALL_TREND_CLIPPED_AT_MODEL_INPUT"


class ValidationMode(str, Enum):
    MODE_A_STRICT_REAL = "MODE_A_STRICT_REAL"
    MODE_B_PROVISIONAL = "MODE_B_PROVISIONAL"
    MODE_C_EVENT_EVIDENCE = "MODE_C_EVENT_EVIDENCE"


@dataclass
class ValidationPredictionRecord:
    timestamp_utc: str
    latitude: float
    longitude: float
    feature_values: Dict[str, Optional[float]]
    feature_provenance: Dict[str, str]
    inference_mode: str
    eligible_for_inference: bool
    provisional_features: List[str]
    missing_features: List[str]
    model_version: str
    prediction_risk_score: Optional[float]
    prediction_risk_category: Optional[str]
    validation_status: str
    scientific_flags: List[str]
    gis_event_reference: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RealDataGBRValidator:
    """
    Validation harness for evaluating the existing synthetic-trained GBR model
    against real-data informed records without modifying model weights or inventing fake rules.
    """

    # Synthetic training metrics (READ-ONLY metadata)
    SYNTHETIC_METRICS = {
        "MAE": 3.3364,
        "RMSE": 4.2142,
        "R2": 0.9258,
        "disclaimer": "Metrics were evaluated on synthetic test data ONLY. No real-world target labels exist.",
    }

    def __init__(self):
        self.predictor: RiskPredictor = get_predictor()
        self.assembler = RealDataFeatureAssembler()
        self.era5 = ERA5Preprocessor()
        self.worldpop = WorldPopPreprocessor()
        self.ghsl = GHSLPreprocessor()
        self.traffic = TrafficPreprocessor()
        self.cwc = CWCObservations()

    def run_mode_a_strict_real(self) -> List[ValidationPredictionRecord]:
        """
        MODE A — STRICT REAL-EVIDENCE MODE
        Requires all 7 features to be supported by real/official evidence.
        Because infrastructure_vulnerability is PROVISIONAL and population_exposure
        lacks a defensible sector aggregation mapping, 0 cases qualify for strict real inference.
        """
        records: List[ValidationPredictionRecord] = []

        for ts in ["2023-07-01T00:00:00Z", "2023-07-13T12:00:00Z", "2023-07-31T23:00:00Z"]:
            rec = self.assembler.assemble_record(ts)
            prov_features = [f for f, prov in rec.feature_provenance.items() if prov == ProvenanceStatus.PROVISIONAL.value]
            missing = [f for f, val in rec.features.items() if val is None]

            records.append(
                ValidationPredictionRecord(
                    timestamp_utc=ts,
                    latitude=rec.latitude,
                    longitude=rec.longitude,
                    feature_values=rec.features,
                    feature_provenance=rec.feature_provenance,
                    inference_mode=ValidationMode.MODE_A_STRICT_REAL.value,
                    eligible_for_inference=False,
                    provisional_features=prov_features,
                    missing_features=missing,
                    model_version=self.predictor.model_version,
                    prediction_risk_score=None,
                    prediction_risk_category=None,
                    validation_status="NOT_ELIGIBLE_FOR_STRICT_REAL_INFERENCE — Missing Real Vulnerability & Population Zonal Mapping",
                    scientific_flags=[
                        ScientificFlag.REAL_DATA_INCOMPLETE.value,
                        ScientificFlag.PROVISIONAL_INPUT_USED.value,
                        ScientificFlag.POPULATION_EXPOSURE_SEMANTICALLY_INCOMPATIBLE.value,
                        ScientificFlag.TEMPORAL_MISMATCH.value,
                        ScientificFlag.NO_GROUND_TRUTH.value,
                        ScientificFlag.NOT_OPERATIONALLY_VALIDATED.value,
                    ],
                    gis_event_reference="GIS_EVENT_REFERENCE_AVAILABLE",
                    details={"mode_explanation": "Strict mode rejects inference when features rely on provisional defaults or lack sector spatial aggregation rules."},
                )
            )

        return records

    def run_mode_b_provisional(self, timestamps: List[str]) -> List[ValidationPredictionRecord]:
        """
        MODE B — PROVISIONAL-INFERENCE MODE
        Evaluates provisional fallback rules.
        Because population_exposure lacks a defensible sector mapping rule, cases are marked
        NOT_ELIGIBLE for valid GBR inference to prevent false accuracy claims.
        """
        self.era5.load()
        records: List[ValidationPredictionRecord] = []

        for ts in timestamps:
            rec = self.assembler.assemble_record(ts)
            prov_features = [f for f, prov in rec.feature_provenance.items() if prov == ProvenanceStatus.PROVISIONAL.value]
            missing = [f for f, val in rec.features.items() if val is None]

            status_msg = "INCOMPLETE_POPULATION_EXPOSURE_EVIDENCE — Skipping Inference (Population Exposure Semantically Incompatible)"
            if "water_level" in missing or "water_level_trend" in missing:
                status_msg = "INCOMPLETE_POPULATION_EXPOSURE_EVIDENCE & INCOMPLETE_WATER_LEVEL_EVIDENCE — Skipping Inference"

            records.append(
                ValidationPredictionRecord(
                    timestamp_utc=ts,
                    latitude=rec.latitude,
                    longitude=rec.longitude,
                    feature_values=rec.features,
                    feature_provenance=rec.feature_provenance,
                    inference_mode=ValidationMode.MODE_B_PROVISIONAL.value,
                    eligible_for_inference=False,
                    provisional_features=prov_features,
                    missing_features=missing,
                    model_version=self.predictor.model_version,
                    prediction_risk_score=None,
                    prediction_risk_category=None,
                    validation_status=status_msg,
                    scientific_flags=[
                        ScientificFlag.REAL_DATA_INCOMPLETE.value,
                        ScientificFlag.PROVISIONAL_INPUT_USED.value,
                        ScientificFlag.POPULATION_EXPOSURE_SEMANTICALLY_INCOMPATIBLE.value,
                        ScientificFlag.TEMPORAL_MISMATCH.value,
                        ScientificFlag.NO_GROUND_TRUTH.value,
                        ScientificFlag.NOT_OPERATIONALLY_VALIDATED.value,
                    ],
                    gis_event_reference="GIS_EVENT_REFERENCE_AVAILABLE",
                    details={
                        "population_exposure_issue": "WorldPop ~100m pixel count (~250) vs sector headcount contract. No documented sector mapping exists.",
                    },
                )
            )

        return records

    def run_mode_c_event_evidence(self) -> List[ValidationPredictionRecord]:
        """
        MODE C — EVENT-EVIDENCE MODE
        Evaluates official July 2023 CWC flood milestone events and documents semantic mismatches.
        Cases are marked NOT_ELIGIBLE for GBR inference due to population exposure semantic incompatibility.
        """
        milestone_timestamps = [
            "2023-07-09T08:00:00Z",  # Peak ERA5 rainfall 260.33 mm/h
            "2023-07-10T06:00:00Z",  # CWC stage 1.50m above danger level
            "2023-07-13T12:00:00Z",  # Peak HFL 208.66m (4.66m relative stage)
            "2023-07-15T18:00:00Z",  # Receding stage 2.10m
        ]
        records: List[ValidationPredictionRecord] = []

        for ts in milestone_timestamps:
            rec = self.assembler.assemble_record(ts)
            prov_features = [f for f, prov in rec.feature_provenance.items() if prov == ProvenanceStatus.PROVISIONAL.value]

            # Document raw vs cleaned rainfall trend for event milestone
            raw_inputs = rec.to_gbr_input_features(fill_provisional_defaults=True)
            cleaned_inputs = validate_and_clean_features(raw_inputs)

            records.append(
                ValidationPredictionRecord(
                    timestamp_utc=ts,
                    latitude=rec.latitude,
                    longitude=rec.longitude,
                    feature_values=rec.features,
                    feature_provenance=rec.feature_provenance,
                    inference_mode=ValidationMode.MODE_C_EVENT_EVIDENCE.value,
                    eligible_for_inference=False,
                    provisional_features=prov_features,
                    missing_features=[],
                    model_version=self.predictor.model_version,
                    prediction_risk_score=None,
                    prediction_risk_category=None,
                    validation_status="NOT_ELIGIBLE — Event Observation Recorded (Inference withheld due to semantic incompatibilities)",
                    scientific_flags=[
                        ScientificFlag.PROVISIONAL_INPUT_USED.value,
                        ScientificFlag.POPULATION_EXPOSURE_SEMANTICALLY_INCOMPATIBLE.value,
                        ScientificFlag.RAINFALL_TREND_CLIPPED_AT_MODEL_INPUT.value,
                        ScientificFlag.TEMPORAL_MISMATCH.value,
                        ScientificFlag.DISTRIBUTION_SHIFT.value,
                        ScientificFlag.NO_GROUND_TRUTH.value,
                        ScientificFlag.NOT_OPERATIONALLY_VALIDATED.value,
                    ],
                    gis_event_reference="GIS_EVENT_REFERENCE_AVAILABLE",
                    details={
                        "cwc_observation": f"Stage {rec.features['water_level']}m" if rec.features["water_level"] is not None else "Unobserved",
                        "era5_rainfall_raw": rec.features["rainfall_intensity"],
                        "rainfall_trend_raw": raw_inputs.get("rainfall_trend"),
                        "rainfall_trend_model_input": cleaned_inputs.get("rainfall_trend"),
                    },
                )
            )

        return records

    def compute_distribution_analysis(self) -> Dict[str, Any]:
        """
        Computes real-data feature distributions and explicitly distinguishes
        RAW_REAL_VALUE from MODEL_INPUT_VALUE (after schema.py clipping).
        """
        self.era5.load()
        rf_vals = list(self.era5._hourly_data.values())
        rf_trends = list(self.era5._hourly_trends.values())

        # Model input values after validate_and_clean_features clipping (schema.py:L57)
        rf_trends_model_input = [max(-50.0, min(50.0, t)) for t in rf_trends]

        cwc_vals = [0.50, 1.50, 4.66, 2.10]
        wp_val, wp_meta = self.worldpop.get_population_exposure(28.64, 77.22)
        wp_mean = wp_meta.get("mean_population_per_cell", 250.51)
        traffic_val, _ = self.traffic.get_road_congestion(12)

        return {
            "rainfall_intensity": {
                "raw_real_value": {
                    "min": round(float(np.min(rf_vals)), 4),
                    "max": round(float(np.max(rf_vals)), 4),
                    "mean": round(float(np.mean(rf_vals)), 4),
                },
                "model_input_value": {
                    "min": round(float(np.min(rf_vals)), 4),
                    "max": round(float(np.max([min(300.0, v) for v in rf_vals])), 4),
                    "mean": round(float(np.mean(rf_vals)), 4),
                },
                "clipping_applied": False,
                "training_spec": FEATURE_SPECS["rainfall_intensity"],
            },
            "rainfall_trend": {
                "raw_real_value": {
                    "min": round(float(np.min(rf_trends)), 4),  # -172.933 mm/h²
                    "max": round(float(np.max(rf_trends)), 4),  # +260.333 mm/h²
                    "mean": round(float(np.mean(rf_trends)), 4),
                },
                "model_input_value": {
                    "min": round(float(np.min(rf_trends_model_input)), 4),  # -50.0 mm/h²
                    "max": round(float(np.max(rf_trends_model_input)), 4),  # +50.0 mm/h²
                    "mean": round(float(np.mean(rf_trends_model_input)), 4),
                },
                "clipping_applied": True,
                "clipping_location": "ml/features/schema.py:L57 (validate_and_clean_features)",
                "clipping_bounds": [-50.0, 50.0],
                "training_spec": FEATURE_SPECS["rainfall_trend"],
            },
            "water_level": {
                "raw_real_value": {
                    "min": round(float(np.min(cwc_vals)), 2),
                    "max": round(float(np.max(cwc_vals)), 2),
                    "mean": round(float(np.mean(cwc_vals)), 2),
                },
                "model_input_value": {
                    "min": round(float(np.min(cwc_vals)), 2),
                    "max": round(float(np.max(cwc_vals)), 2),
                    "mean": round(float(np.mean(cwc_vals)), 2),
                },
                "clipping_applied": False,
                "training_spec": FEATURE_SPECS["water_level"],
            },
            "road_congestion": {
                "raw_real_value": {
                    "min": 0.0,
                    "max": 1.0,
                    "mean": round(float(traffic_val), 4),
                },
                "model_input_value": {
                    "min": 0.0,
                    "max": 1.0,
                    "mean": round(float(traffic_val), 4),
                },
                "clipping_applied": False,
                "training_spec": FEATURE_SPECS["road_congestion"],
            },
            "population_exposure": {
                "raw_real_value": {
                    "source_spatial_unit": "3 arc-sec (~100m) pixel count",
                    "pixel_min": 105.06,
                    "pixel_max": 302.23,
                    "pixel_mean": round(float(wp_mean), 2),
                    "study_bbox_total_population": round(float(wp_meta.get("total_study_bbox_population", 1423899.5)), 1),
                },
                "model_expected_spatial_unit": "Exposed population headcount in sector (0 to 100,000, default 12,430)",
                "semantic_compatibility": "POPULATION_EXPOSURE_SEMANTICALLY_INCOMPATIBLE",
                "semantic_issue": "WorldPop provides ~100m pixel counts (~250). Dividing by 100.0 (L77 in worldpop_preprocessor.py) is an arbitrary division without a documented sector mapping rule.",
                "training_spec": FEATURE_SPECS["population_exposure"],
            },
            "infrastructure_vulnerability": {
                "raw_real_value": None,
                "model_input_value": 0.72,
                "semantic_compatibility": "PROVISIONAL_FALLBACK_ONLY",
                "training_spec": FEATURE_SPECS["infrastructure_vulnerability"],
            },
        }
