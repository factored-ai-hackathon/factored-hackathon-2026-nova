// ============================================================
// Agent Context — manages conversation state
// ============================================================

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from 'react';
import type { Conversation, ConversationMessage, Rating, Transaction, AgentChatRequest } from '../types';
import { mockConversation, mockInitialAgentMessage } from '../data/mockData';
import * as agentService from '../services/agentService';
import { limitReason } from '../api/client';
import { useApp } from './AppContext';
import { t } from '../i18n/translations';
import { KEYS, loadStored, saveStored } from '../utils/persist';

interface AgentContextValue {
  isOpen: boolean;
  isFullView: boolean;
  conversation: Conversation;
  isTyping: boolean;
  /** True once the first token of the reply has arrived (the reply is visible). */
  isStreaming: boolean;
  openAgent: (txn?: Transaction) => void;
  closeAgent: () => void;
  openFullView: () => void;
  closeFullView: () => void;
  sendMessage: (text: string, transaction?: Transaction) => Promise<void>;
  resetConversation: () => void;
  handoff: HandoffState | null;
  rateMessage: (messageId: string, rating: Rating) => Promise<void>;
}

const AgentCtx = createContext<AgentContextValue | null>(null);

/** A human agent took over the conversation (decision 27). */
export interface HandoffState {
  caseId: string;
  status: 'waiting' | 'active' | 'closed';
  agentName: string | null;
  next: number; // case messages already received
}

const POLL_MS = 3000;
const MAX_STORED_MESSAGES = 60;

/** What survives a page reload: the conversation on screen, an open handoff, the panel. */
interface StoredChat {
  customerId: string | null;
  conversation: Conversation;
  handoff: HandoffState | null;
  isOpen: boolean;
}

function restoredChat(customerId: string | undefined): StoredChat | null {
  const stored = loadStored<StoredChat>(KEYS.chat);
  // Only the same customer's conversation: another login starts clean.
  return stored && stored.customerId === (customerId ?? null) ? stored : null;
}

function freshConversation(language: 'es' | 'pt', customerName = 'Miguel Ramírez'): Conversation {
  const firstName = customerName.split(' ')[0];
  return {
    ...mockConversation,
    messages: [{
      ...mockInitialAgentMessage,
      content: `${t('agent.greetingPrefix', language)} ${firstName} 👋 ${t('agent.greeting', language)}`,
      suggestedActions: [
        t('agent.quick.transaction', language),
        t('agent.quick.transfer', language),
        t('agent.quick.card', language),
        t('agent.quick.balance', language),
        t('agent.quick.payment', language),
      ],
      timestamp: new Date().toISOString(),
    }],
    startedAt: new Date().toISOString(),
  };
}

