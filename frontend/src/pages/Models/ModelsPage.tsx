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
import { C, INTENT, pct, usd } from '../../components/models/viz';
import { AbstentionStrip, ChunkSizes, CrossLingual, EmbeddingMap } from '../../components/models/ragCharts';
import { Card, Stat } from '../../components/models/cards';
import LiveSection from '../../components/models/LiveSection';
import '../../styles/models.css';

const { intent, rag, cost } = metrics;

export const MODELS_PASSWORD = 'Modelos2026';

const KIND: Record<string, string> = {
  account: 'Questions about their accounts',
  public: 'Public question (no login)',
  verification: 'Identity check in the chat',
  ambiguous: 'Ambiguous request',
  handoff: 'Hand over to a person',
  unsupported: 'Something Nova cannot do',
  unsafe: 'Unsafe attempt (blocked)',
};

/** A topic id ("declined-purchase") as a label ("Declined Purchase"): the documents are in ES and PT. */
const topicLabel = (id: string) => id.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

const RETRIEVERS = [
  { key: 'hybrid', label: 'Hybrid (in production)' },
  { key: 'dense', label: 'Embeddings only' },
  { key: 'bm25-words', label: 'BM25 words' },
  { key: 'bm25-stems', label: 'BM25 stems' },
] as const;

type Scope = 'all' | 'es' | 'pt';
type RankMetric = 'recall@1' | 'recall@3' | 'mrr';

