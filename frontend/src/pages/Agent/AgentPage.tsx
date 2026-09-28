import { useState, useRef, useEffect } from 'react';
import { ArrowLeft, Send } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { AgentContextPanel } from '../../components/agent/AgentContextPanel';
import { useAgent } from '../../context/AgentContext';
import { useApp } from '../../context/AppContext';
import { t } from '../../i18n/translations';
import { formatTime } from '../../utils/format';
import { mockAccounts, mockTransactions, mockCustomer } from '../../data/mockData';
import { formatCurrency } from '../../utils/format';
import type { ConversationMessage } from '../../types';
import '../../styles/agent.css';
import '../../styles/dashboard.css';

// ------ Left customer context panel -----------------------

function CustomerContextPanel() {
  const { language } = useApp();
  const locale = language === 'pt' ? 'pt-BR' : 'es-CO';
  const primaryAccount = mockAccounts[0];
  const recentTxns = mockTransactions.slice(0, 3);

  return (
    <aside className="agent-full-left" aria-label={t('agent.customerContext', language)}>
      {/* Header */}
      <div className="full-view-header">
        <span className="full-view-title">{t('agent.customerContext', language)}</span>
      </div>

      {/* Customer info */}
      <div className="context-section">
        <div className="context-section-title">{t('agent.customer', language)}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 'var(--space-3)' }}>
          <div
            className="user-avatar"
            style={{ width: 44, height: 44, fontSize: 'var(--text-base)' }}
            aria-hidden="true"
          >
            {mockCustomer.name.split(' ').map((n) => n[0]).slice(0, 2).join('')}
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>{mockCustomer.name}</div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}>
              {mockCustomer.id}
            </div>
          </div>
        </div>
        <div className="context-row">
          <span className="context-label">{t('account.segment', language)}</span>
          <span className="context-value">{t(`account.${mockCustomer.segment}`, language)}</span>
        </div>
        <div className="context-row">
          <span className="context-label">{t('agent.statusLabel', language)}</span>
          <span className="context-value" style={{ color: 'var(--color-success)' }}>{t('account.active', language)}</span>
        </div>
        <div className="context-row">
          <span className="context-label">{t('agent.language', language)}</span>
          <span className="context-value">{language === 'es' ? 'Español' : 'Português'}</span>
        </div>
        <div className="context-row">
          <span className="context-label">{t('agent.memberSince', language)}</span>
          <span className="context-value">{new Date(mockCustomer.memberSince).getFullYear()}</span>
        </div>
      </div>

      {/* Account summary */}
      <div className="context-section">
        <div className="context-section-title">{t('agent.primaryAccount', language)}</div>
        <div className="context-row">
          <span className="context-label">{t('agent.number', language)}</span>
          <span className="context-value" style={{ fontFamily: 'var(--font-mono)' }}>{primaryAccount.number}</span>
        </div>
        <div className="context-row">
          <span className="context-label">{t('dashboard.balance', language)}</span>
          <span className="context-value">
            {formatCurrency(primaryAccount.balance, primaryAccount.currency, locale)}
          </span>
        </div>
        <div className="context-row">
          <span className="context-label">{t('dashboard.available', language)}</span>
          <span className="context-value">
            {formatCurrency(primaryAccount.availableBalance, primaryAccount.currency, locale)}
          </span>
        </div>
      </div>

      {/* Recent transactions */}
      <div className="context-section">
        <div className="context-section-title">{t('agent.recentTransactions', language)}</div>
        {recentTxns.map((txn) => (
          <div key={txn.id} className="context-row" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}>
            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 500 }}>{txn.merchant}</span>
            <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
              <span className="context-label">{new Date(txn.date).toLocaleDateString(locale, { day: '2-digit', month: 'short' })}</span>
              <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: txn.amount < 0 ? 'var(--color-text-primary)' : 'var(--color-accent)' }}>
                {txn.amount > 0 ? '+' : ''}{formatCurrency(txn.amount, txn.currency, locale)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}

// ------ Message row (full view) ---------------------------

