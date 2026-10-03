// Human agent console (/console, legacy alias /asesor): the cases Nova handed over, with the summary, the facts the
// system verified, the evidence Nova consulted, and the live conversation (decision 27).

import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Headset, LineChart, LogOut, RefreshCw, ShieldCheck, ShieldAlert } from 'lucide-react';
import { ct, type ConsoleKey } from '../../i18n/consoleText';
import * as consoleApi from '../../api/agentConsole';
import type { CaseDetail, CaseSummary, QueueStats } from '../../api/agentConsole';
import { FaithfulnessPanel } from '../../components/console/FaithfulnessPanel';
import { MessageContent } from '../../components/agent/MessageContent';
import { ApiError } from '../../api/client';
import { KEYS, clearStored, loadStored, saveStored } from '../../utils/persist';
import '../../styles/agent-console.css';

const POLL_MS = 4000;
// The public demo key (backend settings.agent_console_key, docs/demo.md), shown in the field so
// judges can get in. It guards a demo queue, not real customers.
const DEMO_KEY = 'Asesor2026';

function when(iso: string, locale: string): string {
  return new Date(iso).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' });
}

function reasonLabel(reason: string): string {
  const label: string | undefined = ct(`console.reason.${reason}` as ConsoleKey);
  return label ?? reason;
}

function intentLabel(intent: string): string {
  const label: string | undefined = ct(`console.intent.${intent}` as ConsoleKey);
  return label ?? intent;
}

