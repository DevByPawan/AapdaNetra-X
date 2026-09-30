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
    hazard_type: Optional[str] = "flood"
    capability_status: Optional[str] = "SUPPORTED"
    supported: Optional[bool] = True
    model_available: Optional[bool] = True
    spatial_available: Optional[bool] = True
    telemetry_available: Optional[bool] = True
    alerts_available: Optional[bool] = True
    routing_available: Optional[bool] = True
    decision_support_available: Optional[bool] = True


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
    hazard_type: Optional[str] = "flood"


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

    # Phase 6.16 Advanced What-If Scenario Analysis Extensions
    scenario_id: Optional[str] = None
    fingerprint: Optional[str] = None
    label: str = "SIMULATED SCENARIO OUTPUT"
    baseline_features: Optional[Dict[str, float]] = None
    scenario_features: Optional[Dict[str, float]] = None
    feature_deltas: Optional[Dict[str, float]] = None
    uncertainty: Optional[Dict[str, Any]] = None
    shap: Optional[Dict[str, Any]] = None
    spatial: Optional[Dict[str, Any]] = None
    routes: Optional[Dict[str, Any]] = None
    alerts: Optional[Dict[str, Any]] = None
    reproducibility: Optional[Dict[str, Any]] = None
    disclaimer: str = "SIMULATED SCENARIO OUTPUT — Decision support simulation only, not an official flood forecast or real-world disaster prediction."


class ScenarioCompareRequest(BaseModel):
    scenario_a: SimulationRequest
    scenario_b: SimulationRequest
    incident_id: str = Field(default="INC-2026-DEFAULT", description="Target incident ID")


class ScenarioCompareResponse(BaseModel):
    scenario_a: SimulationResponse
    scenario_b: SimulationResponse
    risk_delta_between_scenarios: float
    route_change_between_scenarios: bool
    summary_comparison: str
    label: str = "SIMULATED SCENARIO COMPARISON OUTPUT"


# ── Phase 6.17 Emergency Decision Support Schemas ────────────────────────
class DecisionSupportResponse(BaseModel):
    decision_id: str
    incident_id: str
    status: Literal["RECOMMENDED", "APPROVED", "REJECTED", "SUPERSEDED"]
    label: str = "AI-assisted decision-support recommendation"
    recommended_action: str
    priority: Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]
    risk_score: float
    risk_category: RiskLevel
    uncertainty_interval: Dict[str, Any]
    confidence: float
    prediction_reliability: float
    evidence: List[str]
    contributing_factors: List[Dict[str, Any]]
    spatial_context: Dict[str, Any]
    route_recommendation: Dict[str, Any]
    active_alerts_summary: List[Dict[str, Any]]
    data_freshness: Dict[str, Any]
    rationale: str
    limitations: List[str]
    generated_at: str
    model_version: str = "v1.0.0"
    source: str = "AapdaNetra-X Decision Engine"
    hazard_type: Optional[str] = "flood"


class DecisionSupportUnavailableResponse(BaseModel):
    hazard_type: str
    decision_support_available: bool = False
    status: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    reason: str
    incident_id: str
    generated_at: str



class DecisionActionRequest(BaseModel):
    decision_id: str = Field(..., min_length=1, max_length=64, description="Target decision recommendation ID")
    responder_id: str = Field(default="OPERATOR-01", min_length=1, max_length=64, description="Authorized emergency responder ID")
    reason: str = Field(default="Operator decision evaluation", min_length=1, max_length=512, description="Rationale for approval or rejection")


class DecisionActionResponse(BaseModel):
    decision_id: str
    status: Literal["RECOMMENDED", "APPROVED", "REJECTED", "SUPERSEDED"]
    approved: bool
    workflow_id: str
    timestamp: str
    audit_logged: bool
    sse_published: bool
    message: str




# ── Response approval ─────────────────────────────────────────────────────
class ApproveRequest(BaseModel):
    incidentId: str = Field(..., min_length=1, max_length=64, description="Target incident identifier")
    responderId: str = Field(default="OPERATOR-01", min_length=1, max_length=64, description="Approving responder ID")


