import axios from 'axios';
import type {
  Incident, RiskState, Forecast, RoutesData,
  AlertsData, SimulationInput, SimulationResult, ApiResponse,
} from '../types';
import {
  simulatedIncident, simulatedRisk, simulatedForecast,
  simulatedRoutes, simulatedAlerts,
} from '../data/simulatedData';

const USE_SIMULATED = import.meta.env.VITE_USE_SIMULATED === 'true';

const client = axios.create({
  baseURL: '/api',
  timeout: 8000,
  headers: { 'Content-Type': 'application/json' },
});

function extractData<T>(res: any): T {
  return res.data?.data ?? res.data;
}

// ── Incident ─────────────────────────────────────────────────────────────
export async function fetchIncident(): Promise<Incident> {
  if (USE_SIMULATED) return simulatedIncident;
  const res = await client.get('/incident');
  return extractData<Incident>(res);
}

// ── Risk ─────────────────────────────────────────────────────────────────
export async function fetchRisk(horizon: number = 0): Promise<RiskState> {
  if (USE_SIMULATED) return simulatedRisk[horizon] ?? simulatedRisk[0];
  const res = await client.get(`/risk?horizon=${horizon}`);
  return extractData<RiskState>(res);
}

// ── Forecast ─────────────────────────────────────────────────────────────
export async function fetchForecast(): Promise<Forecast> {
  if (USE_SIMULATED) return simulatedForecast;
  const res = await client.get('/forecast');
  return extractData<Forecast>(res);
}

// ── Routes ───────────────────────────────────────────────────────────────
export async function fetchRoutes(horizon: number = 0): Promise<RoutesData> {
  if (USE_SIMULATED) return simulatedRoutes;
  const res = await client.get(`/routes?horizon=${horizon}`);
  return extractData<RoutesData>(res);
}

// ── Alerts ───────────────────────────────────────────────────────────────
export async function fetchAlerts(): Promise<AlertsData> {
  if (USE_SIMULATED) return simulatedAlerts;
  const res = await client.get('/alerts');
  return extractData<AlertsData>(res);
}

export async function acknowledgeAlert(alertId: string): Promise<any> {
  if (USE_SIMULATED) return { success: true };
  const res = await client.post(`/alerts/${alertId}/acknowledge`);
  return extractData<any>(res);
}

export async function resolveAlert(alertId: string): Promise<any> {
  if (USE_SIMULATED) return { success: true };
  const res = await client.post(`/alerts/${alertId}/resolve`);
  return extractData<any>(res);
}

