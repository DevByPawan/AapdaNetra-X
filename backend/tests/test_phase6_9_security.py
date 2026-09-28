"""AapdaNetra-X — Phase 6.9 API Security & Backend Hardening Unit Suite

Tests CORS policies, HTTP security headers, Pydantic input validation bounds,
NaN/Infinity rejection, malformed pagination/path parameter handling, and sanitized error responses.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ── TEST 1: CORS ALLOWED ORIGIN & PREFLIGHT ──────────────────────────────────

def test_01_cors_allowed_origin():
    """Verify CORS middleware permits configured origins and credentials."""
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    }
    response = client.options("/api/risk", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


# ── TEST 2: CORS DISALLOWED ORIGIN ───────────────────────────────────────────

def test_02_cors_disallowed_origin():
    """Verify CORS middleware rejects unauthorized origins."""
    headers = {
        "Origin": "http://malicious-disaster-site.com",
        "Access-Control-Request-Method": "GET",
    }
    response = client.options("/api/risk", headers=headers)
    # Disallowed origin should not be reflected in Access-Control-Allow-Origin
    assert response.headers.get("access-control-allow-origin") != "http://malicious-disaster-site.com"


# ── TEST 3: HTTP SECURITY HEADERS ───────────────────────────────────────────

def test_03_http_security_headers():
    """Verify response headers contain nosniff, DENY frame options, and referrer policy."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"
    assert "X-Request-ID" in response.headers


# ── TEST 4: SIMULATION INPUT BOUNDS & NAN / INFINITY REJECTION ───────────────

def test_04_simulation_input_bounds_and_nan_rejection():
    """Verify SimulationRequest rejects out-of-bounds parameters, NaN, and Infinity."""
    # A. Out of bounds evacuationPace (max 5.0)
    res_pace = client.post("/api/simulation", json={"evacuationPace": 10.0})
    assert res_pace.status_code == 422

    # B. Negative rainfallMultiplier (min 0.0)
    res_rain = client.post("/api/simulation", json={"rainfallMultiplier": -1.0})
    assert res_rain.status_code == 422

    # C. Excessive drainageEfficiency (max 1.0)
    res_drain = client.post("/api/simulation", json={"drainageEfficiency": 1.5})
    assert res_drain.status_code == 422

    # D. Valid simulation input
    res_valid = client.post("/api/simulation", json={
        "evacuationPace": 1.5,
        "rainfallMultiplier": 2.0,
        "drainageEfficiency": 0.8,
        "routeBlockage": False,
        "rainfallIncrease": 10.0,
        "populationMovement": 50,
        "waterLevelIncrease": 0.5,
    })
    assert res_valid.status_code == 200
    assert "newRisk" in res_valid.json()


# ── TEST 5: RESPONSE APPROVAL STRING CONSTRAINTS ────────────────────────────

def test_05_approve_request_string_constraints():
    """Verify ApproveRequest validates string length limits."""
    # Empty incidentId
    res_empty = client.post("/api/response/approve", json={"incidentId": ""})
    assert res_empty.status_code == 422

    # Oversized incidentId (> 64 chars)
    res_oversized = client.post("/api/response/approve", json={"incidentId": "A" * 100})
    assert res_oversized.status_code == 422

    # Valid approval
    res_ok = client.post("/api/response/approve", json={"incidentId": "INC-2026-DELHI-01", "responderId": "RESP-01"})
    assert res_ok.status_code == 200
    assert res_ok.json()["approved"] is True


# ── TEST 6: MALFORMED PAGINATION PARAMETERS ─────────────────────────────────

def test_06_malformed_pagination_parameters():
    """Verify pagination query parameters reject invalid limits and inverted time ranges."""
    # Limit 0 (min 1)
    res_zero = client.get("/api/incidents?limit=0")
    assert res_zero.status_code == 422

    # Limit 500 (max 100)
    res_large = client.get("/api/incidents?limit=500")
    assert res_large.status_code == 422

    # Inverted time range (from_time > to_time)
    res_inverted = client.get(
        "/api/incidents?from_time=2026-09-27T10:00:00Z&to_time=2026-09-27T08:00:00Z"
    )
    assert res_inverted.status_code == 422


# ── TEST 7: MALFORMED PATH PARAMETER HANDLING ────────────────────────────────

def test_07_malformed_path_parameter_handling():
    """Verify non-UUID prediction_id in path produces a controlled 404 without internal server error."""
    res = client.get("/api/risk/not-a-valid-uuid-string/explanation")
    assert res.status_code == 404
    assert res.json()["detail"] == "Prediction 'not-a-valid-uuid-string' explanation not found"


# ── TEST 8: ERROR RESPONSE SANITIZATION ─────────────────────────────────────

def test_08_error_response_sanitization():
    """Verify HTTP error responses never expose filesystem paths, passwords, or stack traces."""
    res = client.get("/api/incidents?from_time=invalid_timestamp")
    assert res.status_code == 422
    text = res.text
    assert "/Users/" not in text
    assert "postgresql://" not in text
    assert "password=" not in text
    assert "Traceback" not in text