class ApproveResponse(BaseModel):
    approved: bool
    workflowId: str
    timestamp: str


# ── Phase 6.18 Dynamic Evacuation Intelligence Schemas ───────────────────
RouteStatusEnum = Literal["SAFE", "CAUTION", "HIGH_RISK", "BLOCKED"]


class RouteScoreDetails(BaseModel):
    safety_score: float
    spatial_hazard_penalty: float
    congestion_penalty: float
    eta_penalty: float
    blockage_penalty: float
    composite_score: float


class RouteChangeNotice(BaseModel):
    route_changed: bool
    previous_route_id: Optional[str] = None
    new_route_id: Optional[str] = None
    change_reason: Optional[str] = None


class EvacuationRouteDetail(BaseModel):
    id: str
    name: str
    eta: int
    distance_km: float
    safety_score: float
    failure_probability: float
    risk_score: float
    status: RouteStatusEnum
    is_blocked: bool
    score_details: RouteScoreDetails
    spatial_hazard_exposure: float
    waypoints: List[RouteWaypoint]
    nodes: List[str]
    selection_reason: str


class EvacuationIntelligenceResponse(BaseModel):
    incident_id: str
    horizon: int = 0
    recommended_route: EvacuationRouteDetail
    alternative_routes: List[EvacuationRouteDetail]
    route_change: RouteChangeNotice
    overall_status_warning: Optional[str] = None
    all_routes_unsafe: bool = False
    active_risk_score: float
    active_risk_category: RiskLevel
    data_freshness: Dict[str, Any]
    decision_trace: List[Dict[str, Any]]
    provenance: str
    generated_at: str
    label: str = "AI-assisted dynamic evacuation decision-support intelligence"
    hazard_type: Optional[str] = "flood"


class EvacuationUnavailableResponse(BaseModel):
    hazard_type: str
    routing_available: bool = False
    status: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    reason: str
    incident_id: str
    generated_at: str


class EvacuationRecomputeRequest(BaseModel):
    incident_id: str = Field(default="INC-2026-DEFAULT")
    horizon: int = Field(default=0, ge=0, le=4)
    route_blockage_override: Optional[bool] = None
    publish_sse: bool = Field(default=True)
    hazard_type: Optional[str] = Field(default=None, description="Optional hazard type identifier")



# ── Phase 6.19 Real-Time Telemetry Pipeline Schemas ─────────────────────
class TelemetryIngestionRequest(BaseModel):
    incident_id: str = Field(default="INC-2026-DEFAULT", min_length=1, max_length=64, description="Target incident ID")
    sensor_id: str = Field(default="SENSOR-01", min_length=1, max_length=64, description="Sensor station ID")
    observed_at: Optional[str] = Field(default=None, description="ISO 8601 UTC observation timestamp")
    features: Dict[str, Any] = Field(..., description="Partial or full dictionary of sensor features")
    source: Optional[str] = Field(default="live_sensor_feed", description="Source provider tag")
    client_event_id: Optional[str] = Field(default=None, description="Optional unique client event identifier")
    hazard_type: Optional[str] = Field(default=None, description="Optional hazard type identifier")


class TelemetryIngestionResponse(BaseModel):
    status: Literal["accepted", "duplicate_ignored", "out_of_order", "rejected_validation"]
    observation_id: str
    incident_id: str
    sensor_id: str
    observation_hash: str
    observed_at: str
    ingested_at: str
    features: Dict[str, float]
    trends: Dict[str, float]
    provenance: Dict[str, str]
    persistence_status: str
    cascade_triggered: bool
    message: str
    hazard_type: Optional[str] = Field(default="flood", description="Hazard type identifier")


class TelemetryHealthResponse(BaseModel):
    active_overlay: Dict[str, float]
    data_mode: str
    freshness: Dict[str, Any]
    provenance: Dict[str, str]
    metrics: Dict[str, Any]
