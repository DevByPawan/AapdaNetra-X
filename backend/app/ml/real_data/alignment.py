"""
AapdaNetra-X Unified Real Data Alignment & Validation Entry Point
Combines spatial alignment matrix, temporal alignment matrix, feature provenance schema,
and quality validation reports into a single isolated metadata interface.
"""
from typing import Dict, Any
from app.ml.real_data.spatial_alignment import build_spatial_alignment_matrix, DELHI_STUDY_BBOX
from app.ml.real_data.temporal_alignment import build_temporal_alignment_matrix
from app.ml.real_data.quality import run_all_quality_checks
from app.ml.real_data.provenance import FEATURE_ORDER, ProvenanceStatus


def get_feature_provenance_matrix() -> Dict[str, Any]:
    """Returns official 7-feature schema provenance classification matrix."""
    return {
        "features": {
            "rainfall_intensity": {
                "provenance_status": ProvenanceStatus.DERIVED_FROM_REAL.value,
                "dataset": "ERA5-Land GRIB1 Param 228 (tp)",
                "temporal_context": "July 2023 hourly de-accumulated rainfall (mm/h)",
            },
            "rainfall_trend": {
                "provenance_status": ProvenanceStatus.DERIVED_FROM_REAL.value,
                "dataset": "ERA5-Land GRIB1 Param 228 (tp)",
                "temporal_context": "July 2023 hourly rainfall trend rate (mm/h²)",
            },
            "water_level": {
                "provenance_status": ProvenanceStatus.OFFICIAL_EVENT_ONLY.value,
                "dataset": "CWC Yamuna River Gauge Station (#011-MDNDEL)",
                "temporal_context": "July 2023 official milestone event observations ONLY; unobserved timestamps remain None (unavailable)",
            },
            "water_level_trend": {
                "provenance_status": ProvenanceStatus.OFFICIAL_EVENT_ONLY.value,
                "dataset": "CWC Yamuna River Gauge Station (#011-MDNDEL)",
                "temporal_context": "July 2023 official milestone event rate ONLY; unobserved timestamps remain None (unavailable)",
            },
            "road_congestion": {
                "provenance_status": ProvenanceStatus.DERIVED_FROM_REAL.value,
                "dataset": "Delhi Traffic Density Dataset (IIT Delhi 2020)",
                "temporal_context": "Delhi 2020 empirical baseline (07:00-22:00 IST diurnal profile)",
            },
            "population_exposure": {
                "provenance_status": ProvenanceStatus.DERIVED_FROM_REAL.value,
                "dataset": "WorldPop 2020 Constrained Population Raster",
                "temporal_context": "2020 static baseline population count per ~100m pixel",
            },
            "infrastructure_vulnerability": {
                "provenance_status": ProvenanceStatus.PROVISIONAL.value,
                "dataset": "Provisional Fallback Fill (Default 0.72)",
                "temporal_context": "Provisional structural fallback; not backed by real spatial dataset",
            },
        },
        "extra_contextual_features": {
            "built_up_surface_m2": {
                "provenance_status": ProvenanceStatus.DERIVED_FROM_REAL.value,
                "dataset": "GHSL Built-Up Surface 2020 (R2023A)",
                "temporal_context": "2020 epoch static built-up surface area (m² per cell)",
                "mapped_to_infrastructure_vulnerability": False,
            }
        },
    }


def build_real_data_alignment_summary() -> Dict[str, Any]:
    """
    Compiles full, isolated machine-readable alignment summary:
    - Study area bounding box
    - Spatial alignment matrix
    - Temporal alignment matrix
    - Feature provenance matrix
    - Complete quality validation results
    """
    spatial_matrix = build_spatial_alignment_matrix()
    temporal_matrix = build_temporal_alignment_matrix()
    provenance_matrix = get_feature_provenance_matrix()
    quality_report = run_all_quality_checks()

    return {
        "study_area_bbox": DELHI_STUDY_BBOX,
        "spatial_alignment_matrix": spatial_matrix.to_dict(),
        "temporal_alignment_matrix": temporal_matrix.to_dict(),
        "feature_provenance_matrix": provenance_matrix,
        "quality_validation_report": quality_report.to_dict(),
    }
