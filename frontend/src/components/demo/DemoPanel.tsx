// Demo panel on the login page: test customers from the synthetic dataset (docs/demo.md).
// Kept apart from the bank's UI: it opens only when asked, and says it's a demo.

import { useState } from 'react';
import { FlaskConical, Search, X } from 'lucide-react';
import * as api from '../../api/client';
import { t, type TranslationKey } from '../../i18n/translations';
import type { Language } from '../../types';
import type { LoginForm } from '../../services/authService';

const SCENARIO_KEYS: Record<string, { title: TranslationKey; body: TranslationKey }> = {
  random: { title: 'demo.random', body: 'demo.randomBody' },
  declined_transaction: { title: 'demo.declined', body: 'demo.declinedBody' },
  open_complaint: { title: 'demo.complaint', body: 'demo.complaintBody' },
  past_due: { title: 'demo.pastDue', body: 'demo.pastDueBody' },
};

function birthDate(iso: string): string {
  const [year, month, day] = iso.split('-');
  return `${day}/${month}/${year}`;
}

interface Props {
  language: Language;
  onUse: (form: LoginForm) => void;
}

export function DemoPanel({ language, onUse }: Props) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<api.DemoScenarios | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<api.DemoCustomer | null>(null);

  async function openPanel() {
    setOpen(true);
    setError('');
    try {
      setData(await api.demoScenarios());
    } catch {
      setError(t('demo.unavailable', language));
    }
  }

  async function search(e: React.FormEvent) {
    e.preventDefault();
    setFound(null);
    setError('');
    const id = query.trim();
    if (!id) return;
    try {
      setFound(await api.demoCustomer(id));
    } catch (err) {
      const notFound = err instanceof api.ApiError && (err.status === 404 || err.status === 422);
      setError(t(notFound ? 'demo.notFound' : 'demo.unavailable', language));
    }
  }

  function use(customer: api.DemoCustomer) {
    onUse({
      country: customer.country,
      documentType: customer.document_type,
      documentNumber: customer.document_number,
      password: data?.password ?? '',
    });
    setOpen(false);
  }

  function card(customer: api.DemoCustomer, title?: string, body?: string) {
    const canLogIn = Boolean(customer.phone_last4);
    return (
      <li key={`${title}-${customer.customer_id}`} className="demo-customer">
        {title && <div className="demo-customer-title">{title}</div>}
        {body && <p className="demo-customer-body">{body}</p>}
        <dl className="demo-customer-data">
          <dt>{customer.first_name}</dt>
          <dd>{customer.country} · {customer.document_type} {customer.document_number}</dd>
          <dt>{t('demo.birthDate', language)}</dt>
          <dd>{birthDate(customer.birth_date)}</dd>
          <dt>ID</dt>
          <dd><code>{customer.customer_id}</code></dd>
        </dl>
        {canLogIn ? (
          <button type="button" className="btn-secondary" onClick={() => use(customer)}>
            {t('demo.use', language)}
          </button>
        ) : (
          <p className="form-help">{t('demo.noPhone', language)}</p>
        )}
      </li>
    );
  }

  if (!open) {
    return (
      <button type="button" className="demo-toggle" onClick={() => void openPanel()}>
        <FlaskConical size={14} aria-hidden="true" /> {t('demo.open', language)}
      </button>
    );
  }

  return (
    <section className="demo-panel" aria-labelledby="demo-panel-title">
      <div className="demo-panel-header">
        <h2 id="demo-panel-title">
          <FlaskConical size={16} aria-hidden="true" /> {t('demo.title', language)}
        </h2>
        <button type="button" className="btn-ghost" onClick={() => setOpen(false)} aria-label={t('demo.close', language)}>
          <X size={16} aria-hidden="true" />
        </button>
      </div>
      <p className="demo-panel-note">
        {t('demo.note', language)}{' '}
        {data && <>{t('demo.password', language)} <code>{data.password}</code></>}
      </p>

      {data && (
        <ul className="demo-customers">
          {data.scenarios.map(({ key, customer }) =>
            card(
              customer,
              t(SCENARIO_KEYS[key]?.title ?? 'demo.random', language),
              SCENARIO_KEYS[key] ? t(SCENARIO_KEYS[key].body, language) : undefined,
            ),
          )}
        </ul>
      )}

      <form className="demo-search" onSubmit={(e) => void search(e)}>
        <label htmlFor="demo-customer-id">{t('demo.searchLabel', language)}</label>
        <div className="demo-search-row">
          <input
            id="demo-customer-id"
            className="form-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            maxLength={64}
            spellCheck={false}
            autoComplete="off"
          />
          <button type="submit" className="btn-secondary" aria-label={t('demo.search', language)}>
            <Search size={16} aria-hidden="true" />
          </button>
        </div>
      </form>
      {found && <ul className="demo-customers">{card(found)}</ul>}
      <p className="demo-console-link">
        <a href="/asesor" target="_blank" rel="noopener noreferrer">{t('console.open', language)} ↗</a>
      </p>
      {error && <p className="form-error" role="alert">{error}</p>}
    </section>
  );
}
