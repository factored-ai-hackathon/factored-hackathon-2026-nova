import type { Transaction } from '../../types';
import { formatCurrency, formatDate } from '../../utils/format';
import { useApp } from '../../context/AppContext';
import { t } from '../../i18n/translations';

// Category emoji map for visual clarity
const CATEGORY_EMOJI: Record<string, string> = {
  groceries: '🛒',
  dining: '🍽️',
  transport: '🚌',
  utilities: '💡',
  entertainment: '🎬',
  health: '💊',
  education: '📚',
  transfer: '💸',
  atm: '🏧',
  online: '🌐',
  other: '📋',
};

interface TransactionListItemProps {
  transaction: Transaction;
  onClick: (txn: Transaction) => void;
}

export function TransactionListItem({ transaction, onClick }: TransactionListItemProps) {
  const { language } = useApp();
  const locale = language === 'pt' ? 'pt-BR' : 'es-CO';
  const isCredit = transaction.amount > 0;
  const emoji = CATEGORY_EMOJI[transaction.category] ?? '📋';

  return (
    <div
      className="transaction-item"
      onClick={() => onClick(transaction)}
      role="button"
      tabIndex={0}
      aria-label={`${t('transaction.labelPrefix', language)}: ${transaction.merchant}, ${formatCurrency(transaction.amount, transaction.currency, locale)}`}
      onKeyDown={(e) => e.key === 'Enter' && onClick(transaction)}
    >
      <div className="txn-icon" aria-hidden="true">{emoji}</div>
      <div className="txn-details">
        <div className="txn-merchant">{transaction.merchant}</div>
        <div className="txn-date">{formatDate(transaction.date, language === 'pt' ? 'pt-BR' : 'es-CO')}</div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
        <span className={`txn-amount ${isCredit ? 'credit' : 'debit'}`}>
          {isCredit ? '+' : ''}{formatCurrency(transaction.amount, transaction.currency, locale)}
        </span>
        <span className={`txn-status-badge ${transaction.status}`}>
          {t(`transaction.status.${transaction.status}`, language)}
        </span>
      </div>
    </div>
  );
}
