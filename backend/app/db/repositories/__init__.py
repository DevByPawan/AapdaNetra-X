"""AapdaNetra-X Repositories Package

Exposes all persistence repository classes for database interactions.
"""

from app.db.repositories.analytics import AnalyticsRepository
from app.db.repositories.base import BaseRepository
from app.db.repositories.alert import AlertRepository
from app.db.repositories.asset import CriticalAssetRepository
from app.db.repositories.audit import AuditEventRepository
from app.db.repositories.incident import IncidentRepository
from app.db.repositories.risk import RiskPredictionRepository
from app.db.repositories.route import EvacuationRouteRepository
from app.db.repositories.shap import SHAPRecordRepository
from app.db.repositories.simulation import SimulationRepository
from app.db.repositories.telemetry import TelemetryRepository

__all__ = [
    "BaseRepository",
    "AnalyticsRepository",
    "IncidentRepository",
    "TelemetryRepository",
    "RiskPredictionRepository",
    "SHAPRecordRepository",
    "EvacuationRouteRepository",
    "CriticalAssetRepository",
    "SimulationRepository",
    "AlertRepository",
    "AuditEventRepository",
]
