import { useState, useRef, useEffect } from 'react';
import {
  Maximize2,
  X,
  Send,
} from 'lucide-react';
import { MessageContent } from './MessageContent';
import { useAgent } from '../../context/AgentContext';
import { useApp } from '../../context/AppContext';
import { t } from '../../i18n/translations';
import { formatTime } from '../../utils/format';
import type { ConversationMessage } from '../../types';

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

// ------ Escalation card -----------------------------------

interface EscalationCardProps {
  onTransfer: () => void;
  onContinue: () => void;
  language: ReturnType<typeof useApp>['language'];
}

function EscalationCard({ onTransfer, onContinue, language }: EscalationCardProps) {
  return (
    <div className="escalation-card" role="alert">
      <p>{t('agent.escalate', language)}</p>
      <div className="escalation-actions">
        <button className="btn-escalate" onClick={onTransfer}>
          {t('agent.transferToSpecialist', language)}
        </button>
        <button className="btn-continue" onClick={onContinue}>
          {t('agent.continueWithNova', language)}
        </button>
      </div>
    </div>
  );
}

// ------ Message row ---------------------------------------

interface MessageRowProps {
  message: ConversationMessage;
  onSuggestedAction: (text: string) => void;
}

function MessageRow({ message, onSuggestedAction, language }: MessageRowProps & { language: 'es' | 'pt' }) {
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
        <div className={`msg-bubble ${message.role}`}>
          <MessageContent role={message.role} content={message.content} />
        </div>
        <span className="msg-time">{formatTime(message.timestamp, language === 'pt' ? 'pt-BR' : 'es-CO')}</span>
        {message.role === 'agent' && message.suggestedActions && message.suggestedActions.length > 0 && (
          <div className="suggested-actions" role="group" aria-label={t('agent.suggestedActions', language)}>
            {message.suggestedActions.map((action) => (
              <button
                key={action}
                className="suggested-btn"
                onClick={() => onSuggestedAction(action)}
              >
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

// ------ Main floating panel --------------------------------

export function AgentPanel() {
  const { language } = useApp();
  const {
    isOpen,
    conversation,
    isTyping,
    isStreaming,
    closeAgent,
    openFullView,
    sendMessage,
    resetConversation,
  } = useAgent();

  const [inputValue, setInputValue] = useState('');
  const [showEscalation, setShowEscalation] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  }, [conversation.messages, isTyping]);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  // Check if escalation is needed
  useEffect(() => {
    if (conversation.agentContext.requiresHuman) {
      setShowEscalation(true);
    }
  }, [conversation.agentContext.requiresHuman]);

  if (!isOpen) return null;

  async function handleSend() {
    const text = inputValue.trim();
    if (!text || isTyping) return;
    setInputValue('');
    setShowEscalation(false);
    await sendMessage(text);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  function handleTransferToSpecialist() {
    // Mock escalation: show a system message and reset
    setShowEscalation(false);
    void sendMessage(t('agent.transferRequest', language));
  }

  function handleContinueWithNova() {
    setShowEscalation(false);
    resetConversation();
  }

  const agentStatus = conversation.agentContext.status;

  return (
    <div
      className="agent-panel"
      role="complementary"
      aria-label={t('agent.title', language)}
    >
      {/* Header */}
      <div className="agent-panel-header">
        <div className="agent-avatar" aria-hidden="true">N</div>
        <div>
          <div className="agent-name">Nova</div>
          <div className="agent-status-dot">
            <span className={`status-dot ${agentStatus}`} aria-hidden="true" />
            {t(`agent.status.${agentStatus}`, language)}
          </div>
        </div>
        <div className="agent-panel-actions">
          <button
            className="panel-action-btn"
            onClick={openFullView}
            aria-label={t('agent.openFullView', language)}
            title={t('agent.openFullView', language)}
          >
            <Maximize2 size={14} />
          </button>
          <button
            className="panel-action-btn"
            onClick={closeAgent}
            aria-label={t('common.close', language)}
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="agent-messages" role="log" aria-live="polite" aria-label={t('agent.conversationAria', language)}>
        {conversation.messages.map((msg) => (
          <MessageRow
            key={msg.id}
            message={msg}
            language={language}
            onSuggestedAction={(text) => {
              setInputValue(text);
              inputRef.current?.focus();
            }}
          />
        ))}
        {isTyping && !isStreaming && <TypingIndicator language={language} />}
        <div ref={messagesEndRef} aria-hidden="true" />
      </div>

      {/* Escalation */}
      {showEscalation && (
        <EscalationCard
          onTransfer={handleTransferToSpecialist}
          onContinue={handleContinueWithNova}
          language={language}
        />
      )}

      {/* Input */}
      <div className="agent-input-area">
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
  );
}
