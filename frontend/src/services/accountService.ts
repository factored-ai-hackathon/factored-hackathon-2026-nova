// ============================================================
// Account Service — the logged-in customer's real accounts
// (the challenge's synthetic dataset, through the backend),
// mapped to the UI's Account / Transaction types.
// ============================================================

import type { Account, AccountType, Transaction, TransactionCategory, TransactionStatus } from '../types';
import { getOverview, type OverviewProduct, type OverviewTransaction } from '../api/accounts';

export interface AccountsOverview {
  accounts: Account[];
  transactions: Transaction[];
  dataAsOf: string; // YYYY-MM-DD: the dataset's last day
  openComplaints: number;
}

// Product types as the dataset has them.
const ACCOUNT_TYPES: Record<string, AccountType> = {
  'Cuenta Ahorro': 'savings',
  'Cuenta Corriente': 'checking',
  'Tarjeta Crédito': 'credit',
  'Tarjeta Débito': 'debit',
  'Préstamo Personal': 'loan',
  'Préstamo Hipotecario': 'loan',
  'Inversión': 'investment',
  'Seguro': 'insurance',
};

const CATEGORIES: Record<string, TransactionCategory> = {
  Food: 'dining',
  Transport: 'transport',
  Health: 'health',
  Entertainment: 'entertainment',
  Services: 'utilities',
  Other: 'other',
};

const STATUSES: Record<string, TransactionStatus> = {
  Approved: 'completed',
  Pending: 'pending',
  Declined: 'failed',
  Reversed: 'reversed',
};

/** What a transaction with no merchant is called (the dataset's transaction types). */
export const TRANSACTION_TYPE_LABELS: Record<string, { es: string; pt: string }> = {
  Withdrawal: { es: 'Retiro', pt: 'Saque' },
  Transfer: { es: 'Transferencia', pt: 'Transferência' },
  Deposit: { es: 'Depósito', pt: 'Depósito' },
  Purchase: { es: 'Compra', pt: 'Compra' },
  Payment: { es: 'Pago', pt: 'Pagamento' },
  Adjustment: { es: 'Ajuste', pt: 'Ajuste' },
};

export function toAccount(p: OverviewProduct, customerId: string): Account {
  const type = ACCOUNT_TYPES[p.product_type ?? ''] ?? 'checking';
  const balance = p.current_balance ?? 0;
  const available = type === 'credit' && p.credit_limit != null ? p.credit_limit - balance : balance;
  const status = (p.product_status ?? 'Active').toLowerCase() as Account['status'];
  return {
    id: p.product_id,
    customerId,
    type,
    status,
    currency: p.currency ?? 'USD',
    balance: type === 'credit' || type === 'loan' ? -balance : balance,
    availableBalance: Math.max(available, 0),
    number: p.product_number_last4 ? `****${p.product_number_last4}` : '',
    label: p.product_type ?? '',
  };
}

export function toTransaction(t: OverviewTransaction, language: 'es' | 'pt'): Transaction {
  const kind = t.transaction_type ?? '';
  const incoming = kind === 'Deposit';
  const amount = t.amount ?? 0;
  const category: TransactionCategory =
    CATEGORIES[t.transaction_category ?? ''] ??
    (kind === 'Transfer' || kind === 'Deposit' ? 'transfer' : kind === 'Withdrawal' ? 'atm' : 'other');
  return {
    id: `${t.transaction_at}-${t.product_id ?? ''}-${amount}`,
    accountId: t.product_id ?? '',
    merchant: t.merchant_name ?? TRANSACTION_TYPE_LABELS[kind]?.[language] ?? kind,
    amount: incoming ? amount : -amount,
    currency: t.currency ?? 'USD',
    date: t.transaction_at.replace(' ', 'T'), // ISO, so every browser parses it
    status: STATUSES[t.transaction_status ?? ''] ?? 'completed',
    category,
    reference: t.response_code && t.response_code !== '00' ? `code ${t.response_code}` : undefined,
  };
}

export async function loadOverview(
  sessionId: string,
  customerId: string,
  language: 'es' | 'pt',
): Promise<AccountsOverview> {
  const o = await getOverview(sessionId);
  return {
    accounts: o.products.map((p) => toAccount(p, customerId)),
    transactions: o.recent_transactions.map((t) => toTransaction(t, language)),
    dataAsOf: o.data_as_of,
    openComplaints: o.open_complaints,
  };
}
