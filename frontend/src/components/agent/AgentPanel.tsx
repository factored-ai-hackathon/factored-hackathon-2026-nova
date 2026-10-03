import { useState, useRef, useEffect } from 'react';
import {
  Maximize2,
  Minimize2,
  X,
  Send,
  Download,
  RotateCcw,
  Minus,
  Mail,
  UserRound,
} from 'lucide-react';
import { MessageContent } from './MessageContent';
import { FeedbackButtons } from './FeedbackButtons';
import { SatisfactionPrompt } from './SatisfactionPrompt';
import { IdlePrompt } from './IdlePrompt';
import { useIdleTimer } from '../../hooks/useIdleTimer';
import { idleTimerEnabled } from '../../config/idleTimer';
import { useAgent } from '../../context/AgentContext';
import { useApp } from '../../context/AppContext';
import { t } from '../../i18n/translations';
import { formatTime } from '../../utils/format';
import type { ConversationMessage } from '../../types';
import type { HandoffState } from '../../context/AgentContext';
import { downloadTranscript, transcriptMailto, transcriptText } from '../../utils/transcript';

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

  if (message.role === 'human') {
    return (
      <div className="message-row agent human">
        <div className="msg-avatar human" aria-hidden="true">
          {(message.author ?? 'A').charAt(0).toUpperCase()}
        </div>
        <div>
          <div className="msg-author">{message.author} · {t('agent.humanAgent', language)}</div>
          <div className="msg-bubble human">{message.content}</div>
          <span className="msg-time">{formatTime(message.timestamp, language === 'pt' ? 'pt-BR' : 'es-CO')}</span>
        </div>
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
        <FeedbackButtons message={message} language={language} />
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

// ------ Handoff banner (a human agent has the conversation) ----

export function HandoffBanner({ handoff, language }: { handoff: HandoffState | null; language: 'es' | 'pt' }) {
  if (!handoff || handoff.status === 'closed') return null;
  const text = handoff.status === 'active'
    ? t('agent.handoffActive', language).replace('{name}', handoff.agentName ?? '')
    : t('agent.handoffWaiting', language);
  return (
    <div className={`handoff-banner ${handoff.status}`} role="status">
      <UserRound size={14} aria-hidden="true" />
      <span>
        {text} · <strong>{handoff.caseId}</strong>
      </span>
    </div>
  );
}

// ------ Close confirmation (download or email before closing) ----

function CloseDialog({
  language,
  onDownload,
  onEmail,
  onCancel,
  onConfirm,
}: {
  language: 'es' | 'pt';
  onDownload: () => void;
  onEmail: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="close-dialog-backdrop">
      <div className="close-dialog" role="alertdialog" aria-modal="true" aria-labelledby="close-dialog-title">
        <h3 id="close-dialog-title">{t('agent.closeTitle', language)}</h3>
        <p>{t('agent.closeBody', language)}</p>
        <div className="close-dialog-save">
          <button type="button" className="btn-secondary" onClick={onDownload}>
            <Download size={14} aria-hidden="true" /> {t('agent.download', language)}
          </button>
          <a className="btn-secondary" href={onEmail}>
            <Mail size={14} aria-hidden="true" /> {t('agent.email', language)}
          </a>
        </div>
        <div className="close-dialog-actions">
          <button type="button" className="btn-ghost" onClick={onCancel} autoFocus>
            {t('agent.closeNo', language)}
          </button>
          <button type="button" className="btn-danger" onClick={onConfirm}>
            {t('agent.closeYes', language)}
          </button>
        </div>
      </div>
    </div>
  );
}

// ------ Main floating panel --------------------------------

export function AgentPanel() {
  const { language, customer } = useApp();
  const {
    isOpen,
    isFullView,
    conversation,
    isTyping,
    isStreaming,
    openAgent,
    closeAgent,
    closeFullView,
    openFullView,
    sendMessage,
    resetConversation,
    handoff,
  } = useAgent();
  const [confirmClose, setConfirmClose] = useState(false);

  const [inputValue, setInputValue] = useState('');
  const [showEscalation, setShowEscalation] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Inactivity: never while a human case is open, Nova is answering, the panel is closed or the
  // close dialog is up. The automatic close skips the transcript dialog.
  const idle = useIdleTimer({
    active: (isOpen || isFullView) && !isTyping && !confirmClose
      && (!handoff || handoff.status === 'closed') && idleTimerEnabled(),
    activityKey: `${handoff?.caseId ?? ''}${handoff?.status ?? ''}|${conversation.messages.filter((m) => m.role === 'user').length}`,
    onTimeout: handleCloseChat,
  });

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  }, [conversation.messages, isTyping]);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen || isFullView) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen, isFullView]);

  // Check if escalation is needed
  useEffect(() => {
    if (conversation.agentContext.requiresHuman) {
      setShowEscalation(true);
    }
  }, [conversation.agentContext.requiresHuman]);

  if (!isOpen && !isFullView) return null;

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
  const transcript = () => transcriptText(conversation.messages, customer?.name ?? '', language);

  function handleCloseChat() {
    // The panel stays mounted when closed, so reset its local state here.
    setConfirmClose(false);
    setShowEscalation(false);
    setInputValue('');
    resetConversation();
    closeAgent();
  }

  return (
    <div
      className={`agent-panel${isFullView ? ' agent-panel--full' : ''}`}
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
            onClick={() => downloadTranscript(transcript())}
            aria-label={t('agent.download', language)}
            title={t('agent.download', language)}
          >
            <Download size={14} />
          </button>
          <button
            className="panel-action-btn"
            onClick={resetConversation}
            aria-label={t('agent.restart', language)}
            title={t('agent.restart', language)}
          >
            <RotateCcw size={14} />
          </button>
          {isFullView ? (
            <button
              className="panel-action-btn"
              onClick={() => { closeFullView(); openAgent(); }}
              aria-label={t('agent.minimize', language)}
              title={t('agent.minimize', language)}
            >
              <Minimize2 size={14} />
            </button>
          ) : (
            <button
              className="panel-action-btn"
              onClick={openFullView}
              aria-label={t('agent.openFullView', language)}
              title={t('agent.openFullView', language)}
            >
              <Maximize2 size={14} />
            </button>
          )}
          {!isFullView && (
            <button
              className="panel-action-btn"
              onClick={closeAgent}
              aria-label={t('agent.minimize', language)}
              title={t('agent.minimize', language)}
            >
              <Minus size={14} />
            </button>
          )}
          <button
            className="panel-action-btn"
            onClick={() => setConfirmClose(true)}
            aria-label={t('common.close', language)}
            title={t('common.close', language)}
          >
            <X size={14} />
          </button>
        </div>
      </div>

      <HandoffBanner handoff={handoff} language={language} />

      {confirmClose && (
        <CloseDialog
          language={language}
          onDownload={() => downloadTranscript(transcript())}
          onEmail={transcriptMailto(transcript(), language)}
          onCancel={() => setConfirmClose(false)}
          onConfirm={handleCloseChat}
        />
      )}

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
        <SatisfactionPrompt handoff={handoff} language={language} />
        <IdlePrompt phase={idle.phase} canKeepOpen={idle.canKeepOpen} onKeepOpen={idle.keepOpen} language={language} />
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
