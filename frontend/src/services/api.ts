import axios from 'axios';
import type {
  Incident, RiskState, Forecast, RoutesData, EvacRoute,
  AlertsData, SimulationInput, SimulationResult, ApiResponse,
  DecisionSupportData, DecisionActionRequest, DecisionActionResponse,
  EvacuationIntelligenceData, TelemetryIngestionRequestData, TelemetryIngestionResponseData,
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
  const rawData = extractData<any>(res);

  const normalizeRoute = (r: any): EvacRoute => {
    if (!r) {
      return {
        id: '',
        name: 'Primary Evacuation Route',
        eta: 0,
        failureProbability: 0,
        failure_probability: 0,
        safetyScore: 1.0,
        safety_score: 1.0,
        waypoints: [],
      };
    }
    if (typeof r === 'string') {
      return {
        id: r,
        name: r,
        eta: 0,
        failureProbability: 0,
        failure_probability: 0,
        safetyScore: 1.0,
        safety_score: 1.0,
        waypoints: [],
      };
    }
    const failureProbability = r.failureProbability ?? r.failure_probability ?? 0;
    const safetyScore = r.safetyScore ?? r.safety_score ?? (1 - failureProbability);
    const isBlocked = r.isBlocked ?? r.is_blocked ?? false;
    const distanceKm = r.distanceKm ?? r.distance_km ?? 0;
    const riskScore = r.riskScore ?? r.risk_score ?? 0;
    const eta = r.eta ?? r.eta_minutes ?? 0;

    return {
      ...r,
      id: r.id ?? '',
      name: typeof r.name === 'string' ? r.name : (r.name?.name || 'Evacuation Route'),
      eta,
      eta_minutes: eta,
      failureProbability,
      failure_probability: failureProbability,
      safetyScore,
      safety_score: safetyScore,
      distanceKm,
      distance_km: distanceKm,
      riskScore,
      risk_score: riskScore,
      isBlocked,
      is_blocked: isBlocked,
      waypoints: Array.isArray(r.waypoints) ? r.waypoints : [],
    };
  };

  return {
    ...rawData,
    recommended: normalizeRoute(rawData.recommended),
    alternatives: Array.isArray(rawData.alternatives)
      ? rawData.alternatives.map(normalizeRoute)
      : [],
    recommendation: rawData.recommendation || {
      title: 'Evacuate Sector B',
      text: 'Route optimization active.',
      confidence: 0.95,
    },
    decisionTrace: rawData.decisionTrace || rawData.decision_trace || [],
  };
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

// ── Approve response (Preserved Phase 6 legacy endpoint) ──────────────────
export async function approveResponse(incidentId: string): Promise<{ approved: boolean; workflowId: string }> {
  if (USE_SIMULATED) return { approved: true, workflowId: 'WF-' + Date.now() };
  const res = await client.post('/response/approve', { incidentId, responderId: 'OPERATOR-01' });
  return extractData<{ approved: boolean; workflowId: string }>(res);
}

// ── Phase 6.17 Decision Support APIs ──────────────────────────────────────
export async function fetchDecisionRecommendation(incidentId?: string): Promise<DecisionSupportData> {
  if (USE_SIMULATED) {
    return {
      decision_id: 'dec-sim-' + Date.now(),
      incident_id: incidentId || 'INC-2026-DEFAULT',
      status: 'RECOMMENDED',
      recommended_action: 'Initiate priority evacuation via Route A and dispatch mobile pump units.',
      priority: 'HIGH',
      risk_score: 74.0,
      risk_interval: {
        lower_bound: 67.4,
        upper_bound: 80.6,
        nominal_coverage: 0.90,
        uncertainty_width: 13.2,
      },
      risk_category: 'HIGH',
      evidence: [
        { feature: 'rainfall_intensity', contribution_text: '+12.4 points' },
        { feature: 'water_level', contribution_text: '+10.1 points' },
      ],
      contributing_factors: { rainfall_intensity: 12.4, water_level: 10.1 },
      spatial_context: {
        population_exposure: 450,
        infrastructure_vulnerability: 0.65,
        route_spatial_hazard: 0.08,
        provenance: 'dem:copernicus_glo_30,exposure:ghsl_2025,hazard:provisional_river_proximity',
      },
      route_recommendation: 'Route A (Northern Bypass)',
      route_safety: 0.88,
      route_eta: 12,
      active_alerts: [{ id: 'alt-1', title: 'High Water Level Warning', severity: 'HIGH' }],
      data_freshness: {
        telemetry_age_seconds: 45,
        provenance: 'sensor:water_level_probe_01',
        is_stale: false,
      },
      provenance: 'engine:decision_service_v1,model:gbr_v1,uncertainty:split_conformal,dem:copernicus_glo_30',
      rationale: 'Elevated risk score (74.00) with 90% conformal interval [67.40, 80.60] warrants high-priority action.',
      limitations: 'AI-assisted decision-support recommendation only. Mandatory human approval required.',
      generated_at: new Date().toISOString(),
      source: 'AapdaNetra-X Decision Support Engine',
      version: '6.17.0',
    };
  }
  const url = incidentId ? `/decision/recommend?incident_id=${encodeURIComponent(incidentId)}` : '/decision/recommend';
  const res = await client.get(url);
  return extractData<DecisionSupportData>(res);
}

export async function approveDecision(req: DecisionActionRequest): Promise<DecisionActionResponse> {
  if (USE_SIMULATED) {
    return {
      decision_id: req.decision_id,
      incident_id: 'INC-2026-DEFAULT',
      status: 'APPROVED',
      responder_id: req.responder_id || 'OPERATOR-01',
      reason: req.reason || 'Approved by operator',
      timestamp: new Date().toISOString(),
      audit_id: 'audit-sim-' + Date.now(),
      sse_published: true,
    };
  }
  const res = await client.post('/decision/approve', req);
  return extractData<DecisionActionResponse>(res);
}

export async function rejectDecision(req: DecisionActionRequest): Promise<DecisionActionResponse> {
  if (USE_SIMULATED) {
    return {
      decision_id: req.decision_id,
      incident_id: 'INC-2026-DEFAULT',
      status: 'REJECTED',
      responder_id: req.responder_id || 'OPERATOR-01',
      reason: req.reason || 'Rejected by operator',
      timestamp: new Date().toISOString(),
      audit_id: 'audit-sim-' + Date.now(),
      sse_published: false,
    };
  }
  const res = await client.post('/decision/reject', req);
  return extractData<DecisionActionResponse>(res);
}

// ── Phase 6.18 Dynamic Evacuation Intelligence APIs ──────────────────────
export async function fetchEvacuationRecommendation(incidentId?: string, horizon: number = 0): Promise<EvacuationIntelligenceData> {
  if (USE_SIMULATED) {
    return {
      incident_id: incidentId || 'INC-2026-DEFAULT',
      horizon,
      recommended_route: {
        id: 'route-rec',
        name: 'Sector B → Northern Bypass → SHELTER-04',
        eta: 12,
        distance_km: 4.2,
        safety_score: 0.88,
        failure_probability: 0.12,
        risk_score: 18.0,
        status: 'SAFE',
        is_blocked: false,
        score_details: {
          safety_score: 0.88,
          spatial_hazard_penalty: 3.0,
          congestion_penalty: 2.4,
          eta_penalty: 3.0,
          blockage_penalty: 0.0,
          composite_score: 79.6,
        },
        spatial_hazard_exposure: 0.08,
        waypoints: [
          { id: 'wp-B', lat: 28.6448, lng: 77.2167, label: 'Sector B (Origin)' },
          { id: 'wp-[#1]', lat: 28.6530, lng: 77.2280, label: 'Northern Bypass' },
          { id: 'wp-H', lat: 28.6310, lng: 77.2450, label: 'SHELTER-04 (Safe Zone)' },
        ],
        nodes: ['Sector_B', 'Checkpoint_D', 'Shelter_H'],
        selection_reason: 'Route offers optimal safety (88%) and minimal spatial hazard exposure.',
      },
      alternative_routes: [
        {
          id: 'route-alt-1',
          name: 'Sector B → Southern Link → SHELTER-04',
          eta: 16,
          distance_km: 5.1,
          safety_score: 0.64,
          failure_probability: 0.36,
          risk_score: 42.0,
          status: 'CAUTION',
          is_blocked: false,
          score_details: {
            safety_score: 0.64,
            spatial_hazard_penalty: 6.0,
            congestion_penalty: 7.2,
            eta_penalty: 9.0,
            blockage_penalty: 0.0,
            composite_score: 41.8,
          },
          spatial_hazard_exposure: 0.20,
          waypoints: [
            { id: 'wp-B', lat: 28.6448, lng: 77.2167, label: 'Sector B (Origin)' },
            { id: 'wp-[#2]', lat: 28.6320, lng: 77.2150, label: 'Southern Link' },
            { id: 'wp-H', lat: 28.6310, lng: 77.2450, label: 'SHELTER-04 (Safe Zone)' },
          ],
          nodes: ['Sector_B', 'Checkpoint_F', 'Shelter_H'],
          selection_reason: 'Route is viable but requires caution due to moderate spatial hazard exposure.',
        },
      ],
      route_change: {
        route_changed: false,
        previous_route_id: null,
        new_route_id: 'route-rec',
        change_reason: null,
      },
      overall_status_warning: null,
      all_routes_unsafe: false,
      active_risk_score: 74.0,
      active_risk_category: 'HIGH',
      data_freshness: {
        provider: 'default',
        fallback_used: false,
        observed_at: new Date().toISOString(),
      },
      decision_trace: [
        { factor: 'Recommended Route', value: 'Sector B → Northern Bypass → SHELTER-04', impact: 'Status: SAFE' },
        { factor: 'Composite Route Score', value: '79.6 / 100', impact: 'Highest ranked candidate' },
      ],
      provenance: 'routing:networkx_dijkstra,dem:copernicus_glo_30,hazard:provisional_river_proximity,telemetry:default',
      generated_at: new Date().toISOString(),
      label: 'AI-assisted dynamic evacuation decision-support intelligence',
    };
  }
  const url = `/evacuation/recommendation?incident_id=${encodeURIComponent(incidentId || 'INC-2026-DEFAULT')}&horizon=${horizon}`;
  const res = await client.get(url);
  return extractData<EvacuationIntelligenceData>(res);
}

export async function recomputeEvacuationRoutes(incidentId?: string, horizon: number = 0, routeBlockageOverride?: boolean): Promise<EvacuationIntelligenceData> {
  if (USE_SIMULATED) {
    return fetchEvacuationRecommendation(incidentId, horizon);
  }
  const res = await client.post('/evacuation/recompute', {
    incident_id: incidentId || 'INC-2026-DEFAULT',
    horizon,
    route_blockage_override: routeBlockageOverride,
    publish_sse: true,
  });
  return extractData<EvacuationIntelligenceData>(res);
}

// ── Phase 6.19 Real-Time Telemetry APIs ───────────────────────────────────
export async function sendTelemetryObservation(req: TelemetryIngestionRequestData): Promise<TelemetryIngestionResponseData> {
  if (USE_SIMULATED) {
    const hash = 'sim-hash-' + Date.now();
    return {
      status: 'accepted',
      observation_id: 'obs-' + hash.slice(-8),
      incident_id: req.incident_id || 'INC-2026-DEFAULT',
      sensor_id: req.sensor_id || 'SENSOR-01',
      observation_hash: hash,
      observed_at: req.observed_at || new Date().toISOString(),
      ingested_at: new Date().toISOString(),
      features: req.features,
      trends: {},
      provenance: { rainfall_intensity: 'live_ingest' },
      persistence_status: 'simulated',
      cascade_triggered: true,
      message: 'Telemetry observation ingested successfully (simulated).',
    };
  }
  const res = await client.post('/telemetry/observe', req);
  return extractData<TelemetryIngestionResponseData>(res);
}

export async function fetchLiveTelemetry(): Promise<any> {
  if (USE_SIMULATED) {
    return {
      active_features: { rainfall_intensity: 95.0, water_level: 6.8 },
      provenance: { rainfall_intensity: 'simulated' },
      fallback_used: false,
    };
  }
  const res = await client.get('/telemetry/live');
  return extractData<any>(res);
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
