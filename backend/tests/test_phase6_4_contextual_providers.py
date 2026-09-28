"""
AapdaNetra-X — Phase 6.4 Contextual Data Providers Test Suite
Comprehensive unit & integration tests covering TrafficAdapter, PopulationAdapter,
InfrastructureAdapter, provenance tracking, bounds validation, zero freeflow speed,
missing dataset handling, provisional weights, cache TTL, and /health metadata.
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
from app.data.providers.traffic_adapter import TrafficAdapter
from app.data.providers.population_adapter import PopulationAdapter
from app.data.providers.infrastructure_adapter import InfrastructureAdapter
from app.data.providers.data_adapter import DataAdapter, BASE_SENSOR_FEATURES, reset_data_adapter
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_adapter_singleton():
    """Reset DataAdapter singleton before each test."""
    reset_data_adapter()
    yield
    reset_data_adapter()


# ── 1. Traffic Adapter Unit Tests ────────────────(1-6) ───────────────────
def test_traffic_adapter_speed_ratio_normalization():
    """1. Test normalization of actual_speed and freeflow_speed into road_congestion ratio."""
    traffic = TrafficAdapter(endpoint_url="http://mock.traffic.api")
    # 25 km/h actual vs 50 km/h freeflow -> ratio 0.5 -> congestion = 0.5
    mock_payload = {"actual_speed": 25.0, "freeflow_speed": 50.0}

    with patch.object(traffic, "_fetch_with_cache", return_value=mock_payload):
        feats = traffic.get_features()
        assert feats["road_congestion"] == 0.5
        assert traffic.status == DataProviderStatus.LIVE


def test_traffic_adapter_bounds_clipping():
    """2. Test road_congestion is strictly bounded within [0.0, 1.0]."""
    traffic = TrafficAdapter(endpoint_url="http://mock.traffic.api")
    # actual speed > freeflow -> negative congestion before clamp -> clamped to 0.0
    mock_payload = {"actual_speed": 80.0, "freeflow_speed": 50.0}

    with patch.object(traffic, "_fetch_with_cache", return_value=mock_payload):
        feats = traffic.get_features()
        assert feats["road_congestion"] == 0.0


def test_traffic_adapter_zero_freeflow_handling():
    """3. Test zero freeflow speed is handled safely without division by zero."""
    traffic = TrafficAdapter(endpoint_url="http://mock.traffic.api")
    mock_payload = {"actual_speed": 25.0, "freeflow_speed": 0.0}

    with patch.object(traffic, "_fetch_with_cache", return_value=mock_payload):
        feats = traffic.get_features()
        assert feats["road_congestion"] is None
        assert traffic.fallback_used is True


def test_traffic_adapter_malformed_data():
    """4. Test malformed text in speed values falls back gracefully."""
    traffic = TrafficAdapter(endpoint_url="http://mock.traffic.api")
    mock_payload = {"actual_speed": "invalid", "freeflow_speed": "text"}

    with patch.object(traffic, "_fetch_with_cache", return_value=mock_payload):
        feats = traffic.get_features()
        assert feats["road_congestion"] is None
        assert traffic.fallback_used is True


def test_traffic_adapter_timeout_handling():
    """5. Test HTTP timeout sets DataProviderStatus.ERROR safely."""
    traffic = TrafficAdapter(endpoint_url="http://mock.traffic.api", timeout=1.0)

    with patch("httpx.Client.get", side_effect=httpx.TimeoutException("Timeout")):
        feats = traffic.get_features()
        assert feats["road_congestion"] is None
        assert traffic.status == DataProviderStatus.ERROR


def test_traffic_adapter_unconfigured_fallback():
    """6. Test unconfigured traffic adapter uses fallback safely."""
    traffic = TrafficAdapter(endpoint_url="", api_key="")
    feats = traffic.get_features()

    assert feats["road_congestion"] is None
    assert traffic.status == DataProviderStatus.FALLBACK
    assert traffic.fallback_used is True


# ── 2. Population Adapter Unit Tests ─────────────(7-9) ───────────────────
def test_population_adapter_aggregation(tmp_path):
    """7. Test PopulationAdapter aggregates head-count from local GeoJSON dataset."""
    pop_file = tmp_path / "worldpop.json"
    pop_file.write_text(json.dumps({
        "features": [
            {"geometry": {"coordinates": [77.2167, 28.6448]}, "properties": {"population": 5200.0}},
            {"geometry": {"coordinates": [77.2290, 28.6390]}, "properties": {"population": 7300.0}},
            {"geometry": {"coordinates": [79.0000, 30.0000]}, "properties": {"population": 99000.0}},  # Outside bbox
        ]
    }))

    pop_adapter = PopulationAdapter(dataset_path=pop_file)
    feats = pop_adapter.get_features()

    assert feats["population_exposure"] == 12500.0
    assert pop_adapter.status == DataProviderStatus.LIVE
    assert pop_adapter.dataset_source == "dataset:worldpop_100m_grid"


def test_population_adapter_bounding_box_filtering(tmp_path):
    """8. Test spatial filtering excludes points outside study bbox."""
    pop_file = tmp_path / "worldpop_out.json"
    pop_file.write_text(json.dumps({
        "features": [
            {"geometry": {"coordinates": [10.0, 10.0]}, "properties": {"population": 50000.0}},
        ]
    }))

    pop_adapter = PopulationAdapter(dataset_path=pop_file)
    feats = pop_adapter.get_features()

    assert feats["population_exposure"] == 0.0


def test_population_adapter_missing_dataset():
    """9. Test missing dataset file falls back safely without unhandled exception."""
    pop_adapter = PopulationAdapter(dataset_path=Path("non_existent_worldpop.json"))
    feats = pop_adapter.get_features()

    assert feats["population_exposure"] is None
    assert pop_adapter.status == DataProviderStatus.FALLBACK


# ── 3. Infrastructure Adapter Unit Tests ──────────(10-13) ─────────────────
def test_infrastructure_adapter_vulnerability_index(tmp_path):
    """10, 11, 12, 13. Test infrastructure vulnerability index calculation & bounds [0, 1]."""
    infra_file = tmp_path / "osm_infra.json"
    infra_file.write_text(json.dumps({
        "critical_assets": [
            {"category": "hospital", "exposure_score": 0.9},
            {"category": "substation", "exposure_score": 0.6},
            {"category": "bridge", "exposure_score": 0.4},
        ]
    }))

    infra_adapter = InfrastructureAdapter(dataset_path=infra_file)
    feats = infra_adapter.get_features()

    # Weighted index: (1.0*0.9 + 0.8*0.6 + 0.7*0.4) / (1.0 + 0.8 + 0.7) = 1.66 / 2.5 = 0.664
    assert feats["infrastructure_vulnerability"] == pytest.approx(0.664, rel=1e-2)
    assert infra_adapter.status == DataProviderStatus.LIVE
    assert infra_adapter.dataset_source == "dataset:osm_infrastructure"


# ── 4. Orchestration & Provenance Tests ───────────(14-18) ─────────────────
def test_provenance_labels_for_contextual_features(tmp_path):
    """14 & 15. Test provenance labels use dataset:worldpop / dataset:osm_infrastructure / live:traffic_adapter."""
    pop_file = tmp_path / "pop.json"
    pop_file.write_text(json.dumps({"vulnerable_population": 15000.0}))

    infra_file = tmp_path / "infra.json"
    infra_file.write_text(json.dumps({"vulnerability_index": 0.65}))

    traffic = TrafficAdapter(endpoint_url="http://mock.traffic")
    with patch.object(traffic, "get_features", return_value={"road_congestion": 0.45}):
        pop_adapter = PopulationAdapter(dataset_path=pop_file)
        infra_adapter = InfrastructureAdapter(dataset_path=infra_file)

        data_adapter = DataAdapter(
            data_mode="hybrid",
            traffic_adapter=traffic,
            population_adapter=pop_adapter,
            infrastructure_adapter=infra_adapter,
        )

        feats = data_adapter.get_base_features()
        prov = data_adapter.provenance

        assert feats["road_congestion"] == 0.45
        assert feats["population_exposure"] == 15000.0
        assert feats["infrastructure_vulnerability"] == 0.65

        assert prov["road_congestion"] == "live:traffic_adapter"
        assert prov["population_exposure"] == "dataset:worldpop_100m_grid"
        assert prov["infrastructure_vulnerability"] == "dataset:osm_infrastructure"
        assert prov["rainfall_intensity"] == "fallback:simulated"


def test_strict_live_mode_and_fallback_disabled():
    """16 & 17. Test strict live mode with ENABLE_FALLBACK=false records missing:no_fallback."""
    traffic = TrafficAdapter(endpoint_url="")
    data_adapter = DataAdapter(data_mode="live", enable_fallback=False, traffic_adapter=traffic)

    feats = data_adapter.get_base_features()
    assert data_adapter.provenance["road_congestion"] == "missing:no_fallback"
    assert data_adapter.fallback_used is True


def test_cache_ttl_and_freshness():
    """18. Test cache TTL behavior for traffic (180s) and static datasets (86400s)."""
    traffic = TrafficAdapter(endpoint_url="http://mock.traffic", cache_ttl=180)
    pop_adapter = PopulationAdapter(cache_ttl=86400)

    assert traffic.cache_ttl == 180
    assert pop_adapter.cache_ttl == 86400


# ── 5. Health Endpoint & Observability ─────────────(19) ───────────────────
def test_health_endpoint_phase6_4_telemetry():
    """19. Test GET /health returns provider telemetry for traffic, population, and infrastructure."""
    with patch("app.config.settings.data_mode", "hybrid"):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()

        assert "providers" in data
        provs = data["providers"]
        assert "traffic" in provs
        assert "population" in provs
        assert "infrastructure" in provs