export function AgentProvider({ children }: { children: ReactNode }) {
  const { customer, language } = useApp();
  const [restored] = useState(() => restoredChat(customer?.id));
  const [isOpen, setIsOpen] = useState(restored?.isOpen ?? false);
  const [isFullView, setIsFullView] = useState(false);
  const [conversation, setConversation] = useState<Conversation>(
    () => restored?.conversation ?? freshConversation(language, customer?.name)
  );
  const [isTyping, setIsTyping] = useState(false);
  const [handoff, setHandoff] = useState<HandoffState | null>(restored?.handoff ?? null);

  // Keep it for a reload (a human agent's case keeps being polled from where it was).
  useEffect(() => {
    saveStored(KEYS.chat, {
      customerId: customer?.id ?? null,
      conversation: { ...conversation, messages: conversation.messages.slice(-MAX_STORED_MESSAGES) },
      handoff,
      isOpen,
    } satisfies StoredChat);
  }, [conversation, handoff, isOpen, customer?.id]);
  const [isStreaming, setIsStreaming] = useState(false);
  const transactionContext = conversation.agentContext.transactionContext;

  const conversationForDisplay = conversation.messages.length === 1 && conversation.agentContext.status === 'idle'
    ? {
        ...conversation,
        messages: [{
          ...conversation.messages[0],
          content: `${t('agent.greetingPrefix', language)} ${customer?.name.split(' ')[0] ?? 'Miguel'} 👋 ${t('agent.greeting', language)}`,
          suggestedActions: [
            t('agent.quick.transaction', language),
            t('agent.quick.transfer', language),
            t('agent.quick.card', language),
            t('agent.quick.balance', language),
            t('agent.quick.payment', language),
          ],
        }],
      }
    : conversation;

  const openAgent = useCallback((txn?: Transaction) => {
    if (txn) {
      // Inject transaction context into conversation as a system message
      const contextMsg = {
        id: `msg-ctx-${Date.now()}`,
        role: 'system' as const,
        content: `${t('agent.transactionContext', language)} ${txn.merchant} — ${new Intl.NumberFormat(language === 'pt' ? 'pt-BR' : 'es-CO').format(Math.abs(txn.amount))} COP · ${new Date(txn.date).toLocaleDateString(language === 'pt' ? 'pt-BR' : 'es-CO')}.`,
        timestamp: new Date().toISOString(),
      };
      setConversation((prev) => ({
        ...prev,
        agentContext: { ...prev.agentContext, transactionContext: txn },
        messages: [...prev.messages, contextMsg],
      }));
    }
    setIsOpen(true);
  }, [language]);

  const closeAgent = useCallback(() => {
    setIsOpen(false);
    setIsFullView(false);
  }, []);

  const openFullView = useCallback(() => {
    setIsOpen(false);
    setIsFullView(true);
  }, []);

  const closeFullView = useCallback(() => {
    setIsFullView(false);
  }, []);

  const sendMessage = useCallback(
    async (text: string, transaction?: Transaction) => {
      if (!text.trim()) return;

      const activeTransaction = transaction ?? transactionContext;
      const userMsg = {
        id: `msg-u-${Date.now()}`,
        role: 'user' as const,
        content: text,
        timestamp: new Date().toISOString(),
      };

      setConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, userMsg],
        agentContext: { ...prev.agentContext, status: 'understanding' },
      }));
      setIsTyping(true);

      try {
        const request: AgentChatRequest = {
          customer_id: customer?.id ?? '', // empty: a session not bound to a customer
          message: text,
          conversation_id: conversation.id,
          language,
          ...(activeTransaction ? {
            transaction_context: {
              transaction_id: activeTransaction.id,
              merchant: activeTransaction.merchant,
              amount: activeTransaction.amount,
              date: activeTransaction.date,
            },
          } : {}),
        };

        // Replace the streaming reply in place, or append it the first time.
        const agentMsgId = `msg-a-${Date.now()}`;
        const withAgentMsg = (messages: ConversationMessage[], agentMsg: ConversationMessage) =>
          messages.some((m) => m.id === agentMsgId)
            ? messages.map((m) => (m.id === agentMsgId ? agentMsg : m))
            : [...messages, agentMsg];

        const response = await agentService.sendMessage(request, (textSoFar) => {
          setIsStreaming(true);
          setConversation((prev) => ({
            ...prev,
            messages: withAgentMsg(prev.messages, {
              id: agentMsgId,
              role: 'agent',
              content: textSoFar,
              timestamp: new Date().toISOString(),
            }),
            agentContext: { ...prev.agentContext, status: 'responding' },
          }));
        }, (noticeText, kind) => {
          if (kind === 'handoff') {
            // Handed over to a human: the reply already says so; start listening for the agent.
            setHandoff({ caseId: noticeText, status: 'waiting', agentName: null, next: 0 });
            return;
          }
          // e.g. the demo SMS with the verification code, shown as a system message
          setConversation((prev) => ({
            ...prev,
            messages: [...prev.messages, {
              id: `msg-notice-${Date.now()}`,
              role: 'system',
              content: `📱 ${noticeText}`,
              timestamp: new Date().toISOString(),
            }],
          }));
        });

        const agentMsg: ConversationMessage = {
          id: agentMsgId,
          role: 'agent',
          content: response.message,
          timestamp: new Date().toISOString(),
          suggestedActions: response.suggested_actions,
          serverMessageId: response.message_id,
        };

        setConversation((prev) => ({
          ...prev,
          id: response.conversation_id,
          // With a human agent on the case the bot doesn't answer: no empty bubble.
          messages: response.message
            ? withAgentMsg(prev.messages, agentMsg)
            : prev.messages.filter((m) => m.id !== agentMsgId),
          agentContext: {
            intent: response.intent,
            sentiment: response.sentiment,
            confidence: response.confidence,
            status: response.status,
            recommendedAction: response.recommended_action,
            requiresHuman: response.requires_human,
            conversationId: response.conversation_id,
            transactionContext: activeTransaction,
          },
        }));
      } catch (err) {
        const reason = limitReason(err);
        const errorKey =
          reason === 'daily_budget_exhausted' ? 'agent.limit.budget'
          : reason === 'rate_limited' ? 'agent.limit.rate'
          : 'agent.error';
        setConversation((prev) => ({
          ...prev,
          messages: [...prev.messages, {
            id: `msg-error-${Date.now()}`,
            role: 'agent',
            content: t(errorKey, language),
            timestamp: new Date().toISOString(),
          }],
          agentContext: { ...prev.agentContext, status: 'action_required' },
        }));
      } finally {
        setIsTyping(false);
        setIsStreaming(false);
      }
    },
    [customer, language, conversation.id, transactionContext]
  );

  // Another customer logged in (or logged out): the chat session belonged to the previous one.
  const customerId = customer?.id;
  const previousCustomerId = useRef(customerId);
  useEffect(() => {
    if (previousCustomerId.current === customerId) return;
    previousCustomerId.current = customerId;
    agentService.startForCustomer(customer?.sessionId);
    setConversation(freshConversation(language, customer?.name));
    setHandoff(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a customer change resets
  }, [customerId]);

  // After a handoff: poll for the human agent's messages until the case closes.
  const handoffOpen = handoff !== null && handoff.status !== 'closed';
  const handoffNext = handoff?.next ?? 0;
  useEffect(() => {
    if (!handoffOpen) return;
    const timer = setTimeout(async () => {
      try {
        const update = await agentService.pollHandoff(handoffNext);
        if (!update || update.status === 'none') return;
        if (update.messages.length) {
          setConversation((prev) => ({
            ...prev,
            messages: [
              ...prev.messages,
              ...update.messages.map((m, i) => ({
                id: `msg-h-${update.next}-${i}`,
                role: m.from === 'agent' ? ('human' as const) : ('system' as const),
                content: m.text,
                timestamp: m.at,
                author: m.from === 'agent' ? (update.agent_name ?? undefined) : undefined,
              })),
            ],
          }));
        }
        setHandoff({
          caseId: update.case_id ?? '',
          status: update.status as HandoffState['status'],
          agentName: update.agent_name,
          next: update.next,
        });
      } catch {
        // Try again on the next tick: a missed poll only delays the agent's message.
        setHandoff((prev) => (prev ? { ...prev } : prev));
      }
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [handoffOpen, handoffNext, handoff]);

  const resetConversation = useCallback(() => {
    agentService.resetConversation();
    setConversation(freshConversation(language, customer?.name));
    setHandoff(null);
    setIsTyping(false);
    setIsStreaming(false);
  }, [customer?.name, language]);

  const rateMessage = useCallback(
    async (messageId: string, rating: Rating) => {
      const message = conversation.messages.find((m) => m.id === messageId);
      if (!message?.serverMessageId) return;
      const setFeedback = (feedback: Rating | undefined) =>
        setConversation((prev) => ({
          ...prev,
          messages: prev.messages.map((m) => (m.id === messageId ? { ...m, feedback } : m)),
        }));
      const previous = message.feedback;
      setFeedback(rating); // optimistic
      try {
        await agentService.sendFeedback(conversation.id, message.serverMessageId, rating);
      } catch (err) {
        console.error(err);
        setFeedback(previous);
      }
    },
    [conversation.id, conversation.messages]
  );

  return (
    <AgentCtx.Provider
      value={{
        isOpen,
        isFullView,
        conversation: conversationForDisplay,
        isTyping,
        isStreaming,
        openAgent,
        closeAgent,
        openFullView,
        closeFullView,
        sendMessage,
        resetConversation,
        handoff,
        rateMessage,
      }}
    >
      {children}
    </AgentCtx.Provider>
  );
}

export function useAgent(): AgentContextValue {
  const ctx = useContext(AgentCtx);
  if (!ctx) throw new Error('useAgent must be used within AgentProvider');
  return ctx;
}
