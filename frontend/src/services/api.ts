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

// ── Simulation ───────────────────────────────────────────────────────────
export async function runSimulation(input: SimulationInput): Promise<SimulationResult> {
  if (USE_SIMULATED) {
    const { rainfallIncrease, populationMovement, waterLevelIncrease } = input;
    const newRisk = Math.min(99, 74 + Math.round(rainfallIncrease * 0.45) + Math.round(populationMovement / 1000) * 3 + Math.round(waterLevelIncrease * 0.2));
    const severe = rainfallIncrease >= 30 || populationMovement >= 3500 || waterLevelIncrease >= 40;
    return {
      newRisk,
      riskCategory: newRisk >= 90 ? 'CRITICAL' : newRisk >= 75 ? 'HIGH' : 'MODERATE',
      routeRecommendation: 'Route B',
      flaggedAssets: severe ? ['Bridge-04', 'Pump-Station-7'] : ['Bridge-04'],
      narrative: severe
        ? 'The simulation predicts severe escalation. Route A becomes unreliable; the engine switches the recommendation to Route B and flags Bridge-04 for immediate review.'
        : 'The system detects moderate additional exposure. Route B remains the preferred evacuation path, with continuous monitoring recommended.',
      severity: severe ? 'SEVERE' : newRisk > 80 ? 'MODERATE' : 'MINOR',
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
