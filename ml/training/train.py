"""
AapdaNetra-X — ML Risk Engine Training Script
Trains scikit-learn GradientBoostingRegressor on synthetic flood risk data.
"""
import json
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

# Ensure root directory is in sys.path when executing directly
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ml.features.schema import FEATURE_NAMES
from ml.training.generator import generate_synthetic_dataset

MODELS_DIR = ROOT_DIR / "ml" / "models"


def train_and_evaluate(
    n_samples: int = 1000,
    random_seed: int = 42
):
    """
    Generates dataset, splits data, trains GBR model, computes evaluation metrics,
    and saves trained model artifact and metadata.
    """
    os.makedirs(MODELS_DIR, exist_ok=True)

    print(f"[1/4] Generating synthetic disaster dataset (n={n_samples}, seed={random_seed})...")
    df = generate_synthetic_dataset(n_samples=n_samples, random_seed=random_seed)

    X = df[FEATURE_NAMES]
    y = df["target_risk"]

    # 70% train, 15% val, 15% test
    print("[2/4] Splitting dataset into train (70%), val (15%), test (15%)...")
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.30, random_state=random_seed
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.50, random_state=random_seed
    )

    print("[3/4] Training GradientBoostingRegressor...")
    model = GradientBoostingRegressor(
        n_estimators=120,
        learning_rate=0.08,
        max_depth=4,
        min_samples_split=5,
        random_state=random_seed,
    )
    model.fit(X_train, y_train)

    # Evaluate
    def get_metrics(X_data, y_true):
        preds = model.predict(X_data)
        preds_clipped = np.clip(preds, 0.0, 100.0)
        mae = float(mean_absolute_error(y_true, preds_clipped))
        rmse = float(np.sqrt(mean_squared_error(y_true, preds_clipped)))
        r2 = float(r2_score(y_true, preds_clipped))
        return {"mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4)}

    train_metrics = get_metrics(X_train, y_train)
    val_metrics = get_metrics(X_val, y_val)
    test_metrics = get_metrics(X_test, y_test)

    print("\n" + "=" * 55)
    print("  AAPDANETRA-X ML RISK MODEL EVALUATION REPORT")
    print("  *NOTE: Evaluated on synthetic domain data for MVP demo*")
    print("=" * 55)
    print(f"  Train Set (n={len(X_train)}): MAE={train_metrics['mae']:.4f} | RMSE={train_metrics['rmse']:.4f} | R²={train_metrics['r2']:.4f}")
    print(f"  Val Set   (n={len(X_val)}): MAE={val_metrics['mae']:.4f} | RMSE={val_metrics['rmse']:.4f} | R²={val_metrics['r2']:.4f}")
    print(f"  Test Set  (n={len(X_test)}): MAE={test_metrics['mae']:.4f} | RMSE={test_metrics['rmse']:.4f} | R²={test_metrics['r2']:.4f}")
    print("=" * 55 + "\n")

    # [4/4] Save model artifact & metadata
    model_path = MODELS_DIR / "risk_gbr.joblib"
    joblib.dump(model, model_path)
    print(f"[4/4] Model saved successfully to {model_path}")

    metadata = {
        "model_type": "scikit-learn.GradientBoostingRegressor",
        "random_seed": random_seed,
        "n_samples": n_samples,
        "features": FEATURE_NAMES,
        "hyperparameters": {
            "n_estimators": 120,
            "learning_rate": 0.08,
            "max_depth": 4,
            "min_samples_split": 5,
        },
        "metrics": {
            "train": train_metrics,
            "val": val_metrics,
            "test": test_metrics,
        },
        "disclaimer": "Metrics evaluated on synthetic disaster data. Not verified for real-world operational deployments.",
    }

    metadata_path = MODELS_DIR / "model_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    return model, metadata


if __name__ == "__main__":
    train_and_evaluate()
