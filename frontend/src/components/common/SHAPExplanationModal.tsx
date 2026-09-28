import { useQuery } from '@tanstack/react-query';
import { fetchRiskExplanationHistory } from '../../services/api';
import { LoadingSpinner, ErrorState } from './Feedback';
import { Badge } from './Badge';

interface SHAPExplanationModalProps {
  predictionId: string;
  onClose: () => void;
}

export function SHAPExplanationModal({ predictionId, onClose }: SHAPExplanationModalProps) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['risk-explanation', predictionId],
    queryFn: () => fetchRiskExplanationHistory(predictionId),
    staleTime: 60_000,
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-xs animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl bg-panel border border-line rounded-[14px] p-6 shadow-2xl overflow-hidden flex flex-col max-h-[85vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-line mb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[18px]">🧠</span>
              <h2 className="text-[16px] font-bold text-ax-text">Explainable AI (SHAP) Decision Trace</h2>
            </div>
            <p className="text-[11px] text-ax-muted mt-[2px]">
              Feature contribution breakdown for Risk Prediction ID <code className="text-ax-cyan">{predictionId.slice(0, 8)}...</code>
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full border border-line flex items-center justify-center text-ax-muted hover:text-white hover:bg-line transition-all text-[16px] cursor-pointer"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto space-y-5 pr-1">
          {isLoading && (
            <div className="py-12 flex items-center justify-center text-ax-muted">
              <LoadingSpinner size={32} />
            </div>
          )}

          {isError && (
            <div className="py-8">
              <ErrorState message={(error as Error)?.message || 'Failed to load SHAP explainability record.'} />
            </div>
          )}

          {data && (
            <>
              {/* Summary KPIs */}
              <div className="grid grid-cols-3 gap-3 p-3 rounded-[10px] bg-panel2 border border-line/60">
                <div>
                  <span className="block text-[10px] text-ax-muted uppercase tracking-wider font-semibold">
                    Base Model Value
                  </span>
                  <span className="text-[18px] font-bold text-ax-text">{data.base_value.toFixed(1)}</span>
                </div>
                <div>
                  <span className="block text-[10px] text-ax-muted uppercase tracking-wider font-semibold">
                    Total SHAP Delta
                  </span>
                  <span className={`text-[18px] font-bold ${data.total_shap_delta >= 0 ? 'text-ax-danger' : 'text-ax-success'}`}>
                    {data.total_shap_delta >= 0 ? `+${data.total_shap_delta.toFixed(1)}` : data.total_shap_delta.toFixed(1)}
                  </span>
                </div>
                <div>
                  <span className="block text-[10px] text-ax-muted uppercase tracking-wider font-semibold">
                    Final Prediction
                  </span>
                  <div className="flex items-center gap-2 mt-[2px]">
                    <span className="text-[18px] font-bold text-white">{data.prediction.toFixed(1)}</span>
                    <Badge variant={data.prediction >= 75 ? 'CRITICAL' : data.prediction >= 50 ? 'HIGH' : 'LOW'}>
                      {data.prediction >= 75 ? 'CRITICAL' : data.prediction >= 50 ? 'HIGH' : 'LOW'}
                    </Badge>
                  </div>
                </div>
              </div>

              {/* Feature Drivers Breakdown */}
              <div>
                <h3 className="text-[12px] font-bold text-ax-text uppercase tracking-wider mb-3">
                  Top Feature Impact Drivers
                </h3>
                <div className="space-y-2">
                  {Object.entries(data.features || {}).map(([featureKey, shapVal]) => {
                    const absVal = Math.abs(shapVal);
                    const pct = Math.min(100, Math.max(10, Math.round((absVal / (data.total_shap_delta || 1)) * 100)));
                    const isPositive = shapVal >= 0;
                    return (
                      <div key={featureKey} className="p-2.5 rounded-[8px] bg-[#071321] border border-line/40">
                        <div className="flex items-center justify-between text-[12px] mb-1.5">
                          <span className="font-semibold text-ax-text capitalize">
                            {featureKey.replace(/_/g, ' ')}
                          </span>
                          <span className={`font-mono font-bold text-[11px] ${isPositive ? 'text-ax-danger' : 'text-ax-success'}`}>
                            {isPositive ? `+${shapVal.toFixed(1)} SHAP` : `${shapVal.toFixed(1)} SHAP`}
                          </span>
                        </div>
                        <div className="w-full h-2 rounded-full bg-line/60 overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-300 ${isPositive ? 'bg-ax-danger' : 'bg-ax-success'}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Decision Trace Log */}
              {data.decision_trace && data.decision_trace.length > 0 && (
                <div>
                  <h3 className="text-[12px] font-bold text-ax-text uppercase tracking-wider mb-3">
                    Step-by-Step Model Reasoning Trace
                  </h3>
                  <div className="border border-line/60 rounded-[10px] overflow-hidden">
                    <table className="w-full text-left text-[11px]">
                      <thead className="bg-panel2 text-ax-muted border-b border-line/60 font-semibold uppercase tracking-wider">
                        <tr>
                          <th className="py-2 px-3">Feature</th>
                          <th className="py-2 px-3">Value</th>
                          <th className="py-2 px-3">SHAP</th>
                          <th className="py-2 px-3">Explanation</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line/40">
                        {data.decision_trace.map((item, idx) => (
                          <tr key={idx} className="hover:bg-line/20">
                            <td className="py-2 px-3 font-semibold text-ax-text capitalize">{item.feature.replace(/_/g, ' ')}</td>
                            <td className="py-2 px-3 font-mono text-ax-cyan">{item.val}</td>
                            <td className={`py-2 px-3 font-mono font-bold ${item.shap >= 0 ? 'text-ax-danger' : 'text-ax-success'}`}>
                              {item.shap >= 0 ? `+${item.shap}` : item.shap}
                            </td>
                            <td className="py-2 px-3 text-ax-muted">{item.desc}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
