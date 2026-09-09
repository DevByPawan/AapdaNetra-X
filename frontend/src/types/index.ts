// ── Incident ─────────────────────────────────────────────────────────────
export interface Incident {
  id: string;
  type: string;
  status: 'ACTIVE' | 'CONTAINED' | 'RESOLVED';
  startedAt: string;
  sector: string;
  severity: 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL';
  location: { name: string; lat: number; lng: number };
}

// ── Risk ─────────────────────────────────────────────────────────────────
export type RiskLevel = 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL';

export interface HeatmapZone {
  id: string;
  lat: number;
  lng: number;
  radiusMeters: number;
  level: RiskLevel;
}

export interface RiskState {
  index: number;
  label: string;
  currentRisk: number;
  predictedRisk: number;
  riskCategory: RiskLevel;
  confidence: number;
  affectedPopulation: number;
  criticalPopulation: number;
  criticalAssets: number;
  affectedAssets: number;
  trend: string;
  mapStatusText: string;
  predictionNote: string;
  heatmapZones: HeatmapZone[];
}

// ── Forecast ─────────────────────────────────────────────────────────────
export interface ForecastPoint {
  minutesOffset: number;
  risk: number;
}

export interface Forecast {
  points: ForecastPoint[];
  peakAt: string;
  trend: string;
  confidence: number;
  trendLabel: string;
}

// ── Routes ───────────────────────────────────────────────────────────────
export interface RouteWaypoint {
  id: string;
  lat: number;
  lng: number;
  label: string;
}

export interface EvacRoute {
  id: string;
  name: string;
  eta: number;
  failureProbability: number;
  safetyScore: number;
  waypoints: RouteWaypoint[];
}

export interface DecisionFactor {
  factor: string;
  contribution: string;
}

export interface RoutesData {
  recommended: EvacRoute;
  alternatives: EvacRoute[];
  recommendation: {
    title: string;
    text: string;
    confidence: number;
  };
  decisionTrace: DecisionFactor[];
}

// ── Alerts ───────────────────────────────────────────────────────────────
export type AlertSeverity = 'CRITICAL' | 'HIGH' | 'MODERATE' | 'INFO';

export interface Alert {
  id: string;
  severity: AlertSeverity;
  title: string;
  description: string;
  timestamp: string;
}

export interface AlertsData {
  open: number;
  alerts: Alert[];
}

// ── Simulation ───────────────────────────────────────────────────────────
export interface SimulationInput {
  rainfallIncrease: number;
  populationMovement: number;
  waterLevelIncrease: number;
}

export interface SimulationResult {
  newRisk: number;
  riskCategory: RiskLevel;
  routeRecommendation: string;
  flaggedAssets: string[];
  narrative: string;
  severity: 'MINOR' | 'MODERATE' | 'SEVERE';
}

// ── API envelope ─────────────────────────────────────────────────────────
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  timestamp: string;
  version: string;
}
