import '@testing-library/jest-dom';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import LiveSection from '../components/models/LiveSection';
import type { LiveMetrics } from '../api/liveMetrics';

const LIVE: LiveMetrics = {
  turns: 120,
  conversations: 40,
  window: { first: '2026-10-01T10:00:00+00:00', last: '2026-10-02T09:00:00+00:00' },
  errors: 3,
  error_rate: 0.025,
  tokens: { input_per_conversation: 3812.5, output_per_conversation: 210.2 },
  cost: {
    per_conversation: 0.004863,
    per_1000_conversations: 4.863,
    per_1000_turns: 1.621,
    price_per_mtok: { input: 1, output: 5 },
  },
  latency_ms: { total: { p50: 2400, p95: 6100, n: 117 }, first_token: { p50: 900, p95: 2100, n: 117 } },
  intent: { classified: 100, distribution: { complaint: 30, other: 70 }, confident_share: 0.62, threshold: 0.58 },
  by_lang: { es: { turns: 80, conversations: 25 }, pt: { turns: 40, conversations: 15 } },
  by_channel: { account: { turns: 90, conversations: 30 }, public: { turns: 30, conversations: 10 } },
  generated_at: '2026-10-02T09:05:00+00:00',
  cache_seconds: 60,
};

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('live metrics section', () => {
  it('shows the aggregates from the endpoint, labeled as the deployed traffic', async () => {
    const fetchMock = vi.fn(async () => ok(LIVE));
    vi.stubGlobal('fetch', fetchMock);
    render(<LiveSection />);
    expect(screen.getByRole('heading', { name: 'Live, from production' })).toBeInTheDocument();
    expect(screen.getByText(/mostly the team's own tests and evaluations/)).toBeInTheDocument();
    expect(await screen.findByText('$0.0049')).toBeInTheDocument(); // cost per conversation
    expect(screen.getByText('$4.86 per 1,000')).toBeInTheDocument();
    expect(screen.getByText('2.4 s')).toBeInTheDocument(); // median reply time
    expect(screen.getByText('62%')).toBeInTheDocument(); // intent above the threshold
    expect(screen.getByText(/^From .* to .* · updated/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/v1/metrics/live', expect.anything());
  });

  it('polls again every minute', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok(LIVE))
      .mockResolvedValueOnce(ok({ ...LIVE, conversations: 41 }));
    vi.stubGlobal('fetch', fetchMock);
    render(<LiveSection />);
    expect(await screen.findByText('40')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(await screen.findByText('41')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shows the faithfulness of the recent handed-over cases", async () => {
    const faithfulness = {
      cases: 12, scored: 10, mean: 0.91,
      claims: { supported: 52, total: 58, rate: 0.897 },
      buckets: { all: 7, most: 2, low: 1 },
      window: { first: '2026-10-01T10:00:00+00:00', last: '2026-10-02T09:00:00+00:00' },
      limit: 50,
    };
    vi.stubGlobal('fetch', vi.fn(async () => ok({ ...LIVE, faithfulness })));
    render(<LiveSection />);
    expect(await screen.findByRole('heading', { name: "Are Nova's answers faithful to the data?" })).toBeInTheDocument();
    expect(screen.getByText('91%')).toBeInTheDocument();
    expect(screen.getByText('52/58')).toBeInTheDocument();
    expect(screen.getByText('10 of 12 cases had checkable claims')).toBeInTheDocument();
  });

  it('says when no case has been handed over yet, and works with an older backend', async () => {
    const empty = {
      cases: 0, scored: 0, mean: null, claims: { supported: 0, total: 0, rate: null },
      buckets: { all: 0, most: 0, low: 0 }, window: { first: null, last: null }, limit: 50,
    };
    vi.stubGlobal('fetch', vi.fn(async () => ok({ ...LIVE, faithfulness: empty })));
    const { unmount } = render(<LiveSection />);
    expect(await screen.findByText('No case has been handed to a person yet.')).toBeInTheDocument();
    unmount();
    vi.stubGlobal('fetch', vi.fn(async () => ok(LIVE)));
    render(<LiveSection />);
    expect(await screen.findByText('$0.0049')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /faithful/ })).not.toBeInTheDocument();
  });

  it('says so when production has no messages yet', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ok({ ...LIVE, turns: 0, conversations: 0, window: { first: null, last: null } })));
    render(<LiveSection />);
    expect(await screen.findByText(/No messages recorded in production yet/)).toBeInTheDocument();
  });

  it('degrades gracefully when the endpoint fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{"detail":"boom"}', { status: 500 })));
    render(<LiveSection />);
    expect(await screen.findByRole('status')).toHaveTextContent('not available right now');
  });

  it('shows the customer satisfaction with the advisor, or an empty state', async () => {
    const satisfaction = {
      rated: 4, mean: 4.25, distribution: { '1': 0, '2': 0, '3': 1, '4': 1, '5': 2 },
      window: { first: '2026-10-01T10:00:00+00:00', last: '2026-10-02T09:00:00+00:00' },
    };
    vi.stubGlobal('fetch', vi.fn(async () => ok({ ...LIVE, satisfaction })));
    const { unmount } = render(<LiveSection />);
    expect(await screen.findByRole('heading', { name: 'Are customers satisfied with the human advisor?' })).toBeInTheDocument();
    expect(screen.getByText('4.3 / 5')).toBeInTheDocument();
    expect(screen.getByText('4 rated cases')).toBeInTheDocument();
    expect(screen.getByText(/Self-selected/)).toBeInTheDocument();
    unmount();
    vi.stubGlobal('fetch', vi.fn(async () => ok({ ...LIVE, satisfaction: { ...satisfaction, rated: 0, mean: null, distribution: {} } })));
    render(<LiveSection />);
    expect(await screen.findByText('No customer has rated an advisor yet.')).toBeInTheDocument();
  });
});
