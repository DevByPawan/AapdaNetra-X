"""Pydantic models for all API request/response types."""
from pydantic import BaseModel
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime


# ── Common ────────────────────────────────────────────────────────────────
class ApiResponse(BaseModel):
    success: bool = True
    timestamp: str
    version: str = "0.1.0"


# ── Incident ─────────────────────────────────────────────────────────────
class IncidentLocation(BaseModel):
    name: str
    lat: float
    lng: float


class IncidentResponse(BaseModel):
    id: str
    type: str
    status: Literal["ACTIVE", "CONTAINED", "RESOLVED"]
    startedAt: str
    sector: str
    severity: Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]
    location: IncidentLocation


# ── Risk ─────────────────────────────────────────────────────────────────
RiskLevel = Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]


class HeatmapZone(BaseModel):
    id: str
    lat: float
    lng: float
    radiusMeters: float
    level: RiskLevel


class RiskResponse(BaseModel):
    index: int
    label: str
    currentRisk: float
    predictedRisk: float
    riskCategory: RiskLevel
    confidence: float
    predictionReliability: float = 0.95
    prediction_reliability: float = 0.95
    affectedPopulation: int
    criticalPopulation: int
    criticalAssets: int
    affectedAssets: int
    trend: str
    mapStatusText: str
    predictionNote: str
    heatmapZones: List[HeatmapZone]


# ── Forecast ─────────────────────────────────────────────────────────────
class ForecastPoint(BaseModel):
    minutesOffset: int
    risk: float


class ForecastResponse(BaseModel):
    points: List[ForecastPoint]
    peakAt: str
    trend: str
    confidence: float
    predictionReliability: float = 0.95
    trendLabel: str


# ── Routes ───────────────────────────────────────────────────────────────
class RouteWaypoint(BaseModel):
    id: str
    lat: float
    lng: float
    label: str


class EvacRoute(BaseModel):
    id: str
    name: str
    eta: int
    failureProbability: float
    safetyScore: float
    distanceKm: float = 0.0
    riskScore: float = 0.0
    waypoints: List[RouteWaypoint]
    nodes: Optional[List[str]] = []
    isBlocked: Optional[bool] = False


class RouteRecommendation(BaseModel):
    title: str
    text: str
    confidence: float


class DecisionFactor(BaseModel):
    factor: str
    contribution: str
    direction: Optional[str] = "increases_risk"
    percent: Optional[float] = 0.0
    shapValue: Optional[float] = 0.0


class RoutesResponse(BaseModel):
    horizon: int = 0
    recommended: EvacRoute
    alternatives: List[EvacRoute]
    recommendation: RouteRecommendation
    decisionTrace: List[DecisionFactor]
    blockedSegments: Optional[List[Dict[str, Any]]] = []
    routeReason: Optional[str] = ""


# ── Explainability ────────────────────────────────────────────────────────
class ExplainabilityFeature(BaseModel):
    feature: str
    label: str
    shap_value: float
    direction: str
    direction_symbol: str
    contribution_percent: float
    formatted_contribution: str
    raw_value: float


class ExplainabilityResponse(BaseModel):
    horizon: int = 0
    prediction: float
    base_value: float
    total_shap_delta: float
    features: List[ExplainabilityFeature]
    decision_trace: List[DecisionFactor]
    decisionTrace: List[DecisionFactor]


# ── Alerts ───────────────────────────────────────────────────────────────
AlertSeverity = Literal["CRITICAL", "HIGH", "MODERATE", "INFO"]


class AlertItem(BaseModel):
    id: str
    severity: AlertSeverity
    title: str
    description: str
    timestamp: str


class AlertsResponse(BaseModel):
    open: int
    alerts: List[AlertItem]


# ── Simulation ───────────────────────────────────────────────────────────
class SimulationRequest(BaseModel):
    evacuationPace: float = 1.0
    rainfallMultiplier: float = 1.0
    drainageEfficiency: float = 1.0
    routeBlockage: bool = False
    rainfallIncrease: float = 0.0
    populationMovement: int = 0
    waterLevelIncrease: float = 0.0


class SimulationResponse(BaseModel):
    newRisk: float
    baselineRisk: float = 0.0
    baseline_risk: float = 0.0
    scenarioRisk: float = 0.0
    scenario_risk: float = 0.0
    riskDelta: float = 0.0
    risk_delta: float = 0.0
    riskCategory: RiskLevel
    predictionReliability: float = 0.95
    prediction_reliability: float = 0.95
    routeRecommendation: str
    flaggedAssets: List[str]
    narrative: str
    severity: Literal["MINOR", "MODERATE", "SEVERE"]


# ── Response approval ─────────────────────────────────────────────────────
class ApproveRequest(BaseModel):
    incidentId: str
    responderId: str = "OPERATOR-01"


class ApproveResponse(BaseModel):
    approved: bool
    workflowId: str
    timestamp: str
