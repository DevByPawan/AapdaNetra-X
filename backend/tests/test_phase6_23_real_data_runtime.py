"""

Phase 6.23: Real-Data Runtime Integration Verification Test Suite

Tests real-data integration into the runtime engine, ensuring backward-compatibility of simulated mode,

preservation of feature ordering, explicit provenance handling, clipping tracking, and error resilience.

"""



import pytest

from app.data.providers.data_adapter import DataAdapter, get_data_adapter, reset_data_adapter, BASE_SENSOR_FEATURES

from app.services.risk_engine import compute_risk_state, _get_base_features

from app.config import settings





@pytest.fixture(autouse=True)

def cleanup_adapter():

    reset_data_adapter()

    yield

    reset_data_adapter()





def test_simulated_mode_backward_compatibility():

    """Verify that default simulated mode returns canonical baseline features unchanged."""

    adapter = DataAdapter(data_mode="simulated")

    features = adapter.get_base_features()



    assert features == BASE_SENSOR_FEATURES

    assert adapter.data_mode == "simulated"

    assert adapter.fallback_used is False

    assert adapter.provenance == {k: "simulated" for k in BASE_SENSOR_FEATURES}





def test_real_data_runtime_assembly_and_provenance():

    """Verify real data mode extracts ERA5 rainfall, CWC water level, traffic 2020, and sets proper provenance tags."""

    adapter = DataAdapter(data_mode="real")

    adapter.set_real_data_timestamp("2023-07-13T12:00:00Z")



    features = adapter.get_base_features()

    prov = adapter.provenance



    # 7-feature schema contract

    assert list(features.keys()) == list(BASE_SENSOR_FEATURES.keys())



    # Specific provenance guarantees

    assert prov["rainfall_intensity"] == "DERIVED_FROM_REAL"

    assert prov["rainfall_trend"] == "DERIVED_FROM_REAL"

    assert prov["water_level"] == "OFFICIAL_EVENT_ONLY"

    assert prov["road_congestion"] == "DERIVED_FROM_REAL / 2020 BASELINE"

    assert prov["population_exposure"] == "SEMANTICALLY_INCOMPATIBLE_FOR_CURRENT_GBR"

    assert prov["infrastructure_vulnerability"] == "PROVISIONAL"





def test_raw_rainfall_trend_negative_clipping_tracking():

    """Verify raw negative rainfall trend exceeding lower model bound (-50.0) is clipped while preserving raw value and clipping flag."""

    adapter = DataAdapter(data_mode="real")

    adapter.set_real_data_timestamp("2023-07-09T08:00:00Z")



    features = adapter.get_base_features()

    telemetry_meta = adapter.get_telemetry_metadata()



    # Check that model input feature is clipped to schema bounds (-50.0)

    assert features["rainfall_trend"] == -50.0



    # Raw features should reflect unclipped ERA5 derivative (-133.462)

    assert telemetry_meta["raw_features"]["rainfall_trend"] <= -50.0

    assert telemetry_meta["clipping_flags"]["rainfall_trend"] is True





def test_raw_rainfall_trend_positive_clipping_tracking():

    """Verify raw positive rainfall trend exceeding upper model bound (+50.0) is clipped while preserving raw value and clipping flag."""

    adapter = DataAdapter(data_mode="real")

    adapter.set_real_data_timestamp("2023-07-09T07:00:00Z")



    features = adapter.get_base_features()

    telemetry_meta = adapter.get_telemetry_metadata()



    # Check that model input feature is clipped to schema upper bound (+50.0)

    assert features["rainfall_trend"] == 50.0



    # Raw features should reflect unclipped positive ERA5 derivative (+260.33)

    assert telemetry_meta["raw_features"]["rainfall_trend"] >= 50.0

    assert telemetry_meta["clipping_flags"]["rainfall_trend"] is True





def test_missing_cwc_milestones_remain_unavailable():

    """Verify timestamps without official CWC milestone observations mark water_level as UNAVAILABLE."""

    adapter = DataAdapter(data_mode="real")

    # Outside official July 2023 milestone list

    adapter.set_real_data_timestamp("2023-07-01T00:00:00Z")



    features = adapter.get_base_features()

    prov = adapter.provenance



    assert prov["water_level"] == "UNAVAILABLE"

    assert prov["water_level_trend"] == "UNAVAILABLE"

    assert adapter.fallback_used is True





def test_population_exposure_semantic_incompatibility():

    """Verify population exposure is tagged as semantically incompatible for current sector-level GBR."""

    adapter = DataAdapter(data_mode="real")

    adapter.get_base_features()

    prov = adapter.provenance



    assert prov["population_exposure"] == "SEMANTICALLY_INCOMPATIBLE_FOR_CURRENT_GBR"





def test_provisional_infrastructure_vulnerability_never_mislabeled():

    """Verify provisional infrastructure vulnerability (0.72) is strictly tagged as PROVISIONAL."""

    adapter = DataAdapter(data_mode="real")

    features = adapter.get_base_features()

    prov = adapter.provenance



    assert features["infrastructure_vulnerability"] == 0.72

    assert prov["infrastructure_vulnerability"] == "PROVISIONAL"





def test_provider_failures_do_not_silently_relabel_fallback_as_real():

    """Verify assembler error triggers fallback with explicit fallback provenance tags."""

    adapter = DataAdapter(data_mode="real")

    # Set assembler to a mock object that raises an exception on assemble_record

    class BrokenAssembler:

        def assemble_record(self, **kwargs):

            raise RuntimeError("Provider connection error")



    adapter._assembler = BrokenAssembler()



    features = adapter.get_base_features()

    prov = adapter.provenance



    assert features == BASE_SENSOR_FEATURES

    assert adapter.fallback_used is True

    assert all("fallback" in v for v in prov.values())





def test_risk_engine_integration_with_real_data():

    """Verify risk engine compute_risk_state produces valid RiskResponse in real data mode with appropriate notes."""

    try:

        settings.data_mode = "real"

        adapter = get_data_adapter()

        adapter.set_real_data_timestamp("2023-07-13T12:00:00Z")



        res = compute_risk_state(horizon=1)



        assert res.index == 1

        assert 0.0 <= res.predictedRisk <= 100.0

        assert "REAL" in res.predictionNote

        assert "real_derived_provisional" in res.predictionInterval.dataStatus

        assert "synthetic-trained" in res.predictionInterval.disclaimer.lower()

    finally:

        settings.data_mode = "simulated"

        reset_data_adapter()
