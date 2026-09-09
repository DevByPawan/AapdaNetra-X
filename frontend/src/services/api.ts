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
