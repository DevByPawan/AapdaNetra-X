"""
AapdaNetra-X — Data Provider Abstract Base
Defines the interface contract that all external data adapters must implement.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Optional


from datetime import datetime, timezone
from typing import Dict, Optional, Any


class DataProviderStatus(str, Enum):
    """Status of the most recent data fetch from a provider."""
    LIVE = "live"
    FALLBACK = "fallback"
    ERROR = "error"


class DataProvider(ABC):
    """
    Abstract interface for external data providers.

    Each provider is responsible for fetching one or more ML feature values
    from an external source (API, file, sensor feed) and returning them
    as a partial dict of feature_name → float.

    Contract:
      - Returned dict keys MUST be a subset of ml.features.schema.FEATURE_NAMES.
      - Values of None indicate that the provider could not supply the value
        (the orchestrator will fill from fallback defaults).
      - Providers must never raise unhandled exceptions; errors should be caught
        internally and reflected via self.status = DataProviderStatus.ERROR.
    """

    def __init__(self):
        self.status: DataProviderStatus = DataProviderStatus.FALLBACK
        self.last_error: Optional[str] = None
        self.received_at: Optional[str] = None
        self.observed_at: Optional[str] = None
        self.age_seconds: Optional[float] = None
        self.is_stale: bool = False
        self.cache_status: Optional[str] = "none"
        self.freshness_status: str = "SIMULATED"
        self.unavailability_reason: Optional[str] = None

    @abstractmethod
    def get_features(self) -> Dict[str, Optional[float]]:
        """
        Fetch current feature values from the external source.

        Returns:
            Dict mapping feature names to float values. Keys MUST be valid
            FEATURE_NAMES. Values may be None if unavailable.
        """
        ...

    @property
    def is_live(self) -> bool:
        return self.status == DataProviderStatus.LIVE

    @property
    def provider_name(self) -> str:
        return self.__class__.__name__

    def calculate_age(self, now_reference: Optional[datetime] = None) -> Optional[float]:
        """Calculates age in seconds from observed_at against now_reference or current UTC time."""
        if not self.observed_at:
            return None
        try:
            dt_obs = datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
            ref = now_reference or datetime.now(timezone.utc)
            if dt_obs.tzinfo is None:
                dt_obs = dt_obs.replace(tzinfo=timezone.utc)
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            diff = (ref - dt_obs).total_seconds()
            return max(0.0, round(diff, 1))
        except Exception:
            return None