interface FullMessageRowProps {
  message: ConversationMessage;
  onSuggestedAction: (text: string) => void;
  language: 'es' | 'pt';
}

function FullMessageRow({ message, onSuggestedAction, language }: FullMessageRowProps) {
  if (message.role === 'system') {
    return (
      <div className="message-row system">
        <div className="msg-bubble system">{message.content}</div>
      </div>
    );
  }

  return (
    <div className={`message-row ${message.role}`}>
      {message.role === 'agent' && (
        <div className="msg-avatar" aria-hidden="true">N</div>
      )}
      <div>
        <div className={`msg-bubble ${message.role}`}>{message.content}</div>
        <span className="msg-time">{formatTime(message.timestamp, language === 'pt' ? 'pt-BR' : 'es-CO')}</span>
        {message.role === 'agent' && message.suggestedActions && message.suggestedActions.length > 0 && (
          <div className="suggested-actions">
            {message.suggestedActions.map((action) => (
              <button key={action} className="suggested-btn" onClick={() => onSuggestedAction(action)}>
                {action}
              </button>
            ))}
          </div>
        )}
      </div>
      {message.role === 'user' && (
        <div className="msg-avatar user" aria-hidden="true">{language === 'pt' ? 'Eu' : 'Yo'}</div>
      )}
    </div>
  );
}

// ------ Typing indicator ----------------------------------

function TypingIndicator({ language }: { language: 'es' | 'pt' }) {
  return (
    <div className="message-row agent" role="status" aria-label={t('agent.typing', language)}>
      <div className="msg-avatar" aria-hidden="true">N</div>
      <div className="typing-indicator" aria-hidden="true">
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </div>
    </div>
  );
}

// ------ Main full agent view page -------------------------

export function AgentPage() {
  const navigate = useNavigate();
  const { language } = useApp();
  const { conversation, isTyping, sendMessage } = useAgent();

  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  }, [conversation.messages, isTyping]);

  async function handleSend() {
    const text = inputValue.trim();
    if (!text || isTyping) return;
    setInputValue('');
    await sendMessage(text);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  return (
    <div className="agent-full-view" aria-label={t('agent.title', language)}>
      {/* Left: Customer context */}
      <CustomerContextPanel />

      {/* Center: Conversation */}
      <div className="agent-full-center">
        {/* Header */}
        <div className="full-view-header">
          <button
            className="btn-ghost"
            onClick={() => navigate('/dashboard')}
            aria-label={t('agent.backHome', language)}
            style={{ padding: '6px 10px' }}
          >
            <ArrowLeft size={16} aria-hidden="true" />
          </button>
          <div className="agent-avatar" style={{ width: 32, height: 32, fontSize: 'var(--text-sm)', background: 'var(--color-primary)', color: 'white', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }} aria-hidden="true">
            N
          </div>
          <div>
            <div className="full-view-title">{t('agent.title', language)}</div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
              {t('agent.conversationId', language)}: {conversation.id}
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="full-conversation" role="log" aria-live="polite" aria-label={t('agent.conversation', language)}>
          {conversation.messages.map((msg) => (
            <FullMessageRow
              key={msg.id}
              message={msg}
              language={language}
              onSuggestedAction={(text) => {
                setInputValue(text);
                inputRef.current?.focus();
              }}
            />
          ))}
          {isTyping && <TypingIndicator language={language} />}
          <div ref={messagesEndRef} aria-hidden="true" />
        </div>

        {/* Input */}
        <div className="agent-input-area" style={{ borderTop: '1px solid var(--color-border)' }}>
          <div className="agent-input-row">
            <textarea
              ref={inputRef}
              className="agent-input"
              placeholder={t('agent.placeholder', language)}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={isTyping}
            aria-label={t('agent.placeholder', language)}
            />
            <button
              className="send-btn"
              onClick={() => void handleSend()}
              disabled={!inputValue.trim() || isTyping}
              aria-label={t('agent.send', language)}
            >
              <Send size={15} />
            </button>
          </div>
        </div>
      </div>

      {/* Right: Agent context */}
      <AgentContextPanel />
    </div>
  );
}
