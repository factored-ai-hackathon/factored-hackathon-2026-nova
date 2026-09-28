import { X, MessageCircle } from 'lucide-react';
import type { Transaction } from '../../types';
import { formatCurrency, formatDate, formatTime } from '../../utils/format';
import { useApp } from '../../context/AppContext';
import { useAgent } from '../../context/AgentContext';
import { t } from '../../i18n/translations';

interface TransactionModalProps {
  transaction: Transaction;
  onClose: () => void;
}

export function TransactionModal({ transaction, onClose }: TransactionModalProps) {
  const { language } = useApp();
  const { openAgent, sendMessage } = useAgent();
  const isCredit = transaction.amount > 0;
  const locale = language === 'pt' ? 'pt-BR' : 'es-CO';

  function handleAskNova() {
    onClose();
    openAgent(transaction);
    void sendMessage(
      language === 'pt'
        ? `Não reconheço esta transação de ${transaction.merchant}. Você pode me ajudar?`
        : `No reconozco esta transacción de ${transaction.merchant}. ¿Puedes ayudarme?`,
      transaction
    );
  }

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="txn-modal-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal">
        <div className="modal-header">
          <h2 className="modal-title" id="txn-modal-title">{t('transaction.detailTitle', language)}</h2>
          <button className="modal-close" onClick={onClose} aria-label={t('common.close', language)}>
            <X size={16} />
          </button>
        </div>

        <div className="modal-body">
          <div className="detail-row">
            <span className="detail-label">{t('transaction.merchantDescription', language)}</span>
            <span className="detail-value">{transaction.merchant}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">{t('transaction.amount', language)}</span>
            <span className={`detail-value ${isCredit ? 'credit' : 'debit'}`}>
              {isCredit ? '+' : ''}{formatCurrency(transaction.amount, transaction.currency, locale)}
            </span>
          </div>
          <div className="detail-row">
            <span className="detail-label">{t('transaction.date', language)}</span>
            <span className="detail-value">{formatDate(transaction.date, locale)}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">{t('transaction.time', language)}</span>
            <span className="detail-value">{formatTime(transaction.date, locale)}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">{t('transaction.category', language)}</span>
            <span className="detail-value">{t(`transaction.category.${transaction.category}`, language)}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">{t('transaction.statusLabel', language)}</span>
            <span className="detail-value">
              <span className={`txn-status-badge ${transaction.status}`}>
                {t(`transaction.status.${transaction.status}`, language)}
              </span>
            </span>
          </div>
          {transaction.reference && (
            <div className="detail-row">
              <span className="detail-label">{t('transaction.reference', language)}</span>
              <span className="detail-value" style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
                {transaction.reference}
              </span>
            </div>
          )}
          {transaction.description && (
            <div className="detail-row">
              <span className="detail-label">{t('transaction.note', language)}</span>
              <span className="detail-value">{transaction.status === 'disputed' ? t('transaction.unrecognizedNote', language) : transaction.description}</span>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button
            className="btn-primary"
            onClick={handleAskNova}
            style={{ flex: 1 }}
            aria-label={t('transaction.askNova', language)}
          >
            <MessageCircle size={16} aria-hidden="true" />
            {t('transaction.askNova', language)}
          </button>
          <button className="btn-secondary" onClick={onClose}>
            {t('common.close', language)}
          </button>
        </div>
      </div>
    </div>
  );
}
