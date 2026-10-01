/**
 * ModelsPage — how we know the two learned components work: the intent classifier and the
 * knowledge search (RAG), and what a conversation costs in tokens. Every number comes from the
 * evaluation files in the repo, exported by ml/export_metrics_page.py into src/data/modelMetrics.json.
 *
 * The password is a demo gate, not security: it is shown in the field so judges can get in, and the
 * page holds no customer data (the same idea as the agent console's published key).
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Brain, Coins, Headset, LineChart, Search } from 'lucide-react';
import { KEYS, loadStored, saveStored } from '../../utils/persist';
import metrics from '../../data/modelMetrics.json';
import { Confusion, DotRows, HBars, Segmented } from '../../components/models/charts';
import { C, pct } from '../../components/models/viz';
import { AbstentionStrip, ChunkSizes, CrossLingual, EmbeddingMap } from '../../components/models/ragCharts';
import '../../styles/models.css';

const { intent, rag, cost } = metrics;

export const MODELS_PASSWORD = 'Modelos2026';

const usd = (v: number, digits = 4) => `$${v.toFixed(digits)}`;

const KIND_ES: Record<string, string> = {
  account: 'Consulta de sus cuentas',
  public: 'Pregunta pública (sin login)',
  verification: 'Verificación en el chat',
  ambiguous: 'Petición ambigua',
  handoff: 'Pasar a un asesor',
  unsupported: 'Algo que Nova no puede hacer',
  unsafe: 'Intento inseguro (bloqueado)',
};

const INTENT_ES: Record<string, string> = {
  transactional: 'Transaccional',
  product: 'Producto',
  complaint: 'Queja',
  technical: 'Técnico',
  commercial: 'Comercial',
  retention: 'Retención',
  other: 'Otro',
};

const RETRIEVERS = [
  { key: 'hybrid', label: 'Híbrida (en producción)' },
  { key: 'dense', label: 'Solo embeddings' },
  { key: 'bm25-words', label: 'BM25 palabras' },
  { key: 'bm25-stems', label: 'BM25 raíces' },
] as const;

type Scope = 'all' | 'es' | 'pt';
type RankMetric = 'recall@1' | 'recall@3' | 'mrr';

function Stat({ value, label, sub }: { value: string; label: string; sub?: string }) {
  return (
    <div className="models-stat">
      <div className="models-stat-value">{value}</div>
      <div className="models-stat-label">{label}</div>
      {sub && <div className="models-stat-sub">{sub}</div>}
    </div>
  );
}

function Card({ title, question, children }: { title: string; question?: string; children: React.ReactNode }) {
  return (
    <section className="models-card">
      <header>
        <h3>{title}</h3>
        {question && <p className="models-question">{question}</p>}
      </header>
      {children}
    </section>
  );
}

function IntentSection() {
  const t = intent.test;
  const [few, zero] = [intent.llm[2], intent.llm[1]];
  const ab = intent.ablation.cells;
  const fcr = Object.entries(intent.fcr).sort((a, b) => a[1].fcr - b[1].fcr);
  return (
    <>
      <div className="models-section-head" id="clasificador">
        <Brain size={22} aria-hidden="true" />
        <div>
          <h2>Clasificador de intención</h2>
          <p>
            Lee cada mensaje del cliente y decide el motivo de contacto (6 motivos del banco + “otro”). Si es
            una queja o retención, los motivos que el banco casi nunca resuelve al primer contacto, Nova ofrece
            un asesor antes. TF-IDF + regresión logística, {intent.data.train.es + intent.data.train.pt} frases
            de entrenamiento y {intent.data.test.es + intent.data.test.pt} de test escritas aparte (ES + PT).
          </p>
        </div>
      </div>

      <div className="models-stats">
        <Stat value={t.model.macro_f1.toFixed(2)} label="Macro-F1 en test" sub={`palabras clave: ${t.keywords.macro_f1.toFixed(2)}`} />
        <Stat value={pct(intent.calibration.confident_accuracy)} label="Acierto cuando está seguro" sub={`en el ${pct(intent.calibration.confident_coverage)} de los mensajes (p ≥ ${intent.selection.threshold})`} />
        <Stat value={`+${Math.round(100 * (ab.target_on.person / ab.target_on.runs - ab.target_off.person / ab.target_off.runs))} pts`} label="Más quejas derivadas a una persona" sub="con el modelo activo, en el agente real" />
        <Stat value="0,3 ms" label="Por mensaje" sub="sin coste, sin llamar a otro modelo" />
      </div>

      <div className="models-grid">
        <Card title="¿Es mejor que las alternativas?" question="Macro-F1 sobre las 210 frases de test (ninguna vista al entrenar).">
          <HBars
            labelWidth={190}
            format={(v) => v.toFixed(3)}
            bars={[
              { label: 'Clase mayoritaria', value: t.majority.macro_f1, color: C.base },
              { label: 'Reglas de palabras clave', value: t.keywords.macro_f1, color: C.base },
              {
                label: 'Nuestro modelo',
                value: t.model.macro_f1,
                color: C.model,
                note: '· 0,3 ms · $0',
                tip: `Nuestro modelo: ${t.model.macro_f1.toFixed(3)} · ES ${intent.llm[0].es.toFixed(3)} / PT ${intent.llm[0].pt.toFixed(3)}`,
              },
              {
                label: 'Claude zero-shot',
                value: zero.macro_f1,
                color: C.compare,
                note: `· ${Math.round(zero.latency_ms)} ms`,
                tip: `Claude Haiku zero-shot: ${zero.macro_f1.toFixed(3)} · ${Math.round(zero.latency_ms)} ms · $${zero.cost_per_1000.toFixed(2)} por 1.000`,
              },
              {
                label: 'Claude few-shot',
                value: few.macro_f1,
                color: C.compare,
                note: `· ${Math.round(few.latency_ms)} ms`,
                tip: `Claude Haiku few-shot: ${few.macro_f1.toFixed(3)} · ${Math.round(few.latency_ms)} ms · $${few.cost_per_1000.toFixed(2)} por 1.000`,
              },
            ]}
          />
          <p className="models-read">
            Claude acierta algo más, pero tarda ~1.900 veces más y añadiría medio segundo a cada mensaje. Con
            210 frases la diferencia entre 0,85 y 0,91 está cerca del ruido.
          </p>
        </Card>

        <Card title="¿Dónde acierta y dónde falla?" question="F1 por intención: cada fila compara los tres clasificadores.">
          <DotRows
            series={[
              { label: 'Palabras clave', color: C.base },
              { label: 'Nuestro modelo', color: C.model },
              { label: 'Claude few-shot', color: C.compare },
            ]}
            rows={intent.classes.map((c) => ({
              label: INTENT_ES[c],
              values: [
                t.keywords.f1_by_class[c as keyof typeof t.keywords.f1_by_class],
                t.model.f1_by_class[c as keyof typeof t.model.f1_by_class],
                few.f1_by_class[c as keyof typeof few.f1_by_class],
              ],
            }))}
          />
          <p className="models-read">
            Técnico y retención casi perfectos. El punto débil es transaccional y producto: preguntas de dinero
            redactadas como problema (“me rebotaron la tarjeta”) se confunden con queja.
          </p>
        </Card>

        <Card title="Matriz de confusión" question="Cada fila es la intención real; la diagonal son los aciertos.">
          <Confusion
            labels={intent.confusion.labels}
            names={intent.confusion.labels.map((l) => INTENT_ES[l])}
            rows={intent.confusion.rows_true_cols_pred}
          />
        </Card>

        <Card title="¿Cambia lo que hace Nova?" question="32 mensajes nuevos × 3 repeticiones en el agente real (Bedrock), con y sin la pista del modelo.">
          <HBars
            labelWidth={230}
            format={(v) => pct(v)}
            bars={[
              {
                label: 'Quejas/retención · con modelo',
                value: ab.target_on.person / ab.target_on.runs,
                color: C.model,
                note: `(${ab.target_on.person}/${ab.target_on.runs})`,
              },
              {
                label: 'Quejas/retención · sin modelo',
                value: ab.target_off.person / ab.target_off.runs,
                color: C.base,
                note: `(${ab.target_off.person}/${ab.target_off.runs})`,
              },
              {
                label: 'Otros mensajes · con modelo',
                value: ab.control_on.person / ab.control_on.runs,
                color: C.model,
                note: `(${ab.control_on.person}/${ab.control_on.runs})`,
              },
              {
                label: 'Otros mensajes · sin modelo',
                value: ab.control_off.person / ab.control_off.runs,
                color: C.base,
                note: `(${ab.control_off.person}/${ab.control_off.runs})`,
              },
            ]}
          />
          <p className="models-read">
            Porcentaje de conversaciones en las que Nova ofreció un asesor o abrió un caso. Con el modelo sube
            donde debe (quejas) y apenas cambia donde no hace falta (otros mensajes).
          </p>
        </Card>

        <Card title="¿Por qué importa la intención?" question="Resolución al primer contacto (FCR) real del banco por motivo, 686 mil interacciones.">
          <HBars
            labelWidth={150}
            format={(v) => pct(v)}
            bars={fcr.map(([k, v]) => ({
              label: INTENT_ES[k],
              value: v.fcr,
              color: k === 'complaint' || k === 'retention' ? C.model : C.base,
              tip: `${INTENT_ES[k]}: FCR ${pct(v.fcr, 1)} en ${v.interactions.toLocaleString('es')} interacciones`,
            }))}
          />
          <p className="models-read">
            Las quejas se resuelven al primer contacto solo el {pct(intent.fcr.complaint.fcr)} de las veces: detectarlas
            pronto es lo que permite pasar a una persona antes de que el cliente se frustre.
          </p>
        </Card>

        <Card title="¿Podemos fiarnos de su confianza?" question="Calibración y umbral elegidos solo con validación cruzada sobre entrenamiento.">
          <div className="models-stats models-stats-inner">
            <Stat value={intent.calibration.ece.toFixed(2)} label="Error de calibración (ECE)" sub="0 = perfecto" />
            <Stat value={String(intent.selection.threshold)} label="Umbral de confianza" sub="≥ 90% de precisión en CV" />
            <Stat value={pct(intent.calibration.confident_coverage)} label="Mensajes por encima" sub={`acierto ${pct(intent.calibration.confident_accuracy)}`} />
            <Stat value={intent.leakage.median.toFixed(2)} label="Parecido test↔train (mediana)" sub="Jaccard 4-gramas: no hay fuga" />
          </div>
        </Card>
      </div>
    </>
  );
}

function RagSection() {
  const [scope, setScope] = useState<Scope>('all');
  const [metric, setMetric] = useState<RankMetric>('recall@1');
  const ranking = rag.ranking[scope];
  const hybrid = rag.abstention.hybrid.test;
  const titles = Object.fromEntries(rag.chunks.filter((c) => c.lang === 'es').map((c) => [c.id, c.title]));
  const words = rag.chunks.map((c) => c.words);
  const sameMean = rag.crosslingual.same_topic.reduce((a, b) => a + b.cos, 0) / rag.crosslingual.same_topic.length;

  return (
    <>
      <div className="models-section-head" id="rag">
        <Search size={22} aria-hidden="true" />
        <div>
          <h2>Búsqueda de conocimiento (RAG)</h2>
          <p>
            Las respuestas sobre productos y políticas salen de documentos, no de la memoria del modelo. Búsqueda
            híbrida: BM25 + embeddings {rag.embedding.model.replace('amazon.', '')} ({rag.embedding.dimensions}{' '}
            dimensiones), fusionadas por rango. Evaluada con {rag.questions.test} preguntas de test coloquiales,
            escritas después de los documentos.
          </p>
        </div>
      </div>

      <div className="models-stats">
        <Stat value={pct(rag.ranking.all.hybrid['recall@1'].rate)} label="Recall@1" sub="el documento correcto sale primero" />
        <Stat value={pct(rag.ranking.all.hybrid['recall@3'].rate)} label="Recall@3" sub="está entre los 3 que lee el modelo" />
        <Stat value={rag.ranking.all.hybrid.mrr.toFixed(2)} label="MRR" sub="1 = siempre primero" />
        <Stat value={sameMean.toFixed(2)} label="Similitud ES↔PT del mismo tema" sub={`temas distintos: ${rag.crosslingual.other_topic_mean.toFixed(2)}`} />
      </div>

      <div className="models-grid">
        <Card title="Recall: ¿encuentra el documento correcto?" question="Preguntas de test con respuesta en la base. La barra fina es el intervalo de confianza del 95%.">
          <div className="viz-filters">
            <Segmented
              label="Métrica"
              value={metric}
              onChange={setMetric}
              options={[
                { value: 'recall@1', label: 'Recall@1' },
                { value: 'recall@3', label: 'Recall@3' },
                { value: 'mrr', label: 'MRR' },
              ]}
            />
            <Segmented
              label="Idioma"
              value={scope}
              onChange={setScope}
              options={[
                { value: 'all', label: 'Todos' },
                { value: 'es', label: 'Español' },
                { value: 'pt', label: 'Portugués' },
              ]}
            />
          </div>
          <HBars
            labelWidth={190}
            format={(v) => (metric === 'mrr' ? v.toFixed(3) : pct(v))}
            bars={RETRIEVERS.map(({ key, label }) => {
              const r = ranking[key];
              const m = metric === 'mrr' ? null : r[metric];
              return {
                label,
                value: m ? m.rate : r.mrr,
                ci: m ? (m.ci95 as [number, number]) : undefined,
                note: m ? `(${m.k}/${m.n})` : undefined,
                color: key === 'hybrid' ? C.model : C.base,
                tip: m
                  ? `${label}: ${m.k} de ${m.n} preguntas (IC95 ${pct(m.ci95[0])}–${pct(m.ci95[1])})`
                  : `${label}: MRR ${r.mrr.toFixed(3)}`,
              };
            })}
          />
          <p className="models-read">
            Los embeddings aportan lo que BM25 no ve (sinónimos, otra forma de decirlo): Recall@3 pasa de 92% a
            97%. La híbrida es igual o mejor que cada señal sola, sobre todo en portugués; los intervalos se
            solapan, así que es “al menos tan buena”, no una ventaja demostrada.
          </p>
        </Card>

        <Card title="Embeddings: ¿entiende el significado?" question="Mapa de los fragmentos y las preguntas en el espacio de embeddings.">
          <EmbeddingMap chunks={rag.chunks} questions={rag.test_questions} variance={rag.embedding.pca_variance} />
        </Card>

        <Card title="Embeddings: ¿es realmente multilingüe?" question="Coseno entre el mismo documento en español y en portugués, frente a documentos distintos.">
          <CrossLingual
            items={rag.crosslingual.same_topic}
            otherMean={rag.crosslingual.other_topic_mean}
            otherMax={rag.crosslingual.other_topic_max}
            titles={titles}
          />
        </Card>

        <Card title="Chunking: ¿cómo se partieron los documentos?" question={`${rag.chunks.length} fragmentos: un tema = una idea, el mismo tema en ES y PT, sin solapamiento.`}>
          <ChunkSizes chunks={rag.chunks} />
          <div className="models-stats models-stats-inner">
            <Stat value={String(rag.chunks.length)} label="Fragmentos" sub={`${rag.chunks.length / 2} temas × 2 idiomas`} />
            <Stat value={`${Math.min(...words)}–${Math.max(...words)}`} label="Palabras por fragmento" sub="cabe entero en el contexto" />
            <Stat value={pct(rag.ranking.all.hybrid['recall@3'].rate)} label="Con el correcto en el top 3" sub="lo que lee el modelo" />
          </div>
          <p className="models-read">
            Con fragmentos cortos de una sola idea no hace falta solapamiento: cada uno responde una pregunta
            completa. No comparamos otros tamaños de chunk; con 42 fragmentos el método está probado, no su
            escala.
          </p>
        </Card>

        <Card title="¿Sabe decir “no lo sé”?" question="Similitud del mejor fragmento para cada pregunta de test. Por debajo del umbral, la búsqueda se abstiene.">
          <AbstentionStrip questions={rag.test_questions} threshold={rag.thresholds.dense} />
          <div className="models-stats models-stats-inner">
            <Stat value={pct(hybrid.decision_accuracy.rate)} label="Decisión correcta" sub={`${hybrid.decision_accuracy.k}/${hybrid.decision_accuracy.n} preguntas`} />
            <Stat value={`${hybrid.abstained_answerable.k}/${hybrid.abstained_answerable.n}`} label="Respondibles descartadas" sub="la búsqueda prioriza no perder respuestas" />
            <Stat value={`${hybrid.answered_unanswerable.n - hybrid.answered_unanswerable.k}/${hybrid.answered_unanswerable.n}`} label="Sin respuesta, frenadas aquí" sub="el resto lo decide el modelo al leer" />
          </div>
        </Card>
      </div>
    </>
  );
}


function CostSection() {
  const all = cost.all;
  const inPrice = cost.price_per_token.input;
  const outPrice = cost.price_per_token.output;
  const inCost = all.input_tokens_per_conversation * inPrice;
  const outCost = all.output_tokens_per_conversation * outPrice;
  const kinds = Object.entries(cost.by_kind).sort((a, b) => b[1].cost_per_conversation - a[1].cost_per_conversation);
  const top = Math.max(...kinds.map(([, k]) => k.cost_per_conversation));
  const max = Math.ceil(top * 1000) / 1000;
  const claudeClassifier = intent.llm[1].cost_per_1000;
  return (
    <>
      <div className="models-section-head" id="coste">
        <Coins size={22} aria-hidden="true" />
        <div>
          <h2>Coste por token</h2>
          <p>
            Lo que cuesta cada conversación con Nova ({cost.model.replace('us.anthropic.', '').replace('-v1:0', '')} en
            Bedrock), calculado con los tokens que Bedrock reportó en las {all.conversations} conversaciones de la
            evaluación final, a ${cost.price_per_mtok.input} por millón de tokens de entrada y $
            {cost.price_per_mtok.output} por millón de salida.
          </p>
        </div>
      </div>

      <div className="models-stats">
        <Stat value={usd(all.cost_per_conversation)} label="Por conversación" sub={`p95 ${usd(cost.p95_per_conversation)}`} />
        <Stat value={usd(all.cost_per_conversation * 1000, 2)} label="Por 1.000 conversaciones" sub={`${usd(all.cost_per_message * 1000, 2)} por 1.000 mensajes`} />
        <Stat value={all.input_tokens_per_conversation.toLocaleString('es')} label="Tokens de entrada por conversación" sub={`${all.output_tokens_per_conversation} de salida`} />
        <Stat value={pct(all.input_share_of_cost)} label="Del coste es entrada" sub="prompt, herramientas y datos del cliente" />
      </div>

      <div className="models-grid">
        <Card title="¿Cómo se calcula?" question="Precio por token y una conversación media, paso a paso.">
          <table className="models-table">
            <thead>
              <tr>
                <th />
                <th>Precio por token</th>
                <th>Tokens</th>
                <th>Coste</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Entrada</td>
                <td>{usd(inPrice, 6)}</td>
                <td>{all.input_tokens_per_conversation.toLocaleString('es')}</td>
                <td>{usd(inCost, 6)}</td>
              </tr>
              <tr>
                <td>Salida</td>
                <td>{usd(outPrice, 6)}</td>
                <td>{all.output_tokens_per_conversation.toLocaleString('es')}</td>
                <td>{usd(outCost, 6)}</td>
              </tr>
              <tr className="models-table-total">
                <td>Total</td>
                <td />
                <td>{(all.input_tokens_per_conversation + all.output_tokens_per_conversation).toLocaleString('es')}</td>
                <td>{usd(inCost + outCost, 6)}</td>
              </tr>
            </tbody>
          </table>
          <p className="models-read">
            coste = tokens de entrada × {usd(inPrice, 6)} + tokens de salida × {usd(outPrice, 6)}. La salida es 5 veces
            más cara por token, pero Nova escribe respuestas cortas: lo que pesa es la entrada.
          </p>
          <div className="models-stats models-stats-inner">
            <Stat value="$0" label="Clasificador de intención" sub={`corre en la Lambda; con Claude serían $${claudeClassifier.toFixed(2)} por 1.000`} />
            <Stat value={`$${cost.titan_price_per_mtok}`} label="Embeddings por millón de tokens" sub="Titan V2: una pregunta ≈ $0,000001" />
          </div>
        </Card>

        <Card title="¿Qué conversaciones cuestan más?" question="Coste medio por conversación según el tipo de caso de la evaluación.">
          <HBars
            labelWidth={230}
            max={max}
            format={(v) => usd(v)}
            tickFormat={(v) => usd(v, 3)}
            bars={kinds.map(([k, v]) => ({
              label: KIND_ES[k] ?? k,
              value: v.cost_per_conversation,
              color: C.model,
              tip: (
                <>
                  <b>{KIND_ES[k] ?? k}</b> ({v.conversations} conversaciones, {v.messages} mensajes)
                  <br />
                  {v.input_tokens_per_conversation.toLocaleString('es')} tokens de entrada ·{' '}
                  {v.output_tokens_per_conversation} de salida
                  <br />
                  {usd(v.cost_per_conversation)} por conversación · {usd(v.cost_per_message)} por mensaje
                </>
              ),
            }))}
          />
          <p className="models-read">
            Las consultas de cuenta leen los datos del cliente con herramientas, y eso es entrada. La verificación
            en el chat cuesta más porque son 5 mensajes, aunque cada uno es de los más baratos.
          </p>
        </Card>
      </div>
    </>
  );
}

function ModelsGate({ onEnter }: { onEnter: () => void }) {
  const [value, setValue] = useState('');
  const [error, setError] = useState(false);
  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (value === MODELS_PASSWORD) {
      saveStored(KEYS.models, true);
      onEnter();
    } else {
      setError(true);
    }
  }
  return (
    <div className="models-gate">
      <form className="models-gate-card" onSubmit={submit}>
        <LineChart size={28} aria-hidden="true" />
        <h1>¿Funcionan los modelos?</h1>
        <p>Métricas del clasificador de intención, la búsqueda de conocimiento y el coste por token.</p>
        <label htmlFor="models-password">Contraseña</label>
        <input
          id="models-password"
          type="password"
          className="form-input"
          placeholder={MODELS_PASSWORD}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setError(false);
          }}
          autoComplete="off"
        />
        {error && (
          <p className="form-error" role="alert">
            Contraseña incorrecta.
          </p>
        )}
        <button type="submit" className="btn-primary">
          Entrar
        </button>
        <p className="form-help">Demo: la contraseña es la que aparece en el campo.</p>
        <Link to="/asesor" className="models-gate-link">
          <Headset size={14} aria-hidden="true" /> Ir a la consola del asesor
        </Link>
      </form>
    </div>
  );
}

export default function ModelsPage() {
  const [entered, setEntered] = useState(() => loadStored<boolean>(KEYS.models) === true);
  if (!entered) return <ModelsGate onEnter={() => setEntered(true)} />;
  return (
    <div className="models-page">
      <header className="models-hero">
        <div className="models-top-links">
          <Link to="/login" className="models-back">
            <ArrowLeft size={16} aria-hidden="true" /> NovaBank
          </Link>
          <Link to="/asesor" className="models-back">
            <Headset size={16} aria-hidden="true" /> Consola del asesor
          </Link>
        </div>
        <h1>¿Funcionan los modelos?</h1>
        <p>
          Las métricas que usamos para decidir si cada componente aprendido hace bien su trabajo, medidas sobre
          datos que el modelo no vio. Pasa el ratón por cualquier gráfica para ver el detalle.
        </p>
        <nav className="models-tabs" aria-label="Secciones">
          <a href="#clasificador">Clasificador de intención</a>
          <a href="#rag">Búsqueda de conocimiento</a>
          <a href="#coste">Coste por token</a>
          <a href="#limites">Límites</a>
        </nav>
      </header>

      <main className="models-main">
        <IntentSection />
        <RagSection />
        <CostSection />

        <section className="models-limits" id="limites">
          <h2>Límites, sin esconderlos</h2>
          <ul>
            <li>
              Frases y preguntas escritas por el equipo (sintéticas), no tráfico real: muestran que el modelo
              generaliza entre estilos que escribimos, no a clientes reales. Las transcripciones del banco no
              tienen señal para entrenar (42 textos distintos en 171 mil).
            </li>
            <li>
              Muestras pequeñas (210 frases, 38 preguntas con respuesta): diferencias de pocos puntos están dentro
              del ruido; por eso mostramos intervalos de confianza.
            </li>
            <li>
              Abstenerse es lo más débil de la búsqueda: la similitud no separa bien una pregunta sin respuesta de
              una difícil, y esa decisión la toma el modelo al leer los fragmentos.
            </li>
            <li>Los documentos y cifras de NovaBank son ficticios, escritos para la demo.</li>
          </ul>
          <p className="models-source">
            Fuente: <code>ml/intent/metrics.json</code>, <code>ml/intent/llm_baseline.json</code>,{' '}
            <code>ml/intent/ablation.json</code>, <code>ml/rag/metrics.json</code>, el índice de embeddings y{' '}
            <code>{cost.source}</code>,
            exportados con <code>ml/export_metrics_page.py</code>.
          </p>
        </section>
      </main>
    </div>
  );
}