function IntentSection() {
  const t = intent.test;
  const [few, zero] = [intent.llm[2], intent.llm[1]];
  const ab = intent.ablation.cells;
  const fcr = Object.entries(intent.fcr).sort((a, b) => a[1].fcr - b[1].fcr);
  return (
    <>
      <div className="models-section-head" id="intent">
        <Brain size={22} aria-hidden="true" />
        <div>
          <h2>Intent classifier</h2>
          <p>
            Reads every customer message and picks the contact reason (the bank's 6 reasons + “other”). For a
            complaint or a retention request, the reasons the bank rarely solves on the first contact, Nova offers a
            person sooner. TF-IDF + logistic regression, {intent.data.train.es + intent.data.train.pt} training
            phrases and {intent.data.test.es + intent.data.test.pt} test phrases written separately (Spanish +
            Portuguese).
          </p>
        </div>
      </div>

      <div className="models-stats">
        <Stat value={t.model.macro_f1.toFixed(2)} label="Macro-F1 on the test set" sub={`keyword rules: ${t.keywords.macro_f1.toFixed(2)}`} />
        <Stat value={pct(intent.calibration.confident_accuracy)} label="Accuracy when confident" sub={`on ${pct(intent.calibration.confident_coverage)} of the messages (p ≥ ${intent.selection.threshold})`} />
        <Stat value={`+${Math.round(100 * (ab.target_on.person / ab.target_on.runs - ab.target_off.person / ab.target_off.runs))} pts`} label="More complaint/retention messages offered a person" sub="with the model on, in the real agent" />
        <Stat value="0.3 ms" label="Per message" sub="no cost, no call to another model" />
      </div>

      <div className="models-grid">
        <Card title="Is it better than the alternatives?" question="Macro-F1 on the 210 test phrases (none seen in training).">
          <HBars
            labelWidth={190}
            format={(v) => v.toFixed(3)}
            bars={[
              { label: 'Majority class', value: t.majority.macro_f1, color: C.base },
              { label: 'Keyword rules', value: t.keywords.macro_f1, color: C.base },
              {
                label: 'Our model',
                value: t.model.macro_f1,
                color: C.model,
                note: '· 0.3 ms · $0',
                tip: `Our model: ${t.model.macro_f1.toFixed(3)} · ES ${intent.llm[0].es.toFixed(3)} / PT ${intent.llm[0].pt.toFixed(3)}`,
              },
              {
                label: 'Claude zero-shot',
                value: zero.macro_f1,
                color: C.compare,
                note: `· ${Math.round(zero.latency_ms)} ms`,
                tip: `Claude Haiku zero-shot: ${zero.macro_f1.toFixed(3)} · ${Math.round(zero.latency_ms)} ms · $${zero.cost_per_1000.toFixed(2)} per 1,000`,
              },
              {
                label: 'Claude few-shot',
                value: few.macro_f1,
                color: C.compare,
                note: `· ${Math.round(few.latency_ms)} ms`,
                tip: `Claude Haiku few-shot: ${few.macro_f1.toFixed(3)} · ${Math.round(few.latency_ms)} ms · $${few.cost_per_1000.toFixed(2)} per 1,000`,
              },
            ]}
          />
          <p className="models-read">
            Claude is somewhat more accurate, but about 1,800 times slower: it would add half a second to every message.
            With 210 phrases, the gap between 0.85 and 0.91 is close to the noise.
          </p>
        </Card>

        <Card title="Where does it get it right, and wrong?" question="F1 per intent: each row compares the three classifiers.">
          <DotRows
            series={[
              { label: 'Keyword rules', color: C.base },
              { label: 'Our model', color: C.model },
              { label: 'Claude few-shot', color: C.compare },
            ]}
            rows={intent.classes.map((c) => ({
              label: INTENT[c],
              values: [
                t.keywords.f1_by_class[c as keyof typeof t.keywords.f1_by_class],
                t.model.f1_by_class[c as keyof typeof t.model.f1_by_class],
                few.f1_by_class[c as keyof typeof few.f1_by_class],
              ],
            }))}
          />
          <p className="models-read">
            Technical and retention are almost perfect. The weak spot is transactional and product: money questions
            phrased as a problem (“me rebotaron la tarjeta”, my card was declined) get mistaken for complaints.
          </p>
        </Card>

        <Card title="Confusion matrix" question="Each row is the true intent; the diagonal is the correct ones.">
          <Confusion
            labels={intent.confusion.labels}
            names={intent.confusion.labels.map((l) => INTENT[l])}
            rows={intent.confusion.rows_true_cols_pred}
          />
        </Card>

        <Card title="Does it change what Nova does?" question="32 new messages × 3 repetitions in the real agent (Bedrock), with and without the model's hint.">
          <HBars
            labelWidth={230}
            format={(v) => pct(v)}
            bars={[
              {
                label: 'Complaint/retention · with model',
                value: ab.target_on.person / ab.target_on.runs,
                color: C.model,
                note: `(${ab.target_on.person}/${ab.target_on.runs})`,
              },
              {
                label: 'Complaint/retention · without',
                value: ab.target_off.person / ab.target_off.runs,
                color: C.base,
                note: `(${ab.target_off.person}/${ab.target_off.runs})`,
              },
              {
                label: 'Other messages · with model',
                value: ab.control_on.person / ab.control_on.runs,
                color: C.model,
                note: `(${ab.control_on.person}/${ab.control_on.runs})`,
              },
              {
                label: 'Other messages · without',
                value: ab.control_off.person / ab.control_off.runs,
                color: C.base,
                note: `(${ab.control_off.person}/${ab.control_off.runs})`,
              },
            ]}
          />
          <p className="models-read">
            Share of conversations where Nova offered a person or opened a case. With the model it goes up where it
            should (complaints) and barely moves where it is not needed (other messages).
          </p>
        </Card>

        <Card title="Why does the intent matter?" question="The bank's real first contact resolution (FCR) by reason, 686k interactions.">
          <HBars
            labelWidth={150}
            format={(v) => pct(v)}
            bars={fcr.map(([k, v]) => ({
              label: INTENT[k],
              value: v.fcr,
              color: k === 'complaint' || k === 'retention' ? C.model : C.base,
              tip: `${INTENT[k]}: FCR ${pct(v.fcr, 1)} over ${v.interactions.toLocaleString('en')} interactions`,
            }))}
          />
          <p className="models-read">
            Complaints are solved on the first contact only {pct(intent.fcr.complaint.fcr)} of the time: spotting them
            early is what lets Nova bring in a person before the customer gets frustrated.
          </p>
        </Card>

        <Card title="Can we trust its confidence?" question="Calibration, and a threshold chosen with cross-validation on the training set only.">
          <div className="models-stats models-stats-inner">
            <Stat value={intent.calibration.ece.toFixed(2)} label="Calibration error (ECE)" sub="0 = perfect" />
            <Stat value={String(intent.selection.threshold)} label="Confidence threshold" sub="≥ 90% precision in CV" />
            <Stat value={pct(intent.calibration.confident_coverage)} label="Messages above it" sub={`accuracy ${pct(intent.calibration.confident_accuracy)}`} />
            <Stat value={intent.leakage.median.toFixed(2)} label="Test↔train similarity (median)" sub="char 4-gram Jaccard: no leakage" />
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
  const titles = Object.fromEntries(rag.chunks.filter((c) => c.lang === 'es').map((c) => [c.id, topicLabel(c.id)]));
  const words = rag.chunks.map((c) => c.words);
  const sameMean = rag.crosslingual.same_topic.reduce((a, b) => a + b.cos, 0) / rag.crosslingual.same_topic.length;

  return (
    <>
      <div className="models-section-head" id="rag">
        <Search size={22} aria-hidden="true" />
        <div>
          <h2>Knowledge search (RAG)</h2>
          <p>
            Answers about products and policies come from documents, not from the model's memory. Hybrid search:
            BM25 + {rag.embedding.model.replace('amazon.', '')} embeddings ({rag.embedding.dimensions} dimensions),
            fused by rank. Evaluated on {rag.questions.test} colloquial test questions written after the documents.
          </p>
        </div>
      </div>

      <div className="models-stats">
        <Stat value={pct(rag.ranking.all.hybrid['recall@1'].rate)} label="Recall@1" sub="the right document comes first" />
        <Stat value={pct(rag.ranking.all.hybrid['recall@3'].rate)} label="Recall@3" sub="it is among the 3 the model reads" />
        <Stat value={rag.ranking.all.hybrid.mrr.toFixed(2)} label="MRR" sub="1 = always first" />
        <Stat value={sameMean.toFixed(2)} label="ES↔PT similarity, same topic" sub={`different topics: ${rag.crosslingual.other_topic_mean.toFixed(2)}`} />
      </div>

      <div className="models-grid">
        <Card title="Recall: does it find the right document?" question="Test questions the documents can answer. The thin bar is the 95% confidence interval.">
          <div className="viz-filters">
            <Segmented
              label="Metric"
              value={metric}
              onChange={setMetric}
              options={[
                { value: 'recall@1', label: 'Recall@1' },
                { value: 'recall@3', label: 'Recall@3' },
                { value: 'mrr', label: 'MRR' },
              ]}
            />
            <Segmented
              label="Language"
              value={scope}
              onChange={setScope}
              options={[
                { value: 'all', label: 'All' },
                { value: 'es', label: 'Spanish' },
                { value: 'pt', label: 'Portuguese' },
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
                  ? `${label}: ${m.k} of ${m.n} questions (95% CI ${pct(m.ci95[0])}–${pct(m.ci95[1])})`
                  : `${label}: MRR ${r.mrr.toFixed(3)}`,
              };
            })}
          />
          <p className="models-read">
            The embeddings add what BM25 misses (synonyms, other ways of saying it): Recall@3 goes from 92% to 97%.
            The hybrid is as good as or better than each signal alone, mostly in Portuguese; the intervals overlap, so
            read it as “at least as good”, not as a proven gap.
          </p>
        </Card>

        <Card title="Embeddings: does it capture meaning?" question="The chunks and the questions in the embedding space.">
          <EmbeddingMap chunks={rag.chunks} questions={rag.test_questions} variance={rag.embedding.pca_variance} />
        </Card>

        <Card title="Embeddings: is it really multilingual?" question="Cosine between the same document in Spanish and in Portuguese, against different documents.">
          <CrossLingual
            items={rag.crosslingual.same_topic}
            otherMean={rag.crosslingual.other_topic_mean}
            otherMax={rag.crosslingual.other_topic_max}
            titles={titles}
          />
        </Card>

        <Card title="Chunking: how were the documents split?" question={`${rag.chunks.length} chunks: one topic = one idea, the same topic in ES and PT, no overlap.`}>
          <ChunkSizes chunks={rag.chunks} />
          <div className="models-stats models-stats-inner">
            <Stat value={String(rag.chunks.length)} label="Chunks" sub={`${rag.chunks.length / 2} topics × 2 languages`} />
            <Stat value={`${Math.min(...words)}–${Math.max(...words)}`} label="Words per chunk" sub="fits whole in the context" />
            <Stat value={pct(rag.ranking.all.hybrid['recall@3'].rate)} label="Right chunk in the top 3" sub="what the model reads" />
          </div>
          <p className="models-read">
            With short, single-idea chunks there is no need for overlap: each one answers a whole question. We did
            not compare other chunk sizes; with 42 chunks the method is proven, not its scale.
          </p>
        </Card>

        <Card title="Can it say “I don't know”?" question="Similarity of the best chunk for each test question. Below the threshold, the search abstains.">
          <AbstentionStrip questions={rag.test_questions} threshold={rag.thresholds.dense} />
          <div className="models-stats models-stats-inner">
            <Stat value={pct(hybrid.decision_accuracy.rate)} label="Right decision" sub={`${hybrid.decision_accuracy.k}/${hybrid.decision_accuracy.n} questions`} />
            <Stat value={`${hybrid.abstained_answerable.k}/${hybrid.abstained_answerable.n}`} label="Answerable ones dropped" sub="the search favors not losing answers" />
            <Stat value={`${hybrid.answered_unanswerable.n - hybrid.answered_unanswerable.k}/${hybrid.answered_unanswerable.n}`} label="Unanswerable, stopped here" sub="the model decides the rest when reading" />
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
      <div className="models-section-head" id="cost">
        <Coins size={22} aria-hidden="true" />
        <div>
          <h2>Cost per token</h2>
          <p>
            What a conversation with Nova costs ({cost.model.replace('us.anthropic.', '').replace('-v1:0', '')} on
            Bedrock), from the tokens Bedrock reported in the {all.conversations} conversations of the final
            evaluation, at ${cost.price_per_mtok.input} per million input tokens and ${cost.price_per_mtok.output} per
            million output tokens.
          </p>
        </div>
      </div>

      <div className="models-stats">
        <Stat value={usd(all.cost_per_conversation)} label="Per conversation" sub={`p95 ${usd(cost.p95_per_conversation)}`} />
        <Stat value={usd(all.cost_per_conversation * 1000, 2)} label="Per 1,000 conversations" sub={`${usd(all.cost_per_message * 1000, 2)} per 1,000 messages`} />
        <Stat value={all.input_tokens_per_conversation.toLocaleString('en')} label="Input tokens per conversation" sub={`${all.output_tokens_per_conversation} output`} />
        <Stat value={pct(all.input_share_of_cost)} label="Of the cost is input" sub="prompt, tools and the customer's data" />
      </div>

      <div className="models-grid">
        <Card title="How is it calculated?" question="Price per token and an average conversation, step by step.">
          <table className="models-table">
            <thead>
              <tr>
                <th />
                <th>Price per token</th>
                <th>Tokens</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Input</td>
                <td>{usd(inPrice, 6)}</td>
                <td>{all.input_tokens_per_conversation.toLocaleString('en')}</td>
                <td>{usd(inCost, 6)}</td>
              </tr>
              <tr>
                <td>Output</td>
                <td>{usd(outPrice, 6)}</td>
                <td>{all.output_tokens_per_conversation.toLocaleString('en')}</td>
                <td>{usd(outCost, 6)}</td>
              </tr>
              <tr className="models-table-total">
                <td>Total</td>
                <td />
                <td>{(all.input_tokens_per_conversation + all.output_tokens_per_conversation).toLocaleString('en')}</td>
                <td>{usd(inCost + outCost, 6)}</td>
              </tr>
            </tbody>
          </table>
          <p className="models-read">
            cost = input tokens × {usd(inPrice, 6)} + output tokens × {usd(outPrice, 6)}. Output is 5 times more
            expensive per token, but Nova writes short answers: the input is what weighs.
          </p>
          <div className="models-stats models-stats-inner">
            <Stat value="$0" label="Intent classifier" sub={`runs in the Lambda; with Claude it would be $${claudeClassifier.toFixed(2)} per 1,000`} />
            <Stat value={`$${cost.titan_price_per_mtok}`} label="Embeddings per million tokens" sub="Titan V2: one question ≈ $0.000001" />
          </div>
        </Card>

        <Card title="Which conversations cost more?" question="Mean cost per conversation by kind of evaluation case.">
          <HBars
            labelWidth={230}
            max={max}
            format={(v) => usd(v)}
            tickFormat={(v) => usd(v, 3)}
            bars={kinds.map(([k, v]) => ({
              label: KIND[k] ?? k,
              value: v.cost_per_conversation,
              color: C.model,
              tip: (
                <>
                  <b>{KIND[k] ?? k}</b> ({v.conversations} conversations, {v.messages} messages)
                  <br />
                  {v.input_tokens_per_conversation.toLocaleString('en')} input tokens ·{' '}
                  {v.output_tokens_per_conversation} output
                  <br />
                  {usd(v.cost_per_conversation)} per conversation · {usd(v.cost_per_message)} per message
                </>
              ),
            }))}
          />
          <p className="models-read">
            Account questions read the customer's data with tools, and that is input. The identity check in the chat
            costs more because it takes 5 messages, though each one is among the cheapest.
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
        <h1>Do the models work?</h1>
        <p>Metrics of the intent classifier, the knowledge search and the cost per token.</p>
        <label htmlFor="models-password">Password</label>
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
            Wrong password.
          </p>
        )}
        <button type="submit" className="btn-primary">
          Enter
        </button>
        <p className="form-help">Demo: the password is the one shown in the field.</p>
        <Link to="/console" className="models-gate-link">
          <Headset size={14} aria-hidden="true" /> Go to the human agent console
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
          <Link to="/console" className="models-back">
            <Headset size={16} aria-hidden="true" /> Human agent console
          </Link>
        </div>
        <h1>Do the models work?</h1>
        <p>
          The metrics we use to decide whether each learned component does its job, measured on data the model
          never saw. Hover over any chart for the details.
        </p>
        <nav className="models-tabs" aria-label="Sections">
          <a href="#intent">Intent classifier</a>
          <a href="#rag">Knowledge search</a>
          <a href="#cost">Cost per token</a>
          <a href="#live">Live, from production</a>
          <a href="#protection">How it is protected</a>
          <a href="#limits">Limitations</a>
        </nav>
      </header>

      <main className="models-main">
        <IntentSection />
        <RagSection />
        <CostSection />
        <LiveSection />

        <section className="models-limits" id="limits">
          <h2>Limitations, in the open</h2>
          <ul>
            <li>
              Phrases and questions written by the team (synthetic), not real traffic: they show the model
              generalizes across styles we wrote, not to real customers. The bank's transcripts have no signal to
              train on (42 distinct texts in 171k).
            </li>
            <li>
              Small samples (210 phrases, 38 answerable questions): gaps of a few points are within the noise; that
              is why we show confidence intervals.
            </li>
            <li>
              Abstaining is the weakest part of the search: similarity does not separate an unanswerable question
              from a hard one well, so the model makes that call when it reads the chunks.
            </li>
            <li>NovaBank's documents and figures are fictitious, written for the demo.</li>
          </ul>
          <p className="models-source">
            Source: <code>ml/intent/metrics.json</code>, <code>ml/intent/llm_baseline.json</code>,{' '}
            <code>ml/intent/ablation.json</code>, <code>ml/rag/metrics.json</code>, the embedding index and{' '}
            <code>{cost.source}</code>, exported with <code>ml/export_metrics_page.py</code>.
          </p>
        </section>
      </main>
    </div>
  );
}
