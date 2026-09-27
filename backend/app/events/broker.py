"""AapdaNetra-X — In-Process Async Event Broker

Manages real-time pub/sub subscriptions for Server-Sent Events (SSE).
Uses bounded asyncio queues per client with a deterministic oldest-event drop policy.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Set

from app.events.schemas import EventEnvelope, EventType

logger = logging.getLogger("aapdanetra.events")

QUEUE_MAX_SIZE = 100


class EventBroker:
    """In-process asyncio event broker for real-time SSE streaming."""

    def __init__(self) -> None:
        self._subscribers: Set[asyncio.Queue[EventEnvelope]] = set()

    @property
    def subscriber_count(self) -> int:
        """Number of currently active SSE subscriber connections."""
        return len(self._subscribers)

    def subscribe(self) -> asyncio.Queue[EventEnvelope]:
        """Register a new client subscriber queue with bounded maxsize."""
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self._subscribers.add(queue)
        logger.debug(
            "New SSE client subscribed. Total active subscribers: %d",
            len(self._subscribers),
        )
        return queue

    def unsubscribe(self, queue: asyncio.Queue[EventEnvelope]) -> None:
        """Unregister a client subscriber queue on disconnect."""
        self._subscribers.discard(queue)
        logger.debug(
            "SSE client unsubscribed. Total active subscribers: %d",
            len(self._subscribers),
        )

    def publish(self, event: EventEnvelope) -> None:
        """Publish an event envelope to all active subscribers with isolation and queue overflow protection."""
        if not self._subscribers:
            return

        # Snapshot subscribers to prevent mutation issues during iteration
        for queue in list(self._subscribers):
            try:
                if queue.full():
                    # Overflow Policy: drop the oldest event to prevent memory bloat and unblock pipeline
                    try:
                        dropped = queue.get_nowait()
                        logger.warning(
                            "Subscriber queue full (maxsize=%d). Dropped oldest event %s (%s)",
                            QUEUE_MAX_SIZE,
                            dropped.id,
                            dropped.event,
                        )
                    except asyncio.QueueEmpty:
                        pass
                queue.put_nowait(event)
            except Exception as exc:
                logger.error("Error publishing event to subscriber queue: %s", exc)

        logger.info(
            "Event %s (%s) published to %d subscriber(s)",
            event.id,
            event.event.value if isinstance(event.event, EventType) else event.event,
            len(self._subscribers),
        )


_event_broker: Optional[EventBroker] = None


def get_event_broker() -> EventBroker:
    """Return module-level singleton instance of EventBroker."""
    global _event_broker
    if _event_broker is None:
        _event_broker = EventBroker()
    return _event_broker
