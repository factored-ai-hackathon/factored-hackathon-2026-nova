/** Shared chart tokens, formatting and the hover tooltip hook for the /modelos charts. */
import { useState, type ReactNode, type MouseEvent } from 'react';

export const C = {
  model: 'var(--viz-series-1)',
  compare: 'var(--viz-series-2)',
  base: 'var(--viz-muted)',
};

export const pct = (x: number, digits = 0) => `${(100 * x).toFixed(digits)}%`;

// ---- tooltip ------------------------------------------------------------------------------------

type Tip = { x: number; y: number; body: ReactNode } | null;

export function useTip() {
  const [tip, setTip] = useState<Tip>(null);
  const show = (body: ReactNode) => (e: MouseEvent) => {
    const box = (e.currentTarget as Element).closest('.viz-frame')!.getBoundingClientRect();
    setTip({ x: e.clientX - box.left, y: e.clientY - box.top, body });
  };
  const hide = () => setTip(null);
  const node = tip ? (
    <div
      className="viz-tip"
      role="status"
      style={{ left: tip.x, top: tip.y, transform: `translate(${tip.x > 260 ? '-105%' : '12px'}, -110%)` }}
    >
      {tip.body}
    </div>
  ) : null;
  return { show, hide, node };
}
