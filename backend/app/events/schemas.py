"""AapdaNetra-X — SSE Event Schemas

Provides typed Pydantic event envelopes for real-time Server-Sent Events (SSE).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
import uuid

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Supported real-time domain event types."""

    TELEMETRY_UPDATED = "telemetry.updated"
    RISK_UPDATED = "risk.updated"
    ROUTE_UPDATED = "route.updated"
    ALERT_CREATED = "alert.created"
    SIMULATION_COMPLETED = "simulation.completed"
    DECISION_APPROVED = "decision.approved"


class EventEnvelope(BaseModel):
    """Standardized event envelope format for SSE streaming."""

    id: str = Field(
        default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}",
        description="Unique event identifier",
    )
    event: EventType = Field(..., description="Domain event name")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp",
    )
    incident_id: str = Field(
        default="INC-2026-DEFAULT",
        description="Associated disaster incident identifier",
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event payload attributes",
    )
    persistence_status: Optional[str] = Field(
        default=None,
        description="Non-sensitive persistence metadata (persisted | in_memory_fallback | disabled)",
    )

    def to_sse_format(self) -> str:
        """Format the envelope into valid Server-Sent Events text protocol."""
        import json

        json_data = json.dumps(self.model_dump(), default=str)
        return f"event: {self.event.value}\nid: {self.id}\ndata: {json_data}\n\n"
