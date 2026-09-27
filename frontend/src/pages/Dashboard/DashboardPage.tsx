import { useState } from 'react';
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
import { formatCurrency } from '../../utils/format';
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

function AccountCard({ account }: { account: Account }) {
  const { language } = useApp();
  const locale = language === 'pt' ? 'pt-BR' : 'es-CO';
  const isCredit = account.type === 'credit';
  const label = t(`account.${account.type}`, language);

  return (
    <div className="account-item" tabIndex={0} role="button" aria-label={`${label}, ${t('dashboard.balance', language)} ${formatCurrency(account.balance, account.currency, locale)}`}>
      <div className="account-icon" aria-hidden="true">
        {account.type === 'checking' ? '🏦' : account.type === 'savings' ? '🏛️' : '💳'}
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

export function DashboardPage() {
  const { customer, language } = useApp();
  const { isOpen, isFullView, openAgent } = useAgent();
  const [selectedTxn, setSelectedTxn] = useState<Transaction | null>(null);

  const locale = language === 'pt' ? 'pt-BR' : 'es-CO';
  const primaryAccount = mockAccounts[0];
  const recentTransactions = mockTransactions.slice(0, 5);

  // Total balance across all non-credit accounts
  const totalBalance = mockAccounts
    .filter((a) => a.type !== 'credit')
    .reduce((sum, a) => sum + a.balance, 0);

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
              {new Date().toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })}
            </p>
          </div>

          <div className="dashboard-grid">
            {/* Balance card */}
            <div className="balance-card card">
              <div className="balance-label">{t('dashboard.balance', language)}</div>
              <div className="balance-amount">{formatCurrency(totalBalance, primaryAccount.currency, locale)}</div>
              <div className="balance-row">
                <div className="balance-sub">
                  <span className="balance-sub-label">{t('dashboard.available', language)}</span>
                  <span className="balance-sub-value">
                    {formatCurrency(primaryAccount.availableBalance, primaryAccount.currency, locale)}
                  </span>
                </div>
                <div className="balance-sub">
                  <span className="balance-sub-label">{t('dashboard.mainAccount', language)}</span>
                  <span className="balance-sub-value">{primaryAccount.number}</span>
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
                {mockAccounts.map((account) => (
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
                {MOCK_NOTIFICATIONS.map((n) => (
                  <div key={n.id} className={`notification-item ${n.type}`} role="article">
                    <div className="notification-content">
                      <div className="notification-title">{t(n.title as TranslationKey, language)}</div>
                      <div className="notification-body">{t(n.body as TranslationKey, language)}</div>
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
