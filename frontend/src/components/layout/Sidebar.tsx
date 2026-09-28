import { Link, useLocation } from 'react-router-dom';
import {
  Home,
  CreditCard,
  ArrowLeftRight,
  Receipt,
  HelpCircle,
  Wallet,
  LogOut,
} from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { t } from '../../i18n/translations';

const NAV_ITEMS = [
  { key: 'nav.home', icon: Home, path: '/dashboard' },
  { key: 'nav.accounts', icon: Wallet, path: '/accounts' },
  { key: 'nav.cards', icon: CreditCard, path: '/cards' },
  { key: 'nav.transactions', icon: ArrowLeftRight, path: '/transactions' },
  { key: 'nav.payments', icon: Receipt, path: '/payments' },
  { key: 'nav.help', icon: HelpCircle, path: '/help' },
] as const;

export function Sidebar() {
  const { customer, language, logout } = useApp();
  const location = useLocation();

  const initials = customer
    ? customer.name.split(' ').map((n) => n[0]).slice(0, 2).join('')
    : 'U';

  return (
    <aside className="sidebar" role="navigation" aria-label={t('nav.primary', language)}>
      {/* Brand */}
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon" aria-hidden="true">N</div>
        <span className="sidebar-brand-name">NovaBank</span>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {NAV_ITEMS.map(({ key, icon: Icon, path }) => (
          <Link
            key={path}
            to={path}
            className={`nav-item${location.pathname === path ? ' active' : ''}`}
            aria-current={location.pathname === path ? 'page' : undefined}
          >
            <Icon size={18} aria-hidden="true" />
            {t(key, language)}
          </Link>
        ))}
      </nav>

      {/* User footer */}
      <div className="sidebar-footer">
        <div className="user-card">
          <div className="user-avatar" aria-hidden="true">{initials}</div>
          <div className="user-info">
            <div className="user-name">{customer?.name ?? t('agent.customer', language)}</div>
            <div className="user-segment">{customer ? t(`account.${customer.segment}`, language) : ''}</div>
          </div>
        </div>
        <button
          className="nav-item"
          onClick={logout}
          aria-label={t('common.logout', language)}
          style={{ color: 'var(--color-error)', marginTop: '4px' }}
        >
          <LogOut size={18} aria-hidden="true" />
          {t('common.logout', language)}
        </button>
      </div>
    </aside>
  );
}
