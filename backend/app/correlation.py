"""AapdaNetra-X — Correlation & Request ID Context

Provides context-local storage and header management for request correlation IDs.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional
import uuid

_request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def generate_request_id() -> str:
    """Generate a lightweight unique request identifier."""
    return f"req_{uuid.uuid4().hex[:8]}"


def get_request_id() -> Optional[str]:
    """Retrieve the current request ID from context."""
    return _request_id_ctx.get()


def set_request_id(request_id: str) -> None:
    """Set the request ID for the current context."""
    _request_id_ctx.set(request_id)


def clear_request_id() -> None:
    """Clear the request ID for the current context."""
    _request_id_ctx.set(None)
