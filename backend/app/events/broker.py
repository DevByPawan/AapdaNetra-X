"""AapdaNetra-X — In-Process & Distributed Event Broker

Manages real-time pub/sub subscriptions for Server-Sent Events (SSE).
Supports local SSE queues and cross-worker event propagation via PostgreSQL NOTIFY and broker registry.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import deque
from typing import Optional, Set, Any, List, Tuple

from fastapi import HTTPException

from app.events.schemas import EventEnvelope, EventType

logger = logging.getLogger("aapdanetra.events")

QUEUE_MAX_SIZE = 100
MAX_REPLAY_BUFFER_SIZE = 500
MAX_SUBSCRIBERS = 200

_REGISTERED_BROKERS: Set[EventBroker] = set()


class EventBroker:
    """In-process and cross-worker event broker for real-time SSE streaming."""

    def __init__(self) -> None:
        self.broker_id: str = f"broker-{uuid.uuid4().hex[:8]}"
        self._subscribers: Set[asyncio.Queue[EventEnvelope]] = set()
        self._replay_buffer: deque[EventEnvelope] = deque(maxlen=MAX_REPLAY_BUFFER_SIZE)
        self._total_published: int = 0
        self._total_dropped: int = 0
        self._total_subscribed: int = 0
        self._total_unsubscribed: int = 0
        self._listener_task: Optional[asyncio.Task] = None
        self._stop_listener_event: Optional[asyncio.Event] = None
        _REGISTERED_BROKERS.add(self)

    @property
    def subscriber_count(self) -> int:
        """Number of currently active SSE subscriber connections."""
        return len(self._subscribers)

    def get_stats(self) -> dict:
        """Return operational metrics snapshot for monitoring."""
        return {
            "broker_id": self.broker_id,
            "active_subscribers": len(self._subscribers),
            "replay_buffer_size": len(self._replay_buffer),
            "total_published": self._total_published,
            "total_dropped": self._total_dropped,
            "total_subscribed": self._total_subscribed,
            "total_unsubscribed": self._total_unsubscribed,
            "listener_active": self._listener_task is not None and not self._listener_task.done(),
        }

    def record_event_for_replay(self, event: EventEnvelope) -> None:
        """Store an event envelope into the bounded ring buffer for SSE Last-Event-ID replay."""
        if any(e.id == event.id for e in self._replay_buffer):
            return
        self._replay_buffer.append(event)

    def get_replay_events(self, last_event_id: str) -> Tuple[List[EventEnvelope], bool]:
        """Fetch missed events occurring after last_event_id from the replay buffer.

        Returns (list_of_missed_events, is_hit_boolean).
        If last_event_id is found, returns (events_after_id, True).
        If last_event_id is not found in buffer, returns ([], False).
        """
        buffer_snapshot = list(self._replay_buffer)
        match_idx = None
        for idx, evt in enumerate(buffer_snapshot):
            if evt.id == last_event_id:
                match_idx = idx
                break

        if match_idx is not None:
            return buffer_snapshot[match_idx + 1:], True

        return [], False

    def subscribe(self) -> asyncio.Queue[EventEnvelope]:
        """Register a new client subscriber queue with bounded maxsize."""
        if len(self._subscribers) >= MAX_SUBSCRIBERS:
            logger.warning("[EventBroker] Capacity exceeded (%d/%d max subscribers)", len(self._subscribers), MAX_SUBSCRIBERS)
            raise HTTPException(
                status_code=503,
                detail=f"Maximum SSE subscriber capacity ({MAX_SUBSCRIBERS}) reached."
            )

        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self._subscribers.add(queue)
        self._total_subscribed += 1
        logger.debug(
            "New SSE client subscribed to %s. Total active subscribers: %d",
            self.broker_id,
            len(self._subscribers),
        )
        return queue

    def unsubscribe(self, queue: asyncio.Queue[EventEnvelope]) -> None:
        """Unregister a client subscriber queue on disconnect."""
        if queue in self._subscribers:
            self._subscribers.discard(queue)
            self._total_unsubscribed += 1
            logger.debug(
                "SSE client unsubscribed from %s. Total active subscribers: %d",
                self.broker_id,
                len(self._subscribers),
            )

    def publish_local(self, event: EventEnvelope) -> None:
        """Publish an event envelope to local active subscribers on this broker instance."""
        self.record_event_for_replay(event)

        if not self._subscribers:
            return

        self._total_published += 1

        for queue in list(self._subscribers):
            try:
                if queue.full():
                    try:
                        dropped = queue.get_nowait()
                        self._total_dropped += 1
                        logger.warning(
                            "Subscriber queue full on %s (maxsize=%d). Dropped oldest event %s (%s)",
                            self.broker_id,
                            QUEUE_MAX_SIZE,
                            dropped.id,
                            dropped.event,
                        )
                    except asyncio.QueueEmpty:
                        pass
                queue.put_nowait(event)
            except Exception as exc:
                logger.error("Error publishing event to local subscriber queue: %s", exc)

        logger.info(
            "Event %s (%s) published to %d local subscriber(s) on %s",
            event.id,
            event.event.value if isinstance(event.event, EventType) else event.event,
            len(self._subscribers),
            self.broker_id,
        )

    def publish(self, event: EventEnvelope) -> None:
        """Publish an event envelope to local subscribers and broadcast across workers."""
        # 1. Local delivery on this broker instance
        self.publish_local(event)

        # 2. In-memory cross-broker propagation (for multi-instance/test worker simulation)
        for other_broker in list(_REGISTERED_BROKERS):
            if other_broker is not self:
                try:
                    other_broker.publish_local(event)
                except Exception as b_err:
                    logger.debug("Cross-broker local fan-out error: %s", b_err)

        # 3. PostgreSQL NOTIFY for distributed multi-process workers
        self._notify_postgres(event)

    def _notify_postgres(self, event: EventEnvelope) -> None:
        try:
            from app.services.persistence_service import get_persistence_service, run_async_in_sync
            ps = get_persistence_service()
            if not ps.is_enabled or not ps.db_available:
                return

            payload_dict = {
                "sender_id": self.broker_id,
                "envelope": event.model_dump(),
            }
            payload_str = json.dumps(payload_dict)
            if len(payload_str) > 7900:
                logger.warning("Event payload exceeds PostgreSQL NOTIFY max limit (7900 bytes), skipping NOTIFY.")
                return

            async def _send_notify(session: Any):
                from sqlalchemy import text
                await session.execute(
                    text("SELECT pg_notify('aapdanetra_events', :payload)"),
                    {"payload": payload_str},
                )
                await session.commit()

            run_async_in_sync(_send_notify)
        except Exception as n_err:
            logger.debug("PostgreSQL NOTIFY dispatch note: %s", n_err)

    async def start_listener(self) -> None:
        """Start background PostgreSQL LISTEN task for cross-worker event propagation."""
        if self._listener_task is not None and not self._listener_task.done():
            return

        self._stop_listener_event = asyncio.Event()
        self._listener_task = asyncio.create_task(self._listen_loop())
        logger.info("[EventBroker] Started PostgreSQL LISTEN task on %s", self.broker_id)

    async def stop_listener(self) -> None:
        """Stop background PostgreSQL LISTEN task cleanly."""
        if self._stop_listener_event:
            self._stop_listener_event.set()
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except (asyncio.CancelledError, Exception):
                pass
            self._listener_task = None
        logger.info("[EventBroker] Stopped PostgreSQL LISTEN task on %s", self.broker_id)

    async def _listen_loop(self) -> None:
        """Background loop maintaining dedicated LISTEN connection to PostgreSQL aapdanetra_events channel."""
        from app.db.session import get_db_manager
        from app.services.persistence_service import get_persistence_service

        retry_delay = 1.0
        max_retry_delay = 30.0

        while self._stop_listener_event and not self._stop_listener_event.is_set():
            ps = get_persistence_service()
            if not ps.is_enabled or not ps.db_available:
                await asyncio.sleep(2.0)
                continue

            db_mgr = get_db_manager()
            if not db_mgr.is_available or not db_mgr.engine:
                await asyncio.sleep(2.0)
                continue

            conn = None
            asyncpg_conn = None
            try:
                conn = await db_mgr.engine.connect()
                raw_conn = await conn.get_raw_connection()
                asyncpg_conn = getattr(raw_conn, "driver_connection", raw_conn)

                def _on_notification(connection: Any, pid: int, channel: str, payload_str: str) -> None:
                    try:
                        data = json.loads(payload_str)
                        sender_id = data.get("sender_id")
                        envelope_dict = data.get("envelope")

                        # Deduplicate: Ignore self-emitted notifications
                        if sender_id == self.broker_id:
                            return

                        if not envelope_dict or not isinstance(envelope_dict, dict):
                            logger.warning("[EventBroker] Malformed event envelope in PostgreSQL NOTIFY payload")
                            return

                        # Safely reconstruct Pydantic EventEnvelope
                        event = EventEnvelope(**envelope_dict)
                        # Publish ONLY to local subscribers of this worker (do NOT call self.publish to avoid recursion)
                        self.publish_local(event)
                    except Exception as p_err:
                        logger.warning("[EventBroker] Failed to parse PostgreSQL NOTIFY payload: %s", p_err)

                if hasattr(asyncpg_conn, "add_listener"):
                    await asyncpg_conn.add_listener("aapdanetra_events", _on_notification)
                    logger.info("[EventBroker] Connected to PostgreSQL LISTEN aapdanetra_events on %s", self.broker_id)
                    retry_delay = 1.0  # Reset backoff on successful connection

                    while self._stop_listener_event and not self._stop_listener_event.is_set():
                        await asyncio.sleep(1.0)

                    try:
                        if hasattr(asyncpg_conn, "remove_listener"):
                            await asyncpg_conn.remove_listener("aapdanetra_events", _on_notification)
                    except Exception:
                        pass
                else:
                    logger.warning("[EventBroker] Underlying connection driver does not support add_listener")
                    await asyncio.sleep(10.0)

            except asyncio.CancelledError:
                if asyncpg_conn and hasattr(asyncpg_conn, "remove_listener"):
                    try:
                        await asyncpg_conn.remove_listener("aapdanetra_events", _on_notification)
                    except Exception:
                        pass
                raise
            except Exception as listen_err:
                logger.warning("[EventBroker] LISTEN connection error: %s. Retrying in %.1fs...", listen_err, retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2.0, max_retry_delay)
            finally:
                if conn:
                    try:
                        await conn.close()
                    except Exception:
                        pass


_event_broker: Optional[EventBroker] = None


def get_event_broker() -> EventBroker:
    """Return module-level singleton instance of EventBroker."""
    global _event_broker
    if _event_broker is None:
        _event_broker = EventBroker()
    return _event_broker
