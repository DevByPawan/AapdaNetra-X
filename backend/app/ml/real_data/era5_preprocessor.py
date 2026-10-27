"""
ERA5-Land Real Data Preprocessor for AapdaNetra-X
Handles ERA5 total precipitation (tp) GRIB forecast-run accumulation semantics correctly:

Forecast-Run De-accumulation Mathematics:
For every 00 UTC forecast run (init_dt):
  step 1 (p2=1, valid 01:00 UTC): hourly_mm = max(0.0, tp_1 * 1000.0)
  step s (p2=s, s >= 2, valid s:00 UTC): hourly_mm = max(0.0, (tp_s - tp_(s-1)) * 1000.0)

Boundary & Reset Rules:
  - Resets previous_tp at every forecast run boundary (init_dt).
  - Does NOT subtract across forecast-run boundaries.
  - Step 24 of run D (valid (D+1) 00:00 UTC) de-accumulates against Step 23 of run D.
  - Step 1 of run D+1 (valid (D+1) 01:00 UTC) resets previous_tp and uses tp_1 * 1000.0.

July 2023 Window:
  Contains exactly 744 unique hourly timestamps from 2023-07-01T00:00:00Z to 2023-07-31T23:00:00Z.
"""
import os
import zipfile
import struct
import datetime
from typing import Dict, Tuple, Optional, List, Any
from app.ml.real_data.provenance import resolve_data_path


