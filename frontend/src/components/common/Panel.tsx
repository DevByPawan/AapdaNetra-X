interface PanelShellProps {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}

export function PanelShell({ children, className = '', style }: PanelShellProps) {
  return (
    <div
      className={`rounded-[13px] border border-line overflow-hidden ${className}`}
      style={{
        background: 'linear-gradient(180deg, rgba(16,31,51,0.96), rgba(10,23,38,0.96))',
        boxShadow: '0 12px 35px rgba(0,0,0,0.18)',
        ...style,
      }}
    >
      {children}
    </div>
  );
}

interface PanelHeaderProps {
  title: string;
  sub?: string;
  right?: React.ReactNode;
}

export function PanelHeader({ title, sub, right }: PanelHeaderProps) {
  return (
    <div className="h-[55px] border-b border-line flex items-center justify-between px-4 shrink-0">
      <div className="flex items-center gap-2">
        <span className="text-[12px] font-extrabold tracking-[0.8px] uppercase text-ax-text">
          {title}
        </span>
        {sub && <span className="text-ax-muted text-[10px] ml-1">{sub}</span>}
      </div>
      {right && <div>{right}</div>}
    </div>
  );
}
