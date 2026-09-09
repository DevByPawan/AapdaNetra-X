import type { Incident, RiskState, Forecast, RoutesData, AlertsData } from '../types';

export const simulatedIncident: Incident = {
  id: 'INC-2026-0817',
  type: 'FLOOD',
  status: 'ACTIVE',
  startedAt: '2026-09-09T08:00:00Z',
  sector: 'B',
  severity: 'HIGH',
  location: { name: 'Yamuna Floodplain — Sector B', lat: 28.6448, lng: 77.2167 },
};

export const simulatedRisk: RiskState[] = [
  {
    index: 0, label: 'NOW',
    currentRisk: 74, predictedRisk: 91, riskCategory: 'HIGH', confidence: 0.91,
    affectedPopulation: 12430, criticalPopulation: 3180, criticalAssets: 17, affectedAssets: 4,
    trend: '↑ 12% / 20 min',
    mapStatusText: 'High-risk zone expanding toward Sector B',
    predictionNote: 'Current state: Sector B is high risk and expanding.',
    heatmapZones: [
      { id: 'zone-critical', lat: 28.6448, lng: 77.2167, radiusMeters: 1100, level: 'CRITICAL' },
      { id: 'zone-high',     lat: 28.6530, lng: 77.2320, radiusMeters: 1050, level: 'HIGH' },
      { id: 'zone-moderate', lat: 28.6310, lng: 77.2450, radiusMeters:  920, level: 'MODERATE' },
      { id: 'zone-low',      lat: 28.6380, lng: 77.2050, radiusMeters:  800, level: 'LOW' },
    ],
  },
  {
    index: 1, label: '+10 MIN',
    currentRisk: 81, predictedRisk: 94, riskCategory: 'HIGH', confidence: 0.93,
    affectedPopulation: 13200, criticalPopulation: 3800, criticalAssets: 17, affectedAssets: 6,
    trend: '↑ 19% / 20 min',
    mapStatusText: 'High-risk zone expanding toward Sector B',
    predictionNote: 'Early escalation: Route A begins accumulating hazard exposure.',
    heatmapZones: [
      { id: 'zone-critical', lat: 28.6448, lng: 77.2167, radiusMeters: 1300, level: 'CRITICAL' },
      { id: 'zone-high',     lat: 28.6530, lng: 77.2320, radiusMeters: 1200, level: 'HIGH' },
      { id: 'zone-moderate', lat: 28.6310, lng: 77.2450, radiusMeters: 1050, level: 'MODERATE' },
      { id: 'zone-low',      lat: 28.6380, lng: 77.2050, radiusMeters:  850, level: 'LOW' },
    ],
  },
  {
    index: 2, label: '+20 MIN',
    currentRisk: 88, predictedRisk: 97, riskCategory: 'HIGH', confidence: 0.95,
    affectedPopulation: 14100, criticalPopulation: 4600, criticalAssets: 17, affectedAssets: 9,
    trend: '↑ 26% / 20 min',
    mapStatusText: 'Critical escalation predicted; Route A increasingly unsafe',
    predictionNote: 'Critical window: Route A failure probability rises sharply.',
    heatmapZones: [
      { id: 'zone-critical', lat: 28.6448, lng: 77.2167, radiusMeters: 1600, level: 'CRITICAL' },
      { id: 'zone-high',     lat: 28.6530, lng: 77.2320, radiusMeters: 1400, level: 'CRITICAL' },
      { id: 'zone-moderate', lat: 28.6310, lng: 77.2450, radiusMeters: 1200, level: 'HIGH' },
      { id: 'zone-low',      lat: 28.6380, lng: 77.2050, radiusMeters:  950, level: 'MODERATE' },
    ],
  },
  {
    index: 3, label: '+30 MIN',
    currentRisk: 94, predictedRisk: 99, riskCategory: 'CRITICAL', confidence: 0.97,
    affectedPopulation: 15800, criticalPopulation: 6200, criticalAssets: 17, affectedAssets: 13,
    trend: '↑ 32% / 20 min',
    mapStatusText: 'Critical escalation predicted; Route A increasingly unsafe',
    predictionNote: 'Projected peak: Sector B requires immediate evacuation.',
    heatmapZones: [
      { id: 'zone-critical', lat: 28.6448, lng: 77.2167, radiusMeters: 2000, level: 'CRITICAL' },
      { id: 'zone-high',     lat: 28.6530, lng: 77.2320, radiusMeters: 1800, level: 'CRITICAL' },
      { id: 'zone-moderate', lat: 28.6310, lng: 77.2450, radiusMeters: 1500, level: 'HIGH' },
      { id: 'zone-low',      lat: 28.6380, lng: 77.2050, radiusMeters: 1100, level: 'HIGH' },
    ],
  },
];

