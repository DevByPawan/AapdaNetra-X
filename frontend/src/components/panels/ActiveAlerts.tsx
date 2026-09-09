import type { AlertsData } from '../../types';
import { PanelShell, PanelHeader } from '../common/Panel';
import { Badge } from '../common/Badge';
import { useAlertStore } from '../../store';
import { ALERT_COLORS } from '../../utils/riskColors';

interface ActiveAlertsProps {
  alertsData: AlertsData;
}

export function ActiveAlerts({ alertsData }: ActiveAlertsProps) {
  const { dismissed, dismiss } = useAlertStore();

  const visible = alertsData.alerts.filter(a => !dismissed.has(a.id));

  return (
    <PanelShell>
      <PanelHeader
        title="Active Alerts"
        right={<Badge variant="HIGH">{visible.length} OPEN</Badge>}
      />
      <div className="px-[14px] pb-[14px]">
        {visible.length === 0 && (
          <div className="py-6 text-center text-ax-muted text-[11px]">
            ✓ All alerts cleared
          </div>
        )}
        {visible.map((alert, idx) => (
          <div
            key={alert.id}
            className="flex gap-[9px] py-[9px] group cursor-pointer"
            style={{ borderBottom: idx < visible.length - 1 ? '1px solid #1a2a3d' : 'none' }}
            onClick={() => dismiss(alert.id)}
            title="Click to dismiss"
          >
            <i
              className="w-2 h-2 rounded-full shrink-0 mt-1"
              style={{ background: ALERT_COLORS[alert.severity] }}
            />
            <div className="flex-1 min-w-0">
              <b className="text-[9px] text-ax-text block">{alert.title}</b>
              <p className="m-0 mt-[2px] text-ax-muted text-[8px] leading-[1.45]">
                {alert.description}
              </p>
            </div>
            <span className="text-[8px] text-ax-muted opacity-0 group-hover:opacity-100 transition-opacity shrink-0 self-start mt-[2px]">
              ✕
            </span>
          </div>
        ))}
      </div>
    </PanelShell>
  );
}
