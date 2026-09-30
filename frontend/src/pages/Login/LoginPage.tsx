import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MessageSquare } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { startLogin, verifyCode, type LoginForm, type PendingLogin } from '../../services/authService';
import { COUNTRIES, documentTypesFor } from '../../data/documents';
import { DemoPanel } from '../../components/demo/DemoPanel';
import { PublicAssistant } from '../../components/agent/PublicAssistant';
import { t, LANGUAGES, type TranslationKey } from '../../i18n/translations';
import '../../styles/login.css';

const ERROR_KEYS: Record<string, TranslationKey> = {
  INVALID_CREDENTIALS: 'login.invalidCredentials',
  WRONG_CODE: 'login.wrongCode',
  LOGIN_EXPIRED: 'login.expired',
  RATE_LIMITED: 'login.rateLimited',
};

const EMPTY_FORM: LoginForm = {
  country: COUNTRIES[0].value,
  documentType: COUNTRIES[0].documentTypes[0],
  documentNumber: '',
  password: '',
};

function documentLabel(type: string, language: 'es' | 'pt'): string {
  // CC, CE, Pasaporte have a long name; DNI is known by its acronym.
  const label: string | undefined = t(`document.${type}` as TranslationKey, language);
  return label ?? type;
}

export function LoginPage() {
  const navigate = useNavigate();
  const { setCustomer, language, setLanguage } = useApp();

  const [form, setForm] = useState<LoginForm>(EMPTY_FORM);
  const [pending, setPending] = useState<PendingLogin | null>(null);
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  function errorText(err: unknown): string {
    const key = err instanceof Error ? ERROR_KEYS[err.message] : undefined;
    return t(key ?? 'login.authError', language);
  }

  function update(changes: Partial<LoginForm>) {
    setForm((prev) => {
      const next = { ...prev, ...changes };
      const types = documentTypesFor(next.country);
      if (!types.includes(next.documentType)) next.documentType = types[0] ?? '';
      return next;
    });
  }

  async function submitCredentials(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      setPending(await startLogin(form, language));
      setCode('');
    } catch (err) {
      setError(errorText(err));
    } finally {
      setIsLoading(false);
    }
  }

  async function submitCode(e: React.FormEvent) {
    e.preventDefault();
    if (!pending) return;
    setError('');
    setIsLoading(true);
    try {
      setCustomer(await verifyCode(pending.loginId, code));
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(errorText(err));
      // Expired or too many wrong codes: back to the first step.
      if (err instanceof Error && err.message === 'LOGIN_EXPIRED') setPending(null);
    } finally {
      setIsLoading(false);
    }
  }

  function backToCredentials() {
    setPending(null);
    setError('');
  }

  const submitLabel = (key: TranslationKey) =>
    isLoading ? (
      <>
        <span className="spinner" aria-hidden="true" />
        {t('common.loading', language)}
      </>
    ) : (
      t(key, language)
    );

  return (
    <div className="login-root">
      {/* Left decorative panel */}
      <div className="login-left" aria-hidden="true">
        <div className="login-brand">
          <div className="login-logo">
            <div className="login-logo-icon">
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                <path d="M16 4L28 10V22L16 28L4 22V10L16 4Z" fill="white" fillOpacity="0.9" />
                <path d="M16 10L22 13V19L16 22L10 19V13L16 10Z" fill="white" fillOpacity="0.3" />
              </svg>
            </div>
            <span className="login-logo-text">NovaBank</span>
          </div>
          <div className="login-tagline">{t('login.tagline', language)}</div>
        </div>
        <div className="login-hero-text">
          <h2>{t('login.heroTitle', language)}</h2>
          <p>{t('login.heroDescription', language)}</p>
        </div>
      </div>

      {/* Right form panel */}
      <div className="login-right">
        {/* Language selector */}
        <div style={{ marginBottom: 'var(--space-6)' }}>
          <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginBottom: 'var(--space-2)' }}>
            {t('login.language', language)}
          </p>
          <div className="language-selector" role="group" aria-label={t('login.languageSelector', language)}>
            {LANGUAGES.map((lang) => (
              <button
                key={lang.code}
                className={`lang-btn${language === lang.code ? ' active' : ''}`}
                onClick={() => setLanguage(lang.code)}
                aria-pressed={language === lang.code}
              >
                {lang.label}
              </button>
            ))}
          </div>
        </div>

        <div className="login-form-header">
          <h1>{t(pending ? 'login.codeTitle' : 'login.title', language)}</h1>
          <p>
            {pending
              ? t('login.codeSubtitle', language).replace('{last4}', pending.phoneLast4)
              : t('login.subtitle', language)}
          </p>
        </div>

        {pending ? (
          <form className="login-form" onSubmit={(e) => void submitCode(e)} noValidate>
            {/* The SMS a real bank would send to the phone (there is no real SMS in the demo) */}
            <div className="login-sms" role="status">
              <MessageSquare size={16} aria-hidden="true" />
              <span>{pending.demoSms}</span>
            </div>

            <div className="form-group">
              <label htmlFor="login-code">{t('login.code', language)}</label>
              <input
                id="login-code"
                className={`form-input login-code${error ? ' error' : ''}`}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                required
                aria-describedby={error ? 'login-error' : undefined}
              />
            </div>

            {error && (
              <div id="login-error" className="form-error" role="alert">
                {error}
              </div>
            )}

            <button type="submit" className="btn-primary" disabled={isLoading || code.length !== 6} aria-busy={isLoading}>
              {submitLabel('login.verify')}
            </button>
            <button type="button" className="btn-ghost" onClick={backToCredentials}>
              {t('login.back', language)}
            </button>
          </form>
        ) : (
          <form className="login-form" onSubmit={(e) => void submitCredentials(e)} noValidate>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="login-country">{t('login.country', language)}</label>
                <select
                  id="login-country"
                  className="form-input"
                  value={form.country}
                  onChange={(e) => update({ country: e.target.value })}
                >
                  {COUNTRIES.map((c) => (
                    <option key={c.value} value={c.value}>{c.flag} {c.value}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label htmlFor="login-document-type">{t('login.documentType', language)}</label>
                <select
                  id="login-document-type"
                  className="form-input"
                  value={form.documentType}
                  onChange={(e) => update({ documentType: e.target.value })}
                >
                  {documentTypesFor(form.country).map((type) => (
                    <option key={type} value={type}>{documentLabel(type, language)}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="login-document">{t('login.documentNumber', language)}</label>
              <input
                id="login-document"
                className={`form-input${error ? ' error' : ''}`}
                value={form.documentNumber}
                onChange={(e) => update({ documentNumber: e.target.value })}
                autoComplete="username"
                spellCheck={false}
                maxLength={30}
                required
                aria-describedby={error ? 'login-error' : undefined}
              />
            </div>

            <div className="form-group">
              <label htmlFor="login-password">{t('login.password', language)}</label>
              <input
                id="login-password"
                type="password"
                className={`form-input${error ? ' error' : ''}`}
                value={form.password}
                onChange={(e) => update({ password: e.target.value })}
                autoComplete="current-password"
                maxLength={100}
                required
              />
            </div>

            {error && (
              <div id="login-error" className="form-error" role="alert">
                {error}
              </div>
            )}

            <button type="submit" className="btn-primary" disabled={isLoading} aria-busy={isLoading}>
              {submitLabel('login.submit')}
            </button>
          </form>
        )}

        {!pending && (
          <DemoPanel
            language={language}
            onUse={(demo) => {
              setForm(demo);
              setError('');
            }}
          />
        )}

        <div style={{ marginTop: 'var(--space-8)', textAlign: 'center' }}>
          <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
            {t('login.footer', language)}
          </p>
        </div>
      </div>
      <PublicAssistant />
    </div>
  );
}
