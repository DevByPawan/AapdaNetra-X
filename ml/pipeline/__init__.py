"""
AapdaNetra-X — ML Pipeline Dataset Contract & Feature Engineering

Defines the authoritative dataset schema, feature engineering pipeline,
data validation, split methodology, and model versioning contracts.

All training, inference, SHAP, and risk-engine code MUST use these
centralized definitions. Feature names, ordering, and validation rules
are defined here ONCE and consumed everywhere.

Phase 6.12: Real ML Pipeline Foundation
"""
import math
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
import pandas as pd

from ml.features.schema import FEATURE_NAMES, FEATURE_SPECS


# ─── Dataset Schema ──────────────────────────────────────────────────────

# Canonical feature columns — imported from the single source of truth
DATASET_FEATURE_COLUMNS: List[str] = list(FEATURE_NAMES)

# Target column
DATASET_TARGET_COLUMN: str = "risk_score"

# Optional metadata columns (not used as ML features)
DATASET_METADATA_COLUMNS: List[str] = [
    "timestamp",
    "location",
    "source",
    "provenance",
    "data_mode",
    "target_source",
    "dataset_version",
]


class TargetSource(str, Enum):
    """Origin of the target/label value."""
    SYNTHETIC = "synthetic"
    OBSERVED = "observed"
    DERIVED = "derived"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class ModelDataStatus(str, Enum):
    """Training data provenance status — distinct from DATA_MODE."""
    SYNTHETIC = "synthetic"
    REAL = "real"
    HYBRID = "hybrid"
    UNAVAILABLE = "unavailable"


class SplitMethod(str, Enum):
    """Dataset splitting methodology."""
    CHRONOLOGICAL = "chronological"
    RANDOM_STRATIFIED = "random_stratified"
    RANDOM = "random"


# ─── Data Validation ─────────────────────────────────────────────────────

