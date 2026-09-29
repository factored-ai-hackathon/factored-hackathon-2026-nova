// ============================================================
// NovaBank – Shared TypeScript types
// These types form the contract between UI, mock services,
// and the eventual backend agent API.
// ============================================================

// ------ Customer & Banking --------------------------------

export type Language = 'es' | 'pt';

export interface Customer {
  id: string;
  name: string;
  email: string;
  phone: string;
  language: Language;
  memberSince: string; // ISO date string
  status: 'active' | 'blocked' | 'suspended';
  segment: 'standard' | 'premium' | 'vip';
  country?: string;
  documentType?: string;
  documentLast4?: string;
  /** Chat session created by the login, already verified for this customer (real mode only). */
  sessionId?: string;
}

export type AccountType =
  | 'checking'
  | 'savings'
  | 'credit'
  | 'debit'
  | 'loan'
  | 'investment'
  | 'insurance';

export interface Account {
  id: string;
  customerId: string;
  type: AccountType;
  status?: 'active' | 'blocked' | 'closed' | 'suspended';
  currency: string;
  balance: number;
  availableBalance: number;
  number: string; // masked, e.g. "****4521"
  label: string;
}

export interface Card {
  id: string;
  customerId: string;
  accountId: string;
  type: 'debit' | 'credit';
  network: 'visa' | 'mastercard';
  number: string; // masked, e.g. "****8832"
  expiryDate: string; // "MM/YY"
  status: 'active' | 'blocked' | 'expired';
  creditLimit?: number;
  availableCredit?: number;
}

export type TransactionCategory =
  | 'groceries'
  | 'dining'
  | 'transport'
  | 'utilities'
  | 'entertainment'
  | 'health'
  | 'education'
  | 'transfer'
  | 'atm'
  | 'online'
  | 'other';

export type TransactionStatus = 'completed' | 'pending' | 'failed' | 'disputed' | 'reversed';

export interface Transaction {
  id: string;
  accountId: string;
  merchant: string;
  amount: number; // negative = debit, positive = credit
  currency: string;
  date: string; // ISO date string
  status: TransactionStatus;
  category: TransactionCategory;
  description?: string;
  reference?: string;
}

// ------ AI Agent ------------------------------------------

export type Sentiment = 'satisfied' | 'neutral' | 'concerned' | 'frustrated' | 'angry';

export type Intent =
  | 'unknown_transaction'
  | 'card_declined'
  | 'transfer_status'
  | 'balance_inquiry'
  | 'payment_issue'
  | 'dispute'
  | 'general_inquiry'
  | 'account_blocked'
  | 'other';

export type AgentStatus =
  | 'idle'
  | 'understanding'
  | 'responding'
  | 'action_required'
  | 'resolved'
  | 'escalation';

export interface AgentContext {
  intent: Intent | null;
  sentiment: Sentiment;
  confidence: number; // 0–1
  status: AgentStatus;
  recommendedAction: string | null;
  requiresHuman: boolean;
  conversationId: string | null;
  transactionContext?: Transaction; // context injected from banking UI
}

export type MessageRole = 'user' | 'agent' | 'system';

export type Rating = 'up' | 'down';

export interface ConversationMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string; // ISO datetime string
  suggestedActions?: string[];
  serverMessageId?: string; // backend message_id, needed to send feedback
  feedback?: Rating;
}

export interface Conversation {
  id: string;
  customerId: string;
  messages: ConversationMessage[];
  agentContext: AgentContext;
  startedAt: string;
  endedAt?: string;
}

// ------ API Contract (documented for backend team) --------
// See docs/frontend-agent-api-contract.md for full details.

export interface AgentChatRequest {
  customer_id: string;
  message: string;
  conversation_id: string | null;
  language: Language;
  transaction_context?: {
    transaction_id: string;
    merchant: string;
    amount: number;
    date: string;
  };
}

export interface AgentChatResponse {
  conversation_id: string;
  message: string;
  intent: Intent | null;
  sentiment: Sentiment;
  confidence: number;
  status: AgentStatus;
  requires_human: boolean;
  recommended_action: string | null;
  suggested_actions: string[];
  message_id?: string; // absent in mock mode
}
