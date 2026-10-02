// Human agent console (/asesor): the cases Nova handed over, with the summary, the facts the
// system verified, the evidence Nova consulted, and the live conversation (decision 27).

import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Headset, LineChart, LogOut, RefreshCw, ShieldCheck, ShieldAlert } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { t, LANGUAGES, type TranslationKey } from '../../i18n/translations';
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

function reasonLabel(reason: string, language: 'es' | 'pt'): string {
  const label: string | undefined = t(`console.reason.${reason}` as TranslationKey, language);
  return label ?? reason;
}

function intentLabel(intent: string, language: 'es' | 'pt'): string {
  const label: string | undefined = t(`console.intent.${intent}` as TranslationKey, language);
  return label ?? intent;
}

export function AgentConsolePage() {
  const { language, setLanguage } = useApp();
  const locale = language === 'pt' ? 'pt-BR' : 'es-CO';
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
      setError(t(err instanceof ApiError && err.status === 401 ? 'console.badKey' : 'console.error', language));
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
      setError(t('console.error', language));
    }
  }

  if (!signedIn) {
    return (
      <div className="console-login">
        <form className="console-login-card" onSubmit={(e) => void signIn(e)}>
          <Headset size={28} aria-hidden="true" />
          <h1>{t('console.title', language)}</h1>
          <p>{t('console.subtitle', language)}</p>
          <label htmlFor="console-key">{t('console.key', language)}</label>
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
          <button type="submit" className="btn-primary">{t('console.enter', language)}</button>
          <p className="form-help">{t('console.demoKey', language)}</p>
          <Link to="/modelos" className="console-login-link">
            <LineChart size={14} aria-hidden="true" /> {t('console.modelsLink', language)}
          </Link>
        </form>
      </div>
    );
  }

  const facts = selected?.verified_facts;
  const customerLabel = facts?.first_name ?? t('console.customer', language);
  return (
    <div className="console-root">
      <header className="console-header">
        <Headset size={20} aria-hidden="true" />
        <h1>{t('console.title', language)}</h1>
        <div className="console-header-actions">
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              className={`lang-btn${language === l.code ? ' active' : ''}`}
              onClick={() => setLanguage(l.code)}
              aria-pressed={language === l.code}
            >
              {l.label}
            </button>
          ))}
          <button className="btn-ghost" onClick={() => void refresh()} aria-label={t('console.refresh', language)}>
            <RefreshCw size={16} aria-hidden="true" />
          </button>
          <button className="btn-ghost" onClick={() => { clearStored(KEYS.console); setSignedIn(false); setKey(''); setSelected(null); }}>
            <LogOut size={16} aria-hidden="true" /> {t('console.logout', language)}
          </button>
        </div>
      </header>

      <div className="console-body">
        {/* 1. Ticket queue */}
        <aside className="console-list" aria-label={t('console.queue', language)}>
          <div className="console-kpis">
            <div className="console-kpi"><span>{stats?.waiting ?? 0}</span>{t('console.status.waiting', language)}</div>
            <div className="console-kpi"><span>{stats?.active ?? 0}</span>{t('console.status.active', language)}</div>
            <div className="console-kpi"><span>{stats?.closed ?? 0}</span>{t('console.status.closed', language)}</div>
            <div className="console-kpi">
              <span>{stats?.faithfulness_avg == null ? '—' : `${Math.round(stats.faithfulness_avg * 100)}%`}</span>
              {t('console.faithAvg', language)}
            </div>
          </div>
          <h2 className="console-section-title">{t('console.queue', language)}</h2>
          {cases.length === 0 && <p className="console-empty">{t('console.empty', language)}</p>}
          <ul>
            {cases.map((c) => (
              <li key={c.case_id}>
                <button
                  className={`console-case${selectedId === c.case_id ? ' selected' : ''}`}
                  onClick={() => void act(() => consoleApi.getCase(key, c.case_id))}
                >
                  <span className={`console-status ${c.status}`}>{t(`console.status.${c.status}`, language)}</span>
                  <span><strong>{c.case_id}</strong> · {c.customer ?? '—'}</span>
                  <span className="console-case-reason">
                    {reasonLabel(c.reason, language)}
                    {c.intent && ` · ${intentLabel(c.intent, language)}`}
                  </span>
                  <span className="console-case-time">
                    {when(c.created_at, locale)}
                    {c.faithfulness != null && ` · ${t('console.faith', language)} ${Math.round(c.faithfulness * 100)}%`}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        {!selected ? (
          <main className="console-dialog console-empty-state">
            <p className="console-empty">{t('console.pick', language)}</p>
          </main>
        ) : (
          <>
            {/* 2. Dialog: Nova's conversation, then the agent's */}
            <main className="console-dialog" aria-label={t('console.dialog', language)}>
              <div className="console-detail-header">
                <h2>{selected.case_id}</h2>
                <span className={`console-status ${selected.status}`}>
                  {t(`console.status.${selected.status}`, language)}
                </span>
                <span>{customerLabel} · {reasonLabel(selected.reason, language)} · {selected.lang.toUpperCase()}</span>
              </div>
              <ol className="console-thread">
                {selected.transcript.map((m, i) => (
                  <li key={`t${i}`} className={`bubble ${m.role === 'customer' ? 'customer' : 'nova'}`}>
                    <span className="bubble-who">{m.role === 'customer' ? customerLabel : 'Nova'}</span>
                    {m.role === 'customer' ? m.text : <MessageContent role="agent" content={m.text} />}
                  </li>
                ))}
                <li className="console-divider">{t('console.handedOver', language)}</li>
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
                    <label htmlFor="agent-name">{t('console.yourName', language)}</label>
                    <div className="console-action-row">
                      <input id="agent-name" className="form-input" value={agentName} maxLength={60}
                        onChange={(e) => setAgentName(e.target.value)} />
                      <button type="submit" className="btn-primary" disabled={!agentName.trim()}>
                        {t('console.take', language)}
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
                    <label htmlFor="agent-reply">{t('console.reply', language)}</label>
                    <textarea id="agent-reply" className="form-input" rows={2} value={reply} maxLength={2000}
                      onChange={(e) => setReply(e.target.value)} />
                    <div className="console-action-buttons">
                      <button type="submit" className="btn-primary" disabled={!reply.trim()}>
                        {t('console.send', language)}
                      </button>
                      <button type="button" className="btn-secondary"
                        onClick={() => void act(() => consoleApi.closeCase(key, selected.case_id))}>
                        {t('console.close', language)}
                      </button>
                    </div>
                  </form>
                )}
                {error && <p className="form-error" role="alert">{error}</p>}
              </div>
            </main>

            {/* 3. What the agent needs to decide: summary, facts, evidence, faithfulness */}
            <aside className="console-insights" aria-label={t('console.insights', language)}>
              <section className="console-card">
                <h3>{t('console.summary', language)}</h3>
                <p>{selected.summary || '—'}</p>
                {selected.open_questions.length > 0 && (
                  <>
                    <h4>{t('console.questions', language)}</h4>
                    <ul>{selected.open_questions.map((q) => <li key={q}>{q}</li>)}</ul>
                  </>
                )}
              </section>

              <section className="console-card">
                <h3>{t('console.facts', language)}</h3>
                <p className={facts?.identity_verified ? 'console-verified' : 'console-unverified'}>
                  {facts?.identity_verified
                    ? <><ShieldCheck size={16} aria-hidden="true" /> {t('console.verified', language)}</>
                    : <><ShieldAlert size={16} aria-hidden="true" /> {t('console.notVerified', language)}</>}
                </p>
                <dl className="console-facts">
                  <dt>{t('console.customer', language)}</dt><dd>{facts?.first_name ?? '—'}</dd>
                  <dt>{t('console.customerId', language)}</dt><dd><code>{facts?.customer_id ?? facts?.logged_in_customer_id ?? '—'}</code></dd>
                </dl>
              </section>

              <section className="console-card">
                <h3>{t('console.intent', language)}</h3>
                {selected.intent ? (
                  <>
                    <p>
                      <strong>{intentLabel(selected.intent.label, language)}</strong>
                      {` · ${t('console.intentConfidence', language)} ${Math.round(selected.intent.confidence * 100)}%`}
                    </p>
                    {selected.intent.fcr_rate != null && (
                      <p className="form-help">
                        {t('console.intentFcr', language).replace('{rate}', `${Math.round(selected.intent.fcr_rate * 100)}%`)}
                      </p>
                    )}
                    {selected.intent.early_handoff && <p className="form-help">{t('console.intentEarly', language)}</p>}
                  </>
                ) : (
                  <p className="form-help">{t('console.intentNone', language)}</p>
                )}
              </section>

              <FaithfulnessPanel data={selected.faithfulness} language={language} />

              <section className="console-card">
                <h3>{t('console.evidence', language)}</h3>
                {selected.evidence.length === 0 ? (
                  <p className="form-help">{t('console.noEvidence', language)}</p>
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
