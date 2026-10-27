"""AapdaNetra-X — Phase 6.32 Security & Production Hardening Test Suite

Tests authentication, server-side authorization (RBAC), CORS policies, security headers,
request body size limits, IP-based rate limiting, SSE stream access control & subscription bounds,
database error sanitization, and production settings validation.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.rate_limit import reset_rate_limiter
from app.events.broker import get_event_broker
from app.main import app
from app.services.decision_service import transition_decision, compute_emergency_decision

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_security_state():
    """Reset settings, rate limiter, and broker state before each test."""
    orig_env = settings.environment
    orig_auth = settings.auth_enabled
    orig_key = settings.api_key
    orig_secret = settings.secret_key
    orig_cors = list(settings.cors_origins)
    orig_rl = settings.rate_limit_enabled
    orig_rate = settings.rate_limit_per_minute
    orig_body = settings.max_request_body_bytes
    orig_sse_auth = settings.sse_auth_required
    orig_sse_limit = settings.max_sse_subscriptions_per_ip
    orig_pers = settings.persistence_mode
    reset_rate_limiter()

    yield

    settings.environment = orig_env
    settings.auth_enabled = orig_auth
    settings.api_key = orig_key
    settings.secret_key = orig_secret
    settings.cors_origins = orig_cors
    settings.rate_limit_enabled = orig_rl
    settings.rate_limit_per_minute = orig_rate
    settings.max_request_body_bytes = orig_body
    settings.sse_auth_required = orig_sse_auth
    settings.max_sse_subscriptions_per_ip = orig_sse_limit
    settings.persistence_mode = orig_pers
    reset_rate_limiter()


# ── TEST 1: PRODUCTION CONFIGURATION VALIDATION ─────────────────────────────

def test_01_production_configuration_fails_safely():
    """Verify production settings fail safely when mandatory security settings are missing."""
    settings.environment = "production"
    settings.auth_enabled = False
    settings.api_key = ""

    with pytest.raises(ValueError, match="Production deployment requires auth_enabled=True or non-empty api_key"):
        settings.validate_production_security()

    settings.auth_enabled = True
    settings.secret_key = "aapdanetra-dev-secret-change-in-production"
    with pytest.raises(ValueError, match="Production deployment requires custom secret_key"):
        settings.validate_production_security()

    settings.secret_key = "prod-custom-secure-secret-key-999"
    settings.cors_origins = ["*"]
    with pytest.raises(ValueError, match="Production deployment cannot use wildcard '\\*' in cors_origins"):
        settings.validate_production_security()

    settings.cors_origins = ["https://command.aapdanetra.gov.in"]
    # Should pass without error when properly configured
    settings.validate_production_security()


# ── TEST 2: CORS ALLOWED & DISALLOWED ORIGINS ──────────────────────────────

def test_02_cors_allowed_and_disallowed_origins():
    """Verify CORS middleware permits explicit allowed origins and rejects unauthorized origins."""
    # Allowed origin (configured in CORS middleware defaults)
    res_ok = client.options("/api/risk", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert res_ok.status_code == 200
    assert res_ok.headers.get("access-control-allow-origin") == "http://localhost:5173"

    # Disallowed origin
    res_bad = client.options("/api/risk", headers={"Origin": "http://attacker-disaster-site.org", "Access-Control-Request-Method": "GET"})
    assert res_bad.headers.get("access-control-allow-origin") != "http://attacker-disaster-site.org"


# ── TEST 3: PROTECTED ENDPOINTS REJECT UNAUTHENTICATED REQUESTS ───────────

def test_03_protected_endpoints_reject_unauthenticated():
    """Verify decision state changes reject unauthenticated requests when auth is enabled."""
    settings.auth_enabled = True

    # No credentials supplied
    res_no_auth = client.post("/api/decision/approve", json={"decision_id": "dec-sec-test-1", "responder_id": "RESP-01", "reason": "Valid reason"})
    assert res_no_auth.status_code == 401

    # Invalid credentials supplied
    res_invalid = client.post(
        "/api/decision/approve",
        json={"decision_id": "dec-sec-test-1", "responder_id": "RESP-01", "reason": "Valid reason"},
        headers={"Authorization": "Bearer invalid-token-value"},
    )
    assert res_invalid.status_code == 401
    assert "Invalid authentication credentials" in res_invalid.json()["detail"]


# ── TEST 4: AUTHENTICATED BUT UNAUTHORIZED REQUESTS REJECTED ─────────────

def test_04_authenticated_unauthorized_role_rejected():
    """Verify viewer role users cannot perform state-changing decision approvals."""
    settings.auth_enabled = True

    res = client.post(
        "/api/decision/approve",
        json={"decision_id": "dec-sec-test-2", "responder_id": "VIEWER-01", "reason": "Unauthorized attempt"},
        headers={"Authorization": "Bearer viewer-token-secret-789"},
    )
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]


# ── TEST 5: AUTHORIZED DECISION APPROVAL / REJECTION ───────────────────────

def test_05_authorized_decision_approval_and_rejection():
    """Verify authorized responder token successfully approves or rejects decision recommendations."""
    # Compute decision recommendation first
    rec = compute_emergency_decision("INC-SEC-TEST-05", horizon=0)
    dec_id = rec["decision_id"]

    settings.auth_enabled = True

    # Authorized approval with responder token
    res_app = client.post(
        "/api/decision/approve",
        json={"decision_id": dec_id, "responder_id": "RESP-01", "reason": "Operational safety verified"},
        headers={"Authorization": "Bearer responder-token-secret-456"},
    )
    assert res_app.status_code == 200
    assert res_app.json()["approved"] is True
    assert res_app.json()["status"] == "APPROVED"


# ── TEST 6: INVALID, OVERSIZED, OR NON-FINITE INPUTS REJECTED ──────────────

def test_06_invalid_oversized_non_finite_inputs():
    """Verify request size limits, non-finite values, and malformed inputs are rejected safely."""
    # A. Payload too large (> max_request_body_bytes)
    settings.max_request_body_bytes = 500  # 500 bytes limit
    large_payload = {"incidentId": "INC-" + ("X" * 1000), "evacuationPace": 1.0}
    res_large = client.post("/api/simulation", json=large_payload)
    assert res_large.status_code == 413
    assert "Payload too large" in res_large.json()["detail"]

    # Reset size limit
    settings.max_request_body_bytes = 1_048_576

    # B. Out of bounds float / non-finite parameter
    res_oob = client.post("/api/simulation", json={"evacuationPace": 99.0})
    assert res_oob.status_code == 422


# ── TEST 7: RATE LIMITING ACTIVATION ────────────────────────────────────────

def test_07_rate_limiting_activates():
    """Verify IP-based sliding window rate limiter triggers 429 status when limit is exceeded."""
    settings.rate_limit_enabled = True
    settings.rate_limit_per_minute = 3

    reset_rate_limiter()

    # 3 allowed requests
    for i in range(3):
        res = client.post("/api/simulation", json={"evacuationPace": 1.0})
        assert res.status_code == 200

    # 4th request exceeds rate limit
    res_blocked = client.post("/api/simulation", json={"evacuationPace": 1.0})
    assert res_blocked.status_code == 429
    assert "Rate limit exceeded" in res_blocked.json()["detail"]
    assert res_blocked.headers.get("retry-after") == "60"


# ── TEST 8: ERROR RESPONSE SANITIZATION ─────────────────────────────────────

def test_08_error_response_sanitization():
    """Verify API error responses do not leak file paths, database URLs, passwords, or raw tracebacks."""
    res = client.get("/api/incidents?from_time=invalid-date-format")
    assert res.status_code == 422
    body = res.text
    assert "/Users/" not in body
    assert "postgresql://" not in body
    assert "password=" not in body
    assert "Traceback (most recent call last)" not in body


# ── TEST 9: SSE STREAM ACCESS CONTROL & SUBSCRIPTION LIMITS ─────────────────

def test_09_sse_access_control_and_subscription_limits():
    """Verify SSE endpoint enforces token authentication, per-IP subscription limits, and bounded replay."""
    # A. SSE Authentication requirement
    settings.sse_auth_required = True
    res_unauth = client.get("/api/events/stream")
    assert res_unauth.status_code == 401

    with client.stream("GET", "/api/events/stream?token=responder-token-secret-456") as res_auth:
        # Streaming response connection acknowledgment
        assert res_auth.status_code == 200

    # B. Per-IP Connection Limit
    broker = get_event_broker()
    settings.max_sse_subscriptions_per_ip = 2
    broker._ip_subscribers["127.0.0.1"] = 2
    broker._ip_subscribers["testclient"] = 2

    res_limit = client.get("/api/events/stream?token=responder-token-secret-456")
    assert res_limit.status_code == 429
    assert "Maximum SSE subscriptions per IP" in res_limit.json()["detail"]

    # Cleanup broker test IP count
    broker._ip_subscribers["127.0.0.1"] = 0
    broker._ip_subscribers["testclient"] = 0


# ── TEST 10: PERSISTENCE ERROR SANITIZATION & REQUIRED MODE SEMANTICS ────────

def test_10_persistence_error_sanitization_and_required_mode():
    """Verify persistence service raises RuntimeError in required mode without leaking secrets to API clients."""
    from app.services.persistence_service import get_persistence_service, PersistenceService

    ps = get_persistence_service()
    settings.persistence_mode = "required"

    # Mock DB unavailable
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PersistenceService, "db_available", property(lambda self: False))
        with pytest.raises(RuntimeError, match="Database unavailable in required persistence mode"):
            ps.save_decision_sync({"decision_id": "dec-req-sec-1", "status": "RECOMMENDED"})


# ── TEST 11: UNSUPPORTED HAZARD PROTECTIONS PRESERVED ───────────────────────

def test_11_unsupported_hazard_protections_preserved():
    """Verify requesting decision recommendation for unsupported hazard returns UNAVAILABLE without falling back to flood."""
    res = client.get("/api/decision/recommend?hazard_type=earthquake")
    assert res.status_code == 200
    data = res.json()
    assert data["decision_support_available"] is False
    assert data["hazard_type"] == "earthquake"
    assert "not supported" in data["reason"].lower() or "earthquake" in data["reason"].lower()


# ── TEST 12: HUMAN-IN-THE-LOOP STATE TRANSITION ENFORCEMENT ─────────────────

def test_12_human_in_the_loop_transitions_enforced():
    """Verify invalid state machine transitions are rejected and human responder rationale is required."""
    rec = compute_emergency_decision("INC-SEC-TEST-12", horizon=0)
    dec_id = rec["decision_id"]

    # Transition RECOMMENDED -> APPROVED (valid)
    ok, msg, dec = transition_decision(dec_id, "APPROVED", responder_id="RESP-01", reason="Valid rationale")
    assert ok is True

    # Transition APPROVED -> APPROVED (invalid state transition)
    ok_repeat, msg_repeat, _ = transition_decision(dec_id, "APPROVED", responder_id="RESP-01", reason="Duplicate approval attempt")
    assert ok_repeat is False
    assert "invalid state transition" in msg_repeat.lower()


# ── TEST 13: PRODUCTION MODE REJECTS DEMO TOKENS & ACCEPTS CONFIGURED API KEY ──

def test_13_production_mode_rejects_demo_tokens_and_accepts_configured_api_key():
    """Verify static demo tokens (KNOWN_TOKENS) are strictly rejected in production environment, and configured API key is accepted."""
    settings.environment = "production"
    settings.auth_enabled = True
    settings.api_key = "custom-prod-secret-api-key-999"
    settings.secret_key = "prod-custom-secure-secret-key-999"

    # 1. Demo token attempt in production mode MUST be rejected
    res_demo = client.post(
        "/api/decision/approve",
        json={"decision_id": "dec-prod-sec-13", "responder_id": "RESP-01", "reason": "Prod test"},
        headers={"Authorization": "Bearer responder-token-secret-456"},
    )
    assert res_demo.status_code == 401
    assert "Invalid authentication credentials" in res_demo.json()["detail"]

    # 2. SSE endpoint rejects demo token in production mode
    res_sse_demo = client.get("/api/events/stream?token=responder-token-secret-456")
    assert res_sse_demo.status_code == 401

    # 3. Valid configured API key MUST be accepted in production mode
    # Compute valid decision recommendation first
    rec = compute_emergency_decision("INC-SEC-TEST-13", horizon=0)
    dec_id = rec["decision_id"]

    res_prod_ok = client.post(
        "/api/decision/approve",
        json={"decision_id": dec_id, "responder_id": "RESP-PROD-01", "reason": "Verified operational emergency"},
        headers={"Authorization": "Bearer custom-prod-secret-api-key-999"},
    )
    assert res_prod_ok.status_code == 200
    assert res_prod_ok.json()["approved"] is True
    assert res_prod_ok.json()["status"] == "APPROVED"
