"""
Phase 6.12 — Real ML Pipeline Tests
Tests: dataset contract, feature engineering, data validation, split methodology,
leakage detection, baseline models, GBR training, model versioning, model loading,
feature schema validation, prediction bounds, SHAP compatibility, model-info endpoint.
"""
import sys
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
for p in [str(ROOT_DIR), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ml.features.schema import FEATURE_NAMES, FEATURE_SPECS, validate_and_clean_features
from ml.pipeline import (
    DATASET_FEATURE_COLUMNS,
    DATASET_TARGET_COLUMN,
    DATASET_METADATA_COLUMNS,
    TargetSource,
    ModelDataStatus,
    SplitMethod,
    ModelMetadata,
    validate_feature_row,
    validate_target,
    validate_dataset,
    prepare_feature_matrix,
    extract_target,
    split_dataset,
    check_data_leakage,
    validate_model_feature_schema,
)
from ml.pipeline.train_pipeline import (
    compute_metrics,
    MeanPredictor,
    train_baselines,
    train_gbr,
    run_training_pipeline,
    GBR_HYPERPARAMETERS,
)
from ml.training.generator import generate_synthetic_dataset
from ml.inference import predict_risk, get_predictor
from ml.explainability import explain_prediction
from app.main import app


client = TestClient(app)


# ─── Dataset Contract Tests ───────────────────────────────────────────────

class TestDatasetContract:
    """Tests for dataset schema, feature columns, and target column definitions."""

    def test_feature_columns_match_schema(self):
        """Feature columns in pipeline match centralized FEATURE_NAMES."""
        assert DATASET_FEATURE_COLUMNS == FEATURE_NAMES

    def test_seven_features_defined(self):
        """Exactly 7 features are defined."""
        assert len(DATASET_FEATURE_COLUMNS) == 7

    def test_target_column_defined(self):
        """Target column is risk_score."""
        assert DATASET_TARGET_COLUMN == "risk_score"

    def test_feature_ordering_deterministic(self):
        """Feature ordering is deterministic across repeated access."""
        order1 = list(DATASET_FEATURE_COLUMNS)
        order2 = list(DATASET_FEATURE_COLUMNS)
        assert order1 == order2

    def test_metadata_columns_defined(self):
        """Metadata columns are defined."""
        assert "timestamp" in DATASET_METADATA_COLUMNS
        assert "provenance" in DATASET_METADATA_COLUMNS
        assert "target_source" in DATASET_METADATA_COLUMNS


# ─── Data Validation Tests ────────────────────────────────────────────────

class TestDataValidation:
    """Tests for feature row and dataset validation."""

    def test_valid_row_passes(self):
        """A valid feature row passes validation."""
        row = {name: FEATURE_SPECS[name]["default"] for name in FEATURE_NAMES}
        valid, errors = validate_feature_row(row)
        assert valid is True
        assert errors == []

    def test_missing_feature_fails(self):
        """Missing mandatory feature fails validation."""
        row = {"rainfall_intensity": 50.0}
        valid, errors = validate_feature_row(row)
        assert valid is False
        assert any("Missing" in e for e in errors)

    def test_nan_feature_fails(self):
        """NaN feature value fails validation."""
        row = {name: FEATURE_SPECS[name]["default"] for name in FEATURE_NAMES}
        row["water_level"] = float("nan")
        valid, errors = validate_feature_row(row)
        assert valid is False
        assert any("not finite" in e for e in errors)

    def test_infinity_feature_fails(self):
        """Infinity feature value fails validation."""
        row = {name: FEATURE_SPECS[name]["default"] for name in FEATURE_NAMES}
        row["rainfall_intensity"] = float("inf")
        valid, errors = validate_feature_row(row)
        assert valid is False
        assert any("not finite" in e for e in errors)

    def test_out_of_bounds_detected(self):
        """Out-of-bounds value is detected."""
        row = {name: FEATURE_SPECS[name]["default"] for name in FEATURE_NAMES}
        row["road_congestion"] = 5.0  # max is 1.0
        valid, errors = validate_feature_row(row)
        assert valid is False
        assert any("out of bounds" in e for e in errors)

    def test_valid_target_passes(self):
        """Valid target passes validation."""
        valid, err = validate_target(45.0)
        assert valid is True
        assert err is None

    def test_invalid_target_nan(self):
        """NaN target fails."""
        valid, err = validate_target(float("nan"))
        assert valid is False

    def test_target_out_of_range(self):
        """Target > 100 fails."""
        valid, err = validate_target(150.0)
        assert valid is False


class TestDatasetValidation:
    """Tests for full dataset validation."""

    def test_synthetic_dataset_valid(self):
        """Synthetic generated dataset passes validation."""
        df = generate_synthetic_dataset(100, random_seed=42)
        df = df.rename(columns={"target_risk": DATASET_TARGET_COLUMN})
        valid, errors = validate_dataset(df)
        assert valid is True, f"Validation errors: {errors}"

    def test_missing_column_detected(self):
        """Missing feature column is detected."""
        df = pd.DataFrame({"rainfall_intensity": [1.0], DATASET_TARGET_COLUMN: [50.0]})
        valid, errors = validate_dataset(df)
        assert valid is False
        assert any("Missing feature column" in e for e in errors)


# ─── Feature Engineering Tests ────────────────────────────────────────────

class TestFeatureEngineering:
    """Tests for feature matrix preparation."""

    def test_prepare_feature_matrix_order(self):
        """Feature matrix columns are in canonical order."""
        df = generate_synthetic_dataset(10, random_seed=42)
        X = prepare_feature_matrix(df)
        assert list(X.columns) == DATASET_FEATURE_COLUMNS

    def test_missing_column_raises(self):
        """Missing column raises ValueError."""
        df = pd.DataFrame({"rainfall_intensity": [1.0]})
        with pytest.raises(ValueError, match="Missing feature columns"):
            prepare_feature_matrix(df)

    def test_extract_target(self):
        """Target extraction works."""
        df = generate_synthetic_dataset(10, random_seed=42)
        df = df.rename(columns={"target_risk": DATASET_TARGET_COLUMN})
        y = extract_target(df)
        assert len(y) == 10
        assert y.name == DATASET_TARGET_COLUMN


# ─── Data Splitting Tests ─────────────────────────────────────────────────

class TestDataSplitting:
    """Tests for reproducible data splitting."""

    def test_split_sizes(self):
        """70/15/15 split produces correct approximate sizes."""
        df = generate_synthetic_dataset(1000, random_seed=42)
        df = df.rename(columns={"target_risk": DATASET_TARGET_COLUMN})
        split = split_dataset(df, random_seed=42)
        assert split.train_size == 700
        assert split.val_size == 150
        assert split.test_size == 150

    def test_split_reproducibility(self):
        """Same seed produces identical splits."""
        df = generate_synthetic_dataset(100, random_seed=42)
        df = df.rename(columns={"target_risk": DATASET_TARGET_COLUMN})
        s1 = split_dataset(df, random_seed=42)
        s2 = split_dataset(df, random_seed=42)
        assert s1.X_train.equals(s2.X_train)
        assert s1.y_test.equals(s2.y_test)

    def test_no_target_in_features(self):
        """Target column is not included in feature matrix."""
        df = generate_synthetic_dataset(100, random_seed=42)
        df = df.rename(columns={"target_risk": DATASET_TARGET_COLUMN})
        split = split_dataset(df, random_seed=42)
        assert DATASET_TARGET_COLUMN not in split.X_train.columns


# ─── Data Leakage Tests ──────────────────────────────────────────────────

class TestDataLeakage:
    """Tests for train/test leakage detection."""

    def test_no_leakage_in_synthetic(self):
        """Synthetic dataset with 1000 samples has no leakage."""
        df = generate_synthetic_dataset(1000, random_seed=42)
        df = df.rename(columns={"target_risk": DATASET_TARGET_COLUMN})
        split = split_dataset(df, random_seed=42)
        has_leakage, issues = check_data_leakage(split)
        assert has_leakage is False, f"Leakage detected: {issues}"


# ─── Baseline Model Tests ────────────────────────────────────────────────

class TestBaselineModels:
    """Tests for baseline model training and evaluation."""

    @pytest.fixture
    def split(self):
        df = generate_synthetic_dataset(200, random_seed=42)
        df = df.rename(columns={"target_risk": DATASET_TARGET_COLUMN})
        return split_dataset(df, random_seed=42)

    def test_mean_predictor(self, split):
        """Mean predictor produces constant predictions equal to training mean."""
        mp = MeanPredictor()
        mp.fit(split.X_train, split.y_train)
        preds = mp.predict(split.X_test)
        assert np.all(preds == mp.mean_value)

    def test_baselines_have_metrics(self, split):
        """Baselines produce train/val/test metrics."""
        results = train_baselines(split)
        assert "mean_predictor" in results
        assert "linear_regression" in results
        for name, r in results.items():
            for key in ["train", "val", "test"]:
                assert "mae" in r[key]
                assert "rmse" in r[key]
                assert "r2" in r[key]

    def test_gbr_beats_mean(self, split):
        """GBR should outperform mean predictor baseline."""
        baselines = train_baselines(split)
        _, gbr_metrics = train_gbr(split, random_seed=42)
        assert gbr_metrics["test"]["mae"] < baselines["mean_predictor"]["test"]["mae"]


# ─── Model Versioning Tests ──────────────────────────────────────────────

class TestModelVersioning:
    """Tests for model metadata and versioning."""

    def test_metadata_creation(self):
        """ModelMetadata creates valid metadata dict."""
        meta = ModelMetadata(
            model_version="1.0.0",
            model_data_status="synthetic",
            train_rows=700,
            validation_rows=150,
            test_rows=150,
        )
        d = meta.to_dict()
        assert d["model_version"] == "1.0.0"
        assert d["model_data_status"] == "synthetic"
        assert d["train_rows"] == 700
        assert "disclaimer" in d

    def test_metadata_save_load(self, tmp_path):
        """Metadata can be saved and loaded round-trip."""
        meta = ModelMetadata(model_version="2.0.0", model_data_status="synthetic")
        path = tmp_path / "meta.json"
        meta.save(path)
        loaded = ModelMetadata.load(path)
        assert loaded.model_version == "2.0.0"
        assert loaded.model_data_status == "synthetic"

    def test_synthetic_disclaimer(self):
        """Synthetic model generates appropriate disclaimer."""
        meta = ModelMetadata(model_data_status="synthetic")
        assert "synthetic" in meta.disclaimer.lower()
        assert "not validated" in meta.disclaimer.lower()


# ─── Feature Schema Validation Tests ──────────────────────────────────────

class TestFeatureSchemaValidation:
    """Tests for feature schema compatibility checks."""

    def test_matching_schema(self):
        """Matching schema passes."""
        valid, err = validate_model_feature_schema(list(FEATURE_NAMES))
        assert valid is True
        assert err is None

    def test_mismatched_schema_fails(self):
        """Mismatched schema fails."""
        wrong = ["wrong_feature"] + FEATURE_NAMES[1:]
        valid, err = validate_model_feature_schema(wrong)
        assert valid is False
        assert "mismatch" in err.lower()

    def test_wrong_order_fails(self):
        """Wrong feature order fails."""
        reversed_names = list(reversed(FEATURE_NAMES))
        valid, err = validate_model_feature_schema(reversed_names)
        assert valid is False


# ─── Model Loading & Prediction Tests ─────────────────────────────────────

class TestModelLoading:
    """Tests for model loading, metadata, and prediction."""

    def test_predictor_loads_model(self):
        """Predictor loads model artifact."""
        predictor = get_predictor()
        assert predictor.model is not None

    def test_predictor_has_model_info(self):
        """Predictor exposes model_info with version and data status."""
        predictor = get_predictor()
        info = predictor.model_info
        assert "model_name" in info
        assert "model_version" in info
        assert "model_data_status" in info
        assert "disclaimer" in info

    def test_predictor_model_data_status(self):
        """Model data status is 'synthetic'."""
        predictor = get_predictor()
        assert predictor.model_data_status == "synthetic"

    def test_prediction_includes_model_status(self):
        """Prediction result includes model_data_status and model_version."""
        result = predict_risk({name: FEATURE_SPECS[name]["default"] for name in FEATURE_NAMES})
        assert "model_data_status" in result
        assert "model_version" in result
        assert result["model_data_status"] == "synthetic"

    def test_prediction_bounds(self):
        """Prediction is always within [0, 100]."""
        for _ in range(10):
            features = {name: np.random.uniform(FEATURE_SPECS[name]["min"], FEATURE_SPECS[name]["max"]) for name in FEATURE_NAMES}
            result = predict_risk(features)
            assert 0.0 <= result["risk_score"] <= 100.0

    def test_nan_input_rejected(self):
        """NaN input is cleaned to default without crash."""
        features = {name: float("nan") for name in FEATURE_NAMES}
        result = predict_risk(features)
        assert 0.0 <= result["risk_score"] <= 100.0

    def test_infinity_input_handled(self):
        """Infinity input is cleaned to boundary without crash."""
        features = {name: float("inf") for name in FEATURE_NAMES}
        result = predict_risk(features)
        assert 0.0 <= result["risk_score"] <= 100.0


# ─── SHAP Compatibility Tests ────────────────────────────────────────────

class TestSHAPCompatibility:
    """Tests ensuring SHAP explainability continues working with the pipeline."""

    def test_shap_feature_alignment(self):
        """SHAP feature names match pipeline feature columns."""
        features = {name: FEATURE_SPECS[name]["default"] for name in FEATURE_NAMES}
        exp = explain_prediction(features)
        shap_feature_names = [f["feature"] for f in exp["features"]]
        # SHAP features are sorted by importance, not schema order — check set equality
        assert set(shap_feature_names) == set(DATASET_FEATURE_COLUMNS)

    def test_shap_seven_features(self):
        """SHAP produces attributions for all 7 features."""
        exp = explain_prediction({name: FEATURE_SPECS[name]["default"] for name in FEATURE_NAMES})
        assert len(exp["features"]) == 7
        assert len(exp["decision_trace"]) == 7

    def test_shap_prediction_matches(self):
        """SHAP prediction is a valid risk score."""
        exp = explain_prediction({name: FEATURE_SPECS[name]["default"] for name in FEATURE_NAMES})
        assert 0.0 <= exp["prediction"] <= 100.0


# ─── Pipeline Integration Tests ──────────────────────────────────────────

class TestPipelineIntegration:
    """Tests for the full training pipeline."""

    def test_full_pipeline_runs(self, tmp_path):
        """Full pipeline completes and returns valid report."""
        report = run_training_pipeline(
            n_samples=100,
            random_seed=42,
            output_dir=tmp_path,
            model_version="test.0.1",
        )
        assert report["dataset_valid"] is True
        assert report["has_leakage"] is False
        assert report["feature_schema_valid"] is True
        assert report["model_data_status"] == "synthetic"
        assert "gbr_metrics" in report
        assert report["gbr_metrics"]["test"]["r2"] > 0.5  # Basic sanity check

    def test_pipeline_reproducibility(self, tmp_path):
        """Pipeline is reproducible with same seed."""
        r1 = run_training_pipeline(n_samples=100, random_seed=42, output_dir=tmp_path / "r1", model_version="rep.1")
        r2 = run_training_pipeline(n_samples=100, random_seed=42, output_dir=tmp_path / "r2", model_version="rep.1")
        assert r1["gbr_metrics"] == r2["gbr_metrics"]

    def test_pipeline_saves_artifacts(self, tmp_path):
        """Pipeline saves model and metadata artifacts."""
        run_training_pipeline(n_samples=100, random_seed=42, output_dir=tmp_path, model_version="art.1")
        assert (tmp_path / "risk_gbr.joblib").exists()
        assert (tmp_path / "model_metadata.json").exists()
        assert (tmp_path / "risk_gbr_v art_1.joblib".replace(" ", "")).exists() or \
               (tmp_path / "risk_gbr_vart_1.joblib").exists()

    def test_metadata_artifact_content(self, tmp_path):
        """Saved metadata contains all required fields."""
        run_training_pipeline(n_samples=100, random_seed=42, output_dir=tmp_path, model_version="meta.1")
        with open(tmp_path / "model_metadata.json") as f:
            meta = json.load(f)
        assert meta["model_data_status"] == "synthetic"
        assert meta["model_version"] == "meta.1"
        assert meta["target_source"] == "synthetic"
        assert "feature_names" in meta
        assert meta["feature_names"] == FEATURE_NAMES
        assert "disclaimer" in meta


# ─── API Endpoint Tests ──────────────────────────────────────────────────

class TestModelInfoEndpoint:
    """Tests for the /api/model-info endpoint."""

    def test_model_info_endpoint(self):
        """GET /api/model-info returns model metadata."""
        resp = client.get("/api/model-info")
        assert resp.status_code == 200
        data = resp.json()
        assert "model_name" in data
        assert "model_version" in data
        assert "model_data_status" in data
        assert "disclaimer" in data

    def test_model_data_status_is_synthetic(self):
        """Model data status reported as synthetic."""
        resp = client.get("/api/model-info")
        data = resp.json()
        assert data["model_data_status"] == "synthetic"

    def test_health_includes_model(self):
        """Health endpoint includes model metadata."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "model" in data
        assert "model_version" in data["model"]
        assert "model_data_status" in data["model"]


# ─── Enums & Types Tests ─────────────────────────────────────────────────

class TestEnums:
    """Tests for pipeline enums."""

    def test_model_data_status_values(self):
        """ModelDataStatus has correct values."""
        assert ModelDataStatus.SYNTHETIC.value == "synthetic"
        assert ModelDataStatus.REAL.value == "real"
        assert ModelDataStatus.HYBRID.value == "hybrid"

    def test_target_source_values(self):
        """TargetSource has correct values."""
        assert TargetSource.SYNTHETIC.value == "synthetic"
        assert TargetSource.OBSERVED.value == "observed"

    def test_split_method_values(self):
        """SplitMethod has correct values."""
        assert SplitMethod.CHRONOLOGICAL.value == "chronological"
        assert SplitMethod.RANDOM.value == "random"
