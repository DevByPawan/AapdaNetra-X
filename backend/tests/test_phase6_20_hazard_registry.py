"""
AapdaNetra-X — Phase 6.20.1 Hazard Registry & Enums Test Suite
"""
import pytest

from app.hazards import (
    HazardType,
    HazardCapabilityStatus,
    HazardDefinition,
    HazardRegistry,
    get_hazard_registry,
)
from ml.features.schema import FEATURE_SPECS, FEATURE_NAMES
from app.data.providers.data_adapter import BASE_SENSOR_FEATURES


# 1. All six hazard types exist
def test_01_hazard_types_exist():
    expected_hazards = {
        "flood",
        "extreme_rainfall",
        "landslide",
        "cyclone",
        "heatwave",
        "earthquake",
    }
    actual_hazards = {h.value for h in HazardType}
    assert actual_hazards == expected_hazards


# 2. All capability statuses exist
def test_02_capability_statuses_exist():
    expected_statuses = {
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "DEMONSTRATION_ONLY",
        "FUTURE_EXTENSION",
    }
    actual_statuses = {s.value for s in HazardCapabilityStatus}
    assert actual_statuses == expected_statuses


# 3. Flood definition is SUPPORTED with model available
def test_03_flood_definition_supported():
    registry = get_hazard_registry()
    flood_defn = registry.get_definition(HazardType.FLOOD)

    assert flood_defn.hazard_type == HazardType.FLOOD
    assert flood_defn.capability_status == HazardCapabilityStatus.SUPPORTED
    assert flood_defn.supported is True
    assert flood_defn.model_available is True
    assert flood_defn.spatial_available is True
    assert flood_defn.telemetry_available is True
    assert flood_defn.alerts_available is True
    assert flood_defn.routing_available is True
    assert flood_defn.decision_support_available is True
    assert len(flood_defn.supported_features) == 7


# 4. Extreme rainfall is PARTIALLY_SUPPORTED
def test_04_extreme_rainfall_partially_supported():
    registry = get_hazard_registry()
    rain_defn = registry.get_definition(HazardType.EXTREME_RAINFALL)

    assert rain_defn.hazard_type == HazardType.EXTREME_RAINFALL
    assert rain_defn.capability_status == HazardCapabilityStatus.PARTIALLY_SUPPORTED
    assert rain_defn.supported is True
    assert rain_defn.model_available is False  # Uses shared flood pipeline, not an independent model
    assert rain_defn.telemetry_available is True


# 5. Unsupported hazards are not operational
def test_05_unsupported_hazards_not_operational():
    registry = get_hazard_registry()

    for h_type in [HazardType.LANDSLIDE, HazardType.CYCLONE, HazardType.HEATWAVE, HazardType.EARTHQUAKE]:
        defn = registry.get_definition(h_type)
        assert defn.supported is False
        assert defn.model_available is False
        assert defn.routing_available is False
        assert defn.decision_support_available is False


# 6. Flood model is explicitly marked flood-specific
def test_06_flood_model_provenance_and_metadata():
    registry = get_hazard_registry()
    flood_defn = registry.get_definition("flood")

    assert "gbr" in flood_defn.provenance.lower() or "scikit-learn" in flood_defn.provenance.lower()
    assert flood_defn.metadata.get("is_flood_specific") is True
    assert flood_defn.metadata.get("canonical_features") == 7


# 7. Registry lookup operates consistently by Enum or String
def test_07_registry_lookup_case_insensitive():
    registry = get_hazard_registry()

    d1 = registry.get_definition(HazardType.LANDSLIDE)
    d2 = registry.get_definition("landslide")
    d3 = registry.get_definition("LANDSLIDE")

    assert d1 == d2 == d3
    assert d1.hazard_type == HazardType.LANDSLIDE


# 8. get_all() is deterministic and contains 6 definitions
def test_08_get_all_deterministic():
    registry = get_hazard_registry()
    all_hazards = registry.get_all()

    assert len(all_hazards) == 6
    assert set(all_hazards.keys()) == {
        "flood",
        "extreme_rainfall",
        "landslide",
        "cyclone",
        "heatwave",
        "earthquake",
    }


# 9. Capability matrix contains all 6 hazards with correct structure
def test_09_capability_matrix():
    registry = get_hazard_registry()
    matrix = registry.capability_matrix()

    assert len(matrix) == 6
    for item in matrix:
        assert "hazard_type" in item
        assert "display_name" in item
        assert "capability_status" in item
        assert "supported" in item
        assert "model_available" in item


# 10. Unknown hazard lookup fails cleanly with ValueError
def test_10_unknown_hazard_raises_error():
    registry = get_hazard_registry()

    with pytest.raises(ValueError, match="Unknown or unsupported hazard type"):
        registry.get_definition("tsunami")

    with pytest.raises(ValueError, match="Unknown or unsupported hazard type"):
        registry.get_definition("volcano")


# 11. Existing flood feature schema and BASE_SENSOR_FEATURES are untouched
def test_11_flood_feature_schema_untouched():
    assert len(FEATURE_NAMES) == 7
    assert "rainfall_intensity" in FEATURE_SPECS
    assert "water_level" in FEATURE_SPECS
    assert len(BASE_SENSOR_FEATURES) == 7
    assert BASE_SENSOR_FEATURES["water_level"] == 6.8


# 12. No unsupported hazard claims model availability
def test_12_no_false_model_claims():
    registry = get_hazard_registry()
    for h_type, defn in registry.get_all().items():
        if h_type != "flood":
            assert defn.model_available is False
