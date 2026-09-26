"""
AapdaNetra-X — Phase 6.1 Data Provider Tests
Tests for WeatherAdapter, WaterLevelAdapter, DataAdapter, and simulated-mode regression.
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure root workspace and backend directories are in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
for p in [str(ROOT_DIR), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app.data.providers.base import DataProvider, DataProviderStatus
from app.data.providers.weather_adapter import WeatherAdapter
from app.data.providers.water_level_adapter import WaterLevelAdapter
from app.data.providers.data_adapter import (
    DataAdapter,
    BASE_SENSOR_FEATURES,
    reset_data_adapter,
)
from app.services.risk_engine import (
    BASE_SENSOR_FEATURES as ENGINE_BASE_FEATURES,
    get_horizon_features,
    HORIZON_DELTAS,
)


# ── WeatherAdapter Tests ──────────────────────────────────────────────────


class TestWeatherAdapterSuccess:
    """Tests for WeatherAdapter with mocked HTTP success responses."""

    def test_successful_rainfall_extraction(self):
        """Mock a successful OWM response with rain.1h data."""
        adapter = WeatherAdapter(api_key="test_key_123", cache_ttl=30)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "weather": [{"main": "Rain"}],
            "rain": {"1h": 42.5},
            "main": {"temp": 28.0},
        }

        with patch("app.data.providers.weather_adapter.httpx.Client") as MockClient:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = adapter.get_features()

        assert result["rainfall_intensity"] == 42.5
        assert adapter.status == DataProviderStatus.LIVE

    def test_no_rain_key_returns_zero(self):
        """When OWM reports no rain, rainfall_intensity should be 0.0."""
        adapter = WeatherAdapter(api_key="test_key_123", cache_ttl=30)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 32.0},
        }

        with patch("app.data.providers.weather_adapter.httpx.Client") as MockClient:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = adapter.get_features()

        assert result["rainfall_intensity"] == 0.0
        assert adapter.status == DataProviderStatus.LIVE

    def test_rain_3h_fallback(self):
        """When only rain.3h is available, approximate hourly rate."""
        adapter = WeatherAdapter(api_key="test_key_123", cache_ttl=30)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "rain": {"3h": 30.0},
        }

        with patch("app.data.providers.weather_adapter.httpx.Client") as MockClient:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = adapter.get_features()

        assert result["rainfall_intensity"] == pytest.approx(10.0, abs=0.1)

    def test_cache_prevents_duplicate_requests(self):
        """Second call within TTL should use cached response."""
        adapter = WeatherAdapter(api_key="test_key_123", cache_ttl=300)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"rain": {"1h": 20.0}}

        with patch("app.data.providers.weather_adapter.httpx.Client") as MockClient:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result1 = adapter.get_features()
            result2 = adapter.get_features()

        # httpx.Client() should only be called once (cached on second call)
        assert MockClient.call_count == 1
        assert result1["rainfall_intensity"] == 20.0
        assert result2["rainfall_intensity"] == 20.0


class TestWeatherAdapterFailure:
    """Tests for WeatherAdapter failure and fallback scenarios."""

    def test_no_api_key_returns_none_values(self):
        """When no API key is set, return None values and FALLBACK status."""
        adapter = WeatherAdapter(api_key="", cache_ttl=30)
        result = adapter.get_features()

        assert result["rainfall_intensity"] is None
        assert result["rainfall_trend"] is None
        assert adapter.status == DataProviderStatus.FALLBACK

    def test_http_401_returns_none(self):
        """Invalid API key (401) should return None values with ERROR status."""
        adapter = WeatherAdapter(api_key="bad_key", cache_ttl=30)

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("app.data.providers.weather_adapter.httpx.Client") as MockClient:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = adapter.get_features()

        assert result["rainfall_intensity"] is None
        assert adapter.status == DataProviderStatus.ERROR

    def test_network_timeout_returns_none(self):
        """Timeout should return None values with ERROR status."""
        import httpx

        adapter = WeatherAdapter(api_key="test_key", cache_ttl=30)

        with patch("app.data.providers.weather_adapter.httpx.Client") as MockClient:
            mock_client_instance = MagicMock()
            mock_client_instance.get.side_effect = httpx.TimeoutException("Connection timed out")
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = adapter.get_features()

        assert result["rainfall_intensity"] is None
        assert adapter.status == DataProviderStatus.ERROR
        assert "timeout" in adapter.last_error.lower()

    def test_http_500_returns_none(self):
        """Server error should return None values with ERROR status."""
        adapter = WeatherAdapter(api_key="test_key", cache_ttl=30)

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("app.data.providers.weather_adapter.httpx.Client") as MockClient:
            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = adapter.get_features()

        assert result["rainfall_intensity"] is None
        assert adapter.status == DataProviderStatus.ERROR


# ── WaterLevelAdapter Tests ───────────────────────────────────────────────


class TestWaterLevelAdapter:
    """Tests for WaterLevelAdapter from env vars, JSON file, and simulated mode."""

    def test_simulated_mode_returns_none(self):
        """In simulated mode, adapter returns None values for orchestrator fallback."""
        adapter = WaterLevelAdapter(source="simulated")
        result = adapter.get_features()

        assert result["water_level"] is None
        assert result["water_level_trend"] is None
        assert adapter.status == DataProviderStatus.FALLBACK

    def test_env_var_override(self):
        """Environment variables should override water level values."""
        adapter = WaterLevelAdapter(source="manual")

        with patch.dict(os.environ, {
            "WATER_LEVEL_OVERRIDE": "7.5",
            "WATER_LEVEL_TREND_OVERRIDE": "0.8",
        }):
            result = adapter.get_features()

        assert result["water_level"] == 7.5
        assert result["water_level_trend"] == 0.8
        assert adapter.status == DataProviderStatus.LIVE

    def test_json_file_override(self):
        """JSON override file should provide water level values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"water_level": 8.2, "water_level_trend": 1.1}, f)
            temp_path = Path(f.name)

        try:
            adapter = WaterLevelAdapter(source="manual", override_file=temp_path)
            # Clear env vars to ensure file is used
            with patch.dict(os.environ, {}, clear=True):
                result = adapter.get_features()

            assert result["water_level"] == 8.2
            assert result["water_level_trend"] == 1.1
            assert adapter.status == DataProviderStatus.LIVE
        finally:
            temp_path.unlink()

    def test_missing_file_returns_none(self):
        """Missing override file should return None values."""
        adapter = WaterLevelAdapter(
            source="manual",
            override_file=Path("/nonexistent/path/water_level_override.json"),
        )
        with patch.dict(os.environ, {}, clear=True):
            result = adapter.get_features()

        assert result["water_level"] is None
        assert result["water_level_trend"] is None

    def test_invalid_env_value_handled(self):
        """Invalid (non-numeric) env value should be handled gracefully."""
        adapter = WaterLevelAdapter(source="manual")

        with patch.dict(os.environ, {"WATER_LEVEL_OVERRIDE": "not_a_number"}):
            result = adapter.get_features()

        assert adapter.status == DataProviderStatus.ERROR


