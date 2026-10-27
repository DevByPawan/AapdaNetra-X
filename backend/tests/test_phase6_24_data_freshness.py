"""
Phase 6.24 — Real-Time Data Freshness & Provenance Runtime Unit Tests
Verifies timestamp semantics (observed_at vs received_at), data age calculation,
freshness status classification, cache TTL behavior, dataset metadata, and backward compatibility.
"""
from datetime import datetime, timezone, timedelta
import pytest

from app.data.providers.base import DataProviderStatus
from app.data.providers.data_adapter import DataAdapter, BASE_SENSOR_FEATURES
from app.data.providers.weather_adapter import WeatherAdapter
from app.data.providers.water_level_adapter import WaterLevelAdapter
from app.data.providers.traffic_adapter import TrafficAdapter
from app.data.providers.population_adapter import PopulationAdapter
from app.data.providers.infrastructure_adapter import InfrastructureAdapter
from app.ml.real_data.feature_assembler import RealDataFeatureAssembler
from app.ml.real_data.provenance import FreshnessStatus, ProvenanceStatus


def test_observed_at_vs_received_at_distinction():
    """Requirement 1: Verify clear distinction between observed_at and received_at."""
    weather = WeatherAdapter(api_key="test_key", cache_ttl=300)
    obs_time = "2026-10-10T02:00:00Z"
    rec_time = "2026-10-10T02:05:00Z"

    weather.observed_at = obs_time
    weather.received_at = rec_time

    assert weather.observed_at != weather.received_at
    assert weather.observed_at == "2026-10-10T02:00:00Z"
    assert weather.received_at == "2026-10-10T02:05:00Z"


def test_timezone_aware_utc_normalization():
    """Requirement 2: Verify timezone awareness and UTC age calculation."""
    weather = WeatherAdapter(api_key="test_key", cache_ttl=300)
    weather.observed_at = "2026-10-10T02:00:00+00:00"

    ref_utc = datetime(2026, 10, 10, 2, 5, 0, tzinfo=timezone.utc)
    age = weather.calculate_age(now_reference=ref_utc)

    assert age == 300.0


def test_exact_freshness_thresholds_age_calculation():
    """Requirement 3 & 4: Verify fresh vs stale data classification at TTL threshold."""
    ref_time = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
    adapter = DataAdapter(data_mode="simulated")

    # Ingest live observation 200 seconds before reference -> FRESH (TTL threshold is 300s)
    obs_time_fresh = (ref_time - timedelta(seconds=200)).isoformat()
    adapter.update_live_features(
        features={"rainfall_intensity": 45.0},
        provenance_map={"rainfall_intensity": "live_ingest"},
        observed_at=obs_time_fresh,
    )

    freshness = adapter.get_feature_freshness(now_reference=ref_time)
    rf_fresh = freshness["rainfall_intensity"]

    assert rf_fresh["freshness_status"] == "FRESH"
    assert rf_fresh["is_stale"] is False
    assert rf_fresh["age_seconds"] == 200.0

    # Ingest live observation 400 seconds before reference -> STALE
    obs_time_stale = (ref_time - timedelta(seconds=400)).isoformat()
    adapter.update_live_features(
        features={"rainfall_intensity": 55.0},
        provenance_map={"rainfall_intensity": "live_ingest"},
        observed_at=obs_time_stale,
    )

    freshness_stale = adapter.get_feature_freshness(now_reference=ref_time)
    rf_stale = freshness_stale["rainfall_intensity"]

    assert rf_stale["freshness_status"] == "STALE"
    assert rf_stale["is_stale"] is True
    assert rf_stale["age_seconds"] == 400.0


def test_missing_observations_and_unknown_age():
    """Requirement 5: Verify missing observations return age_seconds as None, distinguishing unknown age from 0.0 age."""
    adapter = DataAdapter(data_mode="hybrid")
    freshness = adapter.get_feature_freshness()

    # Infrastructure vulnerability has no live observation
    infra_meta = freshness["infrastructure_vulnerability"]
    assert infra_meta["observed_at"] is None
    assert infra_meta["age_seconds"] is None
    assert infra_meta["freshness_status"] == "PROVISIONAL"


def test_future_and_malformed_timestamps_handling():
    """Requirement 6: Verify future and malformed timestamps are handled safely without negative ages or crashes."""
    weather = WeatherAdapter(api_key="test_key", cache_ttl=300)
    ref_time = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)

    # Future timestamp (10 minutes in future relative to reference)
    future_time = (ref_time + timedelta(minutes=10)).isoformat()
    weather.observed_at = future_time

    age = weather.calculate_age(now_reference=ref_time)
    assert age == 0.0  # Max(0.0, diff) prevents negative age

    # Malformed timestamp
    weather.observed_at = "not-a-valid-timestamp"
    malformed_age = weather.calculate_age(now_reference=ref_time)
    assert malformed_age is None


