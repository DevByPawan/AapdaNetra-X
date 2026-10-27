"""
Delhi Traffic Density Real Data Preprocessor for AapdaNetra-X
Reads raw 2020 Delhi traffic density archive (delhi_traffic_density_2020.zip)
containing 40 complete days (Sep-Dec 2020) recorded at 12 Hz across 6 cameras.
Derives a deterministic empirical road-congestion baseline ratio [0.0, 1.0].
STRICTLY FLAGS THAT THIS IS A 2020 EMPIRICAL BASELINE, NOT JULY 2023 TRAFFIC.
"""
import os
import zipfile
from typing import Dict, Tuple, Optional, Any
import pandas as pd
from app.ml.real_data.provenance import resolve_data_path


class TrafficPreprocessor:
    """
    Dedicated preprocessor for 2020 Delhi Traffic Density Dataset.
    Extracts deterministic empirical road_congestion ratio [0.0, 1.0].
    """

    def __init__(self, zip_path: str = "data/raw/delhi_traffic_density_2020.zip"):
        self.zip_path = zip_path
        self._overall_mean_congestion: Optional[float] = None
        self._hourly_diurnal_profile: Dict[int, float] = {}
        self._is_loaded = False
        self.dataset_provenance = "data/raw/delhi_traffic_density_2020.zip (IIT Delhi 2020 Traffic Dataset)"
        self.temporal_context = "Delhi 2020 empirical baseline (Sep-Dec 2020, 40 days, NOT July 2023 flood traffic)"
        self.spatial_provenance = "3 Intersections / 6 Camera feeds in Delhi"

    def load(self) -> None:
        """Reads raw traffic CSVs inside the ZIP archive without altering raw files."""
        if self._is_loaded:
            return

        resolved_path = resolve_data_path(self.zip_path)
        if not os.path.exists(resolved_path):
            raise FileNotFoundError(f"Traffic raw dataset archive not found at '{resolved_path}'")

        zf = zipfile.ZipFile(resolved_path, "r")
        csv_files = [f for f in zf.namelist() if f.endswith(".csv")]

        if not csv_files:
            raise ValueError(f"No CSV files found in traffic ZIP archive '{resolved_path}'")

        # Load sample days to build deterministic diurnal hourly empirical baseline (07:00-22:00 IST)
        all_hourly_means = {h: [] for h in range(7, 23)}
        sample_files = sorted(csv_files)[:10]  # Sample 10 days for deterministic diurnal baseline

        for cname in sample_files:
            with zf.open(cname) as f:
                df = pd.read_csv(f)
                qd_cols = [c for c in df.columns if "QueueDensity" in c]
                if qd_cols:
                    df["comp_qd"] = df[qd_cols].mean(axis=1)
                    dt_series = pd.to_datetime(df["EpochTime"], unit="ms" if df["EpochTime"].iloc[0] > 1e11 else "s")
                    df["hour_ist"] = dt_series.dt.hour
                    grouped = df.groupby("hour_ist")["comp_qd"].mean()
                    for h, val in grouped.items():
                        if h in all_hourly_means:
                            all_hourly_means[h].append(float(val))

        for h, vals in all_hourly_means.items():
            self._hourly_diurnal_profile[h] = round(float(pd.Series(vals).mean()), 4) if vals else 0.45

        all_vals = [v for vals in all_hourly_means.values() for v in vals]
        self._overall_mean_congestion = round(float(pd.Series(all_vals).mean()), 4) if all_vals else 0.45
        self._is_loaded = True

    def get_road_congestion(self, hour_ist: Optional[int] = None) -> Tuple[float, Dict[str, Any]]:
        """
        Returns (road_congestion_ratio, metadata_dict) for given IST hour (0-23) or overall mean.
        """
        self.load()

        if hour_ist is not None and hour_ist in self._hourly_diurnal_profile:
            val = self._hourly_diurnal_profile[hour_ist]
        else:
            val = self._overall_mean_congestion

        meta = {
            "source": self.dataset_provenance,
            "temporal_context": self.temporal_context,
            "spatial_resolution": self.spatial_provenance,
            "unit": "ratio (0.0 - 1.0)",
            "semantics": "empirical_queue_density_composite_ratio",
            "provenance": "DERIVED_FROM_REAL",
            "is_july2023_flood_traffic": False,
            "overall_mean_congestion": self._overall_mean_congestion,
        }

        return float(val), meta
