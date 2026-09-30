"""AapdaNetra-X — Real-Time Events API Router

Provides GET /api/events/stream SSE endpoint broadcasting live domain events.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Request, Query, Header
from starlette.responses import StreamingResponse

from app.events.broker import get_event_broker
from app.events.schemas import EventEnvelope

logger = logging.getLogger("aapdanetra.events.router")

router = APIRouter()


async def sse_event_generator(
    request: Request,
    last_event_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Async generator yielding Server-Sent Events with Last-Event-ID replay and periodic ping heartbeat."""
    broker = get_event_broker()

    # Determine effective Last-Event-ID (header takes precedence over query param)
    header_last_id = request.headers.get("Last-Event-ID") or request.headers.get("last-event-id")
    effective_last_id = last_event_id or header_last_id

    # Subscribe first to ensure no live events are missed during transition
    queue = broker.subscribe()

    # Initial connection acknowledgment comment
    yield ": connected\n\n"

    replayed_ids: set[str] = set()

    # Replay missed events if Last-Event-ID is provided
    if effective_last_id:
        replay_events, is_hit = broker.get_replay_events(effective_last_id)
        if is_hit:
            logger.info("SSE client reconnected with Last-Event-ID '%s'. Replaying %d event(s).", effective_last_id, len(replay_events))
            for r_evt in replay_events:
                replayed_ids.add(r_evt.id)
                yield r_evt.to_sse_format()
        else:
            logger.warning("SSE client requested Last-Event-ID '%s' outside replay window.", effective_last_id)
            yield f": replay_missed {effective_last_id}\n\n"

    try:
        while True:
            # Check for client disconnect
            if await request.is_disconnected():
                break

            try:
                # Wait up to 15 seconds for a domain event
                event: EventEnvelope = await asyncio.wait_for(
                    queue.get(), timeout=15.0
                )
                # Avoid yielding an event already replayed during initial connection
                if event.id in replayed_ids:
                    continue

                yield event.to_sse_format()
            except asyncio.TimeoutError:
                # Send periodic heartbeat to keep connection alive
                yield ": ping\n\n"

    except asyncio.CancelledError:
        logger.debug("SSE connection stream cancelled by client")
    finally:
        broker.unsubscribe(queue)


@router.get("/events/stream", response_class=StreamingResponse)
async def stream_events(
    request: Request,
    last_event_id: Optional[str] = Query(None, alias="last_event_id"),
    last_event_id_header: Optional[str] = Header(None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Real-time Server-Sent Events (SSE) stream endpoint supporting Last-Event-ID replay."""
    effective_id = last_event_id_header or last_event_id
    if effective_id:
        gen = sse_event_generator(request, last_event_id=effective_id)
    else:
        gen = sse_event_generator(request)

    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
