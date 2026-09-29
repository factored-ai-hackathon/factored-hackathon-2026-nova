// ============================================================
// Agent Context — manages conversation state
// ============================================================

import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react';
import type { Conversation, ConversationMessage, Rating, Transaction, AgentChatRequest } from '../types';
import { mockConversation, mockInitialAgentMessage } from '../data/mockData';
import * as agentService from '../services/agentService';
import { limitReason } from '../api/client';
import { useApp } from './AppContext';
import { t } from '../i18n/translations';

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
  rateMessage: (messageId: string, rating: Rating) => Promise<void>;
}

const AgentCtx = createContext<AgentContextValue | null>(null);

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
  const [isOpen, setIsOpen] = useState(false);
  const [isFullView, setIsFullView] = useState(false);
  const [conversation, setConversation] = useState<Conversation>(() =>
    freshConversation(language, customer?.name)
  );
  const [isTyping, setIsTyping] = useState(false);
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
          customer_id: customer?.id ?? 'demo-001',
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
        }, (noticeText) => {
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
          messages: withAgentMsg(prev.messages, agentMsg),
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

  const resetConversation = useCallback(() => {
    agentService.resetConversation();
    setConversation(freshConversation(language, customer?.name));
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
