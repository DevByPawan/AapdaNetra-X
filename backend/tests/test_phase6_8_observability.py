"""AapdaNetra-X — Phase 6.8 Observability & Operational Monitoring Unit Suite

Tests request correlation IDs, SSE broker metrics, health observability metadata,
sanitized logging, and post-commit event boundaries.
"""

import asyncio
from datetime import datetime, timezone
import uuid
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.correlation import get_request_id, set_request_id, generate_request_id, clear_request_id
from app.events.broker import EventBroker, get_event_broker
from app.events.schemas import EventEnvelope, EventType
from app.db.session import _sanitize_db_error, DatabaseManager
from app.main import app


# ── TEST 1: REQUEST ID & CORRELATION MIDDLEWARE ────────────────────────────

def test_01_request_id_correlation_middleware():
    """Verify X-Request-ID header generation and custom header propagation in HTTP responses."""
    client = TestClient(app)

    # A. Automatic request ID generation
    res1 = client.get("/health")
    assert res1.status_code == 200
    assert "X-Request-ID" in res1.headers
    req_id_1 = res1.headers["X-Request-ID"]
    assert req_id_1.startswith("req_")

    # B. Custom request ID propagation
    custom_id = "req_custom_test_999"
    res2 = client.get("/health", headers={"X-Request-ID": custom_id})
    assert res2.status_code == 200
    assert res2.headers.get("X-Request-ID") == custom_id


# ── TEST 2: SSE BROKER OPERATIONAL METRICS ─────────────────────────────────

@pytest.mark.anyio
async def test_02_sse_broker_operational_metrics():
    """Verify EventBroker tracks subscriber counts, published events, overflow drops, and unsubscribe stats."""
    broker = EventBroker()

    # Initial stats
    stats0 = broker.get_stats()
    assert stats0["active_subscribers"] == 0
    assert stats0["total_published"] == 0
    assert stats0["total_dropped"] == 0

    # Subscribe client
    q1 = broker.subscribe()
    assert broker.subscriber_count == 1
    stats1 = broker.get_stats()
    assert stats1["active_subscribers"] == 1
    assert stats1["total_subscribed"] == 1

    # Publish normal event
    env1 = EventEnvelope(
        event=EventType.TELEMETRY_UPDATED,
        incident_id="INC-OBS-1",
        data={"level": 5.0},
    )
    broker.publish(env1)
    stats2 = broker.get_stats()
    assert stats2["total_published"] == 1

    # Overflow queue test (fill bounded queue of size 100)
    for i in range(105):
        env = EventEnvelope(
            event=EventType.RISK_UPDATED,
            incident_id=f"INC-OVR-{i}",
            data={"i": i},
        )
        broker.publish(env)

    stats3 = broker.get_stats()
    assert stats3["total_dropped"] > 0

    # Unsubscribe client
    broker.unsubscribe(q1)
    stats4 = broker.get_stats()
    assert stats4["active_subscribers"] == 0
    assert stats4["total_unsubscribed"] == 1


# ── TEST 3: HEALTH ENDPOINT OBSERVABILITY SCHEMA ───────────────────────────

def test_03_health_endpoint_observability_schema():
    """Verify /health returns structured metadata for persistence, database, postgis, and SSE without leaking secrets."""
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()

    # Core system properties
    assert "status" in data
    assert "version" in data
    assert "data_mode" in data
    assert "timestamp" in data

    # Persistence & DB health
    assert "persistence" in data
    p = data["persistence"]
    assert "mode" in p
    assert "configured" in p
    assert "available" in p
    assert "database" in p
    assert "postgis" in p

    # SSE Broker stats
    assert "sse" in data
    s = data["sse"]
    assert "active_subscribers" in s
    assert "total_published" in s
    assert "total_dropped" in s

    # Ensure no secret URI or password leak
    raw_text = res.text
    assert "postgres://" not in raw_text
    assert "password=" not in raw_text


# ── TEST 4: ERROR SANITIZATION HELPER ──────────────────────────────────────

def test_04_error_sanitization_helper():
    """Verify _sanitize_db_error strips credentials and raw passwords."""
    raw_err = "failed to connect postgresql+asyncpg://admin:super_secret_pw@10.0.0.1:5432/production password=secret123"
    sanitized = _sanitize_db_error(raw_err)

    assert "super_secret_pw" not in sanitized
    assert "secret123" not in sanitized
    assert "postgresql://" in sanitized
    assert "password=***" in sanitized
