// Stub pages for sidebar routes — styled placeholder matching the visual language

interface StubPageProps {
  icon: string;
  title: string;
  description: string;
  comingSoon?: string[];
}

function StubPage({ icon, title, description, comingSoon = [] }: StubPageProps) {
  return (
    <main className="px-[22px] py-[20px] flex flex-col items-center justify-center min-h-[60vh] text-center">
      <div className="text-[48px] mb-4 opacity-30">{icon}</div>
      <h1 className="text-[22px] font-bold text-ax-text mb-2">{title}</h1>
      <p className="text-ax-muted text-[13px] max-w-sm leading-relaxed mb-6">{description}</p>
      {comingSoon.length > 0 && (
        <div className="grid gap-[8px] text-left w-full max-w-xs">
          {comingSoon.map(item => (
            <div key={item} className="flex items-center gap-2 text-[11px] text-ax-muted">
              <span style={{ color: '#35c7d9' }}>◦</span>
              {item}
            </div>
          ))}
        </div>
      )}
      <div
        className="mt-8 px-4 py-[6px] rounded-[6px] text-[9px] font-extrabold tracking-widest"
        style={{ background: 'rgba(53,199,217,0.1)', color: '#35c7d9', border: '1px solid rgba(53,199,217,0.2)' }}
      >
        COMING IN NEXT PHASE
      </div>
    </main>
  );
}

export function LiveMap() {
  return <StubPage icon="◉" title="Live Map" description="Full-screen geo-referenced map with real-time sensor overlay, wind/water contours, and multi-hazard layer control."
    comingSoon={['Real-time sensor feed overlay', 'Wind & precipitation contours', 'Multi-hazard layer control', 'GIS shapefile integration']} />;
}

export function Forecast() {
  return <StubPage icon="◫" title="Forecast" description="Extended forecast view with multi-model ensemble, probability bands, and downloadable reports."
    comingSoon={['72-hour probabilistic forecast', 'Model ensemble comparison', 'Alert threshold configuration', 'PDF report export']} />;
}

export function Evacuation() {
  return <StubPage icon="⚑" title="Evacuation" description="Full evacuation management with route assignment, shelter capacity, and resource dispatch."
    comingSoon={['Multi-route comparison table', 'Shelter capacity dashboard', 'Resource dispatch board', 'Zone-by-zone population status']} />;
}

export function Resources() {
  return <StubPage icon="▣" title="Resources" description="Asset inventory, deployment status, and logistics coordination for emergency response."
    comingSoon={['Asset inventory management', 'Deployment status tracking', 'Supply chain visibility', 'Mutual-aid request system']} />;
}

export function Simulation() {
  return <StubPage icon="◌" title="Simulation" description="Full multi-hazard scenario builder with cascading failure modeling and ensemble runs."
    comingSoon={['Multi-hazard overlap simulation', 'Cascading infrastructure failure', 'Ensemble Monte Carlo runs', 'Scenario save & compare']} />;
}

export function Analytics() {
  return <StubPage icon="▤" title="Analytics" description="Historical analytics, performance metrics, after-action review, and model accuracy reports."
    comingSoon={['Historical incident browser', 'Response time analytics', 'Model accuracy tracking', 'After-action review generator']} />;
}
