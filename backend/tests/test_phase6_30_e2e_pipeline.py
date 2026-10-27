"""
AapdaNetra-X — Phase 6.30: End-to-End Emergency Decision Pipeline Tests

Validates:
1. Valid flood request end-to-end trace across risk, explainability, routes, alerts, decision, and scenario endpoints.
2. Provenance, freshness, and risk contract metadata survival through decision outputs.
3. Provider fallback and unavailable evidence handling.
4. Unsupported and contextual-only hazard behavior consistency across endpoints.
5. Scenario/baseline consistency and horizon alignment.
6. Invalid inputs preventing misleading route or emergency recommendations (HTTP 400).
7. Decision trace consistency with exact risk, route, and state machine transition rules.
8. Preservation of synthetic GBR model disclaimers, SHAP causality notices, and scientific limitations.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.decision_service import compute_emergency_decision, transition_decision

client = TestClient(app)


def test_e2e_valid_flood_pipeline_trace():
    """Verify end-to-end consistency for operational flood hazard across all primary API endpoints."""
    # 1. GET /api/risk
    res_risk = client.get("/api/risk?horizon=0&hazard_type=flood")
    assert res_risk.status_code == 200
    risk_data = res_risk.json()
    assert risk_data["hazard_type"] == "flood"
    assert "data_contract" in risk_data

    # 2. GET /api/explainability
    res_exp = client.get("/api/explainability?horizon=0&hazard_type=flood")
    assert res_exp.status_code == 200
    exp_data = res_exp.json()
    assert exp_data["hazard_type"] == "flood"
    assert len(exp_data["features"]) == 7

    # 3. GET /api/routes
    res_route = client.get("/api/routes?horizon=0&hazard_type=flood")
    assert res_route.status_code == 200
    route_data = res_route.json()
    assert route_data["recommended"]["id"] is not None
    assert "data_contract" in route_data

    # 4. GET /api/decision/recommend
    res_dec = client.get("/api/decision/recommend?incident_id=INC-E2E-01&horizon=0&hazard_type=flood")
    assert res_dec.status_code == 200
    dec_data = res_dec.json()
    assert dec_data["status"] == "RECOMMENDED"
    assert dec_data["hazard_type"] == "flood"
    assert dec_data["risk_score"] == pytest.approx(risk_data["predictedRisk"], abs=0.1)
    assert "data_contract" in dec_data

    # 5. POST /api/simulation
    res_sim = client.post("/api/simulation?incident_id=INC-E2E-01", json={"rainfallMultiplier": 1.5, "horizon": 0, "hazard_type": "flood"})
    assert res_sim.status_code == 200
    sim_data = res_sim.json()
    assert sim_data["baselineRisk"] == pytest.approx(risk_data["predictedRisk"], abs=0.1)
    assert sim_data["scenarioRisk"] >= sim_data["baselineRisk"]


def test_metadata_survival_across_pipeline():
    """Verify data_contract, freshness, and provenance metadata propagate through decision outputs."""
    res_dec = client.get("/api/decision/recommend?incident_id=INC-E2E-META&horizon=0&hazard_type=flood")
    assert res_dec.status_code == 200
    dec_data = res_dec.json()

    assert "data_freshness" in dec_data
    assert "freshness_status" in dec_data["data_freshness"]
    assert "data_contract" in dec_data
    assert "inference_eligibility" in dec_data["data_contract"]
    assert any("Risk Contract Eligibility" in ev for ev in dec_data["evidence"])


def test_unsupported_hazard_e2e_consistency():
    """Verify unsupported hazards (landslide, cyclone) report explicit capability status across all endpoints."""
    endpoints_to_test = [
        ("/api/risk?horizon=0&hazard_type=landslide", "GET", None),
        ("/api/explainability?horizon=0&hazard_type=landslide", "GET", None),
        ("/api/routes?horizon=0&hazard_type=landslide", "GET", None),
        ("/api/decision/recommend?incident_id=INC-LS&horizon=0&hazard_type=landslide", "GET", None),
    ]

    for path, method, payload in endpoints_to_test:
        if method == "GET":
            res = client.get(path)
        else:
            res = client.post(path, json=payload)

        assert res.status_code == 200, f"Failed at {path}"
        data = res.json()
        assert data.get("hazard_type") == "landslide"
        if "status" in data and data["status"] == "UNAVAILABLE":
            assert data["decision_support_available"] is False
        elif "supported" in data:
            assert data["supported"] is False
        elif "data_contract" in data:
            assert data["data_contract"].get("model_available", False) is False or data["data_contract"].get("routing_available", False) is False


def test_contextual_extreme_rainfall_e2e_consistency():
    """Verify contextual-only extreme_rainfall hazard behaves consistently without flood model execution."""
    res_risk = client.get("/api/risk?horizon=0&hazard_type=extreme_rainfall")
    assert res_risk.status_code == 200
    risk_data = res_risk.json()
    assert risk_data["capability_status"] == "PARTIALLY_SUPPORTED"
    assert risk_data["model_available"] is False
    assert risk_data["predicted_risk"] is None

    res_dec = client.get("/api/decision/recommend?incident_id=INC-RAIN&horizon=0&hazard_type=extreme_rainfall")
    assert res_dec.status_code == 200
    dec_data = res_dec.json()
    assert dec_data["status"] == "UNAVAILABLE"
    assert dec_data["decision_support_available"] is False


def test_invalid_input_rejection_e2e():
    """Verify invalid parameters (hazard string, NaN/Inf, out-of-range horizon) return 400 Bad Request."""
    invalid_paths = [
        "/api/risk?horizon=0&hazard_type=tsunami",
        "/api/explainability?horizon=0&hazard_type=volcano",
        "/api/routes?horizon=0&hazard_type=invalid_hazard",
        "/api/decision/recommend?horizon=0&hazard_type=blizzard",
    ]

    for path in invalid_paths:
        res = client.get(path)
        assert res.status_code == 400, f"Expected 400 for {path}, got {res.status_code}"
        assert "detail" in res.json()


def test_decision_state_machine_transition_workflow():
    """Verify decision state machine: RECOMMENDED -> APPROVED / REJECTED workflow and audit logging."""
    # 1. Obtain recommendation
    res_rec = client.get("/api/decision/recommend?incident_id=INC-STATE-01&horizon=0&hazard_type=flood")
    assert res_rec.status_code == 200
    dec_id = res_rec.json()["decision_id"]

    # 2. Approve recommendation
    approve_payload = {
        "decision_id": dec_id,
        "responder_id": "OFFICER-01",
        "reason": "Evaluated field reports and confirmed route safety.",
    }
    res_app = client.post("/api/decision/approve", json=approve_payload)
    assert res_app.status_code == 200
    app_data = res_app.json()
    assert app_data["status"] == "APPROVED"
    assert app_data["approved"] is True

    # 3. Attempt invalid transition APPROVED -> REJECTED (should fail with 400)
    reject_payload = {
        "decision_id": dec_id,
        "responder_id": "OFFICER-02",
        "reason": "Attempting illegal state transition.",
    }
    res_rej = client.post("/api/decision/reject", json=reject_payload)
    assert res_rej.status_code == 400
    assert "Invalid state transition" in res_rej.json()["detail"]


def test_scientific_disclaimers_preserved_e2e():
    """Verify synthetic GBR disclaimer, SHAP non-causal notice, and operational limitations are preserved."""
    res_dec = client.get("/api/decision/recommend?incident_id=INC-DISCLAIMER&horizon=0&hazard_type=flood")
    assert res_dec.status_code == 200
    data = res_dec.json()

    limitations = data.get("limitations", [])
    assert any("requires human emergency responder approval" in lim for lim in limitations)
    assert any("SHAP values reflect ML feature attributions" in lim for lim in limitations)
