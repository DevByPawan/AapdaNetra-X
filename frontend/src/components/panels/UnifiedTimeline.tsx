import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchIncidentTimeline } from '../../services/api';
import type { TimelineEventItem, TimelineEventType, CursorInfo } from '../../types';
import { useEventStream, getEventDedupeKey } from '../../hooks/useEventStream';
import { Badge } from '../common/Badge';
import { LoadingSpinner, ErrorState } from '../common/Feedback';
import { SHAPExplanationModal } from '../common/SHAPExplanationModal';

interface UnifiedTimelineProps {
  incidentId: string;
}

const EVENT_TYPE_BADGES: Record<string, { label: string; variant: 'CRITICAL' | 'HIGH' | 'MODERATE' | 'LOW' | 'INFO' }> = {
  TELEMETRY_OBSERVED: { label: 'TELEMETRY', variant: 'INFO' },
  RISK_EVALUATED:     { label: 'RISK',      variant: 'HIGH' },
  ROUTE_UPDATED:      { label: 'ROUTE',     variant: 'MODERATE' },
  ALERT_CREATED:      { label: 'ALERT',     variant: 'CRITICAL' },
  SIMULATION_COMPLETED:{ label: 'SIMULATION',variant: 'INFO' },
  DECISION_APPROVED:  { label: 'DECISION',  variant: 'LOW' },
  AUDIT_LOGGED:       { label: 'AUDIT',     variant: 'INFO' },
};

