// Faithfulness of Nova's answers to the data it consulted (decision 28), for the human agent:
// - a headline score (supported claims / all checkable claims),
// - per answer: its score bar, the answer with each checkable token marked ✓ found in the
//   evidence / ✗ not found, and a heatmap of cosine similarity between the answer's sentences and
//   each evidence item (term vectors), with the shared tokens on hover.
// Colors: one sequential blue for similarity (light = unrelated, dark = same content); status
// green/red only for supported/unsupported tokens, always with ✓/✗ and a label.

import { useState } from 'react';
import type { Faithfulness } from '../../api/agentConsole';
import { t } from '../../i18n/translations';

// Reference sequential ramp (blue 100 -> 700), one step per bin of cosine similarity.
const RAMP = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'];
const SERIES = '#2a78d6';

function rampColor(value: number): string {
  return RAMP[Math.min(RAMP.length - 1, Math.floor(value * RAMP.length))];
}

function pct(value: number | null): string {
  return value == null ? '—' : `${Math.round(value * 100)}%`;
}

/** The answer's text with its claims marked: a claim is shown where it first appears. */
function MarkedAnswer({ text, claims, language }: {
  text: string;
  claims: Faithfulness['answers'][number]['claims'];
  language: 'es' | 'pt';
}) {
  const parts: React.ReactNode[] = [];
  let rest = text.replace(/\*\*/g, '');
  let key = 0;
  // Walk the text, cutting at the first occurrence of each claim, in text order.
  const ordered = claims
    .map((c) => ({ ...c, at: rest.indexOf(c.text) }))
    .filter((c) => c.at >= 0)
    .sort((a, b) => a.at - b.at);
  for (const claim of ordered) {
    const at = rest.indexOf(claim.text, 0);
    if (at < 0) continue;
    if (at > 0) parts.push(<span key={key++}>{rest.slice(0, at)}</span>);
    parts.push(
      <mark
        key={key++}
        className={`claim ${claim.supported ? 'supported' : 'unsupported'}`}
        title={t(claim.supported ? 'faith.found' : 'faith.notFound', language)}
      >
        <span aria-hidden="true">{claim.supported ? '✓' : '✗'}</span> {claim.text}
        <span className="sr-only"> ({t(claim.supported ? 'faith.found' : 'faith.notFound', language)})</span>
      </mark>,
    );
    rest = rest.slice(at + claim.text.length);
  }
  parts.push(<span key={key++}>{rest}</span>);
  return <p className="faith-answer-text">{parts}</p>;
}

interface Hover {
  x: number;
  y: number;
  sentence: string;
  tool: string;
  value: number;
  shared: string[];
}

const CELL_W = 64;
const CELL_H = 26;
const LABEL_W = 180;

function Heatmap({ answer, evidence, language }: {
  answer: Faithfulness['answers'][number];
  evidence: Faithfulness['evidence'];
  language: 'es' | 'pt';
}) {
  const [hover, setHover] = useState<Hover | null>(null);
  const rows = answer.sentences;
  const width = LABEL_W + evidence.length * CELL_W;
  const height = 22 + rows.length * CELL_H;
  const short = (s: string) => (s.length > 28 ? `${s.slice(0, 27)}…` : s);
  return (
    <div className="faith-heatmap">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        role="img"
        aria-label={t('faith.heatmapAria', language)}
        onMouseLeave={() => setHover(null)}
      >
        {evidence.map((e, j) => (
          <text key={j} x={LABEL_W + j * CELL_W + CELL_W / 2} y={14} textAnchor="middle" className="faith-axis">
            {e.tool.replace('get_my_', '')}
          </text>
        ))}
        {rows.map((row, i) => (
          <g key={i}>
            <text x={LABEL_W - 6} y={22 + i * CELL_H + CELL_H / 2 + 4} textAnchor="end" className="faith-axis">
              {short(row.text)}
            </text>
            {row.similarity.map((value, j) => (
              <rect
                key={j}
                x={LABEL_W + j * CELL_W + 1}
                y={22 + i * CELL_H + 1}
                width={CELL_W - 2}
                height={CELL_H - 2}
                rx={4}
                fill={rampColor(value)}
                onMouseMove={(ev) => {
                  const box = (ev.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                  setHover({
                    x: ev.clientX - box.left,
                    y: ev.clientY - box.top,
                    sentence: row.text,
                    tool: evidence[j].tool,
                    value,
                    shared: row.shared[j] ?? [],
                  });
                }}
              />
            ))}
          </g>
        ))}
      </svg>
      {hover && (
        <div className="faith-tooltip" style={{ left: hover.x + 12, top: hover.y + 12 }} role="tooltip">
          <strong>{hover.value.toFixed(2)}</strong> · {hover.tool}
          <div className="faith-tooltip-sentence">{hover.sentence}</div>
          <div>
            {t('faith.shared', language)}: {hover.shared.length ? hover.shared.join(', ') : '—'}
          </div>
        </div>
      )}
      <div className="faith-legend" aria-hidden="true">
        <span>0</span>
        <span className="faith-legend-ramp">
          {RAMP.map((c) => <span key={c} style={{ background: c }} />)}
        </span>
        <span>1</span>
        <span className="faith-legend-label">{t('faith.cosine', language)}</span>
      </div>
      <details className="faith-table">
        <summary>{t('faith.table', language)}</summary>
        <table>
          <thead>
            <tr>
              <th>{t('faith.sentence', language)}</th>
              {evidence.map((e, j) => <th key={j}>{e.tool}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                <td>{row.text}</td>
                {row.similarity.map((v, j) => <td key={j}>{v.toFixed(2)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

export function FaithfulnessPanel({ data, language }: { data?: Faithfulness; language: 'es' | 'pt' }) {
  if (!data) return null;
  const answers = data.answers.filter((a) => a.claims.length > 0 || a.sentences.length > 0);
  return (
    <section className="console-card faith" aria-labelledby="faith-title">
      <h3 id="faith-title">{t('faith.title', language)}</h3>
      <div className="faith-hero">
        <span className="faith-hero-number">{pct(data.overall)}</span>
        <span className="faith-hero-label">
          {data.overall == null ? t('faith.noClaims', language) : t('faith.overall', language)}
        </span>
      </div>
      {data.evidence.length === 0 && <p className="form-help">{t('faith.noEvidence', language)}</p>}
      {answers.map((answer, n) => (
        <div key={answer.index} className="faith-answer">
          <div className="faith-answer-head">
            <span>{t('faith.answer', language)} {n + 1}</span>
            {answer.score != null && (
              <span className="faith-bar" aria-label={`${t('faith.score', language)} ${pct(answer.score)}`}>
                <svg viewBox="0 0 100 8" width="120" height="8" aria-hidden="true">
                  <rect x="0" y="0" width="100" height="8" rx="4" fill="#e5e7eb" />
                  <rect x="0" y="0" width={Math.max(answer.score * 100, 4)} height="8" rx="4" fill={SERIES} />
                </svg>
                <strong>{pct(answer.score)}</strong>
              </span>
            )}
          </div>
          <MarkedAnswer text={answer.text} claims={answer.claims} language={language} />
          {data.evidence.length > 0 && answer.sentences.length > 0 && (
            <Heatmap answer={answer} evidence={data.evidence} language={language} />
          )}
        </div>
      ))}
      <p className="form-help">{t('faith.method', language)}</p>
    </section>
  );
}