def validate_feature_row(row: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validates a single feature row against the dataset schema.
    Returns (is_valid, list_of_errors).
    Rejects NaN, Infinity, missing mandatory features, and out-of-bounds values.
    """
    errors: List[str] = []

    for col in DATASET_FEATURE_COLUMNS:
        if col not in row:
            errors.append(f"Missing mandatory feature: {col}")
            continue
        val = row[col]
        if val is None:
            errors.append(f"Feature '{col}' is None")
            continue
        try:
            fval = float(val)
        except (ValueError, TypeError):
            errors.append(f"Feature '{col}' cannot be converted to float: {val!r}")
            continue
        if not math.isfinite(fval):
            errors.append(f"Feature '{col}' is not finite: {fval}")
            continue
        spec = FEATURE_SPECS[col]
        if fval < spec["min"] or fval > spec["max"]:
            errors.append(
                f"Feature '{col}' = {fval} is out of bounds [{spec['min']}, {spec['max']}]"
            )

    return (len(errors) == 0, errors)


def validate_target(value: Any) -> Tuple[bool, Optional[str]]:
    """Validates a target/label value."""
    if value is None:
        return (False, "Target value is None")
    try:
        fval = float(value)
    except (ValueError, TypeError):
        return (False, f"Target cannot be converted to float: {value!r}")
    if not math.isfinite(fval):
        return (False, f"Target is not finite: {fval}")
    if fval < 0.0 or fval > 100.0:
        return (False, f"Target {fval} is out of expected range [0, 100]")
    return (True, None)


def validate_dataset(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Validates an entire dataset DataFrame.
    Returns (is_valid, list_of_errors).
    """
    errors: List[str] = []

    # Check mandatory columns
    for col in DATASET_FEATURE_COLUMNS:
        if col not in df.columns:
            errors.append(f"Missing feature column: {col}")

    if DATASET_TARGET_COLUMN not in df.columns:
        errors.append(f"Missing target column: {DATASET_TARGET_COLUMN}")

    if errors:
        return (False, errors)

    # Check for NaN/Inf in features and target
    feature_cols = DATASET_FEATURE_COLUMNS + [DATASET_TARGET_COLUMN]
    for col in feature_cols:
        nan_count = df[col].isna().sum()
        if nan_count > 0:
            errors.append(f"Column '{col}' contains {nan_count} NaN values")
        inf_count = np.isinf(df[col].astype(float)).sum()
        if inf_count > 0:
            errors.append(f"Column '{col}' contains {inf_count} Inf values")

    # Check feature bounds
    for col in DATASET_FEATURE_COLUMNS:
        spec = FEATURE_SPECS[col]
        below = (df[col] < spec["min"]).sum()
        above = (df[col] > spec["max"]).sum()
        if below > 0:
            errors.append(f"Column '{col}' has {below} values below min ({spec['min']})")
        if above > 0:
            errors.append(f"Column '{col}' has {above} values above max ({spec['max']})")

    # Check target bounds
    below_t = (df[DATASET_TARGET_COLUMN] < 0.0).sum()
    above_t = (df[DATASET_TARGET_COLUMN] > 100.0).sum()
    if below_t > 0:
        errors.append(f"Target column has {below_t} values below 0.0")
    if above_t > 0:
        errors.append(f"Target column has {above_t} values above 100.0")

    # Check duplicates
    dup_count = df.duplicated(subset=DATASET_FEATURE_COLUMNS).sum()
    if dup_count > 0:
        errors.append(f"Dataset contains {dup_count} duplicate feature rows")

    return (len(errors) == 0, errors)


# ─── Feature Engineering ─────────────────────────────────────────────────

def prepare_feature_matrix(
    df: pd.DataFrame,
    feature_columns: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Extracts and orders the feature matrix from a DataFrame.
    Returns a DataFrame with exactly DATASET_FEATURE_COLUMNS in canonical order.

    Raises ValueError if any required feature column is missing.
    """
    cols = feature_columns or DATASET_FEATURE_COLUMNS
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing feature columns: {missing}")
    return df[cols].copy()


def extract_target(df: pd.DataFrame) -> pd.Series:
    """Extracts the target column from a DataFrame."""
    if DATASET_TARGET_COLUMN not in df.columns:
        raise ValueError(f"Missing target column: {DATASET_TARGET_COLUMN}")
    return df[DATASET_TARGET_COLUMN].copy()


# ─── Data Splitting ──────────────────────────────────────────────────────

@dataclass
class DataSplit:
    """Holds train/validation/test splits with metadata."""
    X_train: pd.DataFrame
    X_val: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_val: pd.Series
    y_test: pd.Series
    split_method: SplitMethod
    random_seed: int
    train_size: int = 0
    val_size: int = 0
    test_size: int = 0
    split_boundaries: Optional[Dict[str, str]] = None

    def __post_init__(self):
        self.train_size = len(self.X_train)
        self.val_size = len(self.X_val)
        self.test_size = len(self.X_test)


def split_dataset(
    df: pd.DataFrame,
    method: SplitMethod = SplitMethod.RANDOM,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_seed: int = 42,
    timestamp_column: Optional[str] = None,
) -> DataSplit:
    """
    Splits a dataset into train/val/test according to the specified method.

    For CHRONOLOGICAL: requires timestamp_column. Splits by sorted time.
    For RANDOM/RANDOM_STRATIFIED: uses random_seed for reproducibility.

    Never leaks validation/test data into training.
    """
    from sklearn.model_selection import train_test_split

    assert abs(train_ratio + val_ratio + test_ratio - 1.0) < 1e-6, \
        f"Split ratios must sum to 1.0, got {train_ratio + val_ratio + test_ratio}"

    X = prepare_feature_matrix(df)
    y = extract_target(df)
    split_boundaries = None

    if method == SplitMethod.CHRONOLOGICAL and timestamp_column and timestamp_column in df.columns:
        # Sort by timestamp
        sorted_idx = df[timestamp_column].sort_values().index
        n = len(sorted_idx)
        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))

        train_idx = sorted_idx[:train_end]
        val_idx = sorted_idx[train_end:val_end]
        test_idx = sorted_idx[val_end:]

        split_boundaries = {
            "train_end": str(df.loc[train_idx[-1], timestamp_column]) if len(train_idx) > 0 else "",
            "val_end": str(df.loc[val_idx[-1], timestamp_column]) if len(val_idx) > 0 else "",
        }

        return DataSplit(
            X_train=X.loc[train_idx],
            X_val=X.loc[val_idx],
            X_test=X.loc[test_idx],
            y_train=y.loc[train_idx],
            y_val=y.loc[val_idx],
            y_test=y.loc[test_idx],
            split_method=method,
            random_seed=random_seed,
            split_boundaries=split_boundaries,
        )
    else:
        # Random split: 70% train, then 50/50 of remainder for val/test
        val_test_ratio = val_ratio + test_ratio
        X_train, X_temp, y_train, y_temp = train_test_split(
            X, y, test_size=val_test_ratio, random_state=random_seed,
        )
        relative_test = test_ratio / val_test_ratio
        X_val, X_test, y_val, y_test = train_test_split(
            X_temp, y_temp, test_size=relative_test, random_state=random_seed,
        )
        return DataSplit(
            X_train=X_train,
            X_val=X_val,
            X_test=X_test,
            y_train=y_train,
            y_val=y_val,
            y_test=y_test,
            split_method=method,
            random_seed=random_seed,
        )


# ─── Data Leakage Checks ─────────────────────────────────────────────────

def check_data_leakage(split: DataSplit) -> Tuple[bool, List[str]]:
    """
    Checks for train/test data leakage by detecting duplicate rows across splits.
    Returns (has_leakage, list_of_issues).
    """
    issues: List[str] = []

    # Check train-val overlap
    train_hashes = set(split.X_train.apply(lambda r: hash(tuple(r)), axis=1))
    val_hashes = set(split.X_val.apply(lambda r: hash(tuple(r)), axis=1))
    test_hashes = set(split.X_test.apply(lambda r: hash(tuple(r)), axis=1))

    tv_overlap = train_hashes & val_hashes
    if tv_overlap:
        issues.append(f"Train-validation overlap: {len(tv_overlap)} duplicate feature rows")

    tt_overlap = train_hashes & test_hashes
    if tt_overlap:
        issues.append(f"Train-test overlap: {len(tt_overlap)} duplicate feature rows")

    vt_overlap = val_hashes & test_hashes
    if vt_overlap:
        issues.append(f"Validation-test overlap: {len(vt_overlap)} duplicate feature rows")

    return (len(issues) > 0, issues)


# ─── Model Versioning ────────────────────────────────────────────────────

@dataclass
class ModelMetadata:
    """Complete model version metadata for reproducibility and provenance."""
    model_name: str = "GradientBoostingRegressor"
    model_version: str = "1.0.0"
    training_dataset: str = "synthetic_1000"
    dataset_version: str = "1.0.0"
    training_timestamp: str = ""
    feature_schema_version: str = "1.0.0"
    target_definition: str = "risk_score: domain-formula-derived synthetic flood risk (0-100)"
    target_source: str = "synthetic"
    model_data_status: str = "synthetic"
    train_rows: int = 0
    validation_rows: int = 0
    test_rows: int = 0
    metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    random_seed: int = 42
    data_provenance: str = "ml/training/generator.py generate_synthetic_dataset()"
    training_mode: str = "offline_batch"
    feature_names: List[str] = field(default_factory=lambda: list(DATASET_FEATURE_COLUMNS))
    split_method: str = "random"
    split_ratios: str = "70/15/15"
    disclaimer: str = ""

    def __post_init__(self):
        if not self.training_timestamp:
            self.training_timestamp = datetime.now(timezone.utc).isoformat()
        if not self.disclaimer:
            self.disclaimer = self._generate_disclaimer()

    def _generate_disclaimer(self) -> str:
        if self.model_data_status == ModelDataStatus.SYNTHETIC.value:
            return (
                "Model trained on synthetic data generated by a domain-informed formula. "
                "Metrics reflect synthetic-data performance ONLY. "
                "Not validated for real-world operational deployment."
            )
        elif self.model_data_status == ModelDataStatus.REAL.value:
            return (
                "Model trained on real observed disaster data. "
                "Metrics reflect real-data performance on held-out test set."
            )
        else:
            return "Model training data status unknown. Exercise caution."

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, path: Path):
        """Save metadata to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    @classmethod
    def load(cls, path: Path) -> "ModelMetadata":
        """Load metadata from JSON file."""
        with open(path, "r") as f:
            data = json.load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def validate_model_feature_schema(
    model_feature_names: List[str],
    expected_feature_names: Optional[List[str]] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validates that a loaded model's feature schema matches the expected schema.
    Returns (is_compatible, error_message).
    """
    expected = expected_feature_names or DATASET_FEATURE_COLUMNS
    if model_feature_names != expected:
        return (False, (
            f"Feature schema mismatch. "
            f"Model expects: {model_feature_names}. "
            f"Pipeline expects: {expected}"
        ))
    return (True, None)
