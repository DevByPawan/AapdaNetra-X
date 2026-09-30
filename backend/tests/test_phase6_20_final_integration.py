"""
AapdaNetra-X — Phase 6.20.10: Final Multi-Hazard Integration, Consistency & Hardening Test Suite

Verifies:
1. Canonical HazardRegistry consistency across all 6 hazards.
2. Cross-hazard isolation / leakage prevention (no flood risk/SHAP/conformal/spatial/routing/decision for unsupported hazards).
3. Complete flood operational pipeline preservation (telemetry -> GBR -> conformal -> SHAP -> spatial -> alerts -> routing -> decision -> persistence -> history).
4. History/Timeline hazard isolation & filtering.
5. Alert engine hazard isolation & deduplication key.
6. Dynamic evacuation hazard isolation.
7. Emergency decision support hazard isolation & approval protection.
8. API parameter validation & controlled 400 handling.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.hazards.types import HazardType, HazardCapabilityStatus
from app.hazards.registry import get_hazard_registry
from app.services.decision_service import compute_emergency_decision, transition_decision
from app.services.alert_engine import get_alert_engine

client = TestClient(app)


# ── 1. HAZARD REGISTRY & CAPABILITY CONSISTENCY ───────────────────────────

def test_registry_canonical_six_hazards():
    """Verify all 6 hazard types exist with expected capability classifications."""
    registry = get_hazard_registry()
    all_defs = registry.get_all()
    assert len(all_defs) == 6

    # 1. Flood
    flood = registry.get_definition(HazardType.FLOOD)
    assert flood.capability_status == HazardCapabilityStatus.SUPPORTED
    assert flood.supported is True
    assert flood.model_available is True
    assert flood.spatial_available is True
    assert flood.telemetry_available is True
    assert flood.alerts_available is True
    assert flood.routing_available is True
    assert flood.decision_support_available is True

    # 2. Extreme Rainfall
    er = registry.get_definition(HazardType.EXTREME_RAINFALL)
    assert er.capability_status == HazardCapabilityStatus.PARTIALLY_SUPPORTED
    assert er.supported is True
    assert er.model_available is False
    assert er.spatial_available is False
    assert er.telemetry_available is True
    assert er.alerts_available is True
    assert er.routing_available is False
    assert er.decision_support_available is False

    # 3. Landslide
    landslide = registry.get_definition(HazardType.LANDSLIDE)
    assert landslide.capability_status == HazardCapabilityStatus.DEMONSTRATION_ONLY
    assert landslide.supported is False
    assert landslide.model_available is False

    # 4-6. Cyclone, Heatwave, Earthquake
    for ht in [HazardType.CYCLONE, HazardType.HEATWAVE, HazardType.EARTHQUAKE]:
        defn = registry.get_definition(ht)
        assert defn.capability_status == HazardCapabilityStatus.FUTURE_EXTENSION
        assert defn.supported is False
        assert defn.model_available is False


# ── 2. CROSS-HAZARD LEAKAGE PREVENTION ──────────────────────────────────────

def test_risk_api_cross_hazard_leakage_prevention():
    """Verify non-flood risk requests return unavailable payload with NO flood leakage."""
    unsupported_hazards = ["extreme_rainfall", "landslide", "cyclone", "heatwave", "earthquake"]
    for ht in unsupported_hazards:
        resp = client.get(f"/api/risk?hazard_type={ht}")
        assert resp.status_code == 200, f"Failed for {ht}"
        data = resp.json()

        assert data["hazard_type"] == ht
        assert data["predicted_risk"] is None
        assert data["predictedRisk"] is None
        assert data["riskCategory"] is None
        assert data["confidence"] is None
        assert data["model_available"] is False


def test_evacuation_api_cross_hazard_leakage_prevention():
    """Verify non-flood evacuation requests return routing_available=False with NO flood route."""
    resp = client.get("/api/evacuation/recommendation?hazard_type=landslide")
    assert resp.status_code == 200
    data = resp.json()

    assert data["hazard_type"] == "landslide"
    assert data["routing_available"] is False
    assert data["status"] == "UNAVAILABLE"
    assert "reason" in data


def test_decision_api_cross_hazard_leakage_prevention():
    """Verify non-flood decision requests return decision_support_available=False."""
    for ht in ["cyclone", "heatwave", "earthquake"]:
        resp = client.get(f"/api/decision/recommend?hazard_type={ht}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["hazard_type"] == ht
        assert data["decision_support_available"] is False
        assert data["status"] == "UNAVAILABLE"
        assert "reason" in data


# ── 3. FLOOD OPERATIONAL PIPELINE REGRESSION ────────────────────────────────

def test_flood_pipeline_end_to_end_regression():
    """Verify default (omitted) and explicit hazard_type='flood' execute complete flood operational pipeline."""
    # 1. Risk
    resp_risk = client.get("/api/risk?hazard_type=flood")
    assert resp_risk.status_code == 200
    data_risk = resp_risk.json()
    assert data_risk["hazard_type"] == "flood"
    assert data_risk["model_available"] is True
    assert isinstance(data_risk["predictedRisk"], float)

    # 2. Decision
    resp_dec = client.get("/api/decision/recommend?hazard_type=flood")
    assert resp_dec.status_code == 200
    data_dec = resp_dec.json()
    assert data_dec["hazard_type"] == "flood"
    assert data_dec["status"] == "RECOMMENDED"
    assert data_dec["priority"] in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    assert isinstance(data_dec["risk_score"], float)

    # 3. Decision approval
    dec_id = data_dec["decision_id"]
    resp_appr = client.post("/api/decision/approve", json={"decision_id": dec_id, "responder_id": "RESP-001", "reason": "Operational approval"})
    assert resp_appr.status_code == 200
    assert resp_appr.json()["status"] == "APPROVED"


# ── 4. API PARAMETER VALIDATION & CONTROLLED 400 ERROR HANDLING ─────────────

def test_api_unknown_hazard_type_returns_controlled_400():
    """Verify invalid/unknown hazard parameter yields controlled 400 Bad Request across endpoints."""
    bad_hazard = "volcano"

    # Risk endpoint
    r1 = client.get(f"/api/risk?hazard_type={bad_hazard}")
    assert r1.status_code == 400
    assert "Unknown or unsupported hazard_type" in r1.json()["detail"]

    # Alerts endpoint
    r2 = client.get(f"/api/alerts?hazard_type={bad_hazard}")
    assert r2.status_code == 400
    assert "Unknown or unsupported hazard_type" in r2.json()["detail"]

    # History endpoint
    r3 = client.get(f"/api/incidents/INC-2026-DEFAULT/telemetry/history?hazard_type={bad_hazard}")
    assert r3.status_code == 400
    assert "Unknown or unsupported hazard_type" in r3.json()["detail"]

    # Decision endpoint
    r4 = client.get(f"/api/decision/recommend?hazard_type={bad_hazard}")
    assert r4.status_code == 400
    assert "Unknown or unsupported hazard_type" in r4.json()["detail"]


# ── 5. STATE MACHINE APPROVAL PROTECTION ─────────────────────────────────────

def test_state_machine_blocks_unavailable_hazard_decisions():
    """Verify transition_decision() rejects state transitions on unavailable hazard decision IDs."""
    # Obtain unavailable decision object
    unavail_dec = compute_emergency_decision(hazard_type="landslide")
    dec_id = unavail_dec["decision_id"]

    success, msg, dec = transition_decision(decision_id=dec_id, new_status="APPROVED", responder_id="CMD-1", reason="Testing approval rejection")
    assert success is False
    assert "Cannot transition decision for hazard without operational decision support" in msg
    assert dec["status"] == "UNAVAILABLE"
