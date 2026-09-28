import { useEffect, useState } from 'react';
import type { TimelineEventItem } from '../types';

export function getEventDedupeKey(item: TimelineEventItem): string {
  const entityType = item.entity_type || 'unknown';
  const entityId = item.entity_id || 'unknown';
  const eventType = item.event_type || 'unknown';
  let tsStr = item.timestamp;
  try {
    const d = new Date(item.timestamp);
    if (!isNaN(d.getTime())) {
      tsStr = d.toISOString();
    }
  } catch {
    // Keep raw string if unparseable
  }
  return `${entityType}:${entityId}:${eventType}:${tsStr}`;
}

export function useEventStream(onEvent?: (event: TimelineEventItem) => void) {
  const [connected, setConnected] = useState<boolean>(false);

  useEffect(() => {
    // Disable SSE streaming if VITE_USE_SIMULATED is true
    if (import.meta.env.VITE_USE_SIMULATED === 'true') {
      setConnected(true);
      return;
    }

    let eventSource: EventSource | null = null;
    try {
      eventSource = new EventSource('/api/events/stream');

      eventSource.onopen = () => {
        setConnected(true);
      };

      eventSource.onerror = () => {
        setConnected(false);
      };

      const handleEventMessage = (event: MessageEvent) => {
        try {
          const raw = JSON.parse(event.data);
          const normalized = normalizeSseEvent(raw);
          if (normalized && onEvent) {
            onEvent(normalized);
          }
        } catch {
          // Ignore malformed message frames
        }
      };

      eventSource.addEventListener('telemetry.updated', handleEventMessage);
      eventSource.addEventListener('risk.updated', handleEventMessage);
      eventSource.addEventListener('route.updated', handleEventMessage);
      eventSource.addEventListener('alert.created', handleEventMessage);
      eventSource.addEventListener('simulation.completed', handleEventMessage);
      eventSource.addEventListener('decision.approved', handleEventMessage);
    } catch {
      setConnected(false);
    }

    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [onEvent]);

  return { connected };
}

export function normalizeSseEvent(data: any): TimelineEventItem | null {
  if (!data || typeof data !== 'object') return null;

  const eventType = data.event || data.event_type || 'UNKNOWN';
  const payload = data.data || data.payload || {};
  const incidentId = data.incident_id || payload.incident_id || 'INC-2026-DEFAULT';
  const entityId = payload.id || payload.entity_id || data.id || `sse-${Date.now()}`;
  const timestamp = payload.observed_at || payload.created_at || data.timestamp || new Date().toISOString();

  switch (eventType) {
    case 'telemetry.updated':
      return {
        timestamp,
        event_type: 'TELEMETRY_OBSERVED',
        entity_type: 'telemetry_observation',
        entity_id: String(entityId),
        incident_id: incidentId,
        summary: `Telemetry observed — Rainfall ${payload.rainfall_intensity ?? 0} mm/h, Water level ${payload.water_level ?? 0} m`,
        details: payload,
      };

    case 'risk.updated':
      return {
        timestamp,
        event_type: 'RISK_EVALUATED',
        entity_type: 'risk_prediction',
        entity_id: String(entityId),
        incident_id: incidentId,
        summary: `Risk evaluated — Score ${payload.predicted_risk ?? payload.predictedRisk ?? 0} (${payload.risk_category ?? payload.riskCategory ?? 'HIGH'})`,
        details: payload,
      };

    case 'route.updated':
      return {
        timestamp,
        event_type: 'ROUTE_UPDATED',
        entity_type: 'evacuation_route',
        entity_id: String(entityId),
        incident_id: incidentId,
        summary: `Evacuation route calculated — ${payload.route_name || payload.name || 'Primary Route'} (${payload.distance_km || 0} km)`,
        details: payload,
      };

    case 'alert.created':
      return {
        timestamp,
        event_type: 'ALERT_CREATED',
        entity_type: 'alert',
        entity_id: String(entityId),
        incident_id: incidentId,
        summary: `Alert created — ${payload.title || 'Emergency Alert'} (${payload.severity || 'HIGH'})`,
        details: payload,
      };

    case 'simulation.completed':
      return {
        timestamp,
        event_type: 'SIMULATION_COMPLETED',
        entity_type: 'simulation',
        entity_id: String(entityId),
        incident_id: incidentId,
        summary: `Simulation completed — Scenario risk ${payload.scenario_risk ?? payload.newRisk ?? 0}`,
        details: payload,
      };

    case 'decision.approved':
      return {
        timestamp,
        event_type: 'DECISION_APPROVED',
        entity_type: 'audit_event',
        entity_id: String(entityId),
        incident_id: incidentId,
        summary: `Response workflow approved (${payload.workflowId || 'WF-APPROVED'})`,
        details: payload,
      };

    default:
      return null;
  }
}
