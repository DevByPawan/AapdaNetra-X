"""
AapdaNetra-X — ML Training Pipeline
Reproducible, auditable training with baselines, model versioning,
and explicit synthetic/real data status tracking.

Phase 6.12: Real ML Pipeline

Usage:
    python -m ml.pipeline.train_pipeline [--n_samples 1000] [--seed 42] [--output_dir ml/models]

Given the same dataset, seed, and configuration, this pipeline produces
reproducible model artifacts and evaluation metrics.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Ensure root directory is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ml.features.schema import FEATURE_NAMES
from ml.pipeline import (
    DATASET_FEATURE_COLUMNS,
    DATASET_TARGET_COLUMN,
    ModelDataStatus,
    ModelMetadata,
    SplitMethod,
    DataSplit,
    check_data_leakage,
    split_dataset,
    validate_dataset,
    validate_model_feature_schema,
)
from ml.training.generator import generate_synthetic_dataset


# ─── Evaluation Utilities ─────────────────────────────────────────────────

def compute_metrics(y_true: pd.Series, y_pred: np.ndarray) -> Dict[str, float]:
    """Compute MAE, RMSE, R² on clipped predictions."""
    y_clipped = np.clip(y_pred, 0.0, 100.0)
    mae = float(mean_absolute_error(y_true, y_clipped))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_clipped)))
    r2 = float(r2_score(y_true, y_clipped))
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4)}


# ─── Baseline Models ─────────────────────────────────────────────────────

class MeanPredictor:
    """Mean predictor baseline — always predicts the training set mean."""

    def __init__(self):
        self.mean_value: float = 0.0

    def fit(self, X: pd.DataFrame, y: pd.Series):
        self.mean_value = float(y.mean())
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.full(len(X), self.mean_value)


def train_baselines(
    split: DataSplit,
) -> Dict[str, Dict[str, Any]]:
    """
    Trains baseline models and returns their metrics.
    Baselines:
        1. Mean predictor
        2. Linear Regression
    """
    results: Dict[str, Dict[str, Any]] = {}

    # 1. Mean predictor
    mean_model = MeanPredictor()
    mean_model.fit(split.X_train, split.y_train)
    results["mean_predictor"] = {
        "model": mean_model,
        "train": compute_metrics(split.y_train, mean_model.predict(split.X_train)),
        "val": compute_metrics(split.y_val, mean_model.predict(split.X_val)),
        "test": compute_metrics(split.y_test, mean_model.predict(split.X_test)),
        "config": {"type": "MeanPredictor"},
    }

    # 2. Linear Regression
    lr_model = LinearRegression()
    lr_model.fit(split.X_train, split.y_train)
    results["linear_regression"] = {
        "model": lr_model,
        "train": compute_metrics(split.y_train, lr_model.predict(split.X_train)),
        "val": compute_metrics(split.y_val, lr_model.predict(split.X_val)),
        "test": compute_metrics(split.y_test, lr_model.predict(split.X_test)),
        "config": {"type": "LinearRegression"},
    }

    return results


# ─── Primary Model Training ──────────────────────────────────────────────

GBR_HYPERPARAMETERS = {
    "n_estimators": 120,
    "learning_rate": 0.08,
    "max_depth": 4,
    "min_samples_split": 5,
    "min_samples_leaf": 1,
    "loss": "squared_error",
}


def train_gbr(
    split: DataSplit,
    random_seed: int = 42,
    hyperparameters: Optional[Dict[str, Any]] = None,
) -> Tuple[GradientBoostingRegressor, Dict[str, Dict[str, float]]]:
    """
    Trains GradientBoostingRegressor on train split.
    Evaluates on train/val/test.
    Does NOT tune against the test set.
    """
    params = dict(GBR_HYPERPARAMETERS)
    if hyperparameters:
        params.update(hyperparameters)

    model = GradientBoostingRegressor(
        n_estimators=params["n_estimators"],
        learning_rate=params["learning_rate"],
        max_depth=params["max_depth"],
        min_samples_split=params["min_samples_split"],
        min_samples_leaf=params.get("min_samples_leaf", 1),
        loss=params.get("loss", "squared_error"),
        random_state=random_seed,
    )
    model.fit(split.X_train, split.y_train)

    metrics = {
        "train": compute_metrics(split.y_train, model.predict(split.X_train)),
        "val": compute_metrics(split.y_val, model.predict(split.X_val)),
        "test": compute_metrics(split.y_test, model.predict(split.X_test)),
    }
    return model, metrics


# ─── Full Pipeline ────────────────────────────────────────────────────────

def run_training_pipeline(
    dataset: Optional[pd.DataFrame] = None,
    n_samples: int = 1000,
    random_seed: int = 42,
    output_dir: Optional[Path] = None,
    model_version: str = "1.0.0",
    dataset_source: str = "synthetic",
    target_source: str = "synthetic",
) -> Dict[str, Any]:
    """
    Runs the complete ML training pipeline:
    1. Generate or load dataset
    2. Validate dataset
    3. Split data
    4. Check for leakage
    5. Train baselines
    6. Train GBR
    7. Save model artifact + metadata
    8. Return comprehensive report

    Returns a dict with all results, metrics, and artifact paths.
    """
    out_dir = output_dir or (ROOT_DIR / "ml" / "models")
    out_dir.mkdir(parents=True, exist_ok=True)
    training_timestamp = datetime.now(timezone.utc).isoformat()

    report: Dict[str, Any] = {
        "pipeline_version": "6.12",
        "training_timestamp": training_timestamp,
        "random_seed": random_seed,
    }

    # ── 1. Dataset ──
    if dataset is not None:
        df = dataset.copy()
        # Rename target column if needed
        if "target_risk" in df.columns and DATASET_TARGET_COLUMN not in df.columns:
            df = df.rename(columns={"target_risk": DATASET_TARGET_COLUMN})
        report["dataset_source"] = dataset_source
    else:
        df = generate_synthetic_dataset(n_samples=n_samples, random_seed=random_seed)
        # Rename target column for pipeline consistency
        if "target_risk" in df.columns:
            df = df.rename(columns={"target_risk": DATASET_TARGET_COLUMN})
        report["dataset_source"] = "synthetic"
        dataset_source = "synthetic"

    report["dataset_rows"] = len(df)
    report["feature_count"] = len(DATASET_FEATURE_COLUMNS)
    report["feature_names"] = list(DATASET_FEATURE_COLUMNS)

    # ── 2. Validate ──
    is_valid, validation_errors = validate_dataset(df)
    report["dataset_valid"] = is_valid
    report["validation_errors"] = validation_errors
    if not is_valid:
        print(f"[Pipeline] Dataset validation failed: {validation_errors}")
        # Continue despite validation warnings for synthetic data

    # ── 3. Split ──
    split_method = SplitMethod.RANDOM
    if "timestamp" in df.columns:
        split_method = SplitMethod.CHRONOLOGICAL

    split = split_dataset(
        df, method=split_method, random_seed=random_seed,
        timestamp_column="timestamp" if "timestamp" in df.columns else None,
    )
    report["split_method"] = split_method.value
    report["train_size"] = split.train_size
    report["val_size"] = split.val_size
    report["test_size"] = split.test_size

    # ── 4. Leakage check ──
    has_leakage, leakage_issues = check_data_leakage(split)
    report["has_leakage"] = has_leakage
    report["leakage_issues"] = leakage_issues
    if has_leakage:
        print(f"[Pipeline] WARNING — Data leakage detected: {leakage_issues}")

    # ── 5. Baselines ──
    baseline_results = train_baselines(split)
    report["baselines"] = {
        name: {
            "train": r["train"],
            "val": r["val"],
            "test": r["test"],
            "config": r["config"],
        }
        for name, r in baseline_results.items()
    }

    # ── 6. GBR ──
    gbr_model, gbr_metrics = train_gbr(split, random_seed=random_seed)
    report["gbr_metrics"] = gbr_metrics
    report["gbr_hyperparameters"] = dict(GBR_HYPERPARAMETERS)

    # ── 7. Model data status ──
    if target_source == "synthetic" or dataset_source == "synthetic":
        model_data_status = ModelDataStatus.SYNTHETIC.value
    elif target_source == "observed":
        model_data_status = ModelDataStatus.REAL.value
    else:
        model_data_status = ModelDataStatus.HYBRID.value

    report["model_data_status"] = model_data_status

    # ── 7.5 Conformal Prediction Interval Calibration ──
    from ml.uncertainty.quantifier import ConformalQuantifier
    val_preds = gbr_model.predict(split.X_val)
    test_preds = gbr_model.predict(split.X_test)
    quantifier = ConformalQuantifier(calibration_path=out_dir / "conformal_calibration.json")
    calib_info = quantifier.calibrate(
        y_val=split.y_val,
        y_val_pred=val_preds,
        nominal_coverage=0.90,
        model_data_status=model_data_status,
        y_test=split.y_test,
        y_test_pred=test_preds,
    )
    report["conformal_calibration"] = calib_info

    # ── 8. Save artifacts ──
    # Save versioned model artifact
    model_filename = f"risk_gbr_v{model_version.replace('.', '_')}.joblib"
    model_path = out_dir / model_filename
    joblib.dump(gbr_model, model_path)

    # Also overwrite the canonical model path for backward compatibility
    canonical_model_path = out_dir / "risk_gbr.joblib"
    joblib.dump(gbr_model, canonical_model_path)

    report["model_artifact_path"] = str(model_path)
    report["canonical_model_path"] = str(canonical_model_path)

    # ── 9. Metadata ──
    metadata = ModelMetadata(
        model_name="GradientBoostingRegressor",
        model_version=model_version,
        training_dataset=f"{dataset_source}_{n_samples}" if dataset_source == "synthetic" else dataset_source,
        dataset_version="1.0.0",
        training_timestamp=training_timestamp,
        feature_schema_version="1.0.0",
        target_definition="risk_score: domain-formula-derived synthetic flood risk (0-100)" if dataset_source == "synthetic"
            else "risk_score: observed flood risk severity (0-100)",
        target_source=target_source,
        model_data_status=model_data_status,
        train_rows=split.train_size,
        validation_rows=split.val_size,
        test_rows=split.test_size,
        metrics=gbr_metrics,
        hyperparameters=dict(GBR_HYPERPARAMETERS),
        random_seed=random_seed,
        data_provenance="ml/training/generator.py generate_synthetic_dataset()" if dataset_source == "synthetic"
            else f"external:{dataset_source}",
        training_mode="offline_batch",
        feature_names=list(DATASET_FEATURE_COLUMNS),
        split_method=split_method.value,
        split_ratios="70/15/15",
    )

    metadata_path = out_dir / "model_metadata.json"
    metadata.save(metadata_path)

    # Also save versioned metadata
    versioned_metadata_path = out_dir / f"model_metadata_v{model_version.replace('.', '_')}.json"
    metadata.save(versioned_metadata_path)

    report["metadata_path"] = str(metadata_path)
    report["metadata"] = metadata.to_dict()

    # ── 10. Feature schema validation ──
    schema_valid, schema_err = validate_model_feature_schema(list(DATASET_FEATURE_COLUMNS))
    report["feature_schema_valid"] = schema_valid
    report["feature_schema_error"] = schema_err

    # ── Print summary ──
    print("\n" + "=" * 65)
    print("  AAPDANETRA-X ML PIPELINE — TRAINING REPORT")
    print(f"  Model Version: {model_version}")
    print(f"  Training Data Status: {model_data_status.upper()}")
    print(f"  Dataset: {dataset_source} ({len(df)} rows)")
    print("=" * 65)
    print(f"\n  Baselines:")
    for name, res in baseline_results.items():
        print(f"    {name}: Test MAE={res['test']['mae']:.4f}, RMSE={res['test']['rmse']:.4f}, R²={res['test']['r2']:.4f}")
    print(f"\n  GradientBoostingRegressor:")
    print(f"    Train: MAE={gbr_metrics['train']['mae']:.4f}, RMSE={gbr_metrics['train']['rmse']:.4f}, R²={gbr_metrics['train']['r2']:.4f}")
    print(f"    Val:   MAE={gbr_metrics['val']['mae']:.4f}, RMSE={gbr_metrics['val']['rmse']:.4f}, R²={gbr_metrics['val']['r2']:.4f}")
    print(f"    Test:  MAE={gbr_metrics['test']['mae']:.4f}, RMSE={gbr_metrics['test']['rmse']:.4f}, R²={gbr_metrics['test']['r2']:.4f}")
    print(f"\n  Data Leakage: {'DETECTED' if has_leakage else 'NONE'}")
    print(f"  Feature Schema Valid: {schema_valid}")
    if model_data_status == ModelDataStatus.SYNTHETIC.value:
        print(f"\n  ⚠ IMPORTANT: Model trained on SYNTHETIC data only.")
        print(f"    These metrics do NOT reflect real-world performance.")
    print("=" * 65 + "\n")

    return report


# ─── CLI Entry Point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AapdaNetra-X ML Training Pipeline")
    parser.add_argument("--n_samples", type=int, default=1000, help="Number of synthetic samples")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output_dir", type=str, default=None, help="Model output directory")
    parser.add_argument("--version", type=str, default="1.0.0", help="Model version")
    args = parser.parse_args()

    out = Path(args.output_dir) if args.output_dir else None
    run_training_pipeline(
        n_samples=args.n_samples,
        random_seed=args.seed,
        output_dir=out,
        model_version=args.version,
    )
