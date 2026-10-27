"""
AapdaNetra-X Real Data Temporal Alignment Layer
Explicitly records temporal coverage, native timezones, source years, and observation
frequencies for all 6 real datasets without forcing datasets onto a fake common date.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional

REFERENCE_STUDY_WINDOW = "July 2023 Delhi Flood Event (2023-07-01T00:00:00Z to 2023-07-31T23:00:00Z)"


@dataclass
class DatasetTemporalSpec:
    dataset_name: str
    native_temporal_range: str
    timezone: str
    source_year: int
    observation_frequency: str
    temporal_context_label: str
    is_july2023_telemetry: bool
    temporal_mismatch_notes: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TemporalAlignmentMatrix:
    reference_study_window: str
    datasets: Dict[str, DatasetTemporalSpec]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reference_study_window": self.reference_study_window,
            "datasets": {k: v.to_dict() for k, v in self.datasets.items()},
        }


def get_era5_temporal_spec() -> DatasetTemporalSpec:
    """Returns ERA5 temporal coverage specification."""
    return DatasetTemporalSpec(
        dataset_name="ERA5-Land Total Precipitation",
        native_temporal_range="2023-07-01T00:00:00Z to 2023-07-31T23:00:00Z",
        timezone="UTC",
        source_year=2023,
        observation_frequency="Hourly (744 total valid hourly timestamps)",
        temporal_context_label="July 2023 continuous hourly reanalysis",
        is_july2023_telemetry=True,
        temporal_mismatch_notes="Complete hourly coverage for July 2023 flood window; boundary at 2023-07-01T00:00:00Z de-accumulated from June 30 run step 23.",
        details={
            "total_hourly_timestamps": 744,
            "start_timestamp": "2023-07-01T00:00:00Z",
            "end_timestamp": "2023-07-31T23:00:00Z",
            "boundary_backed_by_real_data": True,
        },
    )


def get_worldpop_temporal_spec() -> DatasetTemporalSpec:
    """Returns WorldPop temporal coverage specification."""
    return DatasetTemporalSpec(
        dataset_name="WorldPop 2020 Constrained Population",
        native_temporal_range="2020 Annual Static Snapshot",
        timezone="N/A (Static Annual Raster)",
        source_year=2020,
        observation_frequency="Static annual population count per pixel",
        temporal_context_label="WorldPop 2020 static baseline snapshot",
        is_july2023_telemetry=False,
        temporal_mismatch_notes="Static 2020 baseline population snapshot used as structural exposure layer; does not capture 2023 micro-shifts.",
        details={
            "static_year": 2020,
            "used_as_real_time_telemetry": False,
        },
    )


def get_ghsl_temporal_spec() -> DatasetTemporalSpec:
    """Returns GHSL temporal coverage specification."""
    return DatasetTemporalSpec(
        dataset_name="GHSL Built-Up Surface 2020 (R2023A)",
        native_temporal_range="2020 Epoch Snapshot (Release R2023A)",
        timezone="N/A (Static Epoch Raster)",
        source_year=2020,
        observation_frequency="Static epoch built-up surface area (m²)",
        temporal_context_label="GHSL 2020 epoch static built-up snapshot",
        is_july2023_telemetry=False,
        temporal_mismatch_notes="Static 2020 built-up surface snapshot; preserved as contextual feature built_up_surface_m2 and NOT mapped to infrastructure_vulnerability.",
        details={
            "static_year": 2020,
            "release_version": "R2023A",
            "mapped_to_infrastructure_vulnerability": False,
        },
    )


def get_traffic_temporal_spec() -> DatasetTemporalSpec:
    """Returns Delhi Traffic temporal coverage specification."""
    return DatasetTemporalSpec(
        dataset_name="Delhi Traffic Density Dataset (IIT Delhi 2020)",
        native_temporal_range="Sep-Dec 2020 (40 complete days)",
        timezone="IST (UTC+5:30)",
        source_year=2020,
        observation_frequency="12 frames/sec aggregated into 07:00-22:00 IST diurnal profile",
        temporal_context_label="Delhi 2020 empirical baseline",
        is_july2023_telemetry=False,
        temporal_mismatch_notes="Empirical baseline traffic profile from Sep-Dec 2020; MUST NOT be claimed as July 2023 real-time flood traffic.",
        details={
            "operating_hours_ist": "07:00 to 22:00 IST",
            "empirical_days_count": 40,
            "is_july2023_flood_traffic": False,
            "traffic_temporal_context": "Delhi 2020 empirical baseline",
        },
    )


def get_cwc_temporal_spec() -> DatasetTemporalSpec:
    """Returns CWC river gauge temporal coverage specification."""
    return DatasetTemporalSpec(
        dataset_name="CWC Yamuna River Gauge Station (#011-MDNDEL)",
        native_temporal_range="July 2023 official milestone event timestamps",
        timezone="UTC",
        source_year=2023,
        observation_frequency="Irregular official event observations (e.g. July 13 12:00 UTC peak HFL)",
        temporal_context_label="CWC July 2023 official event milestones ONLY",
        is_july2023_telemetry=True,
        temporal_mismatch_notes="Sparse official event observations ONLY; unobserved timestamps return None (unavailable) without fabrication, interpolation, or forward-filling.",
        details={
            "documented_peak_timestamp": "2023-07-13T12:00:00Z",
            "documented_peak_hfl_m_navd88": 208.66,
            "documented_peak_relative_stage_m": 4.66,
            "unobserved_timestamps_handling": "return None (unavailable)",
            "continuous_timeline_created": False,
        },
    )


def get_flood_gis_temporal_spec() -> DatasetTemporalSpec:
    """Returns 2023 Delhi Flood KML temporal coverage specification."""
    return DatasetTemporalSpec(
        dataset_name="Delhi July 2023 Inundation Flood Extent Vector Layers (CWC / NIDM)",
        native_temporal_range="July 2023 Flood Event Reference Snapshots",
        timezone="UTC",
        source_year=2023,
        observation_frequency="Satellite imagery inundation snapshots during peak flood event",
        temporal_context_label="July 2023 satellite event validation reference",
        is_july2023_telemetry=True,
        temporal_mismatch_notes="Event-based spatial inundation reference snapshots; classified as SPATIAL_EVENT_VALIDATION (not hourly telemetry).",
        details={
            "event_month": "July 2023",
            "classification": "SPATIAL_EVENT_VALIDATION",
        },
    )


def build_temporal_alignment_matrix() -> TemporalAlignmentMatrix:
    """Builds and returns complete temporal alignment matrix across all 6 real datasets."""
    specs = {
        "era5": get_era5_temporal_spec(),
        "worldpop": get_worldpop_temporal_spec(),
        "ghsl": get_ghsl_temporal_spec(),
        "traffic": get_traffic_temporal_spec(),
        "cwc": get_cwc_temporal_spec(),
        "flood_gis": get_flood_gis_temporal_spec(),
    }
    return TemporalAlignmentMatrix(
        reference_study_window=REFERENCE_STUDY_WINDOW,
        datasets=specs,
    )
