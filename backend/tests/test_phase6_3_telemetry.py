"""
AapdaNetra-X — Phase 6.3 Environmental Telemetry & Data Adapters Test Suite
Comprehensive unit & integration tests covering simulated, hybrid, and live modes,
OWM weather API integration, 3h rainfall fallback, sliding window trend derivation,
CWC water level adapter, TTL caching, stale data detection, error handling,
security checks, and /health endpoint telemetry observability.
"""
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure root workspace and backend directories are in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
for p in [str(ROOT_DIR), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
import httpx
from fastapi.testclient import TestClient

from app.config import settings
from app.data.providers.base import DataProviderStatus
from app.data.providers.weather_adapter import WeatherAdapter
from app.data.providers.water_level_adapter import WaterLevelAdapter
from app.data.providers.cwc_water_adapter import CWCWaterLevelAdapter
from app.data.providers.data_adapter import DataAdapter, BASE_SENSOR_FEATURES, reset_data_adapter
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_adapter_singleton():
    """Reset DataAdapter singleton before each test."""
    reset_data_adapter()
    yield
    reset_data_adapter()


# ── 1. Weather Adapter Unit Tests ──────────────────────────────────────────
def test_simulated_mode_telemetry():
    """1. Verify DATA_MODE=simulated returns 100% Phase 5D features without provider calls."""
    adapter = DataAdapter(data_mode="simulated")
    features = adapter.get_base_features()

    assert features == BASE_SENSOR_FEATURES
    assert all(prov == "simulated" for prov in adapter.provenance.values())
    assert adapter.fallback_used is False


def test_weather_adapter_live_success():
    """2 & 3. Test WeatherAdapter extracts rain.1h from valid OWM response."""
    weather = WeatherAdapter(api_key="valid_key", lat=28.6448, lon=77.2167)
    mock_payload = {"rain": {"1h": 45.5}, "dt": 1700000000}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("httpx.Client.get", return_value=mock_resp):
        feats = weather.get_features()
        assert feats["rainfall_intensity"] == 45.5
        assert weather.status == DataProviderStatus.LIVE
        assert weather.observed_at is not None


def test_weather_adapter_dry_weather():
    """4. Test rain key omitted by OWM indicates 0.0 mm/h (dry weather)."""
    weather = WeatherAdapter(api_key="valid_key")
    mock_payload = {"main": {"temp": 28.0}, "dt": 1700000000}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("httpx.Client.get", return_value=mock_resp):
        feats = weather.get_features()
        assert feats["rainfall_intensity"] == 0.0
        assert weather.status == DataProviderStatus.LIVE


def test_weather_adapter_3h_rainfall_fallback():
    """5. Test fallback to rain.3h / 3.0 when 1h rain is absent."""
    weather = WeatherAdapter(api_key="valid_key")
    mock_payload = {"rain": {"3h": 60.0}, "dt": 1700000000}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("httpx.Client.get", return_value=mock_resp):
        feats = weather.get_features()
        assert feats["rainfall_intensity"] == 20.0
        assert weather.status == DataProviderStatus.LIVE


def test_weather_adapter_trend_derivation():
    """6. Test sliding window rainfall_trend derivation across consecutive observations."""
    weather = WeatherAdapter(api_key="valid_key")

    now1 = time.monotonic()
    now2 = now1 + 3600.0  # +1 hour

    with patch("time.monotonic", return_value=now1):
        weather._derive_trend(10.0)

    with patch("time.monotonic", return_value=now2):
        trend = weather._derive_trend(25.0)

    # (25.0 - 10.0) / 1.0 hour = 15.0 mm/h²
    assert trend == 15.0


def test_weather_adapter_startup_trend_behavior():
    """7. Test trend is None on startup when history buffer has < 2 readings."""
    weather = WeatherAdapter(api_key="valid_key")
    trend = weather._derive_trend(10.0)
    assert trend is None


def test_weather_adapter_timeout_handling():
    """8. Test httpx.TimeoutException handling sets DataProviderStatus.ERROR."""
    weather = WeatherAdapter(api_key="valid_key", timeout=1.0)

    with patch("httpx.Client.get", side_effect=httpx.TimeoutException("Timeout")):
        feats = weather.get_features()
        assert feats["rainfall_intensity"] is None
        assert weather.status == DataProviderStatus.ERROR
        assert "timeout" in weather.last_error.lower()


def test_weather_adapter_http_401():
    """9. Test HTTP 401 invalid API key handling."""
    weather = WeatherAdapter(api_key="invalid_key")
    mock_resp = MagicMock()
    mock_resp.status_code = 401

    with patch("httpx.Client.get", return_value=mock_resp):
        feats = weather.get_features()
        assert feats["rainfall_intensity"] is None
        assert weather.status == DataProviderStatus.ERROR
        assert "401" in weather.last_error


def test_weather_adapter_malformed_response():
    """10. Test malformed JSON payload handling."""
    weather = WeatherAdapter(api_key="valid_key")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"rain": "invalid_string"}

    with patch("httpx.Client.get", return_value=mock_resp):
        feats = weather.get_features()
        assert feats["rainfall_intensity"] is None
        assert weather.status == DataProviderStatus.ERROR


