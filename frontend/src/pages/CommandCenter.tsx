import { useQuery } from '@tanstack/react-query';
import { fetchIncident, fetchRisk, fetchForecast, fetchRoutes, fetchAlerts } from '../services/api';
import { getDynamicIncidentId } from '../data/simulatedData';
import { useMapStore } from '../store';

import { Header } from '../components/layout/Header';
import { SituationalMap } from '../components/map/SituationalMap';
import { IncidentOverview } from '../components/panels/IncidentOverview';
import { AIRecommendation } from '../components/panels/AIRecommendation';
import { ActiveAlerts } from '../components/panels/ActiveAlerts';
import { HazardForecastChart } from '../components/bottom/HazardForecastChart';
import { TimeHorizonSlider } from '../components/bottom/TimeHorizonSlider';
import { WhatIfSimulation } from '../components/bottom/WhatIfSimulation';
import { PanelShell, PanelHeader } from '../components/common/Panel';
import { LoadingSpinner, ErrorState } from '../components/common/Feedback';

export function CommandCenter() {
  const { timeHorizon } = useMapStore();

  const incident = useQuery({ queryKey: ['incident'], queryFn: fetchIncident, staleTime: 30_000 });
  const risk     = useQuery({ queryKey: ['risk', timeHorizon], queryFn: () => fetchRisk(timeHorizon), staleTime: 10_000 });
  const forecast = useQuery({ queryKey: ['forecast'], queryFn: fetchForecast, staleTime: 30_000 });
  const routes   = useQuery({ queryKey: ['routes', timeHorizon], queryFn: () => fetchRoutes(timeHorizon), staleTime: 10_000 });
  const alerts   = useQuery({ queryKey: ['alerts'],   queryFn: fetchAlerts,   staleTime: 15_000 });

  const loading = incident.isLoading || risk.isLoading || forecast.isLoading || routes.isLoading || alerts.isLoading;
  const error   = incident.error   || risk.error   || forecast.error   || routes.error   || alerts.error;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-ax-muted">
        <LoadingSpinner size={36} />
      </div>
    );
  }

  if (error || !risk.data || !forecast.data || !routes.data || !alerts.data) {
    return (
      <div className="flex items-center justify-center h-full">
        <ErrorState message="Failed to load incident data. Check backend connection." />
      </div>
    );
  }

  return (
    <main className="px-[22px] py-[20px] pb-6 min-w-0 overflow-auto">
      <Header incident={incident.data ?? null} />

      {/* ── Top grid: map + right panels ── */}
      <section
        className="grid gap-4 mb-4"
        style={{ gridTemplateColumns: 'minmax(0,1fr) 330px' }}
      >
        {/* Map panel */}
        <PanelShell
          className="relative"
          style={{ height: 570 }}
        >
          <PanelHeader title="Situational Awareness" sub="Dynamic Risk Map" />
          <div className="absolute inset-0 top-[55px]">
            <SituationalMap
              riskState={risk.data}
              routes={{ recommended: routes.data.recommended, alternatives: routes.data.alternatives }}
            />
          </div>
        </PanelShell>

        {/* Right column */}
        <div className="grid gap-4" style={{ alignContent: 'start' }}>
          <IncidentOverview riskState={risk.data} />
          <AIRecommendation routesData={routes.data} incidentId={incident.data?.id ?? getDynamicIncidentId()} />
          <ActiveAlerts alertsData={alerts.data} />
        </div>
      </section>

      {/* ── Bottom row ── */}
      <section
        className="grid gap-4"
        style={{ gridTemplateColumns: '1.3fr 1fr 1fr' }}
      >
        <HazardForecastChart forecast={forecast.data} />
        <TimeHorizonSlider riskState={risk.data} />
        <WhatIfSimulation />
      </section>
    </main>
  );
}