export const simulatedForecast: Forecast = {
  points: [
    { minutesOffset: 0,  risk: 74 },
    { minutesOffset: 10, risk: 81 },
    { minutesOffset: 20, risk: 88 },
    { minutesOffset: 30, risk: 94 },
    { minutesOffset: 45, risk: 97 },
    { minutesOffset: 60, risk: 99 },
  ],
  peakAt: '~22 min',
  trend: 'ESCALATING',
  confidence: 0.91,
  trendLabel: 'Escalating',
};

export const simulatedRoutes: RoutesData = {
  recommended: {
    id: 'route-B',
    name: 'B → E → H',
    eta: 11,
    failureProbability: 0.12,
    safetyScore: 0.88,
    waypoints: [
      { id: 'wp-B', lat: 28.6448, lng: 77.2167, label: 'Sector B (Origin)' },
      { id: 'wp-E', lat: 28.6390, lng: 77.2290, label: 'Checkpoint E' },
      { id: 'wp-H', lat: 28.6310, lng: 77.2450, label: 'SHELTER-04 (Safe Zone)' },
    ],
  },
  alternatives: [
    {
      id: 'route-A',
      name: 'A → D → H',
      eta: 8,
      failureProbability: 0.68,
      safetyScore: 0.32,
      waypoints: [
        { id: 'wp-A',  lat: 28.6530, lng: 77.2060, label: 'Sector A (Origin)' },
        { id: 'wp-D',  lat: 28.6475, lng: 77.2200, label: 'Checkpoint D (HIGH RISK)' },
        { id: 'wp-H2', lat: 28.6310, lng: 77.2450, label: 'SHELTER-04 (Safe Zone)' },
      ],
    },
  ],
  recommendation: {
    title: 'Evacuate Sector B',
    text: 'Route A is predicted to become unsafe within 15–20 minutes. Route B provides lower future hazard exposure and better shelter access.',
    confidence: 0.91,
  },
  decisionTrace: [
    { factor: 'Rainfall trend',     contribution: '+18%' },
    { factor: 'Water-level trend',  contribution: '+27%' },
    { factor: 'Predicted flooding', contribution: '+31%' },
    { factor: 'Congestion exposure',contribution: '+9%' },
  ],
};

export const simulatedAlerts: AlertsData = {
  open: 4,
  alerts: [
    { id: 'alert-001', severity: 'CRITICAL', title: 'Bridge-04 risk elevated',     description: 'Failure probability crossed 70%. Structural assessment required.',          timestamp: '2026-09-09T14:18:00Z' },
    { id: 'alert-002', severity: 'HIGH',     title: 'Sector B escalation',          description: 'Predicted risk exceeds threshold in 18 min. Evacuation recommended.',       timestamp: '2026-09-09T14:22:00Z' },
    { id: 'alert-003', severity: 'INFO',     title: 'Sensor conflict detected',     description: '2 sources disagree on water level at gauge S-21. Manual verification needed.', timestamp: '2026-09-09T14:28:00Z' },
    { id: 'alert-004', severity: 'HIGH',     title: 'Rainfall intensity spike',     description: 'Intensity increased by 34% in the last 15 minutes. Model updating.',        timestamp: '2026-09-09T14:30:00Z' },
  ],
};
