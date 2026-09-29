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
  status?: string;
  source?: string;
  metadata?: Record<string, any>;
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

// ── Phase 6.6 History & Keyset Pagination Types ───────────────────────────
export interface CursorInfo {
  timestamp: string;
  id: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  next_cursor: CursorInfo | null;
  has_more: boolean;
}

export interface PaginationParams {
  limit?: number;
  cursor_timestamp?: string;
  cursor_id?: string;
  from_time?: string;
  to_time?: string;
}

export interface IncidentHistoryItem {
  id: string;
  incident_type: string;
  status: string;
  started_at: string;
  sector: string;
  severity: string;
  location_name: string;
  latitude: number;
  longitude: number;
  created_at: string;
  updated_at: string;
}

export interface TelemetryHistoryItem {
  id: string;
  incident_id: string | null;
  data_mode: string;
  fallback_used: boolean;
  rainfall_intensity: number;
  rainfall_trend: number;
  water_level: number;
  water_level_trend: number;
  road_congestion: number;
  population_exposure: number;
  infrastructure_vulnerability: number;
  location_name: string | null;
  provenance: Record<string, any>;
  observed_at: string;
  created_at: string;
}

export interface RiskHistoryItem {
  id: string;
  incident_id: string;
  telemetry_id: string | null;
  horizon: number;
  horizon_label: string;
  current_risk: number;
  predicted_risk: number;
  risk_category: string;
  confidence: number;
  prediction_reliability: number;
  affected_population: number;
  critical_population: number;
  critical_assets_count: number;
  affected_assets_count: number;
  trend: string;
  map_status_text: string;
  prediction_note: string;
  input_features: Record<string, any>;
  created_at: string;
}

export interface RouteHistoryItem {
  id: string;
  incident_id: string;
  risk_prediction_id: string | null;
  route_name: string;
  route_type: string;
  is_recommended: boolean;
  origin_name: string;
  origin_lat: number;
  origin_lon: number;
  destination_name: string;
  destination_lat: number;
  destination_lon: number;
  waypoint_coords: number[][];
  distance_km: number;
  estimated_minutes: number;
  safety_score: number;
  congestion_index: number;
  created_at: string;
}

export interface AuditHistoryItem {
  id: string;
  incident_id: string | null;
  event_type: string;
  severity: string;
  source: string;
  description: string;
  actor: string;
  event_data: Record<string, any> | null;
  created_at: string;
}

export type TimelineEventType =
  | 'TELEMETRY_OBSERVED'
  | 'RISK_EVALUATED'
  | 'ROUTE_UPDATED'
  | 'ALERT_CREATED'
  | 'SIMULATION_COMPLETED'
  | 'DECISION_APPROVED'
  | 'AUDIT_LOGGED';

export interface TimelineEventItem {
  timestamp: string;
  event_type: TimelineEventType | string;
  entity_type: string;
  entity_id: string;
  incident_id: string;
  summary: string;
  details: Record<string, any>;
}

export interface DecisionTraceItem {
  feature: string;
  val: number;
  shap: number;
  desc: string;
}

export interface SHAPHistoryResponse {
  id: string;
  risk_prediction_id: string;
  horizon: number;
  prediction: number;
  base_value: number;
  total_shap_delta: number;
  features: Record<string, number>;
  decision_trace: DecisionTraceItem[];
  created_at: string;
}

// ── Phase 6.14 Spatial Intelligence Types ───────────────────────────────
export interface ElevationResponse {
  elevation_m: number | null;
  slope_deg: number | null;
  source: string;
  provenance: string;
  is_available: boolean;
  reason?: string;
  observed_at?: string | null;
}

export interface HazardLayerFeature {
  type: string;
  geometry: {
    type: string;
    coordinates: any;
  };
  properties: Record<string, any>;
}

export interface HazardLayersResponse {
  is_available: boolean;
  provenance: string;
  layer_count: number;
  hazard_features: HazardLayerFeature[];
  observed_at: string | null;
}

export interface ExposureSummaryResponse {
  population_exposure: number | null;
  population_provenance: string;
  infrastructure_vulnerability: number | null;
  infrastructure_provenance: string;
  hazard_layers_available: boolean;
  hazard_provenance: string;
  spatial_crs: string;
  projected_crs: string;
}

export interface RouteSpatialSafetyResponse {
  route_id: string;
  spatial_hazard_exposure: number;
  hazard_penalty: number;
  modeled_safety_score: number;
  water_proximity_km: number;
  elevation_min_m: number | null;
  provenance: string;
  terminology_notice: string;
}

export interface SpatialSummaryResponse {
  spatial_crs: string;
  projected_crs: string;
  dem_enabled: boolean;
  dem_source: string;
  hazard_layers: HazardLayersResponse;
  exposure: ExposureSummaryResponse;
  limitation_notice: string;
}
