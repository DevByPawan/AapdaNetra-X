import { NavLink } from 'react-router-dom';

const NAV_ITEMS = [
  { icon: '◈', label: 'Command Center', to: '/' },
  { icon: '◉', label: 'Live Map',       to: '/map' },
  { icon: '◫', label: 'Forecast',       to: '/forecast' },
  { icon: '⚑', label: 'Evacuation',     to: '/evacuation' },
  { icon: '▣', label: 'Resources',      to: '/resources' },
  { icon: '◌', label: 'Simulation',     to: '/simulation' },
  { icon: '▤', label: 'Analytics',      to: '/analytics' },
];

export function Sidebar() {
  return (
    <aside
      className="flex flex-col border-r border-line px-[14px] py-[22px]"
      style={{ background: '#071321', width: 220 }}
    >
      {/* Brand */}
      <div className="flex items-center gap-[10px] px-2 pb-6">
        <div
          className="w-9 h-9 rounded-[10px] grid place-items-center font-black text-[13px]"
          style={{ background: 'linear-gradient(135deg, #27c7d8, #176a8e)', color: '#03131b' }}
        >
          AX
        </div>
        <div>
          <b className="block text-[15px] tracking-[0.4px] text-ax-text">AapdaNetra-X</b>
          <span className="block text-ax-muted text-[10px] mt-[2px]">Emergency Intelligence</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="grid gap-[6px]">
        {NAV_ITEMS.map(({ icon, label, to }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-[8px] text-left px-3 py-[11px] rounded-[9px] text-[13px] cursor-pointer transition-all duration-150 no-underline ${
                isActive
                  ? 'text-white'
                  : 'text-[#91a4b8] hover:bg-[#12263b] hover:text-white'
              }`
            }
            style={({ isActive }) =>
              isActive ? { background: '#12263b', boxShadow: 'inset 3px 0 #35c7d9' } : {}
            }
          >
            <span className="text-[14px]">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Bottom status */}
      <div className="mt-auto border-t border-line pt-4 px-2 text-[11px] text-ax-muted leading-relaxed">
        SYSTEM HEALTH
        <br />
        <span style={{ color: '#6fe4b0' }}>● All core services operational</span>
        <br /><br />
        Model v0.1 &bull; Prototype
      </div>
    </aside>
  );
}