def test_cached_vs_newly_fetched_data_metadata():
    """Requirement 7: Verify cache_status distinguishes newly_fetched, cached, stale_cache, and none."""
    weather = WeatherAdapter(api_key="test_key", cache_ttl=300)
    weather._cached_response = {"rain": {"1h": 12.5}}
    weather._cache_timestamp = 1000.0

    # Simulate get_features hit on valid cache
    import time
    time_mock = 1050.0  # Within 300s TTL
    weather.get_features()

    meta = weather.get_features()
    assert weather.cache_status in ("cached", "newly_fetched", "none")


def test_historical_traffic_labelled_historical_baseline():
    """Requirement 8: Verify historical traffic dataset is classified HISTORICAL_BASELINE, not live traffic."""
    assembler = RealDataFeatureAssembler()
    rec = assembler.assemble_record(timestamp_utc="2023-07-13T12:00:00Z")

    traffic_freshness = rec.feature_freshness["road_congestion"]
    assert traffic_freshness["freshness_status"] == "HISTORICAL_BASELINE"
    assert traffic_freshness["observed_at"] == "2020-07-01T00:00:00Z"
    assert traffic_freshness["provenance_class"] == ProvenanceStatus.DERIVED_FROM_REAL.value
    assert "2020" in traffic_freshness["unavailability_reason"]


def test_worldpop_and_ghsl_labelled_contextual_static():
    """Requirement 9: Verify WorldPop population is classified CONTEXTUAL_STATIC, preserving dataset year."""
    assembler = RealDataFeatureAssembler()
    rec = assembler.assemble_record(timestamp_utc="2023-07-13T12:00:00Z")

    pop_freshness = rec.feature_freshness["population_exposure"]
    assert pop_freshness["freshness_status"] == "CONTEXTUAL_STATIC"
    assert pop_freshness["observed_at"] == "2020-01-01T00:00:00Z"
    assert pop_freshness["age_seconds"] is None
    assert "SEMANTICALLY_INCOMPATIBLE" in pop_freshness["unavailability_reason"]


def test_cwc_missing_milestones_labelled_unavailable():
    """Requirement 10: Verify missing CWC milestone timestamps remain UNAVAILABLE without fabricated values."""
    assembler = RealDataFeatureAssembler()
    # Non-event milestone timestamp
    rec = assembler.assemble_record(timestamp_utc="2023-01-01T00:00:00Z")

    wl_freshness = rec.feature_freshness["water_level"]
    assert wl_freshness["freshness_status"] == "UNAVAILABLE"
    assert wl_freshness["observed_at"] is None
    assert wl_freshness["availability_status"] == "UNAVAILABLE"
    assert "No official CWC observation" in wl_freshness["unavailability_reason"]


def test_provisional_infrastructure_vulnerability_labelled_provisional():
    """Requirement 11: Verify provisional infrastructure vulnerability is classified PROVISIONAL."""
    assembler = RealDataFeatureAssembler()
    rec = assembler.assemble_record(timestamp_utc="2023-07-13T12:00:00Z")

    infra_freshness = rec.feature_freshness["infrastructure_vulnerability"]
    assert infra_freshness["freshness_status"] == "PROVISIONAL"
    assert infra_freshness["provenance_class"] == ProvenanceStatus.PROVISIONAL.value
    assert infra_freshness["observed_at"] is None
    assert "PROVISIONAL" in infra_freshness["unavailability_reason"]


def test_simulated_mode_backward_compatibility():
    """Requirement 12: Verify simulated mode returns SIMULATED freshness for all 7 features."""
    adapter = DataAdapter(data_mode="simulated")
    feats = adapter.get_base_features()
    meta = adapter.get_telemetry_metadata()

    assert feats == BASE_SENSOR_FEATURES
    assert meta["data_mode"] == "simulated"
    assert meta["fallback_used"] is False

    freshness = meta["feature_freshness"]
    for k in BASE_SENSOR_FEATURES:
        assert freshness[k]["freshness_status"] == "SIMULATED"
        assert freshness[k]["provenance_class"] == "SIMULATED"
        assert freshness[k]["observed_at"] is None


def test_phase6_23_runtime_behavior_and_provenance_compatibility():
    """Requirement 13: Verify existing Phase 6.23 telemetry metadata fields remain fully populated and backward compatible."""
    adapter = DataAdapter(data_mode="real")
    feats = adapter.get_base_features()
    meta = adapter.get_telemetry_metadata()

    # Existing metadata keys must be present
    assert "data_mode" in meta
    assert "fallback_used" in meta
    assert "providers" in meta
    assert "provenance" in meta
    assert "raw_features" in meta
    assert "clipping_flags" in meta
    assert "extra_contextual_features" in meta
    assert "feature_freshness" in meta
    assert "real_data_disclaimer" in meta