# ── DataAdapter Tests ─────────────────────────────────────────────────────


class TestDataAdapter:
    """Tests for the DataAdapter orchestrator merge/fallback logic."""

    def test_simulated_mode_returns_exact_base_features(self):
        """In simulated mode, DataAdapter must return BASE_SENSOR_FEATURES unchanged."""
        adapter = DataAdapter(data_mode="simulated")
        result = adapter.get_base_features()

        assert result == BASE_SENSOR_FEATURES
        assert all(v == "simulated" for v in adapter.provenance.values())

    def test_all_seven_feature_keys_present(self):
        """Result must always contain exactly the 7 expected feature keys."""
        adapter = DataAdapter(data_mode="simulated")
        result = adapter.get_base_features()

        expected_keys = {
            "rainfall_intensity", "rainfall_trend", "water_level",
            "water_level_trend", "road_congestion", "population_exposure",
            "infrastructure_vulnerability",
        }
        assert set(result.keys()) == expected_keys

    def test_live_weather_overrides_rainfall(self):
        """Live weather data should override rainfall features in hybrid mode."""
        mock_weather = MagicMock(spec=WeatherAdapter)
        mock_weather.get_features.return_value = {
            "rainfall_intensity": 55.0,
            "rainfall_trend": 8.0,
        }

        adapter = DataAdapter(
            data_mode="hybrid",
            weather_adapter=mock_weather,
        )
        result = adapter.get_base_features()

        assert result["rainfall_intensity"] == 55.0
        assert result["rainfall_trend"] == 8.0
        # Other features remain as defaults
        assert result["water_level"] == BASE_SENSOR_FEATURES["water_level"]
        assert result["road_congestion"] == BASE_SENSOR_FEATURES["road_congestion"]
        assert adapter.provenance["rainfall_intensity"] == "live:weather"
        assert adapter.provenance["water_level"] == "simulated"

    def test_live_water_level_overrides(self):
        """Live water level data should override water features in hybrid mode."""
        mock_water = MagicMock(spec=WaterLevelAdapter)
        mock_water.get_features.return_value = {
            "water_level": 9.1,
            "water_level_trend": 1.2,
        }

        adapter = DataAdapter(
            data_mode="hybrid",
            water_level_adapter=mock_water,
        )
        result = adapter.get_base_features()

        assert result["water_level"] == 9.1
        assert result["water_level_trend"] == 1.2
        assert adapter.provenance["water_level"] == "live:water_level"

    def test_none_values_fallback_to_defaults(self):
        """None values from providers should fall back to simulated defaults."""
        mock_weather = MagicMock(spec=WeatherAdapter)
        mock_weather.get_features.return_value = {
            "rainfall_intensity": None,
            "rainfall_trend": 3.0,
        }

        adapter = DataAdapter(
            data_mode="live",
            weather_adapter=mock_weather,
        )
        result = adapter.get_base_features()

        # rainfall_intensity falls back to default since provider returned None
        assert result["rainfall_intensity"] == BASE_SENSOR_FEATURES["rainfall_intensity"]
        # rainfall_trend is overridden with live value
        assert result["rainfall_trend"] == 3.0

    def test_provider_exception_handled_gracefully(self):
        """Provider exceptions should not crash DataAdapter; defaults used."""
        mock_weather = MagicMock(spec=WeatherAdapter)
        mock_weather.get_features.side_effect = RuntimeError("Connection failed")

        adapter = DataAdapter(
            data_mode="live",
            weather_adapter=mock_weather,
        )
        result = adapter.get_base_features()

        # Should fall back to all defaults
        assert result == BASE_SENSOR_FEATURES

    def test_provider_statuses_tracking(self):
        """Provider status should be correctly tracked."""
        mock_weather = MagicMock(spec=WeatherAdapter)
        mock_weather.status = DataProviderStatus.LIVE

        mock_water = MagicMock(spec=WaterLevelAdapter)
        mock_water.status = DataProviderStatus.FALLBACK

        adapter = DataAdapter(
            data_mode="hybrid",
            weather_adapter=mock_weather,
            water_level_adapter=mock_water,
        )
        statuses = adapter.provider_statuses

        assert statuses["data_mode"] == "hybrid"
        assert statuses["weather"] == "live"
        assert statuses["water_level"] == "fallback"

    def test_no_providers_configured(self):
        """With no providers configured, should return defaults."""
        adapter = DataAdapter(data_mode="live")
        statuses = adapter.provider_statuses

        assert statuses["weather"] == "not_configured"
        assert statuses["water_level"] == "not_configured"

        result = adapter.get_base_features()
        assert result == BASE_SENSOR_FEATURES


