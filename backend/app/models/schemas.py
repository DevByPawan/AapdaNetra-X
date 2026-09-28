"""Pydantic models for all API request/response types."""
from pydantic import BaseModel, Field
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


class PredictionInterval(BaseModel):
    lower: float = 0.0
    upper: float = 100.0
    intervalWidth: float = 0.0
    interval_width: float = 0.0
    nominalCoverage: float = 0.90
    nominal_coverage: float = 0.90
    method: str = "conformal_regression"
    dataStatus: str = "synthetic"
    data_status: str = "synthetic"
    isClipped: bool = False
    is_clipped: bool = False
    status: str = "AVAILABLE"
    disclaimer: str = "Prediction interval calibrated on synthetic data under split-conformal assumptions."


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
    predictionInterval: Optional[PredictionInterval] = None
    prediction_interval: Optional[Dict[str, Any]] = None


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
    attributionStatement: Optional[str] = ""


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
    contribution_magnitude: Optional[float] = 0.0
    attribution_statement: Optional[str] = ""


class ExplainabilityResponse(BaseModel):
    horizon: int = 0
    prediction: float
    base_value: float
    total_shap_delta: float
    features: List[ExplainabilityFeature]
    decision_trace: List[DecisionFactor]
    decisionTrace: List[DecisionFactor]
    is_shap_consistent: Optional[bool] = True
    predictionInterval: Optional[PredictionInterval] = None
    prediction_interval: Optional[Dict[str, Any]] = None


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
import math
from pydantic import field_validator

class SimulationRequest(BaseModel):
    evacuationPace: float = Field(default=1.0, ge=0.1, le=5.0, description="Evacuation pace multiplier")
    rainfallMultiplier: float = Field(default=1.0, ge=0.0, le=10.0, description="Rainfall intensity multiplier")
    drainageEfficiency: float = Field(default=1.0, ge=0.0, le=1.0, description="Drainage capacity efficiency ratio")
    routeBlockage: bool = Field(default=False, description="Whether primary evacuation route is blocked")
    rainfallIncrease: float = Field(default=0.0, ge=0.0, le=500.0, description="Additional rainfall intensity mm/h")
    populationMovement: int = Field(default=0, ge=-100000, le=100000, description="Net population movement delta")
    waterLevelIncrease: float = Field(default=0.0, ge=0.0, le=20.0, description="Additional river gauge water level in meters")

    @field_validator("evacuationPace", "rainfallMultiplier", "drainageEfficiency", "rainfallIncrease", "waterLevelIncrease")
    @classmethod
    def validate_no_inf_nan(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Numeric parameter cannot be NaN or Infinity")
        return v


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
    incidentId: str = Field(..., min_length=1, max_length=64, description="Target incident identifier")
    responderId: str = Field(default="OPERATOR-01", min_length=1, max_length=64, description="Approving responder ID")


class ApproveResponse(BaseModel):
    approved: bool
    workflowId: str
    timestamp: str
