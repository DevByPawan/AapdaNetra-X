import { useEffect, useState } from 'react';
import { useToastStore } from '../../store';

export function Toast() {
  const { message } = useToastStore();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (message) {
      setVisible(true);
    } else {
      setVisible(false);
    }
  }, [message]);

  return (
    <div
      className="fixed right-[22px] bottom-[22px] z-[9999] text-[10px] rounded-[9px] px-[15px] py-[12px] transition-all duration-300"
      style={{
        background: '#10283b',
        border: '1px solid #2c6077',
        boxShadow: '0 15px 35px rgba(0,0,0,0.35)',
        transform: visible ? 'translateY(0)' : 'translateY(30px)',
        opacity: visible ? 1 : 0,
        pointerEvents: visible ? 'auto' : 'none',
      }}
    >
      <span className="text-ax-text">{message}</span>
    </div>
  );
}

export function LoadingSpinner({ size = 24 }: { size?: number }) {
  return (
    <div className="flex items-center justify-center w-full h-full">
      <svg
        width={size} height={size} viewBox="0 0 24 24"
        className="animate-spin"
        style={{ color: '#35c7d9' }}
      >
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5"
          fill="none" strokeDasharray="31.4" strokeDashoffset="10" strokeLinecap="round" />
      </svg>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-2 text-ax-muted text-[11px]">
      <span className="text-ax-danger text-[18px]">⚠</span>
      <span>{message}</span>
    </div>
  );
}
