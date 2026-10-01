/** Charts for the knowledge search (RAG): embedding map, ES↔PT similarity, chunk sizes, abstention. */
import { useState } from 'react';
import { Frame, Legend } from './charts';
import { C, useTip } from './viz';

type ChunkPoint = { id: string; lang: string; title: string; words: number; xy: number[] };
type QuestionPoint = {
  id: string;
  lang: string;
  q: string;
  gold: string | null;
  ranks: Record<string, number | null>;
  top_cos: number | null;
  abstained: boolean;
  top_hit: string | null;
  xy: number[];
};

const short = (s: string, n = 34) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

const LANG_COLOR: Record<string, string> = { es: C.model, pt: C.compare };

export function EmbeddingMap({
  chunks,
  questions,
  variance,
}: {
  chunks: ChunkPoint[];
  questions: QuestionPoint[];
  variance: number[];
}) {
  const { show, hide, node } = useTip();
  const [showQuestions, setShowQuestions] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const width = 640;
  const height = 420;
  const pad = 24;
  const all = [...chunks.map((c) => c.xy), ...(showQuestions ? questions.map((q) => q.xy) : [])];
  const xs = all.map((p) => p[0]);
  const ys = all.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (v: number) => pad + ((v - x0) / (x1 - x0)) * (width - 2 * pad);
  const sy = (v: number) => height - pad - ((v - y0) / (y1 - y0)) * (height - 2 * pad);
  const find = (id: string, lang: string) => chunks.find((c) => c.id === id && c.lang === lang);
  const topics = [...new Set(chunks.map((c) => c.id))];
  const activeQ = questions.find((q) => q.id === active);

  return (
    <Frame label="Mapa de embeddings: fragmentos y preguntas proyectados a 2D">
      <div className="viz-toolbar">
        <Legend
          items={[
            { label: 'Fragmento ES', color: LANG_COLOR.es },
            { label: 'Fragmento PT', color: LANG_COLOR.pt, shape: 'square' },
            { label: 'Pregunta de test', color: 'var(--viz-muted)' },
          ]}
        />
        <label className="viz-check">
          <input type="checkbox" checked={showQuestions} onChange={(e) => setShowQuestions(e.target.checked)} />
          Mostrar preguntas
        </label>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="viz-svg viz-map" role="img">
        <rect x={0} y={0} width={width} height={height} rx={8} className="viz-plot-bg" />
        {topics.map((t) => {
          const es = find(t, 'es');
          const pt = find(t, 'pt');
          if (!es || !pt) return null;
          return (
            <line
              key={t}
              x1={sx(es.xy[0])}
              y1={sy(es.xy[1])}
              x2={sx(pt.xy[0])}
              y2={sy(pt.xy[1])}
              className="viz-pair"
            />
          );
        })}
        {activeQ?.gold &&
          (() => {
            const g = find(activeQ.gold, activeQ.lang);
            return g ? (
              <line
                x1={sx(activeQ.xy[0])}
                y1={sy(activeQ.xy[1])}
                x2={sx(g.xy[0])}
                y2={sy(g.xy[1])}
                className="viz-link"
              />
            ) : null;
          })()}
        {showQuestions &&
          questions.map((q) => (
            <circle
              key={q.id}
              cx={sx(q.xy[0])}
              cy={sy(q.xy[1])}
              r={active === q.id ? 6 : 4}
              className={`viz-q${q.gold ? '' : ' viz-q-none'}`}
              onMouseMove={(e) => {
                setActive(q.id);
                show(
                  <>
                    <b>“{q.q}”</b>
                    <br />
                    {q.gold ? (
                      <>
                        Documento correcto: {q.gold}
                        <br />
                        Posición en la búsqueda híbrida: {q.ranks.hybrid}
                      </>
                    ) : (
                      <>Sin respuesta en la base: {q.abstained ? 'la búsqueda se abstuvo ✓' : 'la búsqueda devolvió algo'}</>
                    )}
                  </>,
                )(e);
              }}
              onMouseLeave={() => {
                setActive(null);
                hide();
              }}
            />
          ))}
        {chunks.map((c) => {
          const cx = sx(c.xy[0]);
          const cy = sy(c.xy[1]);
          const tip = show(
            <>
              <b>{c.title}</b>
              <br />
              {c.lang.toUpperCase()} · {c.words} palabras · tema “{c.id}”
            </>,
          );
          return c.lang === 'es' ? (
            <circle key={c.lang + c.id} cx={cx} cy={cy} r={7} fill={LANG_COLOR.es} className="viz-mark" onMouseMove={tip} onMouseLeave={hide} />
          ) : (
            <rect key={c.lang + c.id} x={cx - 6} y={cy - 6} width={12} height={12} rx={2} fill={LANG_COLOR.pt} className="viz-mark" onMouseMove={tip} onMouseLeave={hide} />
          );
        })}
      </svg>
      <figcaption>
        Cada punto es un vector de 512 dimensiones (Titan V2) proyectado a 2D con PCA, que conserva el{' '}
        {Math.round(100 * (variance[0] + variance[1]))}% de la varianza: las distancias son aproximadas. Las
        líneas grises unen el mismo tema en español y en portugués. Pasa el ratón por una pregunta para ver
        su documento correcto (las preguntas sin respuesta en la base son los círculos vacíos).
      </figcaption>
      {node}
    </Frame>
  );
}

