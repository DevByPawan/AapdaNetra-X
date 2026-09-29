import { create } from 'zustand';

type LayerKey = 'risk' | 'route' | 'assets' | 'hazards' | 'elevation';

interface MapStore {
  activeLayer: LayerKey;
  timeHorizon: number;  // 0=NOW, 1=+10, 2=+20, 3=+30
  setLayer: (layer: LayerKey) => void;
  setHorizon: (h: number) => void;
}

export const useMapStore = create<MapStore>((set) => ({
  activeLayer: 'risk',
  timeHorizon: 0,
  setLayer: (layer) => set({ activeLayer: layer }),
  setHorizon: (h) => set({ timeHorizon: h }),
}));

// ── Simulation store ──────────────────────────────────────────────────────
import type { SimulationResult } from '../types';

interface SimulationStore {
  rainfallIncrease: number;
  populationMovement: number;
  waterLevelIncrease: number;
  result: SimulationResult | null;
  running: boolean;
  setRainfall: (v: number) => void;
  setPopulation: (v: number) => void;
  setWaterLevel: (v: number) => void;
  setResult: (r: SimulationResult) => void;
  setRunning: (v: boolean) => void;
  reset: () => void;
}

export const useSimulationStore = create<SimulationStore>((set) => ({
  rainfallIncrease: 20,
  populationMovement: 2000,
  waterLevelIncrease: 10,
  result: null,
  running: false,
  setRainfall:    (v) => set({ rainfallIncrease: v }),
  setPopulation:  (v) => set({ populationMovement: v }),
  setWaterLevel:  (v) => set({ waterLevelIncrease: v }),
  setResult:      (r) => set({ result: r }),
  setRunning:     (v) => set({ running: v }),
  reset:          ()  => set({ result: null }),
}));

// ── Alert store ──────────────────────────────────────────────────────────
interface AlertStore {
  dismissed: Set<string>;
  dismiss: (id: string) => void;
}

export const useAlertStore = create<AlertStore>((set) => ({
  dismissed: new Set(),
  dismiss: (id) => set((s) => ({ dismissed: new Set([...s.dismissed, id]) })),
}));

// ── Toast store ──────────────────────────────────────────────────────────
interface ToastStore {
  message: string | null;
  show: (msg: string) => void;
  hide: () => void;
}

export const useToastStore = create<ToastStore>((set) => ({
  message: null,
  show: (msg) => {
    set({ message: msg });
    setTimeout(() => set({ message: null }), 2800);
  },
  hide: () => set({ message: null }),
}));
