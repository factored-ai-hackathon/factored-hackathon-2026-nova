import { Bell, Settings } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { t } from '../../i18n/translations';

interface TopHeaderProps {
  title: string;
}

export function TopHeader({ title }: TopHeaderProps) {
  const { customer, language } = useApp();

  const initials = customer
    ? customer.name.split(' ').map((n) => n[0]).slice(0, 2).join('')
    : 'U';

  return (
    <header className="top-header" role="banner">
      <h1 className="header-title">{title}</h1>
      <div className="header-actions">
        <button className="icon-btn" aria-label={t('common.notifications', language)}>
          <Bell size={18} />
          <span className="badge" aria-label={t('common.notificationCount', language)}>2</span>
        </button>
        <button className="icon-btn" aria-label={t('common.settings', language)}>
          <Settings size={18} />
        </button>
        <div className="user-avatar" style={{ width: 36, height: 36 }} aria-hidden="true">
          {initials}
        </div>
      </div>
    </header>
  );
}
