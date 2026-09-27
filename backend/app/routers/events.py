"""AapdaNetra-X — Real-Time Events API Router

Provides GET /api/events/stream SSE endpoint broadcasting live domain events.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from starlette.responses import StreamingResponse

from app.events.broker import get_event_broker
from app.events.schemas import EventEnvelope

logger = logging.getLogger("aapdanetra.events.router")

router = APIRouter()


async def sse_event_generator(request: Request) -> AsyncGenerator[str, None]:
    """Async generator yielding Server-Sent Events with periodic ping heartbeat."""
    broker = get_event_broker()
    queue = broker.subscribe()

    # Initial connection acknowledgment comment
    yield ": connected\n\n"

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
                yield event.to_sse_format()
            except asyncio.TimeoutError:
                # Send periodic heartbeat to keep connection alive
                yield ": ping\n\n"

    except asyncio.CancelledError:
        logger.debug("SSE connection stream cancelled by client")
    finally:
        broker.unsubscribe(queue)


@router.get("/events/stream", response_class=StreamingResponse)
async def stream_events(request: Request) -> StreamingResponse:
    """Real-time Server-Sent Events (SSE) stream endpoint."""
    return StreamingResponse(
        sse_event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
