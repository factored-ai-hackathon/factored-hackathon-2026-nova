import { useEffect, useState } from 'react';
import {
  Send,
  ArrowUpRight,
  Download,
  Plus,
  Phone,
} from 'lucide-react';
import { Sidebar } from '../../components/layout/Sidebar';
import { TopHeader } from '../../components/layout/TopHeader';
import { TransactionListItem } from '../../components/banking/TransactionListItem';
import { TransactionModal } from '../../components/banking/TransactionModal';
import { AgentFAB } from '../../components/agent/AgentFAB';
import { AgentPanel } from '../../components/agent/AgentPanel';
import { useApp } from '../../context/AppContext';
import { useAgent } from '../../context/AgentContext';
import { mockAccounts, mockTransactions } from '../../data/mockData';
import { formatCurrency, formatDate } from '../../utils/format';
import { loadOverview, type AccountsOverview } from '../../services/accountService';
import { t, type TranslationKey } from '../../i18n/translations';
import type { Transaction, Account } from '../../types';
import '../../styles/dashboard.css';

const QUICK_ACTIONS: { icon: typeof Send; label: TranslationKey; ariaLabel: TranslationKey }[] = [
  { icon: Send, label: 'dashboard.transfer', ariaLabel: 'dashboard.transferAria' },
  { icon: ArrowUpRight, label: 'dashboard.pay', ariaLabel: 'dashboard.payAria' },
  { icon: Download, label: 'dashboard.deposit', ariaLabel: 'dashboard.depositAria' },
  { icon: Plus, label: 'dashboard.more', ariaLabel: 'dashboard.moreAria' },
];

const MOCK_NOTIFICATIONS = [
  {
    id: 'n1',
    title: 'dashboard.receivedTitle',
    body: 'dashboard.receivedBody',
    type: 'info' as const,
  },
  {
    id: 'n2',
    title: 'dashboard.unusualTitle',
    body: 'dashboard.unusualBody',
    type: 'warning' as const,
  },
];

const ACCOUNT_ICONS: Record<Account['type'], string> = {
  checking: '🏦',
  savings: '🏛️',
  credit: '💳',
  debit: '💳',
  loan: '🏠',
  investment: '📈',
  insurance: '🛡️',
};

interface Notice {
  id: string;
  title: string;
  body: string;
  type: 'info' | 'warning';
}

function AccountCard({ account }: { account: Account }) {
  const { language } = useApp();
  const locale = language === 'pt' ? 'pt-BR' : 'es-CO';
  const isCredit = account.balance < 0;
  const label = t(`account.${account.type}`, language);

  return (
    <div className="account-item" tabIndex={0} role="button" aria-label={`${label}, ${t('dashboard.balance', language)} ${formatCurrency(account.balance, account.currency, locale)}`}>
      <div className="account-icon" aria-hidden="true">
        {ACCOUNT_ICONS[account.type]}
      </div>
      <div className="account-details">
        <div className="account-name">{label}</div>
        <div className="account-number">{account.number}</div>
      </div>
      <div className="account-balance-col">
        <div className={`account-balance${isCredit ? ' negative' : ''}`}>
          {formatCurrency(account.balance, account.currency, locale)}
        </div>
        <div className="account-available">
          {t('dashboard.accountAvailable', language)} {formatCurrency(account.availableBalance, account.currency, locale)}
        </div>
      </div>
    </div>
  );
}

/** Notifications from the customer's own data: open complaints and the latest declined payment. */
function realNotices(overview: AccountsOverview | null, language: 'es' | 'pt', locale: string): Notice[] {
  if (!overview) return [];
  const notices: Notice[] = [];
  if (overview.openComplaints > 0) {
    notices.push({
      id: 'complaints',
      type: 'info',
      title: t('dashboard.complaintsTitle', language),
      body: t('dashboard.complaintsBody', language).replace('{n}', String(overview.openComplaints)),
    });
  }
  const declined = overview.transactions.find((txn) => txn.status === 'failed');
  if (declined) {
    notices.push({
      id: 'declined',
      type: 'warning',
      title: t('dashboard.declinedTitle', language),
      body: `${declined.merchant} · ${formatCurrency(Math.abs(declined.amount), declined.currency, locale)}`,
    });
  }
  return notices;
}