// ── Simulation ───────────────────────────────────────────────────────────
// ── Simulation ───────────────────────────────────────────────────────────
export async function runSimulation(input: SimulationInput): Promise<SimulationResult> {
  if (USE_SIMULATED) {
    const { rainfallIncrease, populationMovement, waterLevelIncrease, routeBlockage = false } = input;
    const baseRisk = 74.0;
    const newRisk = Math.min(99, Math.max(10, baseRisk + Math.round(rainfallIncrease * 0.45) + Math.round(populationMovement / 1000) * 3 + Math.round(waterLevelIncrease * 0.2)));
    const delta = Math.round((newRisk - baseRisk) * 10) / 10;
    const severe = newRisk >= 80 || routeBlockage || rainfallIncrease >= 30;
    return {
      newRisk,
      baselineRisk: baseRisk,
      baseline_risk: baseRisk,
      scenarioRisk: newRisk,
      scenario_risk: newRisk,
      riskDelta: delta,
      risk_delta: delta,
      riskCategory: newRisk >= 90 ? 'CRITICAL' : newRisk >= 75 ? 'HIGH' : 'MODERATE',
      predictionReliability: 0.95,
      prediction_reliability: 0.95,
      routeRecommendation: routeBlockage ? 'Route B' : (newRisk >= 80 ? 'Route B' : 'Route A'),
      flaggedAssets: severe ? ['Bridge-04', 'Pump-Station-7'] : ['Bridge-04'],
      narrative: `SIMULATED SCENARIO OUTPUT: ML model predicts risk change of ${delta >= 0 ? '+' : ''}${delta} points (Baseline: ${baseRisk} → Scenario: ${newRisk}).`,
      severity: severe ? 'SEVERE' : newRisk > 80 ? 'MODERATE' : 'MINOR',
      scenario_id: 'sim-' + Date.now(),
      fingerprint: 'fp-sim-' + Date.now(),
      label: 'SIMULATED SCENARIO OUTPUT',
      uncertainty: {
        baseline: { lower_bound: baseRisk - 6.6, upper_bound: baseRisk + 6.6, nominal_coverage: 0.90 },
        scenario: { lower_bound: newRisk - 6.6, upper_bound: newRisk + 6.6, nominal_coverage: 0.90 },
        nominal_coverage: 0.90,
        status: 'calibrated',
      },
      shap: {
        canonical_features: ['rainfall_intensity', 'water_level', 'road_congestion'],
        attribution_changes: [
          { feature: 'rainfall_intensity', baseline_value: 45, simulated_value: 45 + rainfallIncrease, baseline_shap: 12.4, scenario_shap: 18.2, shap_attribution_change: 5.8, direction: 'positive', explanation: 'Model attribution changed by +5.800 points for rainfall_intensity' },
          { feature: 'water_level', baseline_value: 4.2, simulated_value: 4.2 + (waterLevelIncrease * 0.01), baseline_shap: 10.1, scenario_shap: 14.3, shap_attribution_change: 4.2, direction: 'positive', explanation: 'Model attribution changed by +4.200 points for water_level' }
        ],
      },
      spatial: {
        baseline_route_spatial_exposure: 0.08,
        scenario_route_spatial_exposure: 0.24,
        spatial_exposure_delta: 0.16,
        baseline_modeled_safety: 0.88,
        scenario_modeled_safety: 0.72,
        safety_score_delta: -0.16,
        provenance: 'hazard:provisional_river_proximity',
        terminology_notice: 'PROVISIONAL / DEMONSTRATION — Decision support layer only.',
      },
      routes: {
        baseline_route: { id: 'rt-a', name: 'Route A', eta: 12, safety_score: 0.88 },
        scenario_route: { id: routeBlockage ? 'rt-b' : 'rt-a', name: routeBlockage ? 'Route B' : 'Route A', eta: routeBlockage ? 16 : 14, safety_score: 0.72 },
        eta_delta: routeBlockage ? 4 : 2,
        safety_score_delta: -0.16,
        route_changed: routeBlockage,
        reason: routeBlockage ? 'Route A blocked; recommended Route B' : 'Route A optimal under scenario',
      },
      alerts: {
        baseline_active_alerts_count: 1,
        scenario_triggered_alerts: severe ? [{
          id: 'sim-alt-1',
          title: '[SIMULATION] High Water Level Warning',
          description: 'Water level threshold exceeded in simulated scenario',
          severity: 'HIGH',
          alert_type: 'TELEMETRY_WATER',
          impact_type: 'NEWLY_TRIGGERED',
          simulation_only: true,
          status: 'SCENARIO_ONLY'
        }] : [],
        newly_triggered_count: severe ? 1 : 0,
        severity_changes_count: 0,
        resolved_alerts_count: 0,
        notice: 'SIMULATION ONLY — Scenario alerts are hypothetical.',
      },
      reproducibility: {
        timestamp: new Date().toISOString(),
        incident_id: 'INC-2026-DEFAULT',
        fingerprint: 'fp-sim-' + Date.now(),
        model_version: 'v1.0.0',
        model_data_status: 'synthetic',
        deterministic: true,
      },
      disclaimer: 'SIMULATED SCENARIO OUTPUT — Decision support simulation only, not an official flood forecast or real-world disaster prediction.',
    };
  }
  const res = await client.post('/simulation', input);
  return extractData<SimulationResult>(res);
}

// ── Approve response ──────────────────────────────────────────────────────
export async function approveResponse(incidentId: string): Promise<{ approved: boolean; workflowId: string }> {
  if (USE_SIMULATED) return { approved: true, workflowId: 'WF-' + Date.now() };
  const res = await client.post('/response/approve', { incidentId, responderId: 'OPERATOR-01' });
  return extractData<{ approved: boolean; workflowId: string }>(res);
}

