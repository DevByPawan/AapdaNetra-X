import { useSimulationStore, useToastStore } from '../../store';
import { runSimulation } from '../../services/api';
import { PanelShell, PanelHeader } from '../common/Panel';
import { LoadingSpinner } from '../common/Feedback';

export function WhatIfSimulation() {
  const {
    evacuationPace, rainfallMultiplier, drainageEfficiency, routeBlockage,
    rainfallIncrease, populationMovement, waterLevelIncrease,
    result, running,
    setEvacuationPace, setRainfallMultiplier, setDrainageEfficiency, setRouteBlockage,
    setRainfall, setPopulation, setWaterLevel,
    setResult, setRunning,
  } = useSimulationStore();
  const showToast = useToastStore(s => s.show);

  async function handleSimulate() {
    setRunning(true);
    try {
      const res = await runSimulation({
        evacuationPace,
        rainfallMultiplier,
        drainageEfficiency,
        routeBlockage,
        rainfallIncrease,
        populationMovement,
        waterLevelIncrease,
      });
      setResult(res);
      showToast('Counterfactual scenario evaluated.');
    } finally {
      setRunning(false);
    }
  }

  const baselineRisk = result?.baselineRisk ?? result?.baseline_risk ?? 74.0;
  const scenarioRisk = result?.scenarioRisk ?? result?.scenario_risk ?? result?.newRisk;
  const delta = result?.riskDelta ?? result?.risk_delta ?? (scenarioRisk != null ? Math.round((scenarioRisk - baselineRisk) * 10) / 10 : 0);

  return (
    <PanelShell>
      <PanelHeader title="What-if Simulation" sub="Scenario builder & decision support" />
      <div className="px-[14px] py-[12px] overflow-y-auto max-h-[440px]">

        {/* Sliders */}
        <div className="grid grid-cols-1 gap-[6px] text-[10px]">
          <SliderRow
            label="Rainfall increase"
            value={rainfallIncrease}
            min={0} max={100}
            display={`+${rainfallIncrease} mm/h`}
            onChange={setRainfall}
          />
          <SliderRow
            label="Rainfall multiplier"
            value={rainfallMultiplier}
            min={0.5} max={3.0} step={0.1}
            display={`${rainfallMultiplier.toFixed(1)}x`}
            onChange={setRainfallMultiplier}
          />
          <SliderRow
            label="Water level delta"
            value={waterLevelIncrease}
            min={0} max={10} step={0.5}
            display={`+${waterLevelIncrease} m`}
            onChange={setWaterLevel}
          />
          <SliderRow
            label="Drainage efficiency"
            value={drainageEfficiency}
            min={0.1} max={1.0} step={0.1}
            display={`${Math.round(drainageEfficiency * 100)}%`}
            onChange={setDrainageEfficiency}
          />
          <SliderRow
            label="Population delta"
            value={populationMovement}
            min={-5000} max={20000} step={500}
            display={`${populationMovement >= 0 ? '+' : ''}${populationMovement.toLocaleString()}`}
            onChange={setPopulation}
          />
          <SliderRow
            label="Evacuation pace"
            value={evacuationPace}
            min={0.5} max={2.0} step={0.1}
            display={`${evacuationPace.toFixed(1)}x`}
            onChange={setEvacuationPace}
          />
          <div className="flex items-center justify-between my-[4px]">
            <span className="text-ax-muted">Primary Route Blocked</span>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={routeBlockage}
                onChange={e => setRouteBlockage(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-7 h-4 bg-[#1b2b3a] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-[#b66d28]" />
            </label>
          </div>
        </div>

        {/* Run button */}
        <button
          onClick={handleSimulate}
          disabled={running}
          className="w-full mt-[10px] rounded-[8px] py-[8px] font-black text-[11px] cursor-pointer transition-all duration-150 disabled:opacity-50"
          style={{ background: '#b66d28', color: '#fff', border: 'none' }}
          onMouseEnter={e => !running && (e.currentTarget.style.background = '#d47e30')}
          onMouseLeave={e => !running && (e.currentTarget.style.background = '#b66d28')}
        >
          {running ? 'Evaluating Scenario…' : 'Run Scenario Simulation'}
        </button>

        {/* Result */}
        {running && (
          <div className="mt-3 h-12 flex items-center justify-center"><LoadingSpinner size={20} /></div>
        )}
        {result && !running && (
          <div
            className="mt-[10px] rounded-[8px] p-[10px] animate-slide-up text-[9px]"
            style={{ background: '#081522', border: '1px solid #21334a' }}
          >
            {/* Header Badge */}
            <div className="flex items-center justify-between mb-[6px] border-b border-[#1b2b3a] pb-[4px]">
              <span className="font-mono text-[8px] font-bold px-[5px] py-[2px] rounded" style={{ background: 'rgba(53,199,217,0.15)', color: '#35c7d9' }}>
                SIMULATED SCENARIO OUTPUT
              </span>
              <span
                className="text-[8px] font-bold px-[6px] py-[2px] rounded"
                style={{
                  background: result.severity === 'SEVERE' ? 'rgba(255,93,108,0.15)' : 'rgba(255,173,77,0.12)',
                  color: result.severity === 'SEVERE' ? '#ff8490' : '#ffc277',
                }}
              >
                {result.severity}
              </span>
            </div>

            {/* Risk Comparison */}
            <div className="grid grid-cols-3 gap-1 text-center my-2 bg-[#050e18] p-2 rounded border border-[#142334]">
              <div>
                <span className="text-[#8ba4be] text-[8px] block">Baseline</span>
                <b className="text-[12px] text-[#e1e9f5]">{baselineRisk.toFixed(1)}%</b>
              </div>
              <div>
                <span className="text-[#8ba4be] text-[8px] block">Scenario</span>
                <b className="text-[12px]" style={{ color: delta > 0 ? '#ff8490' : '#35c7d9' }}>{scenarioRisk?.toFixed(1)}%</b>
              </div>
              <div>
                <span className="text-[#8ba4be] text-[8px] block">Delta</span>
                <b className="text-[12px]" style={{ color: delta > 0 ? '#ff8490' : '#35c7d9' }}>{delta >= 0 ? `+${delta}` : delta}</b>
              </div>
            </div>

            {/* Conformal Uncertainty bounds if available */}
            {result.uncertainty?.scenario && (
              <div className="text-[8px] text-ax-muted my-1 font-mono">
                90% Conformal Interval: [{result.uncertainty.scenario.lower_bound.toFixed(1)}%, {result.uncertainty.scenario.upper_bound.toFixed(1)}%]
              </div>
            )}

            {/* Narrative */}
            <p className="m-0 text-[9px] text-ax-muted leading-[1.45] mb-2">{result.narrative}</p>

            {/* Routes Comparison */}
            {result.routes && (
              <div className="my-2 p-1.5 rounded bg-[#040a12] border border-[#1b2b3a] text-[8px]">
                <div className="font-bold text-[#35c7d9] mb-1">Route & Safety Evaluation</div>
                <div className="flex justify-between text-ax-muted">
                  <span>
                    Baseline: {typeof result.routes.baseline_route === 'string' ? result.routes.baseline_route : (result.routes.baseline_route?.name || 'Primary Route')}
                    {typeof result.routes.baseline_route === 'object' && result.routes.baseline_route?.eta ? ` (${result.routes.baseline_route.eta} min)` : ''}
                  </span>
                  <span>
                    Scenario: {typeof result.routes.scenario_route === 'string' ? result.routes.scenario_route : (result.routes.scenario_route?.name || 'Scenario Route')}
                    {typeof result.routes.scenario_route === 'object' && result.routes.scenario_route?.eta ? ` (${result.routes.scenario_route.eta} min)` : ''}
                  </span>
                </div>
                {result.routes.route_changed && (
                  <div className="text-[#ffc277] mt-1 font-bold">⚠ Route changed: {result.routes.reason}</div>
                )}
              </div>
            )}

            {/* SHAP Attribution Shifts */}
            {result.shap?.attribution_changes && result.shap.attribution_changes.length > 0 && (
              <div className="my-2 p-1.5 rounded bg-[#040a12] border border-[#1b2b3a] text-[8px]">
                <div className="font-bold text-[#a074ff] mb-1">Top Model Attribution Shifts</div>
                {result.shap.attribution_changes.slice(0, 2).map(shift => (
                  <div key={shift.feature} className="flex justify-between text-ax-muted my-0.5">
                    <span>{shift.feature}</span>
                    <span className={shift.shap_attribution_change >= 0 ? 'text-[#ff8490]' : 'text-[#35c7d9]'}>
                      {shift.shap_attribution_change >= 0 ? '+' : ''}{shift.shap_attribution_change.toFixed(3)} pts
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Scenario Alerts */}
            {result.alerts?.scenario_triggered_alerts && result.alerts.scenario_triggered_alerts.length > 0 && (
              <div className="my-2 p-1.5 rounded bg-[#1a080c] border border-[#4a1a24] text-[8px]">
                <div className="font-bold text-[#ff8490] mb-1">Hypothetical Scenario Alerts (Simulation Only)</div>
                {result.alerts.scenario_triggered_alerts.map(alt => (
                  <div key={alt.id} className="text-[#ffc277] my-0.5 font-mono">
                    • {alt.title}
                  </div>
                ))}
              </div>
            )}

            {/* Flagged Assets */}
            {result.flaggedAssets.length > 0 && (
              <div className="mt-[6px] text-[8px]">
                <span className="text-ax-muted">Flagged Assets: </span>
                {result.flaggedAssets.map(a => (
                  <span key={a} className="mx-1 px-[4px] py-[1px] rounded" style={{ background: 'rgba(255,93,108,0.12)', color: '#ff8490' }}>
                    {a}
                  </span>
                ))}
              </div>
            )}

            <div className="mt-2 text-[7px] text-[#55697d] italic leading-tight">
              {result.disclaimer ?? 'SIMULATED SCENARIO OUTPUT — Decision support simulation only, not an official flood forecast.'}
            </div>
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
    <div className="flex items-center justify-between my-[4px] text-[9px]">
      <span className="text-ax-muted shrink-0 mr-2 w-[100px]">{label}</span>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="flex-1"
        style={{ accentColor: '#ffad4d' }}
      />
      <span className="w-[50px] text-right font-bold text-ax-text ml-2 font-mono">{display}</span>
    </div>
  );
}