export function CrossLingual({
  items,
  otherMean,
  otherMax,
  titles,
}: {
  items: { id: string; cos: number }[];
  otherMean: number;
  otherMax: number;
  titles: Record<string, string>;
}) {
  const { show, hide, node } = useTip();
  const sorted = [...items].sort((a, b) => b.cos - a.cos);
  const width = 640;
  const left = 230;
  const row = 20;
  const height = sorted.length * row + 30;
  const x = (v: number) => left + v * (width - left - 50);
  return (
    <Frame label="Similitud entre el mismo tema en español y portugués">
      <svg viewBox={`0 0 ${width} ${height}`} className="viz-svg" role="img">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={0} y2={height - 18} className="viz-grid" />
            <text x={x(t)} y={height - 4} className="viz-axis" textAnchor="middle">
              {t.toFixed(2)}
            </text>
          </g>
        ))}
        <rect x={x(0)} y={0} width={x(otherMean) - x(0)} height={height - 20} className="viz-band" />
        <line x1={x(otherMean)} x2={x(otherMean)} y1={0} y2={height - 20} className="viz-ref" />
        <line x1={x(otherMax)} x2={x(otherMax)} y1={0} y2={height - 20} className="viz-ref viz-ref-soft" />
        {sorted.map((it, i) => {
          const y = i * row + 12;
          return (
            <g
              key={it.id}
              onMouseMove={show(
                <>
                  <b>{titles[it.id] ?? it.id}</b>
                  <br />
                  Coseno ES↔PT: {it.cos.toFixed(3)} (temas distintos: media {otherMean.toFixed(2)})
                </>,
              )}
              onMouseLeave={hide}
            >
              <rect x={0} y={y - 9} width={width} height={row} fill="transparent" />
              <text x={left - 8} y={y + 4} className="viz-label viz-small" textAnchor="end">
                {short(titles[it.id] ?? it.id)}
              </text>
              <line x1={x(otherMean)} x2={x(it.cos)} y1={y} y2={y} className="viz-stem" />
              <circle cx={x(it.cos)} cy={y} r={5} fill={C.model} />
            </g>
          );
        })}
      </svg>
      <figcaption>
        Punto azul: similitud del mismo tema entre idiomas. Línea gris continua: media entre temas{' '}
        <b>distintos</b> ({otherMean.toFixed(2)}). Línea tenue: el par de temas distintos más parecido (
        {otherMax.toFixed(2)}).
      </figcaption>
      {node}
    </Frame>
  );
}

