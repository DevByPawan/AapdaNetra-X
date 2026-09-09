import type { RiskState } from '../../types';
import { PanelShell, PanelHeader } from '../common/Panel';
import { Badge } from '../common/Badge';

interface MetricCardProps {
  label: string;
  value: string;
  sub: string;
}

function MetricCard({ label, value, sub }: MetricCardProps) {
  return (
    <div className="rounded-[9px] p-3" style={{ background: '#0b1829', border: '1px solid #1b2d43' }}>
      <small className="block text-ax-muted text-[9px] uppercase tracking-[0.6px]">{label}</small>
      <strong className="block text-[20px] mt-[5px] text-ax-text">{value}</strong>
      <em className="not-italic text-[9px] text-ax-muted">{sub}</em>
    </div>
  );
}

interface IncidentOverviewProps {
  riskState: RiskState;
}

export function IncidentOverview({ riskState }: IncidentOverviewProps) {
  return (
    <PanelShell>
      <PanelHeader
        title="Incident Overview"
        right={<Badge variant={riskState.riskCategory}>{riskState.riskCategory}</Badge>}
      />
      <div className="grid grid-cols-2 gap-[10px] p-[14px]">
        <MetricCard
          label="Current Risk"
          value={`${riskState.currentRisk}%`}
          sub={riskState.trend}
        />
        <MetricCard
          label="Population at Risk"
          value={riskState.affectedPopulation.toLocaleString()}
          sub={`${riskState.criticalPopulation.toLocaleString()} critical`}
        />
        <MetricCard
          label="Forecast"
          value={`${riskState.predictedRisk}%`}
          sub={`peak in ~22 min`}
        />
        <MetricCard
          label="Critical Assets"
          value={String(riskState.criticalAssets)}
          sub={`${riskState.affectedAssets} affected`}
        />
      </div>
    </PanelShell>
  );
}
