/**
 * "Live, from production": aggregates over the deployed app's interactions table
 * (GET /v1/metrics/live), polled every minute while the page is open. The rest of /modelos is a
 * static snapshot and keeps working if this endpoint fails. The same fetch feeds the firewall
 * numbers of "How the demo is protected" (SecuritySection, decision 50): no second poll.
 */
import { useEffect, useState } from 'react';
import { Activity } from 'lucide-react';
import { getLiveMetrics, type Faithfulness, type Group, type LiveMetrics, type Satisfaction } from '../../api/liveMetrics';
import { HBars } from './charts';
import { Card, Stat } from './cards';
import { C, INTENT, pct, usd } from './viz';
import SecuritySection from './SecuritySection';

const LIVE_POLL_MS = 60_000;

const LANG: Record<string, string> = { es: 'Spanish', pt: 'Portuguese' };
const CHANNEL: Record<string, string> = { account: 'Logged-in chat', public: 'Public assistant' };

const when = (iso: string) =>
  new Date(iso).toLocaleString('en', { dateStyle: 'medium', timeStyle: 'short' });

const ms = (v: number | null) => (v == null ? '–' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`);

function groupBars(groups: Record<string, Group>, names: Record<string, string>, total: number) {
  return Object.entries(groups)
    .sort((a, b) => b[1].turns - a[1].turns)
    .map(([k, g]) => ({
      label: names[k] ?? k,
      value: total ? g.turns / total : 0,
      color: C.model,
      note: `(${g.turns.toLocaleString('en')})`,
      tip: `${names[k] ?? k}: ${g.turns.toLocaleString('en')} messages in ${g.conversations.toLocaleString('en')} conversations`,
    }));
}

function FaithfulnessCard({ f }: { f: Faithfulness }) {
  return (
    <Card
      title="Are Nova's answers faithful to the data?"
      question={`The last ${f.limit} cases handed to a person: each amount, date, last digits or name in Nova's answers, looked up in the data it consulted (the agent console's check).`}
    >
      {f.scored ? (
        <>
          <div className="models-stats models-stats-inner">
            <Stat value={pct(f.mean ?? 0)} label="Mean faithfulness" sub={`${f.scored} of ${f.cases} cases had checkable claims`} />
            <Stat
              value={`${f.claims.supported}/${f.claims.total}`}
              label="Claims found in the data"
              sub={f.claims.rate == null ? undefined : `${pct(f.claims.rate)} of all claims`}
            />
          </div>
          <HBars
            labelWidth={190}
            format={(v) => pct(v)}
            bars={[
              { label: 'Every claim found', value: f.buckets.all / f.scored, color: C.model, note: `(${f.buckets.all})` },
              { label: '75–99% found', value: f.buckets.most / f.scored, color: C.base, note: `(${f.buckets.most})` },
              { label: 'Under 75% found', value: f.buckets.low / f.scored, color: C.compare, note: `(${f.buckets.low})` },
            ].map((b) => ({ ...b, tip: `${b.label}: ${b.note.slice(1, -1)} of ${f.scored} cases` }))}
          />
          <p className="models-read">
            It checks grounding, not correctness: a real figure from the wrong row still counts as found. Only the
            scores leave the server, never the answers.
          </p>
        </>
      ) : (
        <p className="models-read">
          {f.cases ? 'No handed-over case has a checkable claim yet.' : 'No case has been handed to a person yet.'}
        </p>
      )}
    </Card>
  );
}

function SatisfactionCard({ s }: { s: Satisfaction }) {
  return (
    <Card
      title="Are customers satisfied with the human advisor?"
      question="After an advisor closes a case, the customer can rate the experience from 1 to 5 (CSAT). Optional, so only those who chose to answer."
    >
      {s.rated ? (
        <>
          <div className="models-stats models-stats-inner">
            <Stat value={`${(s.mean ?? 0).toFixed(1)} / 5`} label="Mean rating" sub={`${s.rated} rated ${s.rated === 1 ? 'case' : 'cases'}`} />
          </div>
          <HBars
            labelWidth={90}
            format={(v) => pct(v)}
            bars={[5, 4, 3, 2, 1].map((n) => {
              const count = s.distribution[String(n)] ?? 0;
              return {
                label: `${n} ${n === 1 ? 'star' : 'stars'}`,
                value: count / s.rated,
                color: n >= 4 ? C.model : n === 3 ? C.base : C.compare,
                note: `(${count})`,
                tip: `${n} of 5: ${count} of ${s.rated} ratings`,
              };
            })}
          />
          <p className="models-read">
            Self-selected: customers who rate are not a representative sample of all handed-over cases. Only the
            scores leave the server, never the conversations.
          </p>
        </>
      ) : (
        <p className="models-read">No customer has rated an advisor yet.</p>
      )}
    </Card>
  );
}

function LiveNumbers({ data }: { data: LiveMetrics }) {
  const { cost, latency_ms: latency, intent, tokens } = data;
  const intents = Object.entries(intent.distribution).sort((a, b) => b[1] - a[1]);
  return (
    <>
      <div className="models-stats">
        <Stat
          value={data.conversations.toLocaleString('en')}
          label="Conversations"
          sub={`${data.turns.toLocaleString('en')} messages · ${data.errors} errors`}
        />
        <Stat
          value={cost.per_conversation == null ? '–' : usd(cost.per_conversation)}
          label="Per conversation"
          sub={cost.per_1000_conversations == null ? undefined : `${usd(cost.per_1000_conversations, 2)} per 1,000`}
        />
        <Stat
          value={ms(latency.total.p50)}
          label="Reply time (median)"
          sub={`p95 ${ms(latency.total.p95)} · first token ${ms(latency.first_token.p50)}`}
        />
        <Stat
          value={intent.confident_share == null ? '–' : pct(intent.confident_share)}
          label="Intent above the threshold"
          sub={`p ≥ ${intent.threshold} · ${intent.classified.toLocaleString('en')} classified`}
        />
      </div>

      <div className="models-grid">
        <Card title="What do people ask about?" question="The intent classifier's label for each message, as a share of the classified ones.">
          {intents.length ? (
            <HBars
              labelWidth={150}
              format={(v) => pct(v)}
              bars={intents.map(([k, n]) => ({
                label: INTENT[k] ?? k,
                value: n / intent.classified,
                color: k === 'complaint' || k === 'retention' ? C.model : C.base,
                note: `(${n.toLocaleString('en')})`,
                tip: `${INTENT[k] ?? k}: ${n.toLocaleString('en')} of ${intent.classified.toLocaleString('en')} messages`,
              }))}
            />
          ) : (
            <p className="models-read">No message has gone through the classifier yet.</p>
          )}
        </Card>

        <Card title="Where does the traffic come from?" question="Share of messages by language and by channel.">
          <HBars labelWidth={150} format={(v) => pct(v)} bars={groupBars(data.by_lang, LANG, data.turns)} />
          <HBars labelWidth={150} format={(v) => pct(v)} bars={groupBars(data.by_channel, CHANNEL, data.turns)} />
          <p className="models-read">
            {tokens.input_per_conversation == null
              ? 'No tokens reported yet.'
              : `${Math.round(tokens.input_per_conversation).toLocaleString('en')} input and ${Math.round(
                  tokens.output_per_conversation ?? 0,
                ).toLocaleString('en')} output tokens per conversation, at $${cost.price_per_mtok.input} / $${
                  cost.price_per_mtok.output
                } per million.`}
          </p>
        </Card>

        {data.faithfulness && <FaithfulnessCard f={data.faithfulness} />}
        {data.satisfaction && <SatisfactionCard s={data.satisfaction} />}
      </div>
    </>
  );
}

export default function LiveSection() {
  const [data, setData] = useState<LiveMetrics | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let controller = new AbortController();
    const load = () => {
      controller.abort();
      controller = new AbortController();
      getLiveMetrics(controller.signal)
        .then((d) => {
          setData(d);
          setFailed(false);
        })
        .catch((e: unknown) => {
          if ((e as Error)?.name !== 'AbortError') setFailed(true);
        });
    };
    load();
    const timer = setInterval(load, LIVE_POLL_MS);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, []);

  const { first, last } = data?.window ?? { first: null, last: null };
  return (
    <>
      <div className="models-section-head" id="live">
        <Activity size={22} aria-hidden="true" />
        <div>
          <h2>Live, from production</h2>
          <p>
            Computed from the deployed app's interactions table, refreshed every minute while this page is open. This is
            the real deployed traffic: so far mostly the team's own tests and evaluations, not customers. Aggregates
            only: no message text, no ids.
          </p>
          {data && (
            <p className="models-live-window">
              <span className="models-live-dot" aria-hidden="true" />
              {first && last ? `From ${when(first)} to ${when(last)}` : 'No messages yet'} · updated{' '}
              {when(data.generated_at)}
              {failed && ' · the last refresh failed, showing the previous numbers'}
            </p>
          )}
        </div>
      </div>

      {data && data.turns > 0 && <LiveNumbers data={data} />}
      {data && data.turns === 0 && (
        <p className="models-live-empty">No messages recorded in production yet. This section fills in on its own.</p>
      )}
      {!data && failed && (
        <p className="models-live-empty" role="status">
          The live numbers are not available right now. The other sections come from the evaluation files and are not
          affected.
        </p>
      )}
      {!data && !failed && <p className="models-live-empty">Loading the live numbers…</p>}

      <SecuritySection data={data} failed={failed} />
    </>
  );
}
