"""
AapdaNetra-X — Phase 6.20.3 Multi-Hazard Risk Aggregation Test Suite
"""
import pytest

from app.hazards import (
    HazardType,
    HazardCapabilityStatus,
    HazardDefinition,
    HazardEvaluationResult,
    HazardSpatialResult,
    HazardContributionSummary,
    ExcludedHazardSummary,
    MultiHazardRiskAggregate,
    BaseHazardAdapter,
    FloodHazardAdapter,
    ExtremeRainfallHazardAdapter,
    UnsupportedHazardAdapter,
    HazardRegistry,
    get_hazard_registry,
    MultiHazardRiskAggregator,
)
from app.data.providers.data_adapter import BASE_SENSOR_FEATURES
from ml.inference import predict_risk


# 1. Flood-only aggregation works
def test_01_flood_only_aggregation_works():
    aggregator = MultiHazardRiskAggregator()
    result = aggregator.aggregate(BASE_SENSOR_FEATURES)
    assert isinstance(result, MultiHazardRiskAggregate)
    assert result.composite_risk is not None
    assert result.primary_hazard_driver == HazardType.FLOOD


# 2. Flood risk is preserved exactly
def test_02_flood_risk_preserved_exactly():
    aggregator = MultiHazardRiskAggregator()
    direct_flood_risk = predict_risk(BASE_SENSOR_FEATURES)["risk_score"]
    result = aggregator.aggregate(BASE_SENSOR_FEATURES)

    flood_contrib = next(
        c for c in result.contributing_hazards if c.hazard_type == HazardType.FLOOD
    )
    assert flood_contrib.risk == direct_flood_risk
    assert result.composite_risk == direct_flood_risk


# 3. Composite risk equals flood risk when flood is the only operational numerical hazard
def test_03_composite_risk_equals_flood_risk():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    direct_risk = predict_risk(BASE_SENSOR_FEATURES)["risk_score"]
    assert res.composite_risk == direct_risk
    assert len(res.contributing_hazards) == 1
    assert res.contributing_hazards[0].hazard_type == HazardType.FLOOD


# 4. Flood is listed as a contributing hazard
def test_04_flood_listed_as_contributing_hazard():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    contrib_types = [c.hazard_type for c in res.contributing_hazards]
    assert HazardType.FLOOD in contrib_types
    assert len(contrib_types) == 1


# 5. Extreme rainfall is explicitly excluded
def test_05_extreme_rainfall_explicitly_excluded():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    excluded_types = [e.hazard_type for e in res.excluded_hazards]
    assert HazardType.EXTREME_RAINFALL in excluded_types


# 6. Extreme rainfall has risk=None
def test_06_extreme_rainfall_has_risk_none():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    rain_excluded = next(
        e for e in res.excluded_hazards if e.hazard_type == HazardType.EXTREME_RAINFALL
    )
    assert rain_excluded.risk is None
    assert rain_excluded.risk != 0.0


# 7. Extreme rainfall has spatial_available=False
def test_07_extreme_rainfall_spatial_available_false():
    registry = get_hazard_registry()
    defn = registry.get_definition(HazardType.EXTREME_RAINFALL)
    adapter = registry.get_adapter(HazardType.EXTREME_RAINFALL)
    spatial_res = adapter.evaluate_spatial_hazard()

    assert defn.spatial_available is False
    assert spatial_res.spatial_available is False
    assert spatial_res.spatial_hazard_score is None
    assert "hydro-meteorological weather telemetry" in spatial_res.provenance.lower()
    assert "no independent" in spatial_res.message.lower() or "model exists" in spatial_res.message.lower()


# 8. Landslide is excluded
def test_08_landslide_is_excluded():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    ex_types = [e.hazard_type for e in res.excluded_hazards]
    assert HazardType.LANDSLIDE in ex_types


# 9. Cyclone is excluded
def test_09_cyclone_is_excluded():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    ex_types = [e.hazard_type for e in res.excluded_hazards]
    assert HazardType.CYCLONE in ex_types


# 10. Heatwave is excluded
def test_10_heatwave_is_excluded():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    ex_types = [e.hazard_type for e in res.excluded_hazards]
    assert HazardType.HEATWAVE in ex_types


# 11. Earthquake is excluded
def test_11_earthquake_is_excluded():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    ex_types = [e.hazard_type for e in res.excluded_hazards]
    assert HazardType.EARTHQUAKE in ex_types


# 12. Unsupported hazards are never converted to zero
def test_12_unsupported_hazards_never_converted_to_zero():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    for ex in res.excluded_hazards:
        assert ex.risk is None
        assert ex.risk != 0.0
        assert ex.risk != 0


# 13. Missing hazard risk remains None
def test_13_missing_hazard_risk_remains_none():
    aggregator = MultiHazardRiskAggregator()
    # Mock evaluation where flood has no numerical risk
    flood_no_risk = HazardEvaluationResult(
        hazard_type=HazardType.FLOOD,
        supported=True,
        model_available=True,
        predicted_risk=None,
        provenance="Test",
        disclaimer="Test",
        message="No risk available",
    )
    res = aggregator.aggregate(hazard_evaluations={HazardType.FLOOD: flood_no_risk})
    assert res.composite_risk is None
    assert res.primary_hazard_driver is None
    for ex in res.excluded_hazards:
        assert ex.risk is None


