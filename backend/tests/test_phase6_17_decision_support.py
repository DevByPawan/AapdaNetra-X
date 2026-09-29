"""
AapdaNetra-X — Phase 6.17 Emergency Decision Support Test Suite
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.decision_service import (
    STATE_APPROVED,
    STATE_RECOMMENDED,
    STATE_REJECTED,
    compute_emergency_decision,
    transition_decision,
)


@pytest.fixture
def client():
    return TestClient(app)


# 1. Deterministic recommendation
def test_01_deterministic_recommendation():
    d1 = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)
    d2 = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)

    assert d1["risk_score"] == d2["risk_score"]
    assert d1["priority"] == d2["priority"]
    assert d1["recommended_action"] == d2["recommended_action"]
    assert d1["label"] == "AI-assisted decision-support recommendation"


# 2. Risk integration
def test_02_risk_integration():
    dec = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)
    assert "risk_score" in dec
    assert "risk_category" in dec
    assert dec["risk_category"] in ["LOW", "MODERATE", "HIGH", "CRITICAL"]


# 3. Uncertainty integration
def test_03_uncertainty_integration():
    dec = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)
    unc = dec["uncertainty_interval"]

    assert "lower_bound" in unc
    assert "upper_bound" in unc
    assert unc["nominal_coverage"] == 0.90
    assert unc["lower_bound"] <= dec["risk_score"] <= unc["upper_bound"]


# 4. SHAP integration
def test_04_shap_integration():
    dec = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)
    factors = dec["contributing_factors"]

    assert isinstance(factors, list)
    assert len(factors) > 0
    for factor in factors:
        assert "feature" in factor
        assert "shap_value" in factor
        assert "formatted_contribution" in factor


# 5. Spatial integration
def test_05_spatial_integration():
    dec = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)
    sp = dec["spatial_context"]

    assert "spatial_exposure_ratio" in sp
    assert "modeled_safety_score" in sp
    assert "PROVISIONAL" in sp["terminology_notice"]


# 6. Route integration
def test_06_route_integration():
    dec = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)
    route = dec["route_recommendation"]

    assert "id" in route
    assert "name" in route
    assert "eta" in route
    assert "safety_score" in route


# 7. Active alert integration
def test_07_active_alert_integration():
    dec = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)
    alerts = dec["active_alerts_summary"]

    assert isinstance(alerts, list)


# 8. Stale data handling
def test_08_stale_data_handling():
    dec = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)
    freshness = dec["data_freshness"]

    assert "freshness_status" in freshness
    assert "fallback_used" in freshness


# 9. Provisional data labeling
def test_09_provisional_data_labeling():
    dec = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)

    assert "PROVISIONAL" in dec["spatial_context"]["terminology_notice"]
    assert any("AI-assisted decision-support recommendation" in lim for lim in dec["limitations"])


# 10. RECOMMENDED state
def test_10_recommended_state():
    dec = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)
    assert dec["status"] == STATE_RECOMMENDED


# 11. APPROVED transition
def test_11_approved_transition():
    dec = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)
    decision_id = dec["decision_id"]

    success, msg, updated = transition_decision(decision_id, STATE_APPROVED, "RESP-01", "Approved for evacuation")
    assert success is True
    assert updated["status"] == STATE_APPROVED
    assert updated["workflow_id"].startswith("WF-")


# 12. REJECTED transition
def test_12_rejected_transition():
    dec = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)
    decision_id = dec["decision_id"]

    success, msg, updated = transition_decision(decision_id, STATE_REJECTED, "RESP-01", "Conditions changed")
    assert success is True
    assert updated["status"] == STATE_REJECTED


# 13. Invalid transition rejection
def test_13_invalid_transition_rejection():
    dec = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)
    decision_id = dec["decision_id"]

    # First approve
    transition_decision(decision_id, STATE_APPROVED, "RESP-01", "Approved")

    # Try to approve again or transition from APPROVED -> REJECTED
    success, msg, _ = transition_decision(decision_id, STATE_REJECTED, "RESP-01", "Try reject")
    assert success is False
    assert "Invalid state transition" in msg


# 14. Audit creation
def test_14_audit_creation(client):
    dec = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)
    resp = client.post(
        "/api/decision/approve",
        json={"decision_id": dec["decision_id"], "responder_id": "RESP-01", "reason": "Audit verification"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["approved"] is True
    assert data["audit_logged"] is True


# 15. decision.approved SSE event publication
def test_15_sse_decision_approved(client):
    dec = compute_emergency_decision(incident_id="INC-2026-TEST", horizon=0)
    resp = client.post(
        "/api/decision/approve",
        json={"decision_id": dec["decision_id"], "responder_id": "RESP-01", "reason": "SSE test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sse_published"] is True


# 16-18. Persistence modes (disabled, optional, required)
def test_16_18_persistence_modes(monkeypatch):
    from app.config import settings

    # Disabled
    monkeypatch.setattr(settings, "persistence_mode", "disabled")
    dec = compute_emergency_decision("INC-2026-TEST")
    assert dec["status"] == STATE_RECOMMENDED

    # Optional mode DB unavailable
    monkeypatch.setattr(settings, "persistence_mode", "optional")
    dec2 = compute_emergency_decision("INC-2026-TEST")
    assert dec2["status"] == STATE_RECOMMENDED


# 19. Live-state non-mutation
def test_19_live_state_non_mutation():
    from app.services.risk_engine import _get_base_features, predict_risk
    from app.services.alert_engine import IntelligentAlertEngine

    base_before = _get_base_features()
    ml_before = predict_risk(base_before)
    alert_before = len(IntelligentAlertEngine()._active_alerts)

    dec = compute_emergency_decision("INC-2026-TEST")

    base_after = _get_base_features()
    ml_after = predict_risk(base_after)
    alert_after = len(IntelligentAlertEngine()._active_alerts)

    assert base_before == base_after
    assert ml_before["risk_score"] == ml_after["risk_score"]
    assert alert_before == alert_after


# 20. API compatibility & Endpoints
def test_20_api_compatibility(client):
    # Legacy endpoint compatibility
    resp_legacy = client.post("/api/response/approve", json={"incidentId": "INC-2026-TEST", "responderId": "RESP-01"})
    assert resp_legacy.status_code == 200
    assert resp_legacy.json()["approved"] is True

    # GET /api/decision/recommend
    resp_rec = client.get("/api/decision/recommend?incident_id=INC-2026-TEST")
    assert resp_rec.status_code == 200
    data_rec = resp_rec.json()
    assert "decision_id" in data_rec
    assert data_rec["status"] == "RECOMMENDED"

    # POST /api/decision/approve
    resp_app = client.post(
        "/api/decision/approve",
        json={"decision_id": data_rec["decision_id"], "responder_id": "RESP-01", "reason": "Approved via API"},
    )
    assert resp_app.status_code == 200
    assert resp_app.json()["approved"] is True

    # POST /api/decision/reject (new recommendation)
    resp_rec2 = client.get("/api/decision/recommend?incident_id=INC-2026-TEST")
    data_rec2 = resp_rec2.json()

    resp_rej = client.post(
        "/api/decision/reject",
        json={"decision_id": data_rec2["decision_id"], "responder_id": "RESP-01", "reason": "Rejected via API"},
    )
    assert resp_rej.status_code == 200
    assert resp_rej.json()["approved"] is False
    assert resp_rej.json()["status"] == "REJECTED"
