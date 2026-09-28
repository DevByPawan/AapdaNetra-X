"""AapdaNetra-X — Keyset / Cursor Pagination Utility

Provides stable keyset pagination and time-range filtering helper functions
for async SQLAlchemy queries across disaster domain repositories.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union, Tuple
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import Tuple as SATuple, select, or_, and_
from sqlalchemy.sql.selectable import Select

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Parameters for keyset pagination and time-range filtering."""

    limit: int = Field(default=50, ge=1, le=100, description="Page size limit (1 to 100)")
    cursor_timestamp: Optional[datetime] = Field(
        default=None, description="Cursor timestamp threshold for pagination"
    )
    cursor_id: Optional[str] = Field(
        default=None, description="Cursor ID tie-breaker for pagination"
    )
    from_time: Optional[datetime] = Field(
        default=None, description="Start time range filter (inclusive)"
    )
    to_time: Optional[datetime] = Field(
        default=None, description="End time range filter (inclusive)"
    )

    def model_post_init(self, __context: Any) -> None:
        """Validate limit bounds, timezone awareness, and time range ordering."""
        if self.limit < 1 or self.limit > 100:
            raise ValueError("Limit must be between 1 and 100")

        # Reject naive timestamps and normalize timezone-aware timestamps to UTC
        if self.from_time is not None:
            if self.from_time.tzinfo is None or self.from_time.tzinfo.utcoffset(self.from_time) is None:
                raise ValueError("from_time must be timezone-aware")
            self.from_time = self.from_time.astimezone(timezone.utc)

        if self.to_time is not None:
            if self.to_time.tzinfo is None or self.to_time.tzinfo.utcoffset(self.to_time) is None:
                raise ValueError("to_time must be timezone-aware")
            self.to_time = self.to_time.astimezone(timezone.utc)

        if self.cursor_timestamp is not None:
            if self.cursor_timestamp.tzinfo is None or self.cursor_timestamp.tzinfo.utcoffset(self.cursor_timestamp) is None:
                raise ValueError("cursor_timestamp must be timezone-aware")
            self.cursor_timestamp = self.cursor_timestamp.astimezone(timezone.utc)

        if self.from_time and self.to_time and self.from_time > self.to_time:
            raise ValueError("from_time cannot be greater than to_time")



class PageResult(BaseModel, Generic[T]):
    """Standardized keyset pagination result envelope."""

    items: List[Any]
    next_cursor: Optional[Dict[str, str]] = None
    has_more: bool = False


def apply_keyset_pagination(
    stmt: Select,
    timestamp_col: Any,
    id_col: Any,
    params: PaginationParams,
    id_is_uuid: bool = True,
) -> Select:
    """Apply time range filters, cursor conditions, and ordering to a SQLAlchemy select statement."""

    # 1. Time range filters
    if params.from_time is not None:
        stmt = stmt.where(timestamp_col >= params.from_time)
    if params.to_time is not None:
        stmt = stmt.where(timestamp_col <= params.to_time)

    # 2. Keyset cursor filter for DESC ordering (strictly older than cursor)
    if params.cursor_timestamp is not None and params.cursor_id is not None:
        cur_ts = params.cursor_timestamp
        if id_is_uuid:
            try:
                cur_id = uuid.UUID(params.cursor_id) if isinstance(params.cursor_id, str) else params.cursor_id
            except ValueError:
                cur_id = params.cursor_id
        else:
            cur_id = params.cursor_id

        stmt = stmt.where(
            or_(
                timestamp_col < cur_ts,
                and_(timestamp_col == cur_ts, id_col < cur_id),
            )
        )

    # 3. Deterministic descending order by timestamp then ID
    stmt = stmt.order_by(timestamp_col.desc(), id_col.desc())

    # 4. Limit + 1 to detect has_more
    stmt = stmt.limit(params.limit + 1)

    return stmt


def build_page_result(
    items: List[Any],
    limit: int,
    get_timestamp: Any,
    get_id: Any,
) -> PageResult:
    """Build a PageResult envelope from fetched items (where len(items) <= limit + 1)."""
    has_more = len(items) > limit
    page_items = items[:limit] if has_more else items

    next_cursor = None
    if has_more and page_items:
        last_item = page_items[-1]
        ts_val = get_timestamp(last_item)
        id_val = get_id(last_item)

        if isinstance(ts_val, datetime):
            ts_str = ts_val.isoformat()
        else:
            ts_str = str(ts_val)

        next_cursor = {
            "timestamp": ts_str,
            "id": str(id_val),
        }

    return PageResult(
        items=page_items,
        next_cursor=next_cursor,
        has_more=has_more,
    )
