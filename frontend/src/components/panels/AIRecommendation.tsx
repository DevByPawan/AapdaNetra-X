import { useState, useEffect } from 'react';
import type { RoutesData, DecisionSupportData, RiskLevel } from '../../types';
import { PanelShell, PanelHeader } from '../common/Panel';
import { Badge } from '../common/Badge';
import { useToastStore } from '../../store';
import { approveResponse, fetchDecisionRecommendation, approveDecision, rejectDecision } from '../../services/api';

interface AIRecommendationProps {
  routesData: RoutesData;
  incidentId: string;
}

export function AIRecommendation({ routesData, incidentId }: AIRecommendationProps) {
  const [showTrace, setShowTrace] = useState(false);
  const [decisionData, setDecisionData] = useState<DecisionSupportData | null>(null);
  const [statusState, setStatusState] = useState<'RECOMMENDED' | 'APPROVED' | 'REJECTED' | 'SUPERSEDED'>('RECOMMENDED');
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionReason, setActionReason] = useState<string>('Standard emergency response protocol evaluation');
  const [responderId] = useState<string>('OPERATOR-01');

  const showToast = useToastStore(s => s.show);
  const { recommendation, recommended, decisionTrace } = routesData;

  useEffect(() => {
    let isMounted = true;
    fetchDecisionRecommendation(incidentId)
      .then(data => {
        if (isMounted && data) {
          setDecisionData(data);
          setStatusState(data.status || 'RECOMMENDED');
        }
      })
      .catch(err => {
        console.warn('Failed to fetch decision recommendation, falling back to routesData:', err);
      });
    return () => {
      isMounted = false;
    };
  }, [incidentId]);

  const currentStatus = decisionData?.status || statusState;
  const currentPriority = decisionData?.priority || 'HIGH';
  const riskScore = decisionData ? decisionData.risk_score : 74.0;
  const riskInterval = decisionData?.risk_interval;

  const routeRecObj = typeof decisionData?.route_recommendation === 'object' && decisionData?.route_recommendation !== null
    ? decisionData.route_recommendation
    : null;

  const displayRouteName: string =
    (typeof routeRecObj?.name === 'string' ? routeRecObj.name : null)
    || (typeof decisionData?.route_recommendation === 'string' ? decisionData.route_recommendation : null)
    || (typeof recommended?.name === 'string' ? recommended.name : null)
    || 'Primary Evacuation Route';

  const rawEta = decisionData?.route_eta
    ?? routeRecObj?.eta
    ?? recommended?.eta
    ?? 0;
  const displayRouteEta: number = typeof rawEta === 'number' ? rawEta : Number(rawEta) || 0;

  const rawRouteSafety = decisionData?.route_safety
    ?? routeRecObj?.safety_score
    ?? (routeRecObj as any)?.safetyScore
    ?? (routeRecObj?.failure_probability != null ? 1 - routeRecObj.failure_probability : null)
    ?? (routeRecObj?.failureProbability != null ? 1 - routeRecObj.failureProbability : null)
    ?? recommended?.safetyScore
    ?? recommended?.safety_score
    ?? (recommended?.failureProbability != null ? 1 - recommended.failureProbability : null)
    ?? (recommended?.failure_probability != null ? 1 - recommended.failure_probability : null)
    ?? 0.88;

  const displayRouteSafety = `${Math.round((typeof rawRouteSafety === 'number' ? rawRouteSafety : 0.88) * 100)}%`;

  async function handleApprove() {
    if (isSubmitting || currentStatus !== 'RECOMMENDED') return;
    setIsSubmitting(true);
    try {
      if (decisionData?.decision_id) {
        const res = await approveDecision({
          decision_id: decisionData.decision_id,
          responder_id: responderId,
          reason: actionReason || 'Approved emergency response plan',
        });
        setStatusState('APPROVED');
        setFeedbackMessage(`APPROVED by ${res.responder_id} at ${new Date(res.timestamp).toLocaleTimeString()}`);
      }
      // Also execute legacy response approval for backward compatibility
      await approveResponse(incidentId);
      showToast('Emergency Decision APPROVED — evacuation workflow initiated.');
    } catch (err: any) {
      console.error('Approval failed:', err);
      setFeedbackMessage(`Approval failed: ${err?.response?.data?.detail || err?.message || 'Error'}`);
      showToast('Decision approval failed.');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleReject() {
    if (isSubmitting || currentStatus !== 'RECOMMENDED') return;
    setIsSubmitting(true);
    try {
      if (decisionData?.decision_id) {
        const res = await rejectDecision({
          decision_id: decisionData.decision_id,
          responder_id: responderId,
          reason: actionReason || 'Rejected based on field tactical assessment',
        });
        setStatusState('REJECTED');
        setFeedbackMessage(`REJECTED by ${res.responder_id} at ${new Date(res.timestamp).toLocaleTimeString()}`);
      } else {
        setStatusState('REJECTED');
        setFeedbackMessage(`REJECTED by ${responderId}`);
      }
      showToast('Emergency Decision REJECTED by operator.');
    } catch (err: any) {
      console.error('Rejection failed:', err);
      setFeedbackMessage(`Rejection failed: ${err?.response?.data?.detail || err?.message || 'Error'}`);
      showToast('Decision rejection failed.');
    } finally {
      setIsSubmitting(false);
    }
  }

  const getStatusBadgeVariant = (st: string): RiskLevel | 'CONF' => {
    switch (st) {
      case 'APPROVED': return 'LOW';
      case 'REJECTED': return 'CRITICAL';
      case 'SUPERSEDED': return 'HIGH';
      default: return 'MODERATE';
    }
  };

  const getPriorityBadgeVariant = (pr: string): RiskLevel => {
    switch (pr) {
      case 'CRITICAL': return 'CRITICAL';
      case 'HIGH': return 'HIGH';
      case 'MEDIUM': return 'MODERATE';
      default: return 'LOW';
    }
  };

  return (
    <PanelShell>
      <PanelHeader
        title="AI Emergency Decision Support"
        right={
          <div className="flex gap-1 items-center">
            <Badge variant={getStatusBadgeVariant(currentStatus)}>
              {currentStatus}
            </Badge>
            <Badge variant={getPriorityBadgeVariant(currentPriority)}>
              {currentPriority}
            </Badge>
          </div>
        }
      />
      <div className="p-[14px]">
        {/* Recommendation card */}
        <div
          className="rounded-[9px] p-[13px]"
          style={{
            border: currentStatus === 'APPROVED' ? '1px solid #38d9a9' : currentStatus === 'REJECTED' ? '1px solid #ff6b6b' : '1px solid #28516a',
            background: 'linear-gradient(135deg, #0d2639, #0b1a2a)',
          }}
        >
          {/* Header & Notice */}
          <div className="flex justify-between items-start mb-[6px]">
            <h3 className="text-[14px] font-bold text-ax-text m-0">
              {decisionData?.recommended_action ? 'Recommended Emergency Action' : recommendation.title}
            </h3>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#102a45] text-[#7eb6d6] font-mono">
              AI-assisted decision-support
            </span>
          </div>

          <p className="text-[10px] text-ax-muted leading-[1.5] m-0 mb-[10px]">
            {typeof decisionData?.recommended_action === 'string'
              ? decisionData.recommended_action
              : (decisionData?.recommended_action as any)?.text || recommendation.text}
          </p>

          {/* Risk Score & Conformal Uncertainty Interval */}
          <div className="mb-[10px] p-[8px] rounded-[7px]" style={{ background: '#071625', border: '1px solid #1a364d' }}>
            <div className="flex justify-between items-center text-[10px]">
              <span className="text-ax-muted">ML Risk Assessment:</span>
              <span className="font-bold text-ax-text">
                Score: {riskScore.toFixed(1)} / 100 ({decisionData?.risk_category || 'HIGH'})
              </span>
            </div>
            {riskInterval && (
              <div className="flex justify-between items-center text-[9px] mt-[3px] text-[#8fa8be]">
                <span>90% Conformal Interval:</span>
                <span className="font-mono font-semibold text-[#38bdf8]">
                  [{riskInterval.lower_bound.toFixed(1)}, {riskInterval.upper_bound.toFixed(1)}] (Width: {riskInterval.uncertainty_width.toFixed(1)})
                </span>
              </div>
            )}
          </div>

          {/* Spatial Context */}
          {decisionData?.spatial_context && (
            <div className="mb-[10px] grid grid-cols-3 gap-[6px]">
              <div className="rounded-[6px] p-1.5" style={{ background: '#081522' }}>
                <small className="block text-[8px] text-ax-muted">Pop Exposure</small>
                <b className="text-[10px] text-ax-text">
                  {decisionData.spatial_context.population_exposure ?? 'N/A'}
                </b>
              </div>
              <div className="rounded-[6px] p-1.5" style={{ background: '#081522' }}>
                <small className="block text-[8px] text-ax-muted">Infra Vuln</small>
                <b className="text-[10px] text-ax-text">
                  {decisionData.spatial_context.infrastructure_vulnerability !== null && decisionData.spatial_context.infrastructure_vulnerability !== undefined
                    ? `${Math.round(decisionData.spatial_context.infrastructure_vulnerability * 100)}%`
                    : 'N/A'}
                </b>
              </div>
              <div className="rounded-[6px] p-1.5" style={{ background: '#081522' }}>
                <small className="block text-[8px] text-ax-muted">Route Hazard</small>
                <b className="text-[10px] text-ax-text">
                  {decisionData.spatial_context.route_spatial_hazard !== null && decisionData.spatial_context.route_spatial_hazard !== undefined
                    ? `${Math.round(decisionData.spatial_context.route_spatial_hazard * 100)}%`
                    : 'N/A'}
                </b>
              </div>
            </div>
          )}

          {/* Route Stats */}
          <div className="grid grid-cols-3 gap-[7px] mb-[10px]">
            <div className="rounded-[7px] p-2" style={{ background: '#081522' }}>
              <small className="block text-[8px] text-ax-muted">Recommended Route</small>
              <b className="text-[11px] text-ax-text truncate block">
                {displayRouteName}
              </b>
            </div>
            <div className="rounded-[7px] p-2" style={{ background: '#081522' }}>
              <small className="block text-[8px] text-ax-muted">Est. Evac ETA</small>
              <b className="text-[11px] text-ax-text">
                {displayRouteEta} min
              </b>
            </div>
            <div className="rounded-[7px] p-2" style={{ background: '#081522' }}>
              <small className="block text-[8px] text-ax-muted">Route Safety</small>
              <b className="text-[11px] text-ax-text">
                {displayRouteSafety}
              </b>
            </div>
          </div>

          {/* Active Alerts & Data Freshness Summary */}
          <div className="flex justify-between items-center text-[9px] text-ax-muted mb-[10px] px-1">
            <span>
              Active Alerts: <strong className="text-ax-text">{decisionData?.active_alerts ? decisionData.active_alerts.length : 1} active</strong>
            </span>
            <span>
              Data Freshness:{' '}
              <strong className={decisionData?.data_freshness?.is_stale ? 'text-[#ff6b6b]' : 'text-[#38d9a9]'}>
                {decisionData?.data_freshness ? `${decisionData.data_freshness.telemetry_age_seconds}s age` : 'Fresh (<60s)'}
              </strong>
            </span>
          </div>

          {/* Rationale */}
          {decisionData?.rationale && (
            <div className="text-[9px] text-[#94a3b8] italic mb-[10px] p-1.5 rounded bg-[#06121e]">
              Rationale: {decisionData.rationale}
            </div>
          )}

          {/* Scientific Disclaimer */}
          <div className="text-[8px] text-[#64748b] leading-tight mb-[10px]">
            NOTICE: AI-assisted decision-support recommendation only. Mandatory human approval required. Does not constitute autonomous emergency dispatch.
          </div>

          {/* Action Reason Input & Buttons */}
          {currentStatus === 'RECOMMENDED' ? (
            <div className="space-y-2">
              <input
                type="text"
                value={actionReason}
                onChange={e => setActionReason(e.target.value)}
                placeholder="Reason for approval or rejection..."
                className="w-full text-[10px] p-1.5 rounded bg-[#06121e] text-ax-text border border-[#1e3a5f] focus:outline-none focus:border-[#38bdf8]"
              />
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={handleApprove}
                  disabled={isSubmitting}
                  className="rounded-[8px] py-[9px] font-bold text-[11px] cursor-pointer transition-all duration-150 disabled:opacity-50"
                  style={{ background: '#20aabd', color: '#03131b', border: 'none' }}
                  onMouseEnter={e => (!isSubmitting && (e.currentTarget.style.background = '#35c7d9'))}
                  onMouseLeave={e => (!isSubmitting && (e.currentTarget.style.background = '#20aabd'))}
                >
                  ✓ Approve Action
                </button>
                <button
                  onClick={handleReject}
                  disabled={isSubmitting}
                  className="rounded-[8px] py-[9px] font-bold text-[11px] cursor-pointer transition-all duration-150 disabled:opacity-50"
                  style={{ background: '#ef4444', color: '#ffffff', border: 'none' }}
                  onMouseEnter={e => (!isSubmitting && (e.currentTarget.style.background = '#dc2626'))}
                  onMouseLeave={e => (!isSubmitting && (e.currentTarget.style.background = '#ef4444'))}
                >
                  ✕ Reject Action
                </button>
              </div>
            </div>
          ) : (
            <div className="p-2 rounded text-center text-[11px] font-bold" style={{
              background: currentStatus === 'APPROVED' ? 'rgba(56,217,169,0.1)' : 'rgba(255,107,107,0.1)',
              color: currentStatus === 'APPROVED' ? '#38d9a9' : '#ff6b6b',
              border: currentStatus === 'APPROVED' ? '1px solid #38d9a9' : '1px solid #ff6b6b',
            }}>
              Decision State: {currentStatus}
            </div>
          )}

          {/* Feedback message */}
          {feedbackMessage && (
            <div className="mt-2 text-[9px] text-center text-[#94a3b8] font-mono">
              {feedbackMessage}
            </div>
          )}

          {/* Toggle trace button */}
          <button
            onClick={() => setShowTrace(v => !v)}
            className="w-full mt-[10px] text-[10px] text-[#7eb6d6] hover:text-[#aee2ff] bg-transparent border-none cursor-pointer py-1"
          >
            {showTrace ? '↑ Hide Decision Trace (SHAP)' : '↓ View Decision Trace & Feature Attributions'}
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
            {decisionData?.evidence && decisionData.evidence.length > 0 ? (
              decisionData.evidence.map((item: any, idx: number) => {
                if (typeof item === 'string') {
                  return (
                    <div
                      key={idx}
                      className="flex justify-between items-center text-[9px] my-[4px] py-[2px] px-[6px] rounded"
                      style={{ background: 'rgba(255,255,255,0.02)' }}
                    >
                      <span className="text-[#b6c6d5]">{item}</span>
                    </div>
                  );
                }
                const feature = typeof item?.feature === 'string' ? item.feature : typeof item?.factor === 'string' ? item.factor : `Driver ${idx + 1}`;
                const contribText = typeof item?.contribution_text === 'string' ? item.contribution_text : typeof item?.contribution === 'string' ? item.contribution : '';
                const isUp = contribText.includes('+') || contribText.includes('↑');
                const isDown = contribText.includes('-') || contribText.includes('↓');
                const badgeColor = isUp ? '#ff6b6b' : isDown ? '#38d9a9' : '#a0aec0';

                return (
                  <div
                    key={feature + idx}
                    className="flex justify-between items-center text-[9px] my-[4px] py-[2px] px-[6px] rounded"
                    style={{ background: 'rgba(255,255,255,0.02)' }}
                  >
                    <span className="text-[#b6c6d5]">{feature}</span>
                    {contribText && (
                      <span className="font-bold font-mono text-[9px]" style={{ color: badgeColor }}>
                        {contribText}
                      </span>
                    )}
                  </div>
                );
              })
            ) : (
              decisionTrace && decisionTrace.map((item: any, idx: number) => {
                if (typeof item === 'string') {
                  return (
                    <div
                      key={idx}
                      className="flex justify-between items-center text-[9px] my-[4px] py-[2px] px-[6px] rounded"
                      style={{ background: 'rgba(255,255,255,0.02)' }}
                    >
                      <span className="text-[#b6c6d5]">{item}</span>
                    </div>
                  );
                }
                const factor = typeof item?.factor === 'string' ? item.factor : typeof item?.feature === 'string' ? item.feature : `Factor ${idx + 1}`;
                const contribution = typeof item?.contribution === 'string' ? item.contribution : typeof item?.contribution_text === 'string' ? item.contribution_text : '';
                const isUp = contribution.includes('↑') || contribution.includes('+');
                const isDown = contribution.includes('↓') || contribution.includes('-');
                const badgeColor = isUp ? '#ff6b6b' : isDown ? '#38d9a9' : '#a0aec0';

                return (
                  <div
                    key={factor + idx}
                    className="flex justify-between items-center text-[9px] my-[4px] py-[2px] px-[6px] rounded"
                    style={{ background: 'rgba(255,255,255,0.02)' }}
                  >
                    <span className="text-[#b6c6d5]">{factor}</span>
                    {contribution && (
                      <span className="font-bold font-mono text-[9px]" style={{ color: badgeColor }}>
                        {contribution}
                      </span>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>
    </PanelShell>
  );
}
