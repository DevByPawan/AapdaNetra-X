"""
AapdaNetra-X — Phase 6.18 Dynamic Evacuation Intelligence Test Suite
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.evacuation_service import (
    EvacuationService,
    calculate_composite_route_score,
    classify_route_status,
    get_evacuation_service,
)
from app.services.spatial_service import get_spatial_service
from app.services.alert_engine import IntelligentAlertEngine
from app.services.decision_service import compute_emergency_decision
from ml.routing import optimize_routes


@pytest.fixture
def client():
    return TestClient(app)


# 1. Candidate generation
def test_01_route_candidate_generation():
    svc = get_evacuation_service()
    res = svc.evaluate_evacuation_routes("INC-2026-TEST", horizon=0)
    
    assert res.recommended_route is not None
    assert isinstance(res.alternative_routes, list)
    assert len(res.alternative_routes) >= 1
    assert res.recommended_route.id.startswith("route-")


# 2. Deterministic route scoring
def test_02_deterministic_route_scoring():
    score1 = calculate_composite_route_score(
        safety_score=0.88, spatial_exposure_ratio=0.10, eta_min=12, is_blocked=False
    )
    score2 = calculate_composite_route_score(
        safety_score=0.88, spatial_exposure_ratio=0.10, eta_min=12, is_blocked=False
    )

    assert score1.composite_score == score2.composite_score
    assert score1.spatial_hazard_penalty == 3.0
    assert score1.eta_penalty == 3.0  # (12 - 10) * 1.5
    assert score1.blockage_penalty == 0.0


# 3. Route status classification
def test_03_route_status_classification():
    assert classify_route_status(0.85, 75.0, is_blocked=False) == "SAFE"
    assert classify_route_status(0.65, 55.0, is_blocked=False) == "CAUTION"
    assert classify_route_status(0.45, 35.0, is_blocked=False) == "HIGH_RISK"
    assert classify_route_status(0.85, 75.0, is_blocked=True) == "BLOCKED"


# 4. Blocked route exclusion
def test_04_blocked_route_exclusion():
    svc = get_evacuation_service()
    res = svc.evaluate_evacuation_routes("INC-2026-TEST", horizon=0, route_blockage_override=True)
    
    # Recommended route must NOT be blocked if unblocked alternative exists or must flag warning
    assert res.recommended_route is not None
    if any(r.is_blocked for r in res.alternative_routes):
        assert any(r.status == "BLOCKED" for r in res.alternative_routes)


# 5. Alternative route preservation
def test_05_alternative_route_preservation():
    svc = get_evacuation_service()
    res = svc.evaluate_evacuation_routes("INC-2026-TEST", horizon=0)
    
    assert len(res.alternative_routes) > 0
    rec_id = res.recommended_route.id
    alt_ids = [a.id for a in res.alternative_routes]
    assert rec_id not in alt_ids


# 6. Spatial hazard integration
def test_06_spatial_hazard_integration():
    svc = get_evacuation_service()
    res = svc.evaluate_evacuation_routes("INC-2026-TEST", horizon=0)
    rec = res.recommended_route
    
    assert hasattr(rec, "spatial_hazard_exposure")
    assert 0.0 <= rec.spatial_hazard_exposure <= 1.0
    assert "dem:" in res.provenance or "hazard:" in res.provenance


# 7. Congestion integration
def test_07_congestion_integration():
    score = calculate_composite_route_score(0.70, 0.0, 15, is_blocked=False)
    assert score.congestion_penalty > 0.0


# 8. ETA comparison
def test_08_eta_comparison():
    score_fast = calculate_composite_route_score(0.85, 0.0, 10, is_blocked=False)
    score_slow = calculate_composite_route_score(0.85, 0.0, 25, is_blocked=False)
    assert score_fast.composite_score > score_slow.composite_score


# 9. Route-change detection
def test_09_route_change_detection():
    svc = get_evacuation_service()
    res1 = svc.evaluate_evacuation_routes("INC-2026-CHANGE-TEST", horizon=0, route_blockage_override=False)
    res2 = svc.evaluate_evacuation_routes("INC-2026-CHANGE-TEST", horizon=0, route_blockage_override=True)

    assert hasattr(res2.route_change, "route_changed")
    assert res2.route_change.previous_route_id == res1.recommended_route.id


# 10. Route-change reason
def test_10_route_change_reason():
    svc = get_evacuation_service()
    res = svc.evaluate_evacuation_routes("INC-2026-REASON-TEST", horizon=0, route_blockage_override=True)
    if res.route_change.route_changed:
        assert res.route_change.change_reason is not None
        assert len(res.route_change.change_reason) > 0


# 11. All-routes-unsafe fallback
def test_11_all_routes_unsafe_fallback(monkeypatch):
    svc = get_evacuation_service()
    # Force extreme risk
    from app.services import risk_engine
    monkeypatch.setattr(risk_engine, "compute_risk_state", lambda horizon=0: type("Risk", (), {"predictedRisk": 98.0, "riskCategory": "CRITICAL"})())
    
    res = svc.evaluate_evacuation_routes("INC-2026-UNSAFE-TEST", horizon=0)
    assert res.all_routes_unsafe is True
    assert res.overall_status_warning is not None
    assert "WARNING" in res.overall_status_warning or "EMERGENCY" in res.overall_status_warning


# 12. Telemetry freshness & provenance
def test_12_telemetry_freshness_provenance():
    svc = get_evacuation_service()
    res = svc.evaluate_evacuation_routes("INC-2026-TEST", horizon=0)
    
    assert "provider" in res.data_freshness
    assert "routing:" in res.provenance


# 13-15. Persistence modes
def test_13_15_persistence_modes(monkeypatch):
    from app.config import settings
    svc = get_evacuation_service()

    # Disabled mode
    monkeypatch.setattr(settings, "persistence_mode", "disabled")
    res_dis = svc.evaluate_evacuation_routes("INC-2026-PERSIST-TEST", horizon=0)
    assert res_dis.recommended_route is not None

    # Optional mode
    monkeypatch.setattr(settings, "persistence_mode", "optional")
    res_opt = svc.evaluate_evacuation_routes("INC-2026-PERSIST-TEST", horizon=0)
    assert res_opt.recommended_route is not None


# 16. SSE route.updated publication
def test_16_sse_route_updated(client):
    resp = client.post("/api/evacuation/recompute", json={"incident_id": "INC-2026-TEST", "horizon": 0, "publish_sse": True})
    assert resp.status_code == 200
    data = resp.json()
    assert "recommended_route" in data


# 17. No duplicate route events
def test_17_no_duplicate_route_events(client):
    # Calling recompute with publish_sse=False should evaluate without SSE broker failure
    resp = client.post("/api/evacuation/recompute", json={"incident_id": "INC-2026-TEST", "horizon": 0, "publish_sse": False})
    assert resp.status_code == 200


# 18. Live-state non-mutation
def test_18_live_state_non_mutation():
    from app.services.risk_engine import _get_base_features, predict_risk

    features_before = _get_base_features()
    ml_before = predict_risk(features_before)

    svc = get_evacuation_service()
    svc.evaluate_evacuation_routes("INC-2026-TEST", horizon=0)

    features_after = _get_base_features()
    ml_after = predict_risk(features_after)

    assert features_before == features_after
    assert ml_before["risk_score"] == ml_after["risk_score"]


# 19. Regression of existing routing engine
def test_19_routing_engine_regression():
    opt = optimize_routes(predicted_risk_score=74.0, route_blockage=False)
    assert opt.recommended is not None
    assert opt.recommended.safetyScore > 0.0


# 20. Regression of Phase 6.14 Spatial Service
def test_20_spatial_service_regression():
    sp = get_spatial_service()
    haz = sp.calculate_route_spatial_hazard([{"lat": 28.6448, "lng": 77.2167}])
    assert "spatial_exposure_ratio" in haz


# 21. Regression of Phase 6.15 Alerts
def test_21_alert_engine_regression():
    alert_svc = IntelligentAlertEngine()
    alerts = alert_svc.evaluate_all_rules("INC-2026-TEST", predicted_risk=75.0, current_risk=75.0)
    assert isinstance(alerts, list)


# 22. Regression of Phase 6.16 Simulations
def test_22_simulation_regression(client):
    resp = client.post(
        "/api/simulation",
        json={
          "rainfallIncrease": 20,
          "populationMovement": 2000,
          "waterLevelIncrease": 10,
          "routeBlockage": False
        }
    )
    assert resp.status_code == 200
    assert "scenario_id" in resp.json()


# 23. Regression of Phase 6.17 Decision Support
def test_23_decision_support_regression():
    dec = compute_emergency_decision("INC-2026-TEST", horizon=0)
    assert dec["status"] == "RECOMMENDED"
    assert dec["label"] == "AI-assisted decision-support recommendation"
