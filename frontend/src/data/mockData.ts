// ============================================================
// NovaBank – Mock data layer
// All demo/fake data lives here.
// Replace this layer with real API calls when backend is ready.
// ============================================================

import type {
  Customer,
  Account,
  Card,
  Transaction,
  Conversation,
  AgentContext,
  ConversationMessage,
} from '../types';

// ------ Customer -------------------------------------------

export const mockCustomer: Customer = {
  id: 'demo-001',
  name: 'Miguel Ramírez',
  email: 'miguel.ramirez@demo.novabank.lat',
  phone: '+57 310 555 0192',
  language: 'es',
  memberSince: '2021-03-15',
  status: 'active',
  segment: 'premium',
};

// ------ Accounts -------------------------------------------

export const mockAccounts: Account[] = [
  {
    id: 'acc-001',
    customerId: 'demo-001',
    type: 'checking',
    currency: 'COP',
    balance: 4_850_320.75,
    availableBalance: 4_650_320.75,
    number: '****4521',
    label: 'Cuenta Corriente',
  },
  {
    id: 'acc-002',
    customerId: 'demo-001',
    type: 'savings',
    currency: 'COP',
    balance: 12_300_000.0,
    availableBalance: 12_300_000.0,
    number: '****8832',
    label: 'Cuenta de Ahorros',
  },
  {
    id: 'acc-003',
    customerId: 'demo-001',
    type: 'credit',
    currency: 'COP',
    balance: -1_245_800.0,
    availableBalance: 8_754_200.0,
    number: '****2209',
    label: 'Tarjeta de Crédito',
  },
];

// ------ Cards ----------------------------------------------

export const mockCards: Card[] = [
  {
    id: 'card-001',
    customerId: 'demo-001',
    accountId: 'acc-001',
    type: 'debit',
    network: 'visa',
    number: '****4521',
    expiryDate: '08/28',
    status: 'active',
  },
  {
    id: 'card-002',
    customerId: 'demo-001',
    accountId: 'acc-003',
    type: 'credit',
    network: 'mastercard',
    number: '****2209',
    expiryDate: '11/27',
    status: 'active',
    creditLimit: 10_000_000,
    availableCredit: 8_754_200,
  },
];

// ------ Transactions ---------------------------------------

export const mockTransactions: Transaction[] = [
  {
    id: 'txn-001',
    accountId: 'acc-001',
    merchant: 'Supermercado Central',
    amount: -245_500,
    currency: 'COP',
    date: '2026-09-24T14:32:00Z',
    status: 'completed',
    category: 'groceries',
    reference: 'REF20260924001',
  },
  {
    id: 'txn-002',
    accountId: 'acc-001',
    merchant: 'Netflix',
    amount: -47_900,
    currency: 'COP',
    date: '2026-09-23T09:00:00Z',
    status: 'completed',
    category: 'entertainment',
    reference: 'REF20260923002',
  },
  {
    id: 'txn-003',
    accountId: 'acc-001',
    merchant: 'Transferencia recibida - Ana Torres',
    amount: 500_000,
    currency: 'COP',
    date: '2026-09-22T16:45:00Z',
    status: 'completed',
    category: 'transfer',
    reference: 'TRF20260922001',
  },
  {
    id: 'txn-004',
    accountId: 'acc-001',
    merchant: 'Rappi',
    amount: -89_000,
    currency: 'COP',
    date: '2026-09-21T20:15:00Z',
    status: 'completed',
    category: 'dining',
    reference: 'REF20260921004',
  },
  {
    id: 'txn-005',
    accountId: 'acc-001',
    merchant: 'Comercio XYZ Online',
    amount: -312_000,
    currency: 'COP',
    date: '2026-09-20T11:00:00Z',
    status: 'disputed',
    category: 'online',
    description: 'Transacción no reconocida por el cliente',
    reference: 'REF20260920005',
  },
  {
    id: 'txn-006',
    accountId: 'acc-001',
    merchant: 'Farmacia Cruz Verde',
    amount: -67_500,
    currency: 'COP',
    date: '2026-09-19T13:22:00Z',
    status: 'completed',
    category: 'health',
    reference: 'REF20260919006',
  },
  {
    id: 'txn-007',
    accountId: 'acc-001',
    merchant: 'TransMilenio Recarga',
    amount: -100_000,
    currency: 'COP',
    date: '2026-09-18T08:00:00Z',
    status: 'completed',
    category: 'transport',
    reference: 'REF20260918007',
  },
];

// ------ Agent Initial State --------------------------------

export const mockAgentContext: AgentContext = {
  intent: null,
  sentiment: 'neutral',
  confidence: 0,
  status: 'idle',
  recommendedAction: null,
  requiresHuman: false,
  conversationId: null,
};

// ------ Mock Conversation (demo) ---------------------------

export const mockInitialAgentMessage: ConversationMessage = {
  id: 'msg-000',
  role: 'agent',
  content:
    'Hola Miguel 👋 Soy Nova, tu asistente bancario. ¿En qué puedo ayudarte hoy?',
  timestamp: new Date().toISOString(),
  suggestedActions: [
    'No reconozco una transacción',
    '¿Dónde está mi transferencia?',
    'Mi tarjeta fue rechazada',
    'Quiero conocer mi saldo',
    'Tengo un problema con mi pago',
  ],
};

export const mockConversation: Conversation = {
  id: 'conv-001',
  customerId: 'demo-001',
  messages: [mockInitialAgentMessage],
  agentContext: mockAgentContext,
  startedAt: new Date().toISOString(),
};
