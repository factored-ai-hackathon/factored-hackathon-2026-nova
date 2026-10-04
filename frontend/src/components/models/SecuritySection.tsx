/**
 * "How the demo is protected": the layers, in words (no thresholds), plus what the edge firewall
 * blocked in the last 24 hours. The numbers come from the `security` field of the live metrics
 * (GET /v1/metrics/live), which LiveSection already fetches: null hides the live part, an error
 * says so, and the layers show either way.
 */
import { ShieldCheck } from 'lucide-react';
import type { LiveMetrics, SecurityMetrics } from '../../api/liveMetrics';
import { Card, Stat } from './cards';

const LAYERS: { name: string; text: string }[] = [
  {
    name: 'Edge firewall (AWS WAF)',
    text: 'Per-IP rate limits, an allowlist of API routes and methods, AWS managed rules for known attack patterns and bad-reputation IPs, and a request body size limit.',
  },
  {
    name: 'Origin lock',
    text: 'The API only answers requests that came through CloudFront, with a secret header.',
  },
  {
    name: 'Identity checked in code, not by the model',
    text: 'Document, date of birth and a one-time code. The account tools take no customer id, so the model cannot ask for another customer.',
  },
  {
    name: 'Spend limits',
    text: 'A daily model budget and a per-visitor message limit.',
  },
  {
    name: 'Audit trail',
    text: 'Every tool call is recorded, hashed, with no message text.',
  },
  {
    name: 'Security headers',
    text: 'HSTS, frame, content-type and referrer policies on every page.',
  },
];

const REASONS: { key: keyof SecurityMetrics['by_reason']; label: string; sub: string }[] = [
  { key: 'rate_limits', label: 'Rate limits', sub: 'too many requests from one IP' },
  { key: 'unknown_routes', label: 'Unknown routes', sub: 'not on the API allowlist, or too large' },
  { key: 'attack_signatures', label: 'Attack patterns', sub: 'known bad inputs and common exploits' },
  { key: 'bad_reputation', label: 'Bad reputation', sub: 'IPs on a threat list' },
];

const TITLE = 'Blocked at the edge, last 24 h';
const n = (v: number) => v.toLocaleString('en');

function Unavailable() {
  return (
    <Card title={TITLE}>
      <p className="models-read">
        Live security numbers unavailable right now. The layers are unaffected.
      </p>
    </Card>
  );
}

function BlockedAtTheEdge({ security }: { security: SecurityMetrics | { error: string } }) {
  if ('error' in security) return <Unavailable />;
  return (
    <Card
      title={TITLE}
      question="Requests the firewall stopped before they reached the app. Counts only: no IPs, no request contents."
    >
      <div className="models-stats models-stats-inner">
        <Stat value={n(security.requests)} label="Requests" sub={`last ${security.window_hours} hours`} />
        <Stat value={n(security.blocked)} label="Blocked" />
        {REASONS.map((r) => (
          <Stat key={r.key} value={n(security.by_reason[r.key])} label={r.label} sub={r.sub} />
        ))}
      </div>
      <p className="models-read">The firewall's counters lag a few minutes, and they include the team's own tests.</p>
    </Card>
  );
}

export default function SecuritySection({ data, failed }: { data: LiveMetrics | null; failed: boolean }) {
  const security = data?.security;
  return (
    <>
      <div className="models-section-head" id="protection">
        <ShieldCheck size={22} aria-hidden="true" />
        <div>
          <h2>How the demo is protected</h2>
          <p>The public demo is open to anyone, so it is defended in layers. None of them relies on the model behaving.</p>
        </div>
      </div>
      <div className="models-grid">
        <Card title="The layers">
          <ul className="models-layers">
            {LAYERS.map((l) => (
              <li key={l.name}>
                <strong>{l.name}.</strong> {l.text}
              </li>
            ))}
          </ul>
        </Card>
        {security ? (
          <BlockedAtTheEdge security={security} />
        ) : !data && failed ? (
          <Unavailable />
        ) : !data ? (
          <Card title={TITLE}>
            <p className="models-read">Loading the live security numbers…</p>
          </Card>
        ) : null}
      </div>
    </>
  );
}
