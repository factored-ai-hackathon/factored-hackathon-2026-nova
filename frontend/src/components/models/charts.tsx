/**
 * Small SVG charts for the /modelos page. No chart library: each chart is a few marks over a
 * recessive grid, with a hover tooltip on every mark.
 */
import type { ReactNode } from 'react';
import { pct, useTip } from './viz';

export function Frame({ children, label }: { children: ReactNode; label: string }) {
  return (
    <figure className="viz-frame" aria-label={label}>
      {children}
    </figure>
  );
}

export function Legend({ items }: { items: { label: string; color: string; shape?: 'square' }[] }) {
  return (
    <div className="viz-legend">
      {items.map((i) => (
        <span key={i.label}>
          <i className={i.shape === 'square' ? 'sq' : ''} style={{ background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

// ---- horizontal bars ----------------------------------------------------------------------------

export type Bar = {
  label: string;
  value: number;
  color: string;
  note?: string;
  ci?: [number, number];
  tip?: ReactNode;
};

/** One row per bar, value 0..max, label on the left, value at the end of the bar. */
export function HBars({
  bars,
  max = 1,
  format = (v: number) => v.toFixed(3),
  labelWidth = 170,
  tickFormat,
}: {
  bars: Bar[];
  max?: number;
  format?: (v: number) => string;
  labelWidth?: number;
  tickFormat?: (v: number) => string;
}) {
  const { show, hide, node } = useTip();
  const row = 34;
  const width = 640;
  const plot = width - labelWidth - 120;
  const x = (v: number) => labelWidth + (v / max) * plot;
  const height = bars.length * row + 22;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * max);
  return (
    <Frame label={bars.map((b) => `${b.label} ${format(b.value)}`).join(', ')}>
      <svg viewBox={`0 0 ${width} ${height}`} className="viz-svg" role="img">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={0} y2={height - 18} className="viz-grid" />
            <text x={x(t)} y={height - 4} className="viz-axis" textAnchor="middle">
              {tickFormat ? tickFormat(t) : max === 1 ? pct(t) : t}
            </text>
          </g>
        ))}
        {bars.map((b, i) => {
          const y = i * row + 8;
          return (
            <g key={b.label} onMouseMove={show(b.tip ?? `${b.label}: ${format(b.value)}`)} onMouseLeave={hide}>
              <rect x={0} y={y - 6} width={width} height={row} fill="transparent" />
              <text x={labelWidth - 10} y={y + 12} className="viz-label" textAnchor="end">
                {b.label}
              </text>
              <rect x={x(0)} y={y} width={Math.max(2, x(b.value) - x(0))} height={16} rx={4} fill={b.color} />
              {b.ci && (
                <g className="viz-ci">
                  <line x1={x(b.ci[0])} x2={x(b.ci[1])} y1={y + 8} y2={y + 8} />
                  <line x1={x(b.ci[0])} x2={x(b.ci[0])} y1={y + 3} y2={y + 13} />
                  <line x1={x(b.ci[1])} x2={x(b.ci[1])} y1={y + 3} y2={y + 13} />
                </g>
              )}
              <text x={x(Math.max(b.value, b.ci?.[1] ?? 0)) + 8} y={y + 12} className="viz-value">
                {format(b.value)}
                {b.note && <tspan className="viz-note"> {b.note}</tspan>}
              </text>
            </g>
          );
        })}
      </svg>
      {node}
    </Frame>
  );
}

// ---- dot plot (one row per category, one dot per series) -----------------------------------------

export function DotRows({
  rows,
  series,
  labelWidth = 120,
}: {
  rows: { label: string; values: number[] }[];
  series: { label: string; color: string }[];
  labelWidth?: number;
}) {
  const { show, hide, node } = useTip();
  const width = 640;
  const row = 30;
  const plot = width - labelWidth - 30;
  const x = (v: number) => labelWidth + v * plot;
  const height = rows.length * row + 22;
  return (
    <Frame label="F1 por clase">
      <Legend items={series} />
      <svg viewBox={`0 0 ${width} ${height}`} className="viz-svg" role="img">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={0} y2={height - 18} className="viz-grid" />
            <text x={x(t)} y={height - 4} className="viz-axis" textAnchor="middle">
              {t.toFixed(2)}
            </text>
          </g>
        ))}
        {rows.map((r, i) => {
          const y = i * row + 14;
          const lo = Math.min(...r.values);
          const hi = Math.max(...r.values);
          return (
            <g key={r.label}>
              <text x={labelWidth - 10} y={y + 4} className="viz-label" textAnchor="end">
                {r.label}
              </text>
              <line x1={x(lo)} x2={x(hi)} y1={y} y2={y} className="viz-range" />
              {r.values.map((v, s) => (
                <circle
                  key={s}
                  cx={x(v)}
                  cy={y}
                  r={6}
                  fill={series[s].color}
                  className="viz-dot"
                  onMouseMove={show(
                    <>
                      <b>{r.label}</b>
                      <br />
                      {series[s].label}: F1 {v.toFixed(3)}
                    </>,
                  )}
                  onMouseLeave={hide}
                />
              ))}
            </g>
          );
        })}
      </svg>
      {node}
    </Frame>
  );
}