# 14. Excluded hazards include capability status
def test_14_excluded_hazards_include_capability_status():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    status_map = {e.hazard_type: e.capability_status for e in res.excluded_hazards}
    assert status_map[HazardType.EXTREME_RAINFALL] == HazardCapabilityStatus.PARTIALLY_SUPPORTED
    assert status_map[HazardType.LANDSLIDE] == HazardCapabilityStatus.DEMONSTRATION_ONLY
    assert status_map[HazardType.CYCLONE] == HazardCapabilityStatus.FUTURE_EXTENSION
    assert status_map[HazardType.HEATWAVE] == HazardCapabilityStatus.FUTURE_EXTENSION
    assert status_map[HazardType.EARTHQUAKE] == HazardCapabilityStatus.FUTURE_EXTENSION


# 15. Excluded hazards include explicit reasons
def test_15_excluded_hazards_include_explicit_reasons():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    for ex in res.excluded_hazards:
        assert isinstance(ex.reason, str)
        assert len(ex.reason) > 10


# 16. Aggregation policy is reported
def test_16_aggregation_policy_reported():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    assert res.aggregation_policy == "MAX_SEVERITY_OPERATIONAL_HAZARD"
    assert "supported hazard risk models only" in res.disclaimer.lower()


# 17. Primary hazard driver is flood
def test_17_primary_hazard_driver_is_flood():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    assert res.primary_hazard_driver == HazardType.FLOOD


# 18. Flood uncertainty metadata is preserved
def test_18_flood_uncertainty_metadata_preserved():
    aggregator = MultiHazardRiskAggregator()
    # Create evaluation result with explicit flood uncertainty
    flood_eval = FloodHazardAdapter().evaluate_risk(BASE_SENSOR_FEATURES)
    flood_eval.details["uncertainty"] = {
        "interval_lower": 22.0,
        "interval_upper": 32.0,
        "reliability_score": 0.95,
    }
    res = aggregator.aggregate(hazard_evaluations={HazardType.FLOOD: flood_eval})
    assert res.primary_hazard_uncertainty is not None
    assert res.primary_hazard_uncertainty["interval_lower"] == 22.0
    assert res.primary_hazard_uncertainty["interval_upper"] == 32.0


# 19. No composite conformal interval is fabricated
def test_19_no_composite_conformal_interval_fabricated():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    # The aggregate provenance identifies domain aggregation, not a multi-hazard conformal math model
    assert res.provenance == "Multi-hazard decision-support aggregation service"
    assert "composite" not in str(res.primary_hazard_uncertainty or "").lower() or res.primary_hazard_uncertainty is None


# 20. Flood SHAP remains flood-specific
def test_20_flood_shap_remains_flood_specific():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    assert res.explanation_hazard == HazardType.FLOOD


# 21. No SHAP is generated for unsupported hazards
def test_21_no_shap_for_unsupported_hazards():
    aggregator = MultiHazardRiskAggregator()
    res = aggregator.aggregate(BASE_SENSOR_FEATURES)
    for ex in res.excluded_hazards:
        assert not hasattr(ex, "shap_values")
        assert not hasattr(ex, "feature_importances")


# 22. Flood spatial evidence remains flood-specific
def test_22_flood_spatial_evidence_flood_specific():
    flood_adapter = FloodHazardAdapter()
    spatial_res = flood_adapter.evaluate_spatial_hazard(lat=28.6, lon=77.2)
    assert spatial_res.hazard_type == HazardType.FLOOD
    assert spatial_res.spatial_available is True


# 23. No Extreme Rainfall spatial score is generated
def test_23_no_extreme_rainfall_spatial_score():
    rain_adapter = ExtremeRainfallHazardAdapter()
    spatial_res = rain_adapter.evaluate_spatial_hazard(lat=28.6, lon=77.2)
    assert spatial_res.hazard_type == HazardType.EXTREME_RAINFALL
    assert spatial_res.spatial_available is False
    assert spatial_res.spatial_hazard_score is None


# 24. Unknown hazard fails cleanly
def test_24_unknown_hazard_fails_cleanly():
    aggregator = MultiHazardRiskAggregator()
    with pytest.raises(ValueError):
        aggregator.aggregate(hazard_evaluations={"tsunami": FloodHazardAdapter().evaluate_risk()})

    registry = get_hazard_registry()
    with pytest.raises(ValueError, match="Unknown or unsupported hazard type"):
        registry.get_adapter("volcano")


# 25. Aggregation is deterministic
def test_25_aggregation_is_deterministic():
    aggregator = MultiHazardRiskAggregator()
    res1 = aggregator.aggregate(BASE_SENSOR_FEATURES)
    res2 = aggregator.aggregate(BASE_SENSOR_FEATURES)
    assert res1.composite_risk == res2.composite_risk
    assert [c.hazard_type for c in res1.contributing_hazards] == [c.hazard_type for c in res2.contributing_hazards]
    assert [e.hazard_type for e in res1.excluded_hazards] == [e.hazard_type for e in res2.excluded_hazards]


# 26. Existing registry tests remain passing
def test_26_existing_registry_tests_pass():
    registry = get_hazard_registry()
    assert len(registry.get_all()) == 6
    assert registry.is_supported(HazardType.FLOOD) is True
    assert registry.is_supported(HazardType.EXTREME_RAINFALL) is True
    assert registry.is_supported(HazardType.LANDSLIDE) is False


# 27. Existing adapter tests remain passing
def test_27_existing_adapter_tests_pass():
    flood_adapter = FloodHazardAdapter()
    rain_adapter = ExtremeRainfallHazardAdapter()
    landslide_adapter = UnsupportedHazardAdapter(HazardType.LANDSLIDE)

    assert flood_adapter.get_hazard_type() == HazardType.FLOOD
    assert rain_adapter.get_hazard_type() == HazardType.EXTREME_RAINFALL
    assert landslide_adapter.get_hazard_type() == HazardType.LANDSLIDE