class ERA5Preprocessor:
    """
    Dedicated preprocessor for ERA5-Land GRIB dataset (July 2023).
    Extracts hourly de-accumulated rainfall intensity (mm/h) and rainfall trend (mm/h²).
    """

    JULY_2023_START = "2023-07-01T00:00:00Z"
    JULY_2023_END = "2023-07-31T23:00:00Z"

    def __init__(
        self,
        grib_path: str = "data/raw/era5_land_delhi_july2023.grib",
        june30_grib_path: Optional[str] = "data/raw/era5_land_delhi_june30_2023.grib",
    ):
        self.grib_path = grib_path
        self.june30_grib_path = june30_grib_path
        self._hourly_data: Dict[str, float] = {}
        self._hourly_trends: Dict[str, float] = {}
        self._is_loaded = False
        self.dataset_provenance = "data/raw/era5_land_delhi_july2023.grib (ECMWF ERA5-Land GRIB1 Param 228 tp)"
        self.spatial_provenance = "ERA5 Grid (0.1° x 0.1°, ~11 km resolution covering Delhi study bbox 77.19-77.26E, 28.61-28.67N)"

    def load(self) -> None:
        """Reads raw ERA5 GRIB file without modifying it and de-accumulates hourly values."""
        if self._is_loaded:
            return

        resolved_july_path = resolve_data_path(self.grib_path)
        if not os.path.exists(resolved_july_path):
            raise FileNotFoundError(f"ERA5 raw dataset not found at '{resolved_july_path}'")

        grib_files_to_read = [resolved_july_path]

        if self.june30_grib_path:
            resolved_june30_path = resolve_data_path(self.june30_grib_path)
            if os.path.exists(resolved_june30_path):
                grib_files_to_read.append(resolved_june30_path)

        # Group raw GRIB messages by forecast initialization time (init_dt)
        runs: Dict[datetime.datetime, List[Tuple[int, datetime.datetime, float]]] = {}

        for filepath in grib_files_to_read:
            # ERA5 file is a ZIP archive containing data.grib
            with zipfile.ZipFile(filepath, "r") as z:
                buf = z.read("data.grib")

            pos = 0
            while pos < len(buf):
                idx = buf.find(b"GRIB", pos)
                if idx == -1:
                    break
                tot_len = (buf[idx + 4] << 16) + (buf[idx + 5] << 8) + buf[idx + 6]
                pds_offset = idx + 8
                pds_len = (buf[pds_offset] << 16) + (buf[pds_offset + 1] << 8) + buf[pds_offset + 2]
                gds_offset = pds_offset + pds_len
                gds_len = (buf[gds_offset] << 16) + (buf[gds_offset + 1] << 8) + buf[gds_offset + 2]
                bds_offset = gds_offset + gds_len

                year = buf[pds_offset + 12]
                century = buf[pds_offset + 24]
                month = buf[pds_offset + 13]
                day = buf[pds_offset + 14]
                hour = buf[pds_offset + 15]
                p2 = buf[pds_offset + 19]

                full_year = (century - 1) * 100 + year
                init_dt = datetime.datetime(full_year, month, day, hour, tzinfo=datetime.timezone.utc)
                valid_dt = init_dt + datetime.timedelta(hours=p2)

                # Unpack BDS reference value (cumulative meters of water)
                ref_val = struct.unpack(">f", buf[bds_offset + 6 : bds_offset + 10])[0]

                if init_dt not in runs:
                    runs[init_dt] = []
                # Avoid duplicate messages if both files contain the same record
                rec = (p2, valid_dt, ref_val * 1000.0)
                if rec not in runs[init_dt]:
                    runs[init_dt].append(rec)

                pos = idx + tot_len

        # De-accumulate within each forecast initialization run independently
        raw_hourly_records: List[Tuple[datetime.datetime, float]] = []

        for init_dt in sorted(runs.keys()):
            # Sort forecast steps by p2 (1, 2, ..., 24)
            step_list = sorted(runs[init_dt], key=lambda x: x[0])

            # Handle partial June 30 run where step 23 is missing
            if len(step_list) == 1 and step_list[0][0] == 24:
                valid_dt = step_list[0][1]
                dt_str = valid_dt.isoformat().replace("+00:00", "Z")
                if dt_str.startswith("2023-07"):
                    raise ValueError(
                        f"Cannot de-accumulate boundary observation at {dt_str}: "
                        "preceding forecast step 23 (June 30 23:00 UTC) is missing. "
                        "Do not use artificial fallback values."
                    )
                continue

            # Standard forecast run de-accumulation
            prev_tp_mm = 0.0  # Reset previous_tp at start of each 00 UTC run

            for p2, valid_dt, curr_tp_mm in step_list:
                dt_str = valid_dt.isoformat().replace("+00:00", "Z")

                if not dt_str.startswith("2023-07"):
                    prev_tp_mm = curr_tp_mm
                    continue

                if p2 == 1:
                    # Step 1: tp1 * 1000.0 (previous_tp reset)
                    hourly_mm = max(0.0, curr_tp_mm)
                else:
                    # Step s (s >= 2): (tp_s - tp_(s-1)) * 1000.0
                    diff_mm = curr_tp_mm - prev_tp_mm
                    hourly_mm = max(0.0, diff_mm)

                prev_tp_mm = curr_tp_mm
                raw_hourly_records.append((valid_dt, hourly_mm))

        # Sort all July hourly records by valid timestamp
        raw_hourly_records.sort(key=lambda x: x[0])

        # Deduplicate and populate hourly intensity map
        for dt, val in raw_hourly_records:
            dt_str = dt.isoformat().replace("+00:00", "Z")
            self._hourly_data[dt_str] = round(val, 4)

        # Calculate rainfall trend (mm/h²) across consecutive real hourly timesteps ONLY
        sorted_timestamps = sorted(self._hourly_data.keys())
        for i, dt_str in enumerate(sorted_timestamps):
            if i == 0:
                self._hourly_trends[dt_str] = 0.0
            else:
                prev_str = sorted_timestamps[i - 1]
                prev_dt = datetime.datetime.fromisoformat(prev_str.replace("Z", "+00:00"))
                curr_dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

                elapsed_hours = (curr_dt - prev_dt).total_seconds() / 3600.0
                if elapsed_hours == 1.0:
                    trend = (self._hourly_data[dt_str] - self._hourly_data[prev_str]) / 1.0  # mm/h²
                    self._hourly_trends[dt_str] = round(trend, 4)
                else:
                    self._hourly_trends[dt_str] = 0.0

        self._is_loaded = True

    def get_rainfall_features(self, timestamp_utc: str) -> Tuple[Optional[float], Optional[float], Dict[str, Any]]:
        """
        Returns (rainfall_intensity, rainfall_trend, metadata_dict) for target UTC timestamp string.
        """
        self.load()

        intensity = self._hourly_data.get(timestamp_utc)
        trend = self._hourly_trends.get(timestamp_utc)

        meta = {
            "source": self.dataset_provenance,
            "spatial_resolution": self.spatial_provenance,
            "temporal_window": f"{self.JULY_2023_START} to {self.JULY_2023_END}",
            "unit_intensity": "mm/h",
            "unit_trend": "mm/h²",
            "provenance_intensity": "DERIVED_FROM_REAL",
            "provenance_trend": "DERIVED_FROM_REAL",
            "is_within_valid_window": timestamp_utc in self._hourly_data,
        }

        return intensity, trend, meta