def test_weather_adapter_cache_hit_and_expiry():
    """11 & 12. Test weather cache hit within TTL and re-fetching after expiry."""
    weather = WeatherAdapter(api_key="valid_key", cache_ttl=60)
    mock_payload1 = {"rain": {"1h": 10.0}, "dt": 1700000000}

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload1

    t0 = time.monotonic()

    with patch("time.monotonic", return_value=t0):
        with patch("httpx.Client.get", return_value=mock_resp):
            feats1 = weather.get_features()
            assert feats1["rainfall_intensity"] == 10.0
            assert weather._cached_response is not None

    # Within TTL (t0 + 30s) -> cache hit
    with patch("time.monotonic", return_value=t0 + 30):
        assert weather._cached_response is not None

    # After TTL (t0 + 70s) -> cache invalidated
    weather.invalidate_cache()
    assert weather._cached_response is None


def test_weather_adapter_stale_data():
    """13. Test serving stale cache when network fails after initial success."""
    weather = WeatherAdapter(api_key="valid_key", cache_ttl=10)
    mock_payload = {"rain": {"1h": 15.0}, "dt": 1700000000}

    t0 = time.monotonic()
    with patch("time.monotonic", return_value=t0):
        with patch("httpx.Client.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_payload
            mock_get.return_value = mock_resp
            weather.get_features()

    # Expire TTL and simulate network error beyond 2 * TTL (70s > 60s)
    with patch("time.monotonic", return_value=t0 + 70):
        with patch("httpx.Client.get", side_effect=httpx.RequestError("Network Error")):
            raw = weather._fetch_with_cache()
            assert raw == mock_payload
            assert weather.is_stale is True


# ── 2. Water Level & CWC Adapter Tests ────────────────────────────────────
def test_water_level_adapter_manual_override(tmp_path):
    """14 & 16. Test manual ENV and JSON file water level overrides."""
    override_file = tmp_path / "water_override.json"
    override_file.write_text(json.dumps({"water_level": 7.5, "water_level_trend": 0.6}))

    water = WaterLevelAdapter(source="manual", override_file=override_file)
    feats = water.get_features()

    assert feats["water_level"] == 7.5
    assert feats["water_level_trend"] == 0.6
    assert water.status == DataProviderStatus.LIVE


def test_water_level_adapter_caching(tmp_path):
    """15. Test TTL caching for WaterLevelAdapter."""
    override_file = tmp_path / "water_override.json"
    override_file.write_text(json.dumps({"water_level": 6.9}))

    water = WaterLevelAdapter(source="manual", override_file=override_file, cache_ttl=60)
    feats1 = water.get_features()
    assert feats1["water_level"] == 6.9
    assert water._cached_features is not None


def test_cwc_water_adapter_unavailable():
    """17. Test CWCWaterLevelAdapter with no endpoint returns status FALLBACK safely."""
    cwc = CWCWaterLevelAdapter(endpoint_url="")
    feats = cwc.get_features()

    assert feats["water_level"] is None
    assert feats["water_level_trend"] is None
    assert cwc.status == DataProviderStatus.FALLBACK
    assert cwc.fallback_used is True


# ── 3. Data Mode & Orchestrator Tests ────────────────────────────────────
def test_hybrid_mode_telemetry():
    """18. Test DATA_MODE=hybrid merges live weather/water and keeps traffic/exposure simulated."""
    weather = WeatherAdapter(api_key="valid_key")
    with patch.object(weather, "get_features", return_value={"rainfall_intensity": 50.0, "rainfall_trend": 5.0}):
        data_adapter = DataAdapter(data_mode="hybrid", weather_adapter=weather)
        feats = data_adapter.get_base_features()

        assert feats["rainfall_intensity"] == 50.0
        assert feats["rainfall_trend"] == 5.0
        assert feats["road_congestion"] == 0.72  # Simulated
        assert feats["population_exposure"] == 12430.0  # Simulated
        assert data_adapter.provenance["rainfall_intensity"] == "live:weather"
        assert data_adapter.provenance["road_congestion"] == "fallback:simulated"


def test_strict_live_mode_without_fallback():
    """19. Test DATA_MODE=live with ENABLE_FALLBACK=false marks provenance missing:no_fallback."""
    weather = WeatherAdapter(api_key="")  # Unconfigured key
    data_adapter = DataAdapter(data_mode="live", enable_fallback=False, weather_adapter=weather)
    feats = data_adapter.get_base_features()

    assert data_adapter.provenance["rainfall_intensity"] == "missing:no_fallback"
    assert data_adapter.fallback_used is True


def test_live_mode_with_explicit_fallback():
    """20. Test DATA_MODE=live with ENABLE_FALLBACK=true records fallback:simulated."""
    weather = WeatherAdapter(api_key="")  # Unconfigured key
    data_adapter = DataAdapter(data_mode="live", enable_fallback=True, weather_adapter=weather)
    feats = data_adapter.get_base_features()

    assert data_adapter.provenance["rainfall_intensity"] == "fallback:simulated"
    assert data_adapter.fallback_used is True


# ── 4. Observability, Health & Security Tests ─────────────────────────────
def test_telemetry_metadata_structure():
    """21. Test DataAdapter.get_telemetry_metadata() exposes required structure."""
    weather = WeatherAdapter(api_key="valid_key")
    data_adapter = DataAdapter(data_mode="hybrid", weather_adapter=weather)
    data_adapter.get_base_features()

    meta = data_adapter.get_telemetry_metadata()
    assert "data_mode" in meta
    assert "fallback_used" in meta
    assert "providers" in meta
    assert "provenance" in meta
    assert "weather" in meta["providers"]
    assert "water_level" in meta["providers"]


def test_health_endpoint_telemetry_info():
    """22. Test GET /health endpoint exposes provider telemetry statuses without breaking schema."""
    with patch("app.config.settings.data_mode", "hybrid"):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "operational"
        assert data["data_mode"] == "hybrid"
        assert "providers" in data
        assert "telemetry" in data


def test_api_key_not_exposed_in_metadata():
    """23. Test OPENWEATHERMAP_API_KEY is never exposed in metadata or /health endpoint."""
    secret_key = "secret_owm_api_key_99999"
    weather = WeatherAdapter(api_key=secret_key)
    data_adapter = DataAdapter(data_mode="hybrid", weather_adapter=weather)

    meta = data_adapter.get_telemetry_metadata()
    meta_json = json.dumps(meta)
    assert secret_key not in meta_json

    with patch("app.config.settings.openweathermap_api_key", secret_key):
        res = client.get("/health")
        assert secret_key not in res.text
