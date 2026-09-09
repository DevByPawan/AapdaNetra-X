import { useMapStore } from '../../store';
import { PanelShell, PanelHeader } from '../common/Panel';
import type { RiskState } from '../../types';

const HORIZON_LABELS = ['NOW', '+10M', '+20M', '+30M'];

interface TimeHorizonSliderProps {
  riskState: RiskState;
}

export function TimeHorizonSlider({ riskState }: TimeHorizonSliderProps) {
  const { timeHorizon, setHorizon } = useMapStore();

  return (
    <PanelShell>
      <PanelHeader title="Time Horizon" sub="Predictive view" />
      <div className="px-[14px] py-[12px]">
        {/* Current label */}
        <div className="flex justify-between text-[10px] mb-2">
          <b className="text-ax-text">{riskState.label}</b>
          <span className="text-ax-muted">Move to inspect predicted state</span>
        </div>

        {/* Slider */}
        <input
          type="range"
          min={0} max={3} step={1}
          value={timeHorizon}
          onChange={e => setHorizon(Number(e.target.value))}
          className="w-full accent-cyan"
          style={{ accentColor: '#35c7d9' }}
        />

        {/* Labels */}
        <div className="flex justify-between text-[8px] text-ax-muted mt-[5px]">
          {HORIZON_LABELS.map(l => (
            <span key={l}>{l}</span>
          ))}
        </div>

        {/* Prediction note */}
        <div
          className="mt-3 rounded-[8px] p-[10px] text-[9px] leading-[1.5]"
          style={{ background: '#081522', color: '#9eb1c2' }}
        >
          {riskState.predictionNote}
        </div>

        {/* Horizon risk indicators */}
        <div className="grid grid-cols-4 gap-[6px] mt-3">
          {[0, 1, 2, 3].map(i => {
            const risks = [74, 81, 88, 94];
            const isActive = i === timeHorizon;
            return (
              <button
                key={i}
                onClick={() => setHorizon(i)}
                className="rounded-[6px] py-[6px] text-[8px] font-bold transition-all duration-150 cursor-pointer"
                style={{
                  background: isActive ? 'rgba(53,199,217,0.15)' : '#081522',
                  border: `1px solid ${isActive ? '#35c7d9' : '#21334a'}`,
                  color: isActive ? '#35c7d9' : '#8fa3b8',
                }}
              >
                {HORIZON_LABELS[i]}
                <span className="block text-[10px] font-extrabold" style={{ color: isActive ? '#fff' : '#8fa3b8' }}>
                  {risks[i]}%
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </PanelShell>
  );
}
