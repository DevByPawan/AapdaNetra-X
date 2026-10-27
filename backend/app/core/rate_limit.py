"""AapdaNetra-X — Rate Limiting & Request Protection

Phase 6.32: Implements explicit, bounded rate limiting for sensitive endpoints.
Provides IP-based sliding window rate limiting and documentation for cluster deployment.

NOTE: This in-process rate limiter is process-local. Distributed multi-worker production deployments
require Redis or a shared key-value store for cluster-wide rate limit enforcement.
"""

from collections import defaultdict
from datetime import datetime, timezone
import logging
from typing import Dict, List
from fastapi import HTTPException, Request, status

from app.config import settings

logger = logging.getLogger("aapdanetra.security.rate_limit")

# Process-local request timestamp store per client IP
_request_history: Dict[str, List[float]] = defaultdict(list)


def reset_rate_limiter() -> None:
    """Clear in-process rate limit records (useful for test isolation)."""
    _request_history.clear()


async def check_rate_limit(request: Request) -> bool:
    """Enforces sliding-window rate limiting per client IP address."""
    if not settings.rate_limit_enabled:
        return True

    now = datetime.now(timezone.utc).timestamp()
    client_ip = request.client.host if request.client else "127.0.0.1"

    # Purge timestamps older than 60 seconds
    window_start = now - 60.0
    history = [t for t in _request_history[client_ip] if t >= window_start]
    _request_history[client_ip] = history

    if len(history) >= settings.rate_limit_per_minute:
        logger.warning(
            "Rate limit exceeded for client IP '%s' (%d requests in 60s limit %d)",
            client_ip,
            len(history),
            settings.rate_limit_per_minute,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Maximum requests per minute reached.",
            headers={"Retry-After": "60"},
        )

    _request_history[client_ip].append(now)
    return True
