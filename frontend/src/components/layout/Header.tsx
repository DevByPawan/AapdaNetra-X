import { useClock } from '../../hooks/useClock';
import type { Incident } from '../../types';

interface HeaderProps {
  incident: Incident | null;
}

export function Header({ incident }: HeaderProps) {
  const time = useClock();

  return (
    <header className="flex justify-between items-center mb-[18px]">
      <div className="text-ax-muted text-[12px] tracking-wide">
        COMMAND CENTER /{' '}
        <strong className="text-[#dbe8f4]">
          {incident ? `${incident.type} INCIDENT` : 'LOADING…'}
        </strong>
      </div>

      <div className="flex items-center gap-[12px]">
        {incident && (
          <div className="text-[12px] text-[#c8d6e3] font-mono">{incident.id}</div>
        )}
        <div className="flex items-center gap-[10px] text-[11px] text-[#a9bdcf]">
          <span
            className="w-2 h-2 rounded-full animate-pulse-dot"
            style={{ background: '#4bd39b' }}
          />
          LIVE
        </div>
        <div
          className="font-bold text-white tabular-nums"
          style={{ fontVariantNumeric: 'tabular-nums' }}
        >
          {time}
        </div>
      </div>
    </header>
  );
}
