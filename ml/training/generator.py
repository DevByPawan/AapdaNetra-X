"""
AapdaNetra-X — Synthetic Disaster Dataset Generator
Generates reproducible synthetic flood risk samples with domain-informed physical target relations.
"""
import numpy as np
import pandas as pd
from typing import Tuple
from ml.features.schema import FEATURE_NAMES, FEATURE_SPECS


def generate_synthetic_dataset(
    n_samples: int = 1000,
    random_seed: int = 42
) -> pd.DataFrame:
    """
    Generates a synthetic dataset of disaster feature vectors and calculated target risk scores.
    Uses fixed random seed for reproducibility.
    """
    rng = np.random.RandomState(random_seed)

    # 1. Generate realistic feature ranges
    rainfall_intensity = rng.uniform(0.0, 180.0, n_samples)  # mm/h
    rainfall_trend = rng.normal(2.0, 10.0, n_samples)        # mm/h²
    water_level = rng.uniform(0.5, 9.5, n_samples)           # m
    water_level_trend = rng.normal(0.2, 0.6, n_samples)      # m/h
    road_congestion = rng.beta(2, 2, n_samples)              # 0.0 - 1.0
    population_exposure = rng.uniform(500, 50000, n_samples) # count
    infra_vulnerability = rng.beta(3, 2, n_samples)          # 0.0 - 1.0

    # Clip features to valid domain bounds
    rainfall_intensity = np.clip(rainfall_intensity, 0.0, 300.0)
    rainfall_trend = np.clip(rainfall_trend, -50.0, 50.0)
    water_level = np.clip(water_level, 0.0, 15.0)
    water_level_trend = np.clip(water_level_trend, -2.0, 5.0)
    road_congestion = np.clip(road_congestion, 0.0, 1.0)
    population_exposure = np.clip(population_exposure, 0.0, 100000.0)
    infra_vulnerability = np.clip(infra_vulnerability, 0.0, 1.0)

    # 2. Calculate target risk score using a meaningful domain formula:
    # Hydrological risk sub-score (non-linear impact of water level & rainfall intensity)
    hydro_risk = 35.0 * (water_level / 10.0)**1.4 + 25.0 * (rainfall_intensity / 150.0)**1.2
    
    # Dynamic trend escalation factor
    trend_factor = 1.0 + 0.15 * np.maximum(0, water_level_trend) + 0.10 * np.maximum(0, rainfall_trend / 20.0)

    # Vulnerability & exposure sub-score
    exposure_factor = 0.5 + 0.5 * (population_exposure / 30000.0)
    vuln_factor = 0.6 + 0.4 * infra_vulnerability
    congestion_penalty = 1.0 + 0.25 * (road_congestion**2)

    # Composite target risk score
    raw_risk = hydro_risk * trend_factor * exposure_factor * vuln_factor * congestion_penalty

    # Add controlled Gaussian noise (std = 3.0) to model real-world variability
    noise = rng.normal(0, 3.0, n_samples)
    target_risk = np.clip(raw_risk + noise, 0.0, 100.0)

    # Build DataFrame
    df = pd.DataFrame({
        "rainfall_intensity": rainfall_intensity,
        "rainfall_trend": rainfall_trend,
        "water_level": water_level,
        "water_level_trend": water_level_trend,
        "road_congestion": road_congestion,
        "population_exposure": population_exposure,
        "infrastructure_vulnerability": infra_vulnerability,
        "target_risk": target_risk,
    })

    return df


if __name__ == "__main__":
    data = generate_synthetic_dataset(1000, seed=42)
    print(f"Generated dataset shape: {data.shape}")
    print(data.describe())
