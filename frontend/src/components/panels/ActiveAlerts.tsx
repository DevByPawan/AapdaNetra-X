import type { AlertsData, Alert } from '../../types';
import { PanelShell, PanelHeader } from '../common/Panel';
import { Badge } from '../common/Badge';
import { useAlertStore } from '../../store';
import { ALERT_COLORS } from '../../utils/riskColors';
import { acknowledgeAlert } from '../../services/api';

interface ActiveAlertsProps {
  alertsData: AlertsData;
}

export function ActiveAlerts({ alertsData }: ActiveAlertsProps) {
  const { dismissed, dismiss } = useAlertStore();

  const visible = alertsData.alerts.filter(a => !dismissed.has(a.id));

  const handleDismiss = async (alert: Alert) => {
    dismiss(alert.id);
    try {
      await acknowledgeAlert(alert.id);
    } catch {
      // Ignored for UI responsiveness
    }
  };

  return (
    <PanelShell>
      <PanelHeader
        title="Active Alerts"
        right={<Badge variant="HIGH">{visible.length} OPEN</Badge>}
      />
      <div className="px-[14px] pb-[14px] max-h-[280px] overflow-y-auto">
        {visible.length === 0 && (
          <div className="py-6 text-center text-ax-muted text-[11px]">
            ✓ All alerts cleared
          </div>
        )}
        {visible.map((alert, idx) => {
          const isProvisional = alert.metadata?.is_provisional || alert.title.includes('PROVISIONAL') || alert.description.includes('PROVISIONAL');
          const source = alert.source || 'system';
          const unc = alert.metadata?.uncertainty;

          return (
            <div
              key={alert.id}
              className="flex gap-[9px] py-[9px] group cursor-pointer"
              style={{ borderBottom: idx < visible.length - 1 ? '1px solid #1a2a3d' : 'none' }}
              onClick={() => handleDismiss(alert)}
              title="Click to acknowledge/dismiss"
            >
              <i
                className="w-2 h-2 rounded-full shrink-0 mt-1"
                style={{ background: ALERT_COLORS[alert.severity] || '#35c7d9' }}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-[6px] flex-wrap">
                  <b className="text-[9px] text-ax-text">{alert.title}</b>
                  {isProvisional && (
                    <span className="text-[7px] bg-[#d97706]/30 text-[#fde68a] border border-[#d97706] px-[4px] py-[1px] rounded font-bold">
                      PROVISIONAL
                    </span>
                  )}
                  <span className="text-[7px] text-[#6b7c93] bg-[#0c1827] px-[4px] py-[1px] rounded border border-[#1e2d42]">
                    {source}
                  </span>
                </div>

                <p className="m-0 mt-[3px] text-ax-muted text-[8px] leading-[1.45]">
                  {alert.description}
                </p>

                {unc && unc.lower_bound !== undefined && (
                  <div className="mt-[3px] text-[7px] text-[#8fe6ef]">
                    90% Conformal Interval: [{unc.lower_bound?.toFixed(1)}, {unc.upper_bound?.toFixed(1)}]
                  </div>
                )}
              </div>

              <span className="text-[8px] text-ax-muted opacity-0 group-hover:opacity-100 transition-opacity shrink-0 self-start mt-[2px]">
                ✕
              </span>
            </div>
          );
        })}
      </div>
    </PanelShell>
  );
}
