import type { RiskLevel, AlertSeverity } from '../types';

export const RISK_COLORS: Record<RiskLevel, string> = {
  CRITICAL: '#ff5d6c',
  HIGH:     '#ffad4d',
  MODERATE: '#f4d35e',
  LOW:      '#4bd39b',
};

export const RISK_BG: Record<RiskLevel, string> = {
  CRITICAL: 'rgba(255,93,108,0.13)',
  HIGH:     'rgba(255,173,77,0.12)',
  MODERATE: 'rgba(244,211,94,0.12)',
  LOW:      'rgba(75,211,155,0.12)',
};

export const RISK_TEXT: Record<RiskLevel, string> = {
  CRITICAL: '#ff8490',
  HIGH:     '#ffc277',
  MODERATE: '#f7e08a',
  LOW:      '#6fe4b0',
};

export const ALERT_COLORS: Record<AlertSeverity, string> = {
  CRITICAL: '#ff5d6c',
  HIGH:     '#ffad4d',
  MODERATE: '#f4d35e',
  INFO:     '#35c7d9',
};

export function getRiskColor(level: RiskLevel): string {
  return RISK_COLORS[level] ?? RISK_COLORS.LOW;
}

export function formatRisk(value: number): string {
  return `${value}%`;
}

export function formatPopulation(value: number): string {
  return value.toLocaleString();
}

export function formatTime(isoString: string): string {
  return new Date(isoString).toLocaleTimeString('en-GB', { hour12: false });
}