export function DashboardPage() {
  const { customer, language } = useApp();
  const { isOpen, isFullView, openAgent } = useAgent();
  const [selectedTxn, setSelectedTxn] = useState<Transaction | null>(null);

  const locale = language === 'pt' ? 'pt-BR' : 'es-CO';

  // Logged in with the real login: the customer's accounts from the dataset. Mock mode (no chat
  // session): the fictional mock data.
  const sessionId = customer?.sessionId;
  const [overview, setOverview] = useState<AccountsOverview | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  useEffect(() => {
    if (!sessionId || !customer) return;
    let cancelled = false;
    void (async () => {
      try {
        const loaded = await loadOverview(sessionId, customer.id, language);
        if (!cancelled) {
          setOverview(loaded);
          setLoadFailed(false);
        }
      } catch {
        if (!cancelled) setLoadFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, customer, language]);

  const real = Boolean(sessionId);
  const accounts = real ? (overview?.accounts ?? []) : mockAccounts;
  const recentTransactions = (real ? (overview?.transactions ?? []) : mockTransactions).slice(0, 5);
  const loading = real && !overview && !loadFailed;

  const primaryAccount =
    accounts.find((a) => a.type === 'checking' || a.type === 'savings') ?? accounts[0];
  const currency = primaryAccount?.currency ?? 'COP';
  // Total balance across the accounts with money in them (not cards or loans), in their currency
  const totalBalance = accounts
    .filter((a) => a.balance > 0 && a.type !== 'insurance' && a.currency === currency)
    .reduce((sum, a) => sum + a.balance, 0);

  const notices: Notice[] = real
    ? realNotices(overview, language, locale)
    : MOCK_NOTIFICATIONS.map((n) => ({
        ...n,
        title: t(n.title as TranslationKey, language),
        body: t(n.body as TranslationKey, language),
      }));

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-content" id="main-content">
        <TopHeader title={t('nav.home', language)} />
        <div className="page-container">
          {/* Welcome */}
          <div style={{ marginBottom: 'var(--space-5)' }}>
            <h2 style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: 'var(--color-text-primary)' }}>
              {t('dashboard.welcome', language)}, {customer?.name.split(' ')[0]} 👋
            </h2>
            <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', marginTop: 4 }}>
              {overview
                ? `${t('dashboard.dataAsOf', language)} ${formatDate(`${overview.dataAsOf}T12:00:00`, locale)}`
                : new Date().toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })}
            </p>
            {loading && <p className="dashboard-status" role="status">{t('dashboard.loading', language)}</p>}
            {loadFailed && <p className="dashboard-status" role="alert">{t('dashboard.loadError', language)}</p>}
          </div>

          <div className="dashboard-grid">
            {/* Balance card */}
            <div className="balance-card card">
              <div className="balance-label">{t('dashboard.balance', language)}</div>
              <div className="balance-amount">{formatCurrency(totalBalance, currency, locale)}</div>
              <div className="balance-row">
                <div className="balance-sub">
                  <span className="balance-sub-label">{t('dashboard.available', language)}</span>
                  <span className="balance-sub-value">
                    {formatCurrency(primaryAccount?.availableBalance ?? 0, currency, locale)}
                  </span>
                </div>
                <div className="balance-sub">
                  <span className="balance-sub-label">{t('dashboard.mainAccount', language)}</span>
                  <span className="balance-sub-value">{primaryAccount?.number ?? '—'}</span>
                </div>
              </div>
            </div>

            {/* Quick actions */}
            <div className="card span-2">
              <div className="card-header">
                <span className="card-title">{t('dashboard.quickActions', language)}</span>
              </div>
              <div className="quick-actions-grid">
                {QUICK_ACTIONS.map(({ icon: Icon, label, ariaLabel }) => (
                  <button key={label} className="quick-action-btn" aria-label={t(ariaLabel, language)}>
                    <div className="quick-action-icon">
                      <Icon size={22} aria-hidden="true" />
                    </div>
                    <span className="quick-action-label">{t(label, language)}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* My accounts */}
            <div className="card span-2">
              <div className="card-header">
                <span className="card-title">{t('nav.accounts', language)}</span>
                <button className="card-action">{t('dashboard.viewAll', language)}</button>
              </div>
              <div className="account-list">
                {accounts.map((account) => (
                  <AccountCard key={account.id} account={account} />
                ))}
              </div>
            </div>

            {/* Notifications */}
            <div className="card">
              <div className="card-header">
                <span className="card-title">{t('dashboard.notifications', language)}</span>
              </div>
              <div className="notification-list">
                {notices.map((n) => (
                  <div key={n.id} className={`notification-item ${n.type}`} role="article">
                    <div className="notification-content">
                      <div className="notification-title">{n.title}</div>
                      <div className="notification-body">{n.body}</div>
                    </div>
                  </div>
                ))}
                {/* Agent promo notification */}
                <div
                  className="notification-item"
                  style={{ borderLeftColor: 'var(--color-accent)', cursor: 'pointer', background: '#f0fdf4' }}
                  role="button"
                  tabIndex={0}
                  aria-label={t('dashboard.openNova', language)}
                  onClick={() => openAgent()}
                >
                  <div className="notification-content">
                    <div className="notification-title" style={{ color: 'var(--color-accent)' }}>
                      <Phone size={14} style={{ display: 'inline', marginRight: 4 }} aria-hidden="true" />
                      {t('dashboard.novaAvailable', language)}
                    </div>
                    <div className="notification-body">
                      {t('dashboard.novaBody', language)}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Recent transactions */}
            <div className="card span-3">
              <div className="card-header">
                <span className="card-title">{t('dashboard.recentTransactions', language)}</span>
                <button className="card-action">{t('dashboard.viewAll', language)}</button>
              </div>
              <div className="transaction-list" role="list" aria-label={t('dashboard.transactionsAria', language)}>
                {recentTransactions.map((txn) => (
                  <div key={txn.id} role="listitem">
                    <TransactionListItem
                      transaction={txn}
                      onClick={setSelectedTxn}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* AI Agent layer */}
      {!isFullView && (
        <>
          <AgentFAB />
          {isOpen && <AgentPanel />}
        </>
      )}

      {/* Transaction detail modal */}
      {selectedTxn && (
        <TransactionModal
          transaction={selectedTxn}
          onClose={() => setSelectedTxn(null)}
        />
      )}
    </div>
  );
}
