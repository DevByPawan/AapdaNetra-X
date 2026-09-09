import type { RiskLevel, AlertSeverity } from '../../types';
import { RISK_BG, RISK_TEXT, ALERT_COLORS } from '../../utils/riskColors';

type BadgeVariant = RiskLevel | AlertSeverity | 'CONF';

interface BadgeProps {
  variant: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

const variantStyles: Record<string, { bg: string; color: string }> = {
  CRITICAL: { bg: 'rgba(255,93,108,0.13)',  color: '#ff8490' },
  HIGH:     { bg: 'rgba(255,173,77,0.12)',  color: '#ffc277' },
  MODERATE: { bg: 'rgba(244,211,94,0.12)',  color: '#f7e08a' },
  LOW:      { bg: 'rgba(75,211,155,0.12)',  color: '#6fe4b0' },
  INFO:     { bg: 'rgba(53,199,217,0.12)',  color: '#35c7d9' },
  CONF:     { bg: 'rgba(75,211,155,0.12)',  color: '#6fe4b0' },
};

export function Badge({ variant, children, className = '' }: BadgeProps) {
  const s = variantStyles[variant] ?? variantStyles.LOW;
  return (
    <span
      className={`inline-flex items-center px-[7px] py-[4px] rounded-[5px] text-[9px] font-extrabold tracking-wide ${className}`}
      style={{ background: s.bg, color: s.color }}
    >
      {children}
    </span>
  );
}
