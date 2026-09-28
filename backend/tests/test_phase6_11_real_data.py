"""AapdaNetra-X — Phase 6.11 Real Data Activation Unit Tests

Verifies Weather, Water Level, Traffic, Population, Infrastructure providers,
DataAdapter orchestration, data modes (simulated, hybrid, live), bounds validation,
provenance metadata, and security sanitization.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.data.providers.base import DataProviderStatus
from app.data.providers.cwc_water_adapter import CWCWaterLevelAdapter
from app.data.providers.data_adapter import DataAdapter, reset_data_adapter, BASE_SENSOR_FEATURES
from app.data.providers.infrastructure_adapter import InfrastructureAdapter
from app.data.providers.population_adapter import PopulationAdapter
from app.data.providers.traffic_adapter import TrafficAdapter
from app.data.providers.water_level_adapter import WaterLevelAdapter
from app.data.providers.weather_adapter import WeatherAdapter


@pytest.fixture(autouse=True)
def reset_adapter_singleton():
    """Ensure global DataAdapter singleton is clean for every test."""
    reset_data_adapter()
    yield
    reset_data_adapter()


# ── 1. Weather Adapter Tests ───────────────────────────────────────────────

def test_weather_adapter_missing_api_key():
    adapter = WeatherAdapter(api_key="")
    features = adapter.get_features()
    assert features["rainfall_intensity"] is None
    assert features["rainfall_trend"] is None
    assert adapter.status == DataProviderStatus.FALLBACK
    assert adapter.fallback_used is True


def test_weather_adapter_valid_api_response():
    adapter = WeatherAdapter(api_key="valid_dummy_key")
    mock_payload = {
        "dt": 1758980000,
        "rain": {"1h": 45.5},
        "main": {"temp": 28.5},
    }
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_get.return_value = mock_resp

        features = adapter.get_features()
        assert features["rainfall_intensity"] == 45.5
        assert adapter.status == DataProviderStatus.LIVE
        assert adapter.fallback_used is False
        assert adapter.observed_at is not None


def test_weather_adapter_bounds_validation():
    adapter = WeatherAdapter(api_key="valid_key")
    mock_payload = {"rain": {"1h": 500.0}}  # Exceeds max 300 mm/h limit
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_get.return_value = mock_resp

        features = adapter.get_features()
        assert features["rainfall_intensity"] == 300.0  # Clamped to upper bound


def test_weather_adapter_http_401_error():
    adapter = WeatherAdapter(api_key="invalid_key")
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        features = adapter.get_features()
        assert features["rainfall_intensity"] is None
        assert adapter.status == DataProviderStatus.ERROR
        assert "401" in adapter.last_error


# ── 2. Water Level Adapter Tests ────────────────────────────────────────────

def test_water_level_adapter_env_override():
    adapter = WaterLevelAdapter(source="manual")
    with patch.dict("os.environ", {"WATER_LEVEL_OVERRIDE": "8.5", "WATER_LEVEL_TREND_OVERRIDE": "0.6"}):
        features = adapter.get_features()
        assert features["water_level"] == 8.5
        assert features["water_level_trend"] == 0.6
        assert adapter.status == DataProviderStatus.LIVE


def test_cwc_water_level_adapter_unconfigured():
    adapter = CWCWaterLevelAdapter(endpoint_url="", station_id="STN-01")
    features = adapter.get_features()
    assert features["water_level"] is None
    assert features["water_level_trend"] is None
    assert adapter.status == DataProviderStatus.FALLBACK
    assert adapter.fallback_used is True


# ── 3. Traffic Adapter Tests ───────────────────────────────────────────────

def test_traffic_adapter_unconfigured():
    adapter = TrafficAdapter(api_key="", endpoint_url="")
    features = adapter.get_features()
    assert features["road_congestion"] is None
    assert adapter.status == DataProviderStatus.FALLBACK


def test_traffic_adapter_speed_ratio_calculation():
    adapter = TrafficAdapter(api_key="key", endpoint_url="http://traffic.example.com/api")
    mock_payload = {"actual_speed": 15.0, "freeflow_speed": 60.0}
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_get.return_value = mock_resp

        features = adapter.get_features()
        # actual/freeflow = 15/60 = 0.25 -> congestion = 1.0 - 0.25 = 0.75
        assert features["road_congestion"] == 0.75
        assert adapter.status == DataProviderStatus.LIVE


# ── 4. Population Adapter Tests ────────────────────────────────────────────

def test_population_adapter_sample_dataset(tmp_path):
    sample_file = tmp_path / "population_sample.json"
    sample_data = {
        "dataset_name": "WorldPop Test Grid",
        "vulnerable_population": 15000.0,
    }
    sample_file.write_text(json.dumps(sample_data))

    adapter = PopulationAdapter(dataset_path=sample_file)
    features = adapter.get_features()
    assert features["population_exposure"] == 15000.0
    assert adapter.status == DataProviderStatus.LIVE
    assert "worldpop" in adapter.dataset_source


def test_population_adapter_missing_file():
    adapter = PopulationAdapter(dataset_path=Path("/nonexistent/file.json"))
    features = adapter.get_features()
    assert features["population_exposure"] is None
    assert adapter.status == DataProviderStatus.FALLBACK


# ── 5. Infrastructure Adapter Tests ────────────────────────────────────────

def test_infrastructure_adapter_sample_dataset(tmp_path):
    sample_file = tmp_path / "infrastructure_sample.json"
    sample_data = {
        "dataset_name": "OSM Infrastructure Test",
        "vulnerability_index": 0.82,
    }
    sample_file.write_text(json.dumps(sample_data))

    adapter = InfrastructureAdapter(dataset_path=sample_file)
    features = adapter.get_features()
    assert features["infrastructure_vulnerability"] == 0.82
    assert adapter.status == DataProviderStatus.LIVE
    assert adapter.dataset_source == "dataset:osm_infrastructure"


# ── 6. DataAdapter Orchestrator Tests ──────────────────────────────────────

def test_data_adapter_simulated_mode():
    da = DataAdapter(data_mode="simulated")
    feats = da.get_base_features()
    assert feats == BASE_SENSOR_FEATURES
    assert all(v == "simulated" for v in da.provenance.values())
    assert da.fallback_used is False


def test_data_adapter_hybrid_mode_with_mock_providers():
    mock_weather = MagicMock()
    mock_weather.get_features.return_value = {"rainfall_intensity": 120.0, "rainfall_trend": 15.0}

    da = DataAdapter(
        data_mode="hybrid",
        weather_adapter=mock_weather,
    )
    feats = da.get_base_features()
    assert feats["rainfall_intensity"] == 120.0
    assert feats["rainfall_trend"] == 15.0
    assert da.provenance["rainfall_intensity"] == "live:weather"
    assert da.provenance["water_level"] == "fallback:simulated"
    assert da.fallback_used is True


def test_data_adapter_telemetry_metadata_security_sanitization():
    da = DataAdapter(data_mode="simulated")
    meta = da.get_telemetry_metadata()

    assert "data_mode" in meta
    assert "providers" in meta
    assert "provenance" in meta

    # Ensure no secrets or credentials leaked
    meta_str = str(meta)
    assert "api_key" not in meta_str.lower()
    assert "password" not in meta_str.lower()
    assert "secret" not in meta_str.lower()
