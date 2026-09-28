import { useState } from 'react';
import { useClock } from '../../hooks/useClock';
import type { Incident } from '../../types';
import { UnifiedTimeline } from '../panels/UnifiedTimeline';

interface HeaderProps {
  incident: Incident | null;
}

export function Header({ incident }: HeaderProps) {
  const time = useClock();
  const [showTimelineDrawer, setShowTimelineDrawer] = useState(false);

  return (
    <header className="flex justify-between items-center mb-[18px]">
      <div className="text-ax-muted text-[12px] tracking-wide">
        COMMAND CENTER /{' '}
        <strong className="text-[#dbe8f4]">
          {incident ? `${incident.type} INCIDENT` : 'LOADING…'}
        </strong>
      </div>

      <div className="flex items-center gap-[12px]">
        <button
          onClick={() => setShowTimelineDrawer(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-[8px] text-[11px] font-bold bg-line/80 hover:bg-line text-ax-text border border-line cursor-pointer transition-all hover:border-ax-cyan/50"
        >
          <span>📜</span> Unified Timeline
        </button>

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

      {/* Timeline Drawer Modal */}
      {showTimelineDrawer && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/70 backdrop-blur-xs animate-fade-in"
          onClick={() => setShowTimelineDrawer(false)}
        >
          <div
            className="w-full max-w-xl h-full bg-panel border-l border-line p-4 shadow-2xl overflow-hidden animate-slide-up"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 border-b border-line mb-3">
              <span className="text-[14px] font-bold text-ax-text">Incident Timeline Drawer</span>
              <button
                onClick={() => setShowTimelineDrawer(false)}
                className="w-7 h-7 rounded-full border border-line flex items-center justify-center text-ax-muted hover:text-white cursor-pointer"
              >
                ✕
              </button>
            </div>
            <div className="h-[calc(100%-50px)]">
              <UnifiedTimeline incidentId={incident?.id || 'INC-2026-DEFAULT'} />
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
