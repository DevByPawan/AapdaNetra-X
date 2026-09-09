import { useState } from 'react';
import type { RoutesData } from '../../types';
import { PanelShell, PanelHeader } from '../common/Panel';
import { Badge } from '../common/Badge';
import { useToastStore } from '../../store';
import { approveResponse } from '../../services/api';

interface AIRecommendationProps {
  routesData: RoutesData;
  incidentId: string;
}

export function AIRecommendation({ routesData, incidentId }: AIRecommendationProps) {
  const [showTrace, setShowTrace] = useState(false);
  const showToast = useToastStore(s => s.show);

  const { recommendation, recommended, decisionTrace } = routesData;
  const confPct = Math.round(recommendation.confidence * 100);

  async function handleApprove() {
    setShowTrace(v => !v);
    await approveResponse(incidentId);
    showToast('Response plan approved — evacuation workflow initiated.');
  }

  return (
    <PanelShell>
      <PanelHeader
        title="AI Response Recommendation"
        right={<Badge variant="CONF">{confPct}% CONF.</Badge>}
      />
      <div className="p-[14px]">
        {/* Recommendation card */}
        <div
          className="rounded-[9px] p-[13px]"
          style={{
            border: '1px solid #28516a',
            background: 'linear-gradient(135deg, #0d2639, #0b1a2a)',
          }}
        >
          <h3 className="text-[14px] font-bold text-ax-text m-0 mb-[5px]">
            {recommendation.title}
          </h3>
          <p className="text-[10px] text-ax-muted leading-[1.5] m-0 mb-[12px]">
            {recommendation.text}
          </p>

          {/* Route stats */}
          <div className="grid grid-cols-3 gap-[7px]">
            {[
              { label: 'Route',   value: recommended.name },
              { label: 'ETA',     value: `${recommended.eta} min` },
              { label: 'Failure', value: `${Math.round(recommended.failureProbability * 100)}%` },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-[7px] p-2" style={{ background: '#081522' }}>
                <small className="block text-[8px] text-ax-muted">{label}</small>
                <b className="text-[11px] text-ax-text">{value}</b>
              </div>
            ))}
          </div>

          {/* Approve button */}
          <button
            onClick={handleApprove}
            className="w-full mt-[11px] rounded-[8px] py-[10px] font-black text-[12px] cursor-pointer transition-all duration-150"
            style={{ background: '#20aabd', color: '#03131b', border: 'none' }}
            onMouseEnter={e => (e.currentTarget.style.background = '#35c7d9')}
            onMouseLeave={e => (e.currentTarget.style.background = '#20aabd')}
          >
            {showTrace ? '↑ Hide Decision Trace' : '✓ Approve Response Plan'}
          </button>
        </div>

        {/* Decision trace / SHAP explainability */}
        {showTrace && (
          <div
            className="mt-[10px] pt-[10px] animate-slide-up"
            style={{ borderTop: '1px solid #21334a' }}
          >
            <div className="flex justify-between items-center mb-[7px]">
              <span className="text-[10px] font-extrabold tracking-wide text-ax-text">DECISION TRACE (SHAP EXPLAINABILITY)</span>
              <span className="text-[8px] text-ax-muted">ML Feature Attribution</span>
            </div>
            {decisionTrace.map(({ factor, contribution }) => {
              const isUp = contribution.includes('↑');
              const isDown = contribution.includes('↓');
              const badgeColor = isUp ? '#ff6b6b' : isDown ? '#38d9a9' : '#a0aec0';

              return (
                <div
                  key={factor}
                  className="flex justify-between items-center text-[9px] my-[6px] py-[2px] px-[4px] rounded"
                  style={{ background: 'rgba(255,255,255,0.02)' }}
                >
                  <span className="text-[#b6c6d5]">{factor}</span>
                  <span className="font-bold font-mono text-[9px]" style={{ color: badgeColor }}>
                    {contribution}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </PanelShell>
  );
}
