import { useEffect, useRef, useState } from 'react';
import { MessageCircle, Send, X } from 'lucide-react';
import { MessageContent } from './MessageContent';
import { useApp } from '../../context/AppContext';
import { t } from '../../i18n/translations';
import * as api from '../../api/client';
import { limitReason } from '../../api/client';
import '../../styles/agent.css';

const USE_MOCK = import.meta.env.VITE_MOCK === '1';

interface PublicMessage {
  id: number;
  role: 'user' | 'agent';
  content: string;
}

/**
 * Assistant for visitors outside the login (decision 30): NovaBank hours and branches, nothing
 * about customers. Its own session and endpoints (/v1/public/chat): it has no customer and no
 * account data to read, so there's nothing the page has to hide.
 */
export function PublicAssistant() {
  const { language } = useApp();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<PublicMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const sessionRef = useRef<string | null>(null);
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  }, [messages]);

  function add(role: PublicMessage['role'], content: string): number {
    const id = nextId.current++;
    setMessages((prev) => [...prev, { id, role, content }]);
    return id;
  }

  function setContent(id: number, content: string) {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, content } : m)));
  }

  async function ask(text: string) {
    const question = text.trim();
    if (!question || busy) return;
    setInput('');
    add('user', question);
    setBusy(true);
    const answer = add('agent', '…');
    try {
      if (USE_MOCK) {
        setContent(answer, t('public.mock', language));
        return;
      }
      sessionRef.current ??= await api.createPublicSession(language);
      let reply = '';
      for await (const event of api.sendMessage(
        sessionRef.current, question, language, undefined, '/v1/public/chat',
      )) {
        if (event.type === 'token') {
          reply += event.text;
          setContent(answer, reply);
        } else if (event.type === 'error') {
          throw new Error(event.code);
        }
      }
    } catch (err) {
      if (err instanceof api.ApiError && err.status === 404) sessionRef.current = null; // expired
      const reason = limitReason(err);
      setContent(
        answer,
        reason === 'daily_budget_exhausted' ? t('agent.limit.budget', language)
          : reason === 'rate_limited' ? t('agent.limit.rate', language)
          : t('public.error', language),
      );
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void ask(input);
    }
  }

  const quick = ['public.quick.hours', 'public.quick.branches', 'public.quick.account'] as const;

  return (
    <>
      <div className="agent-fab">
        <span className="agent-fab-label">{t('public.label', language)}</span>
        {!isOpen && <span className="agent-fab-pulse" aria-hidden="true" />}
        <button
          className={`agent-fab-btn${isOpen ? ' active' : ''}`}
          onClick={() => setIsOpen((open) => !open)}
          aria-label={isOpen ? t('public.close', language) : t('public.open', language)}
          aria-expanded={isOpen}
        >
          {isOpen ? <X size={22} /> : <MessageCircle size={22} />}
        </button>
      </div>

      {isOpen && (
        <div className="agent-panel" role="complementary" aria-label={t('public.title', language)}>
          <div className="agent-panel-header">
            <div className="agent-avatar" aria-hidden="true">N</div>
            <div>
              <div className="agent-name">Nova</div>
              <div className="agent-status-dot">{t('public.title', language)}</div>
            </div>
          </div>

          <div className="agent-messages" role="log" aria-live="polite">
            <div className="message-row system">
              <div className="msg-bubble system">{t('public.notice', language)}</div>
            </div>
            <div className="message-row agent">
              <div className="msg-avatar" aria-hidden="true">N</div>
              <div>
                <div className="msg-bubble agent">
                  <MessageContent role="agent" content={t('public.greeting', language)} />
                </div>
              </div>
            </div>
            {messages.length === 0 && (
              <div className="suggested-actions" role="group">
                {quick.map((key) => (
                  <button key={key} className="suggested-btn" onClick={() => void ask(t(key, language))}>
                    {t(key, language)}
                  </button>
                ))}
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`message-row ${m.role}`}>
                {m.role === 'agent' && <div className="msg-avatar" aria-hidden="true">N</div>}
                <div className={`msg-bubble ${m.role}`}>
                  <MessageContent role={m.role} content={m.content} />
                </div>
                {m.role === 'user' && (
                  <div className="msg-avatar user" aria-hidden="true">{language === 'pt' ? 'Eu' : 'Yo'}</div>
                )}
              </div>
            ))}
            <div ref={endRef} aria-hidden="true" />
          </div>

          <div className="agent-input-area">
            <div className="agent-input-row">
              <textarea
                className="agent-input"
                placeholder={t('public.placeholder', language)}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                rows={1}
                maxLength={api.MAX_TEXT_CHARS}
                disabled={busy}
                aria-label={t('public.placeholder', language)}
              />
              <button
                className="send-btn"
                onClick={() => void ask(input)}
                disabled={!input.trim() || busy}
                aria-label={t('public.send', language)}
              >
                <Send size={15} />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