// ── Phase 6.6 Historical & Timeline API Functions ─────────────────────────
import type {
  PaginationParams,
  PaginatedResponse,
  IncidentHistoryItem,
  TelemetryHistoryItem,
  RiskHistoryItem,
  RouteHistoryItem,
  AuditHistoryItem,
  TimelineEventItem,
  SHAPHistoryResponse,
} from '../types';

function buildPaginationQuery(params?: PaginationParams): string {
  if (!params) return '';
  const q = new URLSearchParams();
  if (params.limit !== undefined) q.append('limit', String(params.limit));
  if (params.cursor_timestamp) q.append('cursor_timestamp', params.cursor_timestamp);
  if (params.cursor_id) q.append('cursor_id', params.cursor_id);
  if (params.from_time) q.append('from_time', params.from_time);
  if (params.to_time) q.append('to_time', params.to_time);
  const str = q.toString();
  return str ? `?${str}` : '';
}

export async function fetchIncidentsHistory(params?: PaginationParams): Promise<PaginatedResponse<IncidentHistoryItem>> {
  if (USE_SIMULATED) {
    return {
      items: [
        {
          id: 'INC-2026-DEFAULT',
          incident_type: 'flood',
          status: 'ACTIVE',
          started_at: new Date().toISOString(),
          sector: 'Sector B',
          severity: 'HIGH',
          location_name: 'Yamuna Sector B',
          latitude: 28.61,
          longitude: 77.23,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      next_cursor: null,
      has_more: false,
    };
  }
  const res = await client.get(`/incidents${buildPaginationQuery(params)}`);
  return extractData<PaginatedResponse<IncidentHistoryItem>>(res);
}

export async function fetchIncidentDetail(incidentId: string): Promise<IncidentHistoryItem> {
  if (USE_SIMULATED) {
    return {
      id: incidentId,
      incident_type: 'flood',
      status: 'ACTIVE',
      started_at: new Date().toISOString(),
      sector: 'Sector B',
      severity: 'HIGH',
      location_name: 'Yamuna Sector B',
      latitude: 28.61,
      longitude: 77.23,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
  }
  const res = await client.get(`/incidents/${incidentId}`);
  return extractData<IncidentHistoryItem>(res);
}

export async function fetchTelemetryHistory(
  incidentId: string,
  params?: PaginationParams
): Promise<PaginatedResponse<TelemetryHistoryItem>> {
  if (USE_SIMULATED) return { items: [], next_cursor: null, has_more: false };
  const res = await client.get(`/incidents/${incidentId}/telemetry/history${buildPaginationQuery(params)}`);
  return extractData<PaginatedResponse<TelemetryHistoryItem>>(res);
}

export async function fetchRiskHistory(
  incidentId: string,
  horizon?: number,
  params?: PaginationParams
): Promise<PaginatedResponse<RiskHistoryItem>> {
  if (USE_SIMULATED) return { items: [], next_cursor: null, has_more: false };
  const q = new URLSearchParams();
  if (horizon !== undefined) q.append('horizon', String(horizon));
  if (params?.limit) q.append('limit', String(params.limit));
  if (params?.cursor_timestamp) q.append('cursor_timestamp', params.cursor_timestamp);
  if (params?.cursor_id) q.append('cursor_id', params.cursor_id);
  if (params?.from_time) q.append('from_time', params.from_time);
  if (params?.to_time) q.append('to_time', params.to_time);
  const queryStr = q.toString() ? `?${q.toString()}` : '';
  const res = await client.get(`/incidents/${incidentId}/risk/history${queryStr}`);
  return extractData<PaginatedResponse<RiskHistoryItem>>(res);
}

export async function fetchRouteHistory(
  incidentId: string,
  params?: PaginationParams
): Promise<PaginatedResponse<RouteHistoryItem>> {
  if (USE_SIMULATED) return { items: [], next_cursor: null, has_more: false };
  const res = await client.get(`/incidents/${incidentId}/routes/history${buildPaginationQuery(params)}`);
  return extractData<PaginatedResponse<RouteHistoryItem>>(res);
}

export async function fetchAuditHistory(
  incidentId: string,
  params?: PaginationParams
): Promise<PaginatedResponse<AuditHistoryItem>> {
  if (USE_SIMULATED) return { items: [], next_cursor: null, has_more: false };
  const res = await client.get(`/incidents/${incidentId}/audit${buildPaginationQuery(params)}`);
  return extractData<PaginatedResponse<AuditHistoryItem>>(res);
}

export async function fetchIncidentTimeline(
  incidentId: string,
  params?: PaginationParams
): Promise<PaginatedResponse<TimelineEventItem>> {
  if (USE_SIMULATED) {
    const now = new Date();
    return {
      items: [
        {
          timestamp: new Date(now.getTime() - 5 * 60000).toISOString(),
          event_type: 'DECISION_APPROVED',
          entity_type: 'audit_event',
          entity_id: 'aud-sim-1',
          incident_id: incidentId,
          summary: 'Response workflow approved (RESPONSE_WORKFLOW_APPROVED)',
          details: { actor: 'OPERATOR-01', source: 'CommandCenter' },
        },
        {
          timestamp: new Date(now.getTime() - 15 * 60000).toISOString(),
          event_type: 'SIMULATION_COMPLETED',
          entity_type: 'simulation',
          entity_id: 'sim-sim-1',
          incident_id: incidentId,
          summary: 'Simulation completed — Scenario risk 84.0 (Delta: +10.0)',
          details: { baseline_risk: 74.0, scenario_risk: 84.0, route_recommendation: 'Route B' },
        },
        {
          timestamp: new Date(now.getTime() - 30 * 60000).toISOString(),
          event_type: 'ALERT_CREATED',
          entity_type: 'alert',
          entity_id: 'alt-sim-1',
          incident_id: incidentId,
          summary: 'Alert created — Flash Flood Warning (CRITICAL)',
          details: { title: 'Flash Flood Warning', severity: 'CRITICAL', status: 'OPEN' },
        },
        {
          timestamp: new Date(now.getTime() - 45 * 60000).toISOString(),
          event_type: 'ROUTE_UPDATED',
          entity_type: 'evacuation_route',
          entity_id: 'rt-sim-1',
          incident_id: incidentId,
          summary: 'Evacuation route calculated — Route Alpha (12.4 km, safety score 88)',
          details: { route_name: 'Route Alpha', safety_score: 88, is_recommended: true },
        },
        {
          timestamp: new Date(now.getTime() - 60 * 60000).toISOString(),
          event_type: 'RISK_EVALUATED',
          entity_type: 'risk_prediction',
          entity_id: 'pred-sim-1',
          incident_id: incidentId,
          summary: 'Risk evaluated — Score 74.0 (HIGH) [NOW]',
          details: { current_risk: 74.0, predicted_risk: 74.0, risk_category: 'HIGH', horizon: 0 },
        },
        {
          timestamp: new Date(now.getTime() - 75 * 60000).toISOString(),
          event_type: 'TELEMETRY_OBSERVED',
          entity_type: 'telemetry_observation',
          entity_id: 'obs-sim-1',
          incident_id: incidentId,
          summary: 'Telemetry observed — Rainfall 42.0 mm/h, Water level 3.85 m',
          details: { rainfall_intensity: 42.0, water_level: 3.85, road_congestion: 0.65 },
        },
      ],
      next_cursor: null,
      has_more: false,
    };
  }
  const res = await client.get(`/incidents/${incidentId}/timeline${buildPaginationQuery(params)}`);
  return extractData<PaginatedResponse<TimelineEventItem>>(res);
}

export async function fetchRiskExplanationHistory(predictionId: string): Promise<SHAPHistoryResponse> {
  if (USE_SIMULATED) {
    return {
      id: 'shap-sim-1',
      risk_prediction_id: predictionId,
      horizon: 0,
      prediction: 74.0,
      base_value: 30.0,
      total_shap_delta: 44.0,
      features: {
        rainfall_intensity: 18.5,
        water_level: 14.2,
        road_congestion: 6.1,
        population_exposure: 3.8,
        infrastructure_vulnerability: 1.4,
      },
      decision_trace: [
        { feature: 'rainfall_intensity', val: 42.0, shap: 18.5, desc: 'Heavy monsoon rainfall spike' },
        { feature: 'water_level', val: 3.85, shap: 14.2, desc: 'River gauge above threshold' },
        { feature: 'road_congestion', val: 0.65, shap: 6.1, desc: 'Moderate evacuation traffic delay' },
        { feature: 'population_exposure', val: 12500, shap: 3.8, desc: 'Dense urban zone exposure' },
        { feature: 'infrastructure_vulnerability', val: 0.72, shap: 1.4, desc: 'Low-lying drainage risk' },
      ],
      created_at: new Date().toISOString(),
    };
  }
  const res = await client.get(`/risk/${predictionId}/explanation`);
  return extractData<SHAPHistoryResponse>(res);
}

// ── Phase 6.14 Spatial Intelligence API Functions ────────────────────────
import type {
  SpatialSummaryResponse, ElevationResponse, HazardLayersResponse,
  ExposureSummaryResponse, RouteSpatialSafetyResponse,
} from '../types';

export async function fetchSpatialSummary(): Promise<SpatialSummaryResponse> {
  if (USE_SIMULATED) {
    return {
      spatial_crs: 'EPSG:4326',
      projected_crs: 'EPSG:3857',
      dem_enabled: false,
      dem_source: 'unavailable',
      hazard_layers: {
        is_available: false,
        provenance: 'hazard:unavailable',
        layer_count: 0,
        hazard_features: [],
        observed_at: null,
      },
      exposure: {
        population_exposure: 12430,
        population_provenance: 'simulated',
        infrastructure_vulnerability: 0.78,
        infrastructure_provenance: 'simulated',
        hazard_layers_available: false,
        hazard_provenance: 'hazard:unavailable',
        spatial_crs: 'EPSG:4326',
        projected_crs: 'EPSG:3857',
      },
      limitation_notice: 'Provisional spatial risk layers explicitly labeled.',
    };
  }
  const res = await client.get('/spatial/summary');
  return extractData<SpatialSummaryResponse>(res);
}

export async function fetchElevation(lat: number, lng: number): Promise<ElevationResponse> {
  if (USE_SIMULATED) {
    return {
      elevation_m: null,
      slope_deg: null,
      source: 'unavailable',
      provenance: 'elevation:unavailable',
      is_available: false,
      reason: 'No real DEM dataset configured',
    };
  }
  const res = await client.get(`/spatial/elevation?lat=${lat}&lng=${lng}`);
  return extractData<ElevationResponse>(res);
}

export async function fetchHazards(): Promise<HazardLayersResponse> {
  if (USE_SIMULATED) {
    return {
      is_available: false,
      provenance: 'hazard:unavailable',
      layer_count: 0,
      hazard_features: [],
      observed_at: null,
    };
  }
  const res = await client.get('/spatial/hazards');
  return extractData<HazardLayersResponse>(res);
}

export async function fetchExposure(): Promise<ExposureSummaryResponse> {
  if (USE_SIMULATED) {
    return {
      population_exposure: 12430,
      population_provenance: 'simulated',
      infrastructure_vulnerability: 0.78,
      infrastructure_provenance: 'simulated',
      hazard_layers_available: false,
      hazard_provenance: 'hazard:unavailable',
      spatial_crs: 'EPSG:4326',
      projected_crs: 'EPSG:3857',
    };
  }
  const res = await client.get('/spatial/exposure');
  return extractData<ExposureSummaryResponse>(res);
}

export async function fetchRouteSpatialSafety(routeId: string): Promise<RouteSpatialSafetyResponse> {
  if (USE_SIMULATED) {
    return {
      route_id: routeId,
      spatial_hazard_exposure: 0.12,
      hazard_penalty: 0.04,
      modeled_safety_score: 0.88,
      water_proximity_km: 1.45,
      elevation_min_m: null,
      provenance: 'hazard:provisional_river_proximity',
      terminology_notice: 'Higher modeled route safety score indicates lower estimated spatial exposure.',
    };
  }
  const res = await client.get(`/spatial/routes/${routeId}`);
  return extractData<RouteSpatialSafetyResponse>(res);
}
