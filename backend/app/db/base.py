"""AapdaNetra-X Database Base — Phase 6.5B

SQLAlchemy 2.x DeclarativeBase with common mixins for ORM models.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all AapdaNetra-X ORM models."""
    pass


class TimestampMixin:
    """Mixin providing timezone-aware created_at and updated_at columns.

    Uses server-side defaults for consistency across application instances.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