export function ChunkSizes({ chunks }: { chunks: ChunkPoint[] }) {
  const { show, hide, node } = useTip();
  const bin = 5;
  const lo = Math.floor(Math.min(...chunks.map((c) => c.words)) / bin) * bin;
  const hi = Math.ceil((Math.max(...chunks.map((c) => c.words)) + 1) / bin) * bin;
  const bins: { from: number; es: ChunkPoint[]; pt: ChunkPoint[] }[] = [];
  for (let b = lo; b < hi; b += bin) {
    const inBin = chunks.filter((c) => c.words >= b && c.words < b + bin);
    bins.push({ from: b, es: inBin.filter((c) => c.lang === 'es'), pt: inBin.filter((c) => c.lang === 'pt') });
  }
  const maxCount = Math.max(...bins.map((b) => b.es.length + b.pt.length));
  const width = 640;
  const height = 200;
  const bottom = 26;
  const colW = (width - 40) / bins.length;
  const unit = (height - bottom - 10) / maxCount;
  return (
    <Frame label="Tamaño de los fragmentos en palabras">
      <Legend
        items={[
          { label: 'Español', color: LANG_COLOR.es },
          { label: 'Portugués', color: LANG_COLOR.pt },
        ]}
      />
      <svg viewBox={`0 0 ${width} ${height}`} className="viz-svg" role="img">
        <line x1={30} x2={width - 10} y1={height - bottom} y2={height - bottom} className="viz-baseline" />
        {bins.map((b, i) => {
          const x = 30 + i * colW + 3;
          const esH = b.es.length * unit;
          const ptH = b.pt.length * unit;
          const base = height - bottom;
          const tip = show(
            <>
              <b>
                {b.from}–{b.from + bin - 1} palabras
              </b>
              <br />
              ES {b.es.length} · PT {b.pt.length}
              {[...b.es, ...b.pt].slice(0, 4).map((c) => (
                <div key={c.lang + c.id} className="viz-tip-sub">
                  {c.lang.toUpperCase()} {c.title}
                </div>
              ))}
            </>,
          );
          return (
            <g key={b.from} onMouseMove={tip} onMouseLeave={hide}>
              <rect x={x - 3} y={0} width={colW} height={height} fill="transparent" />
              {esH > 0 && <rect x={x} y={base - esH} width={colW - 6} height={esH} rx={3} fill={LANG_COLOR.es} />}
              {ptH > 0 && (
                <rect x={x} y={base - esH - ptH} width={colW - 6} height={Math.max(0, ptH - 2)} rx={3} fill={LANG_COLOR.pt} />
              )}
              <text x={x + (colW - 6) / 2} y={height - 8} className="viz-axis" textAnchor="middle">
                {b.from}
              </text>
            </g>
          );
        })}
      </svg>
      {node}
    </Frame>
  );
}

export function AbstentionStrip({ questions, threshold }: { questions: QuestionPoint[]; threshold: number }) {
  const { show, hide, node } = useTip();
  const width = 640;
  const left = 150;
  const height = 150;
  const vals = questions.map((q) => q.top_cos ?? 0);
  const [lo, hi] = [0.1, Math.max(0.7, ...vals)];
  const x = (v: number) => left + ((v - lo) / (hi - lo)) * (width - left - 20);
  const rows = [
    { label: 'Con respuesta', items: questions.filter((q) => q.gold), y: 40 },
    { label: 'Sin respuesta', items: questions.filter((q) => !q.gold), y: 95 },
  ];
  return (
    <Frame label="Similitud del mejor fragmento, por tipo de pregunta">
      <svg viewBox={`0 0 ${width} ${height}`} className="viz-svg" role="img">
        {[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={10} y2={height - 22} className="viz-grid" />
            <text x={x(t)} y={height - 6} className="viz-axis" textAnchor="middle">
              {t.toFixed(1)}
            </text>
          </g>
        ))}
        <rect x={x(lo)} y={10} width={x(threshold) - x(lo)} height={height - 32} className="viz-band" />
        <line x1={x(threshold)} x2={x(threshold)} y1={6} y2={height - 22} className="viz-ref" />
        <text x={x(threshold) + 6} y={16} className="viz-note">
          umbral {threshold}
        </text>
        {rows.map((r) => (
          <g key={r.label}>
            <text x={left - 12} y={r.y + 4} className="viz-label" textAnchor="end">
              {r.label} ({r.items.length})
            </text>
            {r.items.map((q, i) => (
              <circle
                key={q.id}
                cx={x(q.top_cos ?? 0)}
                cy={r.y + ((i % 5) - 2) * 4}
                r={5}
                fill={q.gold ? C.model : C.compare}
                className="viz-dot"
                onMouseMove={show(
                  <>
                    <b>“{q.q}”</b>
                    <br />
                    Coseno del mejor fragmento: {(q.top_cos ?? 0).toFixed(3)}
                    <br />
                    {q.abstained ? 'La búsqueda se abstuvo' : `Devolvió “${q.top_hit}”`}
                  </>,
                )}
                onMouseLeave={hide}
              />
            ))}
          </g>
        ))}
      </svg>
      <figcaption>
        Las preguntas sin respuesta (naranja) caen en la misma zona que las que sí la tienen: por eso
        un umbral de similitud solo descarta las claramente fuera de tema, y el resto lo decide el
        modelo al leer los fragmentos.
      </figcaption>
      {node}
    </Frame>
  );
}
