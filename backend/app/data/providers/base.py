"""
AapdaNetra-X — Data Provider Abstract Base
Defines the interface contract that all external data adapters must implement.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Optional


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