export function AgentConsolePage() {
  const locale = 'en-US';
  // A reload keeps the agent signed in, with the open case, until they log out.
  const [stored] = useState(() =>
    loadStored<{ key: string; agentName: string; selected?: string }>(KEYS.console)
  );
  const [key, setKey] = useState(stored?.key ?? '');
  const [signedIn, setSignedIn] = useState(false);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [stats, setStats] = useState<QueueStats | null>(null);
  const [selected, setSelected] = useState<CaseDetail | null>(null);
  const [agentName, setAgentName] = useState(stored?.agentName ?? '');
  const [reply, setReply] = useState('');
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    const list = await consoleApi.listCases(key);
    setCases(list.cases);
    setStats(list.stats ?? null);
    return list.cases;
  }, [key]);

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    try {
      await refresh();
      setSignedIn(true);
    } catch (err) {
      setError(ct(err instanceof ApiError && err.status === 401 ? 'console.badKey' : 'console.error'));
    }
  }

  useEffect(() => {
    if (!stored?.key) return;
    void (async () => {
      try {
        const list = await consoleApi.listCases(stored.key);
        setCases(list.cases);
        setStats(list.stats ?? null);
        setSignedIn(true);
        if (stored.selected) setSelected(await consoleApi.getCase(stored.key, stored.selected));
      } catch {
        clearStored(KEYS.console); // the key no longer works: the login form
      }
    })();
  }, [stored]);

  useEffect(() => {
    if (signedIn) saveStored(KEYS.console, { key, agentName, selected: selected?.case_id });
  }, [signedIn, key, agentName, selected?.case_id]);

  // Keep the list and the open case fresh while signed in.
  const selectedId = selected?.case_id;
  useEffect(() => {
    if (!signedIn) return;
    const timer = setInterval(async () => {
      try {
        await refresh();
        if (selectedId) setSelected(await consoleApi.getCase(key, selectedId));
      } catch {
        // next tick
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [signedIn, refresh, selectedId, key]);

  async function act(action: () => Promise<CaseDetail>) {
    setError('');
    try {
      setSelected(await action());
      await refresh();
    } catch {
      setError(ct('console.error'));
    }
  }

  if (!signedIn) {
    return (
      <div className="console-login">
        <form className="console-login-card" onSubmit={(e) => void signIn(e)}>
          <Headset size={28} aria-hidden="true" />
          <h1>{ct('console.title')}</h1>
          <p>{ct('console.subtitle')}</p>
          <label htmlFor="console-key">{ct('console.key')}</label>
          <input
            id="console-key"
            type="password"
            className="form-input"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={DEMO_KEY}
            autoComplete="off"
          />
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="submit" className="btn-primary">{ct('console.enter')}</button>
          <p className="form-help">{ct('console.demoKey')}</p>
          <Link to="/models" className="console-login-link">
            <LineChart size={14} aria-hidden="true" /> {ct('console.modelsLink')}
          </Link>
        </form>
      </div>
    );
  }

  const facts = selected?.verified_facts;
  const customerLabel = facts?.first_name ?? ct('console.customer');
  return (
    <div className="console-root">
      <header className="console-header">
        <Headset size={20} aria-hidden="true" />
        <h1>{ct('console.title')}</h1>
        <div className="console-header-actions">
          <button className="btn-ghost" onClick={() => void refresh()} aria-label={ct('console.refresh')}>
            <RefreshCw size={16} aria-hidden="true" />
          </button>
          <button className="btn-ghost" onClick={() => { clearStored(KEYS.console); setSignedIn(false); setKey(''); setSelected(null); }}>
            <LogOut size={16} aria-hidden="true" /> {ct('console.logout')}
          </button>
        </div>
      </header>

      <div className="console-body">
        {/* 1. Ticket queue */}
        <aside className="console-list" aria-label={ct('console.queue')}>
          <div className="console-kpis">
            <div className="console-kpi"><span>{stats?.waiting ?? 0}</span>{ct('console.status.waiting')}</div>
            <div className="console-kpi"><span>{stats?.active ?? 0}</span>{ct('console.status.active')}</div>
            <div className="console-kpi"><span>{stats?.closed ?? 0}</span>{ct('console.status.closed')}</div>
            <div className="console-kpi">
              <span>{stats?.faithfulness_avg == null ? '—' : `${Math.round(stats.faithfulness_avg * 100)}%`}</span>
              {ct('console.faithAvg')}
            </div>
            <div className="console-kpi" title={ct('console.ratingHint')}>
              <span>{stats?.satisfaction_avg == null ? '—' : `${stats.satisfaction_avg.toFixed(1)}/5`}</span>
              {ct('console.ratingAvg')}{stats?.rated ? ` (${stats.rated})` : ''}
            </div>
          </div>
          <h2 className="console-section-title">{ct('console.queue')}</h2>
          {cases.length === 0 && <p className="console-empty">{ct('console.empty')}</p>}
          <ul>
            {cases.map((c) => (
              <li key={c.case_id}>
                <button
                  className={`console-case${selectedId === c.case_id ? ' selected' : ''}`}
                  onClick={() => void act(() => consoleApi.getCase(key, c.case_id))}
                >
                  <span className={`console-status ${c.status}`}>{ct(`console.status.${c.status}`)}</span>
                  <span><strong>{c.case_id}</strong> · {c.customer ?? '—'}</span>
                  <span className="console-case-reason">
                    {reasonLabel(c.reason)}
                    {c.intent && ` · ${intentLabel(c.intent)}`}
                  </span>
                  <span className="console-case-time">
                    {when(c.created_at, locale)}
                    {c.faithfulness != null && ` · ${ct('console.faith')} ${Math.round(c.faithfulness * 100)}%`}
                    {c.rating != null && ` · ${ct('console.ratingShort')} ${c.rating}/5`}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        {!selected ? (
          <main className="console-dialog console-empty-state">
            <p className="console-empty">{ct('console.pick')}</p>
          </main>
        ) : (
          <>
            {/* 2. Dialog: Nova's conversation, then the agent's */}
            <main className="console-dialog" aria-label={ct('console.dialog')}>
              <div className="console-detail-header">
                <h2>{selected.case_id}</h2>
                <span className={`console-status ${selected.status}`}>
                  {ct(`console.status.${selected.status}`)}
                </span>
                <span>{customerLabel} · {reasonLabel(selected.reason)} · {selected.lang.toUpperCase()}</span>
                <span className="console-rating">
                  {selected.rating != null ? `${ct('console.rating')}: ${selected.rating}/5` : ct('console.notRated')}
                </span>
              </div>
              <ol className="console-thread">
                {selected.transcript.map((m, i) => (
                  <li key={`t${i}`} className={`bubble ${m.role === 'customer' ? 'customer' : 'nova'}`}>
                    <span className="bubble-who">{m.role === 'customer' ? customerLabel : 'Nova'}</span>
                    {m.role === 'customer' ? m.text : <MessageContent role="agent" content={m.text} />}
                  </li>
                ))}
                <li className="console-divider">{ct('console.handedOver')}</li>
                {selected.messages.map((m, i) => (
                  <li
                    key={`m${i}`}
                    className={`bubble ${m.from === 'customer' ? 'customer' : m.from === 'agent' ? 'agent' : 'system'}`}
                  >
                    {m.from !== 'system' && (
                      <span className="bubble-who">{m.from === 'customer' ? customerLabel : selected.agent_name}</span>
                    )}
                    {m.text}
                    <span className="console-case-time">{when(m.at, locale)}</span>
                  </li>
                ))}
              </ol>

              <div className="console-composer">
                {selected.status === 'waiting' && (
                  <form
                    className="console-action"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (agentName.trim()) void act(() => consoleApi.takeCase(key, selected.case_id, agentName.trim()));
                    }}
                  >
                    <label htmlFor="agent-name">{ct('console.yourName')}</label>
                    <div className="console-action-row">
                      <input id="agent-name" className="form-input" value={agentName} maxLength={60}
                        onChange={(e) => setAgentName(e.target.value)} />
                      <button type="submit" className="btn-primary" disabled={!agentName.trim()}>
                        {ct('console.take')}
                      </button>
                    </div>
                  </form>
                )}
                {selected.status === 'active' && (
                  <form
                    className="console-action"
                    onSubmit={(e) => {
                      e.preventDefault();
                      const text = reply.trim();
                      if (!text) return;
                      setReply('');
                      void act(() => consoleApi.replyCase(key, selected.case_id, text));
                    }}
                  >
                    <label htmlFor="agent-reply">{ct('console.reply')}</label>
                    <textarea id="agent-reply" className="form-input" rows={2} value={reply} maxLength={2000}
                      onChange={(e) => setReply(e.target.value)} />
                    <div className="console-action-buttons">
                      <button type="submit" className="btn-primary" disabled={!reply.trim()}>
                        {ct('console.send')}
                      </button>
                      <button type="button" className="btn-secondary"
                        onClick={() => void act(() => consoleApi.closeCase(key, selected.case_id))}>
                        {ct('console.close')}
                      </button>
                    </div>
                  </form>
                )}
                {error && <p className="form-error" role="alert">{error}</p>}
              </div>
            </main>

            {/* 3. What the agent needs to decide: summary, facts, evidence, faithfulness */}
            <aside className="console-insights" aria-label={ct('console.insights')}>
              <section className="console-card">
                <h3>{ct('console.summary')}</h3>
                <p>{selected.summary || '—'}</p>
                {selected.open_questions.length > 0 && (
                  <>
                    <h4>{ct('console.questions')}</h4>
                    <ul>{selected.open_questions.map((q) => <li key={q}>{q}</li>)}</ul>
                  </>
                )}
              </section>

              <section className="console-card">
                <h3>{ct('console.facts')}</h3>
                <p className={facts?.identity_verified ? 'console-verified' : 'console-unverified'}>
                  {facts?.identity_verified
                    ? <><ShieldCheck size={16} aria-hidden="true" /> {ct('console.verified')}</>
                    : <><ShieldAlert size={16} aria-hidden="true" /> {ct('console.notVerified')}</>}
                </p>
                <dl className="console-facts">
                  <dt>{ct('console.customer')}</dt><dd>{facts?.first_name ?? '—'}</dd>
                  <dt>{ct('console.customerId')}</dt><dd><code>{facts?.customer_id ?? facts?.logged_in_customer_id ?? '—'}</code></dd>
                </dl>
              </section>

              <section className="console-card">
                <h3>{ct('console.intent')}</h3>
                {selected.intent ? (
                  <>
                    <p>
                      <strong>{intentLabel(selected.intent.label)}</strong>
                      {` · ${ct('console.intentConfidence')} ${Math.round(selected.intent.confidence * 100)}%`}
                    </p>
                    {selected.intent.fcr_rate != null && (
                      <p className="form-help">
                        {ct('console.intentFcr').replace('{rate}', `${Math.round(selected.intent.fcr_rate * 100)}%`)}
                      </p>
                    )}
                    {selected.intent.early_handoff && <p className="form-help">{ct('console.intentEarly')}</p>}
                  </>
                ) : (
                  <p className="form-help">{ct('console.intentNone')}</p>
                )}
              </section>

              <FaithfulnessPanel data={selected.faithfulness} />

              <section className="console-card">
                <h3>{ct('console.evidence')}</h3>
                {selected.evidence.length === 0 ? (
                  <p className="form-help">{ct('console.noEvidence')}</p>
                ) : (
                  selected.evidence.map((e, i) => (
                    <details key={i} className="console-evidence">
                      <summary><code>{e.tool}</code> {JSON.stringify(e.args)} · {when(e.at, locale)}</summary>
                      <pre>{e.result}</pre>
                    </details>
                  ))
                )}
              </section>
            </aside>
          </>
        )}
      </div>
    </div>
  );
}