export function UnifiedTimeline({ incidentId }: UnifiedTimelineProps) {
  const [filter, setFilter] = useState<string>('ALL');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selectedPredictionId, setSelectedPredictionId] = useState<string | null>(null);

  // Pagination state
  const [pages, setPages] = useState<TimelineEventItem[]>([]);
  const [nextCursor, setNextCursor] = useState<CursorInfo | null>(null);
  const [hasMore, setHasMore] = useState<boolean>(false);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const [liveEvents, setLiveEvents] = useState<TimelineEventItem[]>([]);

  // 1. Initial Page Query
  const initialQuery = useQuery({
    queryKey: ['timeline-initial', incidentId],
    queryFn: async () => {
      const res = await fetchIncidentTimeline(incidentId, { limit: 20 });
      setPages(res.items);
      setNextCursor(res.next_cursor);
      setHasMore(res.has_more);
      return res;
    },
    staleTime: 15_000,
  });

  // 2. Live SSE Event Callback & Composite Deduplication
  const handleLiveEvent = useCallback((newEvent: TimelineEventItem) => {
    setLiveEvents((prev) => {
      const newKey = getEventDedupeKey(newEvent);
      // Suppress duplicate SSE event delivery if same composite event key is present
      if (prev.some((e) => getEventDedupeKey(e) === newKey)) return prev;
      return [newEvent, ...prev];
    });
  }, []);

  const { connected: sseConnected } = useEventStream(handleLiveEvent);

  // 3. Load More Handler (Cursor Pagination)
  const handleLoadMore = async () => {
    if (!nextCursor || isLoadingMore) return;
    setIsLoadingMore(true);

    try {
      const res = await fetchIncidentTimeline(incidentId, {
        limit: 20,
        cursor_timestamp: nextCursor.timestamp,
        cursor_id: nextCursor.id,
      });

      setPages((prev) => {
        const existingKeys = new Set(prev.map(getEventDedupeKey));
        const newUniqueItems = res.items.filter((item) => !existingKeys.has(getEventDedupeKey(item)));
        return [...prev, ...newUniqueItems];
      });

      setNextCursor(res.next_cursor);
      setHasMore(res.has_more);
    } catch {
      // Handle pagination error gracefully
    } finally {
      setIsLoadingMore(false);
    }
  };

  // Merge Live Events + Historical Pages with Composite Key Deduplication
  const loadedHistoricalKeys = new Set(pages.map(getEventDedupeKey));
  const uniqueLiveEvents = liveEvents.filter((e) => !loadedHistoricalKeys.has(getEventDedupeKey(e)));
  const rawCombinedTimeline = [...uniqueLiveEvents, ...pages];

  const seenKeys = new Set<string>();
  const combinedTimeline: TimelineEventItem[] = [];
  for (const item of rawCombinedTimeline) {
    const k = getEventDedupeKey(item);
    if (!seenKeys.has(k)) {
      seenKeys.add(k);
      combinedTimeline.push(item);
    }
  }

  // Apply Filter
  const filteredEvents = combinedTimeline.filter((item) => {
    if (filter === 'ALL') return true;
    return item.event_type === filter || item.entity_type === filter.toLowerCase();
  });

  return (
    <div className="flex flex-col h-full bg-panel border border-line rounded-[12px] p-5 shadow-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-line mb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[16px]">📜</span>
            <h2 className="text-[15px] font-bold text-ax-text">Unified Incident Timeline</h2>
            {sseConnected && (
              <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold bg-ax-success/15 text-ax-success border border-ax-success/30 animate-fade-in">
                <span className="w-1.5 h-1.5 rounded-full bg-ax-success animate-pulse-dot" />
                LIVE SSE
              </span>
            )}
          </div>
          <p className="text-[11px] text-ax-muted mt-0.5">
            Real-time merged audit & domain occurrences for incident{' '}
            <code className="text-ax-cyan font-mono">{incidentId}</code>
          </p>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1 bg-[#071321] p-1 rounded-[8px] border border-line/60 text-[11px]">
          {['ALL', 'TELEMETRY_OBSERVED', 'RISK_EVALUATED', 'ROUTE_UPDATED', 'ALERT_CREATED', 'SIMULATION_COMPLETED', 'DECISION_APPROVED'].map((f) => {
            const shortLabel = f === 'ALL' ? 'All' : EVENT_TYPE_BADGES[f]?.label || f;
            const active = filter === f;
            return (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-2.5 py-1 rounded-[6px] font-semibold transition-all cursor-pointer ${
                  active ? 'bg-line text-white shadow-xs' : 'text-ax-muted hover:text-ax-text'
                }`}
              >
                {shortLabel}
              </button>
            );
          })}
        </div>
      </div>

      {/* Main List */}
      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {initialQuery.isLoading && (
          <div className="py-12 flex items-center justify-center text-ax-muted">
            <LoadingSpinner size={32} />
          </div>
        )}

        {initialQuery.isError && (
          <div className="py-8">
            <ErrorState
              message={
                (initialQuery.error as any)?.response?.status === 503
                  ? 'Database service unavailable (Required mode failure).'
                  : 'Unable to connect to historical database service.'
              }
            />
          </div>
        )}

        {!initialQuery.isLoading && !initialQuery.isError && filteredEvents.length === 0 && (
          <div className="py-12 text-center text-ax-muted border border-dashed border-line/60 rounded-[10px] my-4">
            <span className="text-[28px] block mb-2 opacity-50">📭</span>
            <p className="text-[13px] font-semibold">No timeline events recorded</p>
            <p className="text-[11px] text-ax-muted mt-1">
              Events will appear in real-time as sensors, ML evaluations, or user decisions occur.
            </p>
          </div>
        )}

        {filteredEvents.map((item) => {
          const badgeMeta = EVENT_TYPE_BADGES[item.event_type] || { label: item.event_type, variant: 'INFO' };
          const isExpanded = expandedId === item.entity_id;
          const isRiskEvent = item.event_type === 'RISK_EVALUATED' || item.entity_type === 'risk_prediction';

          return (
            <div
              key={item.entity_id}
              className="p-3.5 rounded-[10px] bg-panel2 border border-line/60 hover:border-ax-cyan/40 transition-all duration-150 animate-fade-in"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <Badge variant={badgeMeta.variant}>{badgeMeta.label}</Badge>
                  <div>
                    <h4 className="text-[13px] font-semibold text-ax-text leading-snug">{item.summary}</h4>
                    <div className="flex items-center gap-3 text-[11px] text-ax-muted mt-1 font-mono">
                      <span>🕒 {new Date(item.timestamp).toLocaleString()}</span>
                      <span>•</span>
                      <span>ID: {item.entity_id.slice(0, 8)}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {isRiskEvent && (
                    <button
                      onClick={() => setSelectedPredictionId(item.entity_id)}
                      className="px-2 py-1 text-[10px] font-bold rounded-[6px] bg-ax-cyan/15 text-ax-cyan border border-ax-cyan/30 hover:bg-ax-cyan/25 transition-all cursor-pointer"
                    >
                      🧠 SHAP Drivers
                    </button>
                  )}
                  {item.details && Object.keys(item.details).length > 0 && (
                    <button
                      onClick={() => setExpandedId(isExpanded ? null : item.entity_id)}
                      className="text-[11px] text-ax-muted hover:text-ax-cyan transition-colors px-1 py-0.5 cursor-pointer"
                    >
                      {isExpanded ? '▲ Hide' : '▼ Details'}
                    </button>
                  )}
                </div>
              </div>

              {/* Expandable lightweight details */}
              {isExpanded && item.details && (
                <div className="mt-3 pt-3 border-t border-line/40 grid grid-cols-2 gap-2 text-[11px] bg-[#071321] p-3 rounded-[8px]">
                  {Object.entries(item.details).map(([k, v]) => (
                    <div key={k} className="truncate">
                      <span className="text-ax-muted capitalize">{k.replace(/_/g, ' ')}: </span>
                      <span className="font-mono text-ax-text font-semibold">
                        {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {/* Load More Button */}
        {hasMore && (
          <div className="pt-3 pb-2 text-center">
            <button
              onClick={handleLoadMore}
              disabled={isLoadingMore}
              className="px-5 py-2 text-[12px] font-bold rounded-[8px] bg-line hover:bg-line/80 text-ax-text border border-line/80 transition-all cursor-pointer disabled:opacity-50 inline-flex items-center gap-2 shadow-sm"
            >
              {isLoadingMore ? (
                <>
                  <LoadingSpinner size={16} /> Loading older records...
                </>
              ) : (
                '⬇ Load Older Events'
              )}
            </button>
          </div>
        )}
      </div>

      {/* SHAP Modal */}
      {selectedPredictionId && (
        <SHAPExplanationModal
          predictionId={selectedPredictionId}
          onClose={() => setSelectedPredictionId(null)}
        />
      )}
    </div>
  );
}
