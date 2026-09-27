import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Info } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { login, getDemoCredentials } from '../../services/authService';
import { t, LANGUAGES } from '../../i18n/translations';
import '../../styles/login.css';

export function LoginPage() {
  const navigate = useNavigate();
  const { setCustomer, language, setLanguage } = useApp();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const demo = getDemoCredentials();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      const { customer } = await login({ email, password });
      setCustomer(customer);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      const code = err instanceof Error ? err.message : 'AUTH_ERROR';
      const message = code === 'MISSING_CREDENTIALS'
        ? t('login.invalidCredentials', language)
        : code === 'INVALID_EMAIL'
          ? t('login.invalidEmail', language)
          : t('login.authError', language);
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  function fillDemo() {
    setEmail(demo.email);
    setPassword(demo.password);
  }

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
          <h1>{t('login.title', language)}</h1>
          <p>{t('login.subtitle', language)}</p>
        </div>

        <form className="login-form" onSubmit={(e) => void handleSubmit(e)} noValidate>
          {/* Demo hint */}
          <div className="login-demo-hint" role="note">
            <Info size={16} style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
            <span>
              {t('login.demoHint', language)}
              {' '}
              <button
                type="button"
                onClick={fillDemo}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--color-info)',
                  fontWeight: 600,
                  cursor: 'pointer',
                  padding: 0,
                  fontSize: 'inherit',
                }}
              >
                {t('login.fillDemo', language)}
              </button>
            </span>
          </div>

          {/* Email */}
          <div className="form-group">
            <label htmlFor="email">{t('login.email', language)}</label>
            <input
              id="email"
              type="email"
              className={`form-input${error ? ' error' : ''}`}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
              aria-required="true"
              aria-describedby={error ? 'login-error' : undefined}
            />
          </div>

          {/* Password */}
          <div className="form-group">
            <label htmlFor="password">{t('login.password', language)}</label>
            <input
              id="password"
              type="password"
              className={`form-input${error ? ' error' : ''}`}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              aria-required="true"
            />
          </div>

          {/* Error */}
          {error && (
            <div id="login-error" className="form-error" role="alert">
              {error}
            </div>
          )}

          {/* Forgot password */}
          <button type="button" className="login-forgot" aria-label={t('login.forgotPassword', language)}>
            {t('login.forgotPassword', language)}
          </button>

          {/* Submit */}
          <button
            type="submit"
            className="btn-primary"
            disabled={isLoading}
            aria-busy={isLoading}
          >
            {isLoading ? (
              <>
                <span className="spinner" aria-hidden="true" />
                {t('common.loading', language)}
              </>
            ) : (
              t('login.submit', language)
            )}
          </button>
        </form>

        <div style={{ marginTop: 'var(--space-8)', textAlign: 'center' }}>
          <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
            {t('login.footer', language)}
          </p>
        </div>
      </div>
    </div>
  );
}