# ── Phase 5D Regression Tests ─────────────────────────────────────────────


class TestPhase5DRegression:
    """
    Critical regression tests to verify that DATA_MODE=simulated
    produces identical behavior to Phase 5D.
    """

    def test_base_sensor_features_unchanged(self):
        """BASE_SENSOR_FEATURES in risk_engine.py must match canonical values."""
        expected = {
            "rainfall_intensity": 95.0,
            "rainfall_trend": 12.0,
            "water_level": 6.8,
            "water_level_trend": 0.45,
            "road_congestion": 0.72,
            "population_exposure": 12430.0,
            "infrastructure_vulnerability": 0.78,
        }
        assert ENGINE_BASE_FEATURES == expected

    def test_get_horizon_features_horizon_0_unchanged(self):
        """get_horizon_features(0) must produce the exact Phase 5D result."""
        with patch("app.config.settings") as mock_settings:
            mock_settings.data_mode = "simulated"
            result = get_horizon_features(0)

        # Horizon 0 should be BASE_SENSOR_FEATURES unchanged
        assert result["rainfall_intensity"] == 95.0
        assert result["water_level"] == 6.8
        assert result["water_level_trend"] == 0.45
        assert result["road_congestion"] == 0.72

    def test_get_horizon_features_horizon_3_unchanged(self):
        """get_horizon_features(3) must produce the exact Phase 5D +30M result."""
        with patch("app.config.settings") as mock_settings:
            mock_settings.data_mode = "simulated"
            result = get_horizon_features(3)

        delta = HORIZON_DELTAS[3]
        expected_rainfall = min(300.0, 95.0 * delta["rainfall_mul"])
        expected_water = min(15.0, 6.8 + delta["water_add"])
        expected_wl_trend = min(5.0, 0.45 + delta["trend_add"])
        expected_congestion = min(1.0, 0.72 + delta["congestion_add"])

        assert result["rainfall_intensity"] == pytest.approx(expected_rainfall, abs=0.01)
        assert result["water_level"] == pytest.approx(expected_water, abs=0.01)
        assert result["water_level_trend"] == pytest.approx(expected_wl_trend, abs=0.01)
        assert result["road_congestion"] == pytest.approx(expected_congestion, abs=0.01)

    def test_horizon_deltas_unchanged(self):
        """HORIZON_DELTAS must be the exact Phase 5D values."""
        assert len(HORIZON_DELTAS) == 4
        assert HORIZON_DELTAS[0] == {"rainfall_mul": 1.0, "water_add": 0.0, "trend_add": 0.0, "congestion_add": 0.0}
        assert HORIZON_DELTAS[3] == {"rainfall_mul": 1.48, "water_add": 1.35, "trend_add": 0.30, "congestion_add": 0.20}

    def test_data_adapter_base_features_match_engine(self):
        """DataAdapter BASE_SENSOR_FEATURES must be identical to risk_engine BASE_SENSOR_FEATURES."""
        assert BASE_SENSOR_FEATURES == ENGINE_BASE_FEATURES

    def test_simulated_mode_ml_prediction_unchanged(self):
        """Full ML inference in simulated mode must produce valid, stable predictions."""
        from ml.inference import predict_risk

        with patch("app.config.settings") as mock_settings:
            mock_settings.data_mode = "simulated"
            features = get_horizon_features(0)

        result = predict_risk(features)
        assert 0.0 <= result["risk_score"] <= 100.0
        assert result["risk_category"] in ["LOW", "MODERATE", "HIGH", "CRITICAL"]
        assert 0.0 <= result["prediction_reliability"] <= 1.0