// ---- confusion matrix ---------------------------------------------------------------------------

const RAMP = ['#f3f7fd', '#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'];

export function Confusion({ labels, names, rows }: { labels: string[]; names: string[]; rows: number[][] }) {
  const { show, hide, node } = useTip();
  const cell = 52;
  const left = 120;
  const top = 92;
  const size = labels.length * cell;
  return (
    <Frame label="Matriz de confusión">
      <svg viewBox={`0 0 ${left + size + 10} ${top + size + 30}`} className="viz-svg viz-square" role="img">
        <text x={left + size / 2} y={14} className="viz-axis-title" textAnchor="middle">
          Predicho por el modelo →
        </text>
        {names.map((n, j) => (
          <text
            key={n}
            className="viz-axis"
            transform={`translate(${left + j * cell + cell / 2 + 4}, ${top - 8}) rotate(-45)`}
          >
            {n}
          </text>
        ))}
        {rows.map((r, i) => {
          const total = r.reduce((a, b) => a + b, 0);
          return (
            <g key={labels[i]}>
              <text x={left - 10} y={top + i * cell + cell / 2 + 4} className="viz-label" textAnchor="end">
                {names[i]}
              </text>
              {r.map((v, j) => {
                const share = total ? v / total : 0;
                const fill = v === 0 ? 'var(--viz-surface-2)' : RAMP[Math.min(7, 1 + Math.floor(share * 7))];
                return (
                  <g
                    key={j}
                    onMouseMove={show(
                      <>
                        Real <b>{names[i]}</b> → predicho <b>{names[j]}</b>
                        <br />
                        {v} de {total} frases ({pct(share)})
                      </>,
                    )}
                    onMouseLeave={hide}
                  >
                    <rect
                      x={left + j * cell + 1}
                      y={top + i * cell + 1}
                      width={cell - 2}
                      height={cell - 2}
                      rx={4}
                      fill={fill}
                      className={i === j ? 'viz-diag' : ''}
                    />
                    {v > 0 && (
                      <text
                        x={left + j * cell + cell / 2}
                        y={top + i * cell + cell / 2 + 5}
                        textAnchor="middle"
                        className={share > 0.45 ? 'viz-cell viz-cell-inv' : 'viz-cell'}
                      >
                        {v}
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          );
        })}
        <text
          className="viz-axis-title"
          transform={`translate(14, ${top + size / 2}) rotate(-90)`}
          textAnchor="middle"
        >
          Intención real
        </text>
      </svg>
      {node}
    </Frame>
  );
}

// ---- segmented control --------------------------------------------------------------------------

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="viz-seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          className={value === o.value ? 'on' : ''}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
