import '@testing-library/jest-dom';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import LiveSection from '../components/models/LiveSection';
import type { LiveMetrics } from '../api/liveMetrics';

const BASE: LiveMetrics = {
  turns: 0,
  conversations: 0,
  window: { first: null, last: null },
  errors: 0,
  error_rate: null,
  tokens: { input_per_conversation: null, output_per_conversation: null },
  cost: {
    per_conversation: null,
    per_1000_conversations: null,
    per_1000_turns: null,
    price_per_mtok: { input: 1, output: 5 },
  },
  latency_ms: { total: { p50: null, p95: null, n: 0 }, first_token: { p50: null, p95: null, n: 0 } },
  intent: { classified: 0, distribution: {}, confident_share: null, threshold: 0.58 },
  by_lang: {},
  by_channel: {},
  generated_at: '2026-10-04T09:05:00+00:00',
  cache_seconds: 60,
};

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
const serve = (body: unknown) => vi.stubGlobal('fetch', vi.fn(async () => ok(body)));

afterEach(() => vi.unstubAllGlobals());

describe('how the demo is protected', () => {
  it('shows the layers, without numbers, before the live data arrives', () => {
    serve({ ...BASE, security: null });
    render(<LiveSection />);
    expect(screen.getByRole('heading', { name: 'How the demo is protected' })).toBeInTheDocument();
    expect(screen.getByText(/Edge firewall \(AWS WAF\)\./)).toBeInTheDocument();
    expect(screen.getByText(/Origin lock\./)).toBeInTheDocument();
    expect(screen.getByText(/Identity checked in code, not by the model\./)).toBeInTheDocument();
    expect(screen.getByText(/Spend limits\./)).toBeInTheDocument();
    expect(screen.getByText(/Audit trail\./)).toBeInTheDocument();
    expect(screen.getByText(/Security headers\./)).toBeInTheDocument();
    expect(screen.getByText('Loading the live security numbers…')).toBeInTheDocument();
  });

  it('shows what was blocked at the edge', async () => {
    serve({
      ...BASE,
      security: {
        window_hours: 24,
        requests: 12345,
        blocked: 678,
        by_reason: { rate_limits: 500, unknown_routes: 100, attack_signatures: 60, bad_reputation: 18 },
        generated_at: '2026-10-04T09:05:00+00:00',
      },
    });
    render(<LiveSection />);
    expect(await screen.findByText('12,345')).toBeInTheDocument();
    expect(screen.getByText('Blocked at the edge, last 24 h')).toBeInTheDocument();
    expect(screen.getByText('Unknown routes')).toBeInTheDocument();
    expect(screen.getByText('678')).toBeInTheDocument();
    expect(screen.getByText('500')).toBeInTheDocument();
    expect(screen.getByText('100')).toBeInTheDocument();
    expect(screen.getByText('60')).toBeInTheDocument();
    expect(screen.getByText('18')).toBeInTheDocument();
    expect(screen.getByText('Rate limits')).toBeInTheDocument();
    expect(screen.getByText('Bad reputation')).toBeInTheDocument();
  });

  it('says the live numbers are unavailable when the server reports an error', async () => {
    serve({ ...BASE, security: { error: 'unavailable' } });
    render(<LiveSection />);
    expect(await screen.findByText(/Live security numbers unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/Edge firewall \(AWS WAF\)\./)).toBeInTheDocument();
  });

  it('hides the live part when security is null, keeping the layers', async () => {
    serve({ ...BASE, security: null });
    render(<LiveSection />);
    expect(await screen.findByText(/No messages recorded in production yet/)).toBeInTheDocument();
    expect(screen.queryByText('Blocked at the edge, last 24 h')).not.toBeInTheDocument();
    expect(screen.queryByText(/Loading the live security numbers/)).not.toBeInTheDocument();
    expect(screen.getByText(/Origin lock\./)).toBeInTheDocument();
  });

  it('says unavailable when the whole live request fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 500 })));
    render(<LiveSection />);
    expect(await screen.findByText(/Live security numbers unavailable/)).toBeInTheDocument();
  });
});
