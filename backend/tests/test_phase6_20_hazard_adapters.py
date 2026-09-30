"""
AapdaNetra-X — Phase 6.20.2 Hazard Adapter Layer Test Suite
"""
import pytest

from app.hazards import (
    HazardType,
    HazardCapabilityStatus,
    HazardDefinition,
    HazardEvaluationResult,
    HazardSpatialResult,
    HazardRoutePenaltyResult,
    BaseHazardAdapter,
    FloodHazardAdapter,
    ExtremeRainfallHazardAdapter,
    UnsupportedHazardAdapter,
    HazardRegistry,
    get_hazard_registry,
)
from ml.features.schema import FEATURE_SPECS, FEATURE_NAMES
from app.data.providers.data_adapter import BASE_SENSOR_FEATURES


# 1. FloodHazardAdapter returns HazardType.FLOOD
def test_01_flood_adapter_hazard_type():
    adapter = FloodHazardAdapter()
    assert adapter.get_hazard_type() == HazardType.FLOOD


# 2. ExtremeRainfallHazardAdapter returns HazardType.EXTREME_RAINFALL
def test_02_extreme_rainfall_adapter_hazard_type():
    adapter = ExtremeRainfallHazardAdapter()
    assert adapter.get_hazard_type() == HazardType.EXTREME_RAINFALL


# 3. Unsupported hazard adapters never claim model availability
def test_03_unsupported_adapters_no_model_claims():
    for h_type in [HazardType.LANDSLIDE, HazardType.CYCLONE, HazardType.HEATWAVE, HazardType.EARTHQUAKE]:
        adapter = UnsupportedHazardAdapter(h_type)
        res = adapter.evaluate_risk()
        assert res.hazard_type == h_type
        assert res.supported is False
        assert res.model_available is False
        assert res.predicted_risk is None


# 4. Registry resolves FloodHazardAdapter for FLOOD
def test_04_registry_resolves_flood_adapter():
    registry = get_hazard_registry()
    adapter = registry.get_adapter(HazardType.FLOOD)
    assert isinstance(adapter, FloodHazardAdapter)
    assert adapter.get_hazard_type() == HazardType.FLOOD


# 5. Registry resolves ExtremeRainfallHazardAdapter for EXTREME_RAINFALL
def test_05_registry_resolves_extreme_rainfall_adapter():
    registry = get_hazard_registry()
    adapter = registry.get_adapter("extreme_rainfall")
    assert isinstance(adapter, ExtremeRainfallHazardAdapter)
    assert adapter.get_hazard_type() == HazardType.EXTREME_RAINFALL


# 6. Registry does not resolve unsupported hazards to FloodHazardAdapter
def test_06_unsupported_hazards_do_not_resolve_to_flood():
    registry = get_hazard_registry()
    for h_type in ["landslide", "cyclone", "heatwave", "earthquake"]:
        adapter = registry.get_adapter(h_type)
        assert not isinstance(adapter, FloodHazardAdapter)
        assert isinstance(adapter, UnsupportedHazardAdapter)


# 7. Unknown hazard lookup fails cleanly
def test_07_unknown_hazard_adapter_raises_error():
    registry = get_hazard_registry()
    with pytest.raises(ValueError, match="Unknown or unsupported hazard type"):
        registry.get_adapter("tsunami")

    with pytest.raises(ValueError, match="Unknown or unsupported hazard type"):
        registry.get_adapter("volcano")


# 8. Unsupported evaluate_risk operation is controlled and does not fabricate a score
def test_08_unsupported_evaluate_risk_controlled():
    adapter = UnsupportedHazardAdapter(HazardType.LANDSLIDE)
    res = adapter.evaluate_risk({"water_level": 10.0})
    assert isinstance(res, HazardEvaluationResult)
    assert res.predicted_risk is None
    assert res.model_available is False
    assert "unavailable" in res.message.lower() or "not operational" in res.disclaimer.lower()


# 9. Unsupported spatial operation does not fabricate a spatial score
def test_09_unsupported_spatial_operation_controlled():
    adapter = UnsupportedHazardAdapter(HazardType.CYCLONE)
    res = adapter.evaluate_spatial_hazard(lat=28.6, lon=77.2)
    assert isinstance(res, HazardSpatialResult)
    assert res.spatial_available is False
    assert res.spatial_hazard_score is None


# 10. Unsupported route penalty does not fabricate a penalty
def test_10_unsupported_route_penalty_controlled():
    adapter = UnsupportedHazardAdapter(HazardType.HEATWAVE)
    res = adapter.get_route_penalty(route_segment=None)
    assert isinstance(res, HazardRoutePenaltyResult)
    assert res.routing_available is False
    assert res.penalty_score is None


# 11. Flood adapter delegates to existing flood components rather than duplicate GBR
def test_11_flood_adapter_delegates_to_existing_gbr():
    from ml.inference import predict_risk

    adapter = FloodHazardAdapter()
    sample_features = dict(BASE_SENSOR_FEATURES)
    res = adapter.evaluate_risk(sample_features)

    direct_score = predict_risk(sample_features)["risk_score"]
    assert res.predicted_risk == direct_score
    assert res.model_available is True
    assert res.details["is_flood_specific"] is True


# 12. Existing flood feature schema remains unchanged
def test_12_flood_feature_schema_unchanged():
    assert len(FEATURE_NAMES) == 7
    assert list(BASE_SENSOR_FEATURES.keys()) == FEATURE_NAMES


# 13. Existing registry tests compatibility
def test_13_registry_definitions_intact():
    registry = get_hazard_registry()
    all_defs = registry.get_all()
    assert len(all_defs) == 6
    assert registry.is_supported(HazardType.FLOOD) is True
    assert registry.is_supported(HazardType.LANDSLIDE) is False


# 14. Adapter type contracts are deterministic
def test_14_adapter_contracts_deterministic():
    registry = get_hazard_registry()
    for h_name, h_enum in [("flood", HazardType.FLOOD), ("landslide", HazardType.LANDSLIDE)]:
        adapter = registry.get_adapter(h_name)
        assert isinstance(adapter, BaseHazardAdapter)
        assert adapter.get_hazard_type() == h_enum


# 15. No fake hazard data/model/provider was introduced
def test_15_no_fake_hazard_claims():
    registry = get_hazard_registry()
    for h_type in [HazardType.LANDSLIDE, HazardType.CYCLONE, HazardType.HEATWAVE, HazardType.EARTHQUAKE]:
        adapter = registry.get_adapter(h_type)
        risk_res = adapter.evaluate_risk()
        spatial_res = adapter.evaluate_spatial_hazard()
        route_res = adapter.get_route_penalty()

        assert risk_res.predicted_risk is None
        assert spatial_res.spatial_hazard_score is None
        assert route_res.penalty_score is None
