import { useSimulationStore, useToastStore } from '../../store';
import { runSimulation } from '../../services/api';
import { PanelShell, PanelHeader } from '../common/Panel';
import { LoadingSpinner } from '../common/Feedback';

export function WhatIfSimulation() {
  const {
    rainfallIncrease, populationMovement, waterLevelIncrease,
    result, running,
    setRainfall, setPopulation, setWaterLevel,
    setResult, setRunning,
  } = useSimulationStore();
  const showToast = useToastStore(s => s.show);

  async function handleSimulate() {
    setRunning(true);
    try {
      const res = await runSimulation({ rainfallIncrease, populationMovement, waterLevelIncrease });
      setResult(res);
      showToast('Counterfactual scenario evaluated.');
    } finally {
      setRunning(false);
    }
  }

  return (
    <PanelShell>
      <PanelHeader title="What-if Simulation" sub="Scenario builder" />
      <div className="px-[14px] py-[12px]">

        {/* Rainfall slider */}
        <SliderRow
          label="Rainfall increase"
          value={rainfallIncrease}
          min={0} max={50}
          display={`+${rainfallIncrease}%`}
          onChange={setRainfall}
        />

        {/* Population slider */}
        <SliderRow
          label="Population movement"
          value={populationMovement}
          min={0} max={5000} step={500}
          display={`+${populationMovement.toLocaleString()}`}
          onChange={setPopulation}
        />

        {/* Water level slider (new vs prototype) */}
        <SliderRow
          label="Water-level increase"
          value={waterLevelIncrease}
          min={0} max={100} step={5}
          display={`+${waterLevelIncrease} cm`}
          onChange={setWaterLevel}
        />

        {/* Run button */}
        <button
          onClick={handleSimulate}
          disabled={running}
          className="w-full mt-[10px] rounded-[8px] py-[10px] font-black text-[12px] cursor-pointer transition-all duration-150 disabled:opacity-50"
          style={{ background: '#b66d28', color: '#fff', border: 'none' }}
          onMouseEnter={e => !running && (e.currentTarget.style.background = '#d47e30')}
          onMouseLeave={e => !running && (e.currentTarget.style.background = '#b66d28')}
        >
          {running ? 'Running…' : 'Run Scenario Simulation'}
        </button>

        {/* Result */}
        {running && (
          <div className="mt-3 h-12"><LoadingSpinner size={20} /></div>
        )}
        {result && !running && (
          <div
            className="mt-[10px] rounded-[8px] p-[10px] animate-slide-up"
            style={{ background: '#081522', border: '1px solid #21334a' }}
          >
            <div className="flex items-center justify-between mb-[6px]">
              <b className="text-[10px] text-ax-text">
                Scenario outcome · Risk {result.newRisk}%
              </b>
              <span
                className="text-[8px] font-bold px-[6px] py-[3px] rounded"
                style={{
                  background: result.severity === 'SEVERE' ? 'rgba(255,93,108,0.15)' : 'rgba(255,173,77,0.12)',
                  color: result.severity === 'SEVERE' ? '#ff8490' : '#ffc277',
                }}
              >
                {result.severity}
              </span>
            </div>
            <p className="m-0 text-[9px] text-ax-muted leading-[1.45]">{result.narrative}</p>
            {result.flaggedAssets.length > 0 && (
              <div className="mt-[8px] text-[8px]">
                <span className="text-ax-muted">Flagged: </span>
                {result.flaggedAssets.map(a => (
                  <span key={a} className="mx-1 px-[5px] py-[2px] rounded" style={{ background: 'rgba(255,93,108,0.12)', color: '#ff8490' }}>
                    {a}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </PanelShell>
  );
}

interface SliderRowProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  display: string;
  onChange: (v: number) => void;
}

function SliderRow({ label, value, min, max, step = 1, display, onChange }: SliderRowProps) {
  return (
    <div className="flex items-center justify-between my-[10px] text-[10px]">
      <span className="text-ax-muted shrink-0 mr-2">{label}</span>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="flex-1"
        style={{ accentColor: '#ffad4d' }}
      />
      <span className="w-[52px] text-right font-extrabold text-ax-text ml-2">{display}</span>
    </div>
  );
}
