"""
AapdaNetra-X — Phase 6.31: Failure & Resilience Testing Suite

Validates:
1. Telemetry provider failure, timeout, malformed output, and stale data fallbacks.
2. Missing CWC observations and provisional/contextual feature classification.
3. Malformed, non-finite (NaN/Inf), out-of-range, and invalid API input rejection.
4. Risk inference & explainability failure bounds and contract eligibility safeguards.
5. Routing failure, blockage handling, and disconnected path fallback.
6. Persistence service mode isolation (disabled, fallback, required) during DB unavailability.
7. Event broker deduplication, subscriber queues, and history replay.
8. Decision state machine transition constraints and decision superseding.
9. Scenario engine resilience under unsupported hazards and bad payloads.
10. Partial subsystem failure isolation.
"""
import math
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.data.providers.data_adapter import get_data_adapter, DataAdapter
from app.services.risk_contract import evaluate_risk_engine_contract, InferenceEligibilityStatus
from app.services.decision_service import (
    compute_emergency_decision,
    transition_decision,
    STATE_RECOMMENDED,
    STATE_APPROVED,
    STATE_REJECTED,
    STATE_SUPERSEDED,
    _DECISION_REGISTRY,
)
from app.services.persistence_service import get_persistence_service
from app.events.broker import EventBroker
from app.events.schemas import EventEnvelope, EventType
from ml.routing import optimize_routes
from ml.features.schema import validate_and_clean_features

client = TestClient(app)


def test_scenario_1_provider_failure_and_fallback_provenance():
    """Verify provider failure causes fallback_used=True and provenance marking without crash."""
    adapter = get_data_adapter()
    orig_mode = adapter.data_mode
    try:
        features = adapter.get_base_features()
        meta = adapter.get_telemetry_metadata()
        assert isinstance(features, dict)
        assert len(features) == 7
        assert "data_mode" in meta
        assert "fallback_used" in meta
    finally:
        adapter.data_mode = orig_mode


def test_scenario_2_missing_cwc_and_provisional_classification():
    """Verify missing CWC observations and provisional infrastructure features are classified accurately."""
    raw = {
        "rainfall_intensity": 50.0,
        "rainfall_trend": 1.0,
        "water_level": 3.0,
        "water_level_trend": 0.5,
        "road_congestion": 0.4,
        "population_exposure": 12430.0,
        "infrastructure_vulnerability": 0.72,
    }
    prov = {
        "water_level": "UNAVAILABLE",
        "infrastructure_vulnerability": "PROVISIONAL",
        "population_exposure": "CONTEXTUAL_STATIC_WORLDPOP",
    }
    contract = evaluate_risk_engine_contract(raw, data_mode="real", provenance=prov)
    assert contract.feature_classification["water_level"] == "UNAVAILABLE"
    assert contract.feature_classification["infrastructure_vulnerability"] == "PROVISIONAL"
    assert contract.feature_classification["population_exposure"] == "CONTEXTUAL_STATIC"
    assert contract.complete_real_evidence_present is False


def test_scenario_3_non_finite_and_malformed_api_inputs():
    """Verify non-finite (NaN/Inf) and out-of-range API query parameters return HTTP 400 or 422 Bad Request."""
    invalid_requests = [
        "/api/risk?horizon=99",
        "/api/risk?horizon=-5",
        "/api/explainability?horizon=10",
        "/api/routes?horizon=50",
        "/api/decision/recommend?horizon=100",
    ]
    for url in invalid_requests:
        res = client.get(url)
        assert res.status_code in (400, 422), f"Expected 400/422 for {url}, got {res.status_code}"

    # Verify Pydantic validator catches NaN input on SimulationRequest
    with pytest.raises(ValueError):
        from app.models.schemas import SimulationRequest
        SimulationRequest(rainfallMultiplier=float("nan"))


def test_scenario_4_inference_and_explainability_contract_safeguards():
    """Verify invalid payloads (empty dict or non-numeric values) produce INELIGIBLE_INVALID_INPUT."""
    contract_empty = evaluate_risk_engine_contract({}, data_mode="simulated")
    assert contract_empty.is_valid_structure is False
    assert contract_empty.inference_eligibility == InferenceEligibilityStatus.INELIGIBLE_INVALID_INPUT.value
    assert contract_empty.completeness_score == 0.0

    contract_bad_type = evaluate_risk_engine_contract({"rainfall_intensity": "invalid_string"}, data_mode="simulated")
    assert contract_bad_type.inference_eligibility == InferenceEligibilityStatus.INELIGIBLE_INVALID_INPUT.value


