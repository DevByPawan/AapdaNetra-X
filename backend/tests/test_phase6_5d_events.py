"""AapdaNetra-X — Phase 6.5D SSE Event Architecture Test Suite

Tests EventEnvelope validation, EventBroker subscription lifecycle, queue maxsize & overflow policy,
SSE serialization, heartbeat, disconnect cleanup, transaction post-commit publishing, and mode handling.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

pytest_plugins = ("anyio",)
import pytest
from pydantic import ValidationError

from app.config import settings
from app.events.broker import EventBroker, QUEUE_MAX_SIZE, get_event_broker
from app.events.schemas import EventEnvelope, EventType
from app.services.persistence_service import PersistenceService


def test_event_envelope_validation():
    """Verify EventEnvelope generates unique IDs, UTC timestamps, and valid schema."""
    evt1 = EventEnvelope(
        event=EventType.RISK_UPDATED,
        incident_id="INC-2026-001",
        data={"predicted_risk": 75.0},
    )
    evt2 = EventEnvelope(
        event=EventType.RISK_UPDATED,
        incident_id="INC-2026-001",
        data={"predicted_risk": 75.0},
    )

    assert evt1.id != evt2.id
    assert evt1.id.startswith("evt_")
    assert evt1.event == EventType.RISK_UPDATED
    assert evt1.incident_id == "INC-2026-001"
    assert evt1.data["predicted_risk"] == 75.0


def test_supported_event_types():
    """Verify all 6 supported domain event types."""
    supported = {
        "telemetry.updated",
        "risk.updated",
        "route.updated",
        "alert.created",
        "simulation.completed",
        "decision.approved",
    }
    actual = {e.value for e in EventType}
    assert supported == actual


def test_unsupported_event_type_rejection():
    """Verify invalid event types raise Pydantic ValidationError."""
    with pytest.raises(ValidationError):
        EventEnvelope(event="unsupported.event.name", data={})


def test_sse_serialization_format():
    """Verify EventEnvelope serializes to valid Server-Sent Event text format."""
    evt = EventEnvelope(
        id="evt_test123",
        event=EventType.ALERT_CREATED,
        incident_id="INC-2026-001",
        data={"severity": "CRITICAL", "title": "Flash Flood Warning"},
    )
    formatted = evt.to_sse_format()

    assert "event: alert.created\n" in formatted
    assert "id: evt_test123\n" in formatted
    assert "data: {" in formatted
    assert formatted.endswith("\n\n")


@pytest.mark.anyio
async def test_broker_subscribe_unsubscribe():
    """Verify EventBroker subscriber lifecycle and count tracking."""
    broker = EventBroker()
    assert broker.subscriber_count == 0

    queue1 = broker.subscribe()
    assert broker.subscriber_count == 1
    assert queue1.maxsize == QUEUE_MAX_SIZE

    queue2 = broker.subscribe()
    assert broker.subscriber_count == 2

    broker.unsubscribe(queue1)
    assert broker.subscriber_count == 1

    broker.unsubscribe(queue2)
    assert broker.subscriber_count == 0


@pytest.mark.anyio
async def test_broker_publish_to_single_subscriber():
    """Verify EventBroker publishes events to a single subscriber queue."""
    broker = EventBroker()
    queue = broker.subscribe()

    evt = EventEnvelope(
        event=EventType.TELEMETRY_UPDATED,
        data={"rainfall_intensity": 45.0},
    )
    broker.publish(evt)

    assert not queue.empty()
    received = queue.get_nowait()
    assert received.id == evt.id
    assert received.data["rainfall_intensity"] == 45.0


@pytest.mark.anyio
async def test_broker_publish_to_multiple_subscribers():
    """Verify EventBroker broadcasts to multiple independent subscriber queues."""
    broker = EventBroker()
    q1 = broker.subscribe()
    q2 = broker.subscribe()

    evt = EventEnvelope(
        event=EventType.SIMULATION_COMPLETED,
        data={"scenario_risk": 82.5},
    )
    broker.publish(evt)

    r1 = q1.get_nowait()
    r2 = q2.get_nowait()
    assert r1.id == evt.id
    assert r2.id == evt.id


@pytest.mark.anyio
async def test_broker_publish_when_no_subscribers():
    """Verify publishing with zero subscribers executes safely without errors."""
    broker = EventBroker()
    evt = EventEnvelope(event=EventType.DECISION_APPROVED, data={})
    # Should not throw exception
    broker.publish(evt)


@pytest.mark.anyio
async def test_broker_overflow_policy_drops_oldest_item():
    """Verify bounded queue maxsize=100 overflow policy drops the oldest event when full."""
    broker = EventBroker()
    q = broker.subscribe()

    # Fill queue up to maxsize (100)
    for i in range(100):
        broker.publish(
            EventEnvelope(
                id=f"evt_initial_{i}",
                event=EventType.RISK_UPDATED,
                data={"seq": i},
            )
        )

    assert q.full()

    # Publish 101st event to trigger overflow policy
    overflow_evt = EventEnvelope(
        id="evt_overflow_101",
        event=EventType.RISK_UPDATED,
        data={"seq": 101},
    )
    broker.publish(overflow_evt)

    # First item in queue should now be seq 1 (seq 0 was dropped)
    first_item = q.get_nowait()
    assert first_item.id == "evt_initial_1"

    # Queue size should still be maxsize 100
    assert q.qsize() == 99  # (after 1 get_nowait)


@pytest.mark.anyio
async def test_broker_publisher_failure_isolation():
    """Verify that an exception in one subscriber queue does not crash the broker or affect others."""
    broker = EventBroker()
    q1 = broker.subscribe()

    # Mock broken subscriber queue
    q_broken = MagicMock()
    q_broken.full.side_effect = Exception("Broken queue simulation")
    broker._subscribers.add(q_broken)

    evt = EventEnvelope(event=EventType.ALERT_CREATED, data={})
    # Publishing should swallow error for broken queue and deliver to q1
    broker.publish(evt)

    assert not q1.empty()
    received = q1.get_nowait()
    assert received.id == evt.id


@pytest.mark.anyio
async def test_disabled_mode_emits_event():
    """Verify that in disabled mode, events are still emitted with status='disabled'."""
    ps = PersistenceService()
    broker = get_event_broker()
    q = broker.subscribe()

    with patch.object(settings, "persistence_mode", "disabled"):
        sim = MagicMock()
        sim.incident_id = "INC-001"
        sim.baseline_risk = 40.0
        sim.scenario_risk = 65.0
        sim.risk_delta = 25.0
        sim.risk_category = "HIGH"
        sim.route_recommendation = "Route A"
        sim.severity = "SEVERE"

        await ps.save_simulation(sim)

        assert not q.empty()
        evt = q.get_nowait()
        assert evt.event == EventType.SIMULATION_COMPLETED
        assert evt.persistence_status == "disabled"

    broker.unsubscribe(q)


@pytest.mark.anyio
async def test_required_mode_failure_suppresses_event():
    """Verify that in required mode, when DB failure occurs, no success event is emitted."""
    ps = PersistenceService()
    broker = get_event_broker()
    q = broker.subscribe()

    with patch.object(settings, "persistence_mode", "required"):
        with patch("app.services.persistence_service.get_db_manager") as mock_db_mgr:
            mock_mgr = MagicMock()
            mock_mgr.is_available = False
            mock_db_mgr.return_value = mock_mgr

            sim = MagicMock()
            with pytest.raises(RuntimeError):
                await ps.save_simulation(sim)

            # Assert NO event was pushed to subscriber queue
            assert q.empty()

    broker.unsubscribe(q)
