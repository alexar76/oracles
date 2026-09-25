export interface Telemetry {
  tick: number;
  kappa: number;
  order_parameter: number;
  lyapunov: number;
  projection: { x: number; y: number };
  viewers: number;
  oscillators: {
    amplitudes: number[];
    phases: number[];
  };
  pca_energy_3: number;
  projection_angles: { theta1: number; theta2: number };
}

export interface Witness {
  event: string;
  text: string;
  source: string;
  model: string | null;
  timestamp: number;
}

export interface AgentInvoke {
  capability_id: string;
  source: string;
  input: Record<string, unknown>;
  summary: string;
  is_prediction: boolean;
  prediction?: {
    surrogate?: DreamPoint[];
    truth?: DreamPoint[];
    divergence_at?: number;
    text?: string;
    event?: string;
  } | null;
  timestamp: number;
}

export interface DreamPreview {
  surrogate: DreamPoint[];
  truth: DreamPoint[];
  divergence_at: number;
  source: string;
}

export interface DreamPoint {
  x: number;
  y: number;
}

export function formatMetric(value: number, digits = 3): string {
  return value.toFixed(digits);
}

export function phaseColor(phase: number, amp: number): string {
  const hue = ((phase + Math.PI) / (2 * Math.PI)) * 280 + 180;
  const sat = 70 + amp * 25;
  const light = 45 + amp * 35;
  return `hsl(${hue}, ${sat}%, ${light}%)`;
}

export const N_OSCILLATORS = 32;
export const SPHERE_RADIUS = 3.3;

/** Fibonacci-sphere unit direction for oscillator `index` (0..31). */
export function fibonacciDirection(
  index: number,
  n = N_OSCILLATORS
): [number, number, number] {
  const y = 1 - (index / (n - 1)) * 2;
  const rad = Math.sqrt(Math.max(0, 1 - y * y));
  const th = index * Math.PI * (3 - Math.sqrt(5));
  return [Math.cos(th) * rad, y, Math.sin(th) * rad];
}

/** Legacy flat grid — 2D fallback canvas only. */
export function gridPosition(index: number, cols = 8): [number, number, number] {
  const row = Math.floor(index / cols);
  const col = index % cols;
  const x = (col - (cols - 1) / 2) * 1.4;
  const z = (row - 1.5) * 1.4;
  return [x, 0, z];
}
