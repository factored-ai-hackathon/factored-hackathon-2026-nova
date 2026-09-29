// ============================================================
// Agent Service
// Real mode (default): talks to the FastAPI backend through
// src/api/client.ts (contract: docs/api-contract.md) and streams
// the reply token by token.
// Mock mode (VITE_MOCK=1): keyword-based replies, no backend.
// ============================================================

import type {
  Rating,
  AgentChatRequest,
  AgentChatResponse,
  AgentContext,
  Conversation,
  ConversationMessage,
  Intent,
  Sentiment,
} from '../types';
import { mockConversation, mockAgentContext } from '../data/mockData';
import { t } from '../i18n/translations';
import * as api from '../api/client';

const USE_MOCK = import.meta.env.VITE_MOCK === '1';

// Backend session for the current conversation (real mode only)
let sessionId: string | null = null;

// In-memory conversation store (mock only)
let currentConversation: Conversation = { ...mockConversation, messages: [...mockConversation.messages] };

// Simulated agent responses keyed by user intent keywords
const intentMap: Array<{ keywords: string[]; intent: Intent; response: string; sentiment: Sentiment; action: string }> = [
  {
    keywords: ['transacción', 'transacao', 'transação', 'transaction', 'reconozco', 'reconheço', 'cargo', 'cobro', 'desconozco', 'desconheço'],
    intent: 'unknown_transaction',
    response:
      'Entiendo que hay una transacción que no reconoces. Por favor, dime el monto o la fecha aproximada para buscarla en tu cuenta.',
    sentiment: 'concerned',
    action: 'Verificar detalle de la transacción',
  },
  {
    keywords: ['tarjeta', 'cartão', 'cartao', 'rechazada', 'recusado', 'bloqueada', 'bloqueado', 'declinada'],
    intent: 'card_declined',
    response:
      'Lamento que tu tarjeta haya sido rechazada. Puede deberse a un límite de crédito, una restricción de seguridad o un problema técnico. Déjame revisar el estado de tu tarjeta.',
    sentiment: 'concerned',
    action: 'Revisar estado de la tarjeta',
  },
  {
    keywords: ['transferencia', 'transferência', 'transferencia', 'transfer', 'enviei', 'envié', 'chegou', 'llegó'],
    intent: 'transfer_status',
    response:
      'Voy a revisar el estado de tu transferencia. Las transferencias entre cuentas Nova son inmediatas. Las transferencias interbancarias pueden tardar hasta 24 horas hábiles.',
    sentiment: 'neutral',
    action: 'Consultar estado de transferencia',
  },
  {
    keywords: ['saldo', 'quanto tenho', 'quanto tenho', 'cuánto tengo', 'balance', 'disponível', 'disponible'],
    intent: 'balance_inquiry',
    response:
      'Tu saldo disponible en tu Cuenta Corriente ****4521 es de $4.650.320,75 COP. ¿Quieres que te muestre los detalles de tus otras cuentas?',
    sentiment: 'neutral',
    action: 'Mostrar resumen de saldo',
  },
  {
    keywords: ['pago', 'pagar', 'factura', 'servicio', 'problema pago'],
    intent: 'payment_issue',
    response:
      'Entiendo que tienes un problema con un pago. Cuéntame más: ¿es un pago que realizaste y no se procesó, o un cobro que no reconoces?',
    sentiment: 'neutral',
    action: 'Revisar historial de pagos',
  },
  {
    keywords: ['especialista', 'humano', 'persona', 'agente'],
    intent: 'general_inquiry',
    response:
      'Entiendo. Para ayudarte mejor con este caso, puedo transferir la conversación a un especialista de nuestro equipo.',
    sentiment: 'neutral',
    action: 'Preparar escalamiento',
  },
];

function detectIntent(message: string): typeof intentMap[0] | null {
  const lower = message.toLowerCase();
  return intentMap.find((item) => item.keywords.some((kw) => lower.includes(kw))) ?? null;
}