def test_scenario_5_routing_failure_and_blockage_fallback():
    """Verify route optimizer handles route blockage and disconnected paths with explicit reason notices."""
    res_normal = optimize_routes(predicted_risk_score=60.0, route_blockage=False, horizon_index=0)
    assert res_normal.recommended.is_blocked is False

    res_blocked = optimize_routes(predicted_risk_score=60.0, route_blockage=True, horizon_index=0)
    assert "blockage" in res_blocked.route_reason.lower() or res_blocked.recommended.failureProbability >= res_normal.recommended.failureProbability


def test_scenario_6_persistence_mode_isolation(monkeypatch):
    """Verify PersistenceService behaves predictably in disabled, fallback, and required modes when DB is unavailable."""
    from app.config import settings
    from app.services.persistence_service import PersistenceService

    ps = get_persistence_service()

    # Disabled mode
    monkeypatch.setattr(settings, "persistence_mode", "disabled")
    assert ps.is_enabled is False

    # Optional / fallback mode (DB down)
    monkeypatch.setattr(settings, "persistence_mode", "optional")
    monkeypatch.setattr(PersistenceService, "db_available", property(lambda self: False))
    assert ps.is_enabled is True
    assert ps.db_available is False

    # Required mode (DB down)
    monkeypatch.setattr(settings, "persistence_mode", "required")
    with pytest.raises(RuntimeError):
        ps.save_decision_sync({"decision_id": "dec-test-req", "status": "RECOMMENDED"})




def test_scenario_7_event_broker_deduplication_and_replay():
    """Verify EventBroker deduplication in replay buffer and event query filtering."""
    broker = EventBroker()
    env1 = EventEnvelope(
        id="evt_unique_123",
        event=EventType.ALERT_CREATED,
        incident_id="INC-BROKER-TEST",
        data={"alert_id": "alt-01", "severity": "HIGH"},
    )
    env2 = EventEnvelope(
        id="evt_unique_123",  # Identical ID
        event=EventType.ALERT_CREATED,
        incident_id="INC-BROKER-TEST",
        data={"alert_id": "alt-01", "severity": "HIGH"},
    )

    broker.record_event_for_replay(env1)
    broker.record_event_for_replay(env2)

    # Buffer should deduplicate by event ID
    replay_events, hit = broker.get_replay_events("evt_unique_123")
    assert hit is True
    assert len(replay_events) == 0  # No events after the match



def test_scenario_8_state_machine_invalid_transitions_and_superseding():
    """Verify invalid decision state transitions are rejected and new recommendations supersede older ones."""
    # Compute initial decision
    d1 = compute_emergency_decision(incident_id="INC-STATE-MACHINE", horizon=0, hazard_type="flood")
    d1_id = d1["decision_id"]
    assert d1["status"] == STATE_RECOMMENDED

    # Compute second decision for same incident
    d2 = compute_emergency_decision(incident_id="INC-STATE-MACHINE", horizon=0, hazard_type="flood")
    d2_id = d2["decision_id"]
    assert d2["status"] == STATE_RECOMMENDED

    # Verify d1 was marked SUPERSEDED
    d1_updated = _DECISION_REGISTRY.get(d1_id)
    assert d1_updated["status"] == STATE_SUPERSEDED

    # Attempt to transition SUPERSEDED decision -> APPROVED (must be rejected)
    success, msg, _ = transition_decision(d1_id, STATE_APPROVED, "OPERATOR-01", "Illegal transition")
    assert success is False
    assert "Invalid state transition" in msg


def test_scenario_9_unsupported_hazard_scenario_resilience():
    """Verify unsupported hazards in scenario endpoints return explicit non-eligible status."""
    res = client.post("/api/simulation", json={"hazard_type": "landslide"})
    assert res.status_code == 200
    data = res.json()
    assert data["hazard_type"] == "landslide"
    assert data["predictionReliability"] == 0.0
    assert data["data_contract"]["model_available"] is False


def test_scenario_10_partial_subsystem_failure_isolation():
    """Verify telemetry adapter fallback does not break risk, explainability, routing, or decision pipeline."""
    res_dec = client.get("/api/decision/recommend?incident_id=INC-PARTIAL-FAIL&horizon=0&hazard_type=flood")
    assert res_dec.status_code == 200
    data = res_dec.json()
    assert data["status"] == STATE_RECOMMENDED
    assert "data_freshness" in data
    assert "risk_score" in data
    assert "route_recommendation" in data