function generateConversationId(): string {
  return `conv-${Date.now()}`;
}

function generateMessageId(): string {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

// Simulates network latency
function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const portugueseResponses: Partial<Record<Intent, { message: string; action: string }>> = {
  unknown_transaction: { message: 'Entendo que há uma transação que você não reconhece. Pode me informar o valor ou a data aproximada para eu localizar na sua conta?', action: 'Verificar os detalhes da transação' },
  card_declined: { message: 'Sinto muito que seu cartão tenha sido recusado. Isso pode acontecer por limite, segurança ou uma falha técnica. Vou ajudar você a verificar.', action: 'Verificar o status do cartão' },
  transfer_status: { message: 'Vou ajudar a verificar sua transferência. Transferências entre contas Nova são imediatas; transferências entre bancos podem levar até 24 horas úteis.', action: 'Consultar o status da transferência' },
  balance_inquiry: { message: 'O saldo disponível na sua conta ****4521 é de $4.650.320 COP. Quer ver o resumo das outras contas?', action: 'Mostrar resumo do saldo' },
  payment_issue: { message: 'Entendo que você está com um problema de pagamento. O pagamento não foi processado ou você não reconhece uma cobrança?', action: 'Verificar o histórico de pagamentos' },
  general_inquiry: { message: 'Para ajudar com este caso, posso transferir a conversa para um especialista da nossa equipe.', action: 'Preparar transferência para especialista' },
};

// ------ Public API -----------------------------------------

/**
 * Send a message to the agent and get a response.
 * In real mode, `onToken` receives the reply text accumulated so far while it streams, and
 * `onNotice` out-of-band messages (the demo SMS with the identity verification code).
 */
export async function sendMessage(
  request: AgentChatRequest,
  onToken?: (textSoFar: string) => void,
  onNotice?: (text: string) => void,
): Promise<AgentChatResponse> {
  return USE_MOCK ? mockSendMessage(request) : backendSendMessage(request, onToken, onNotice);
}

async function backendSendMessage(
  request: AgentChatRequest,
  onToken?: (textSoFar: string) => void,
  onNotice?: (text: string) => void,
): Promise<AgentChatResponse> {
  const text = withTransactionContext(request);
  let reply: { text: string; messageId: string };
  try {
    reply = await streamReply(text, request.language, onToken, onNotice);
  } catch (err) {
    // The backend keeps sessions in memory; after a restart, start a new one once.
    if (!(err instanceof api.ApiError && err.status === 404)) throw err;
    sessionId = null;
    reply = await streamReply(text, request.language, onToken, onNotice);
  }

  // The MVP backend returns only text; intent/sentiment/escalation come later.
  return {
    conversation_id: sessionId!,
    message: reply.text,
    message_id: reply.messageId,
    intent: null,
    sentiment: 'neutral',
    confidence: 0,
    status: 'idle',
    requires_human: false,
    recommended_action: null,
    suggested_actions: [],
  };
}

async function streamReply(
  text: string,
  language: AgentChatRequest['language'],
  onToken?: (textSoFar: string) => void,
  onNotice?: (text: string) => void,
): Promise<{ text: string; messageId: string }> {
  sessionId ??= await api.createSession(language);
  let reply = '';
  for await (const event of api.sendMessage(sessionId, text, language)) {
    if (event.type === 'token') {
      reply += event.text;
      onToken?.(reply);
    } else if (event.type === 'notice') {
      onNotice?.(event.text);
    } else if (event.type === 'error') {
      throw new Error(`agent error: ${event.code}`);
    } else {
      return { text: reply, messageId: event.messageId };
    }
  }
  throw new Error('stream ended without done/error');
}

/**
 * Rate an agent reply. `conversationId` is the backend session. No-op in mock mode.
 */
export async function sendFeedback(conversationId: string, messageId: string, rating: Rating): Promise<void> {
  if (USE_MOCK) return;
  await api.sendFeedback(conversationId, messageId, rating);
}

// The chat API only takes text, so the selected transaction travels as a prefix.
function withTransactionContext(request: AgentChatRequest): string {
  const txn = request.transaction_context;
  if (!txn) return request.message;
  const label = request.language === 'pt' ? 'Transação selecionada' : 'Transacción seleccionada';
  return `[${label}: ${txn.merchant}, ${txn.amount} COP, ${txn.date}]\n${request.message}`;
}

async function mockSendMessage(request: AgentChatRequest): Promise<AgentChatResponse> {
  await delay(800 + Math.random() * 700); // simulate 0.8–1.5 s latency

  const conversationId = request.conversation_id ?? generateConversationId();
  const detected = detectIntent(request.message);

  // Build user message
  const userMessage: ConversationMessage = {
    id: generateMessageId(),
    role: 'user',
    content: request.message,
    timestamp: new Date().toISOString(),
  };

  // Build agent response
  const intent: Intent = detected?.intent ?? 'other';
  const sentiment: Sentiment = detected?.sentiment ?? 'neutral';
  const requiresHuman = intent === 'general_inquiry';
  const portuguese = request.language === 'pt' && detected ? portugueseResponses[detected.intent] : undefined;
  const action = portuguese?.action ?? detected?.action ?? null;
  const agentText = portuguese?.message ?? detected?.response ??
    (request.language === 'pt'
      ? 'Entendi. Estou verificando sua solicitação. Você pode me dar mais detalhes para ajudar?'
      : 'Entendido. Estoy revisando tu consulta. ¿Puedes darme más detalles para ayudarte mejor?');

  const suggestedActions: string[] = requiresHuman
    ? [t('agent.transferToSpecialist', request.language), t('agent.continueWithNova', request.language)]
    : [t('agent.quick.transaction', request.language), t('agent.quick.card', request.language), t('agent.quick.balance', request.language)];

  const agentMessage: ConversationMessage = {
    id: generateMessageId(),
    role: 'agent',
    content: agentText,
    timestamp: new Date().toISOString(),
    suggestedActions,
  };

  // Update in-memory conversation
  if (!currentConversation.id || currentConversation.id !== conversationId) {
    currentConversation = {
      id: conversationId,
      customerId: request.customer_id,
      messages: [currentConversation.messages[0], userMessage, agentMessage],
      agentContext: {
        ...mockAgentContext,
        intent,
        sentiment,
        confidence: detected ? 0.91 : 0.45,
        status: requiresHuman ? 'escalation' : 'resolved',
        recommendedAction: detected?.action ?? null,
        requiresHuman,
        conversationId,
      },
      startedAt: currentConversation.startedAt,
    };
  } else {
    currentConversation.messages.push(userMessage, agentMessage);
    currentConversation.agentContext = {
      ...currentConversation.agentContext,
      intent,
      sentiment,
      confidence: detected ? 0.91 : 0.45,
      status: requiresHuman ? 'escalation' : 'resolved',
      recommendedAction: detected?.action ?? null,
      requiresHuman,
    };
  }

  return {
    conversation_id: conversationId,
    message: agentText,
    intent,
    sentiment,
    confidence: currentConversation.agentContext.confidence,
    status: currentConversation.agentContext.status,
    requires_human: requiresHuman,
    recommended_action: action,
    suggested_actions: suggestedActions,
  };
}

/**
 * Get the current conversation.
 */
export async function getConversation(): Promise<Conversation> {
  await delay(200);
  return { ...currentConversation, messages: [...currentConversation.messages] };
}

/**
 * Get the current agent context (status, intent, sentiment).
 */
export async function getAgentStatus(): Promise<AgentContext> {
  await delay(100);
  return { ...currentConversation.agentContext };
}

/**
 * Reset conversation (e.g. after escalation or resolution).
 */
export function resetConversation(): void {
  sessionId = null;
  currentConversation = {
    ...mockConversation,
    messages: [...mockConversation.messages],
    id: generateConversationId(),
    startedAt: new Date().toISOString(),
  };
}
