import '@testing-library/jest-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useEffect } from 'react';
import { AllProviders } from './testUtils';
import { useApp } from '../context/AppContext';
import { DashboardPage } from '../pages/Dashboard/DashboardPage';
import { toAccount, toTransaction } from '../services/accountService';
import { getOverview } from '../api/accounts';
import type { Customer } from '../types';

vi.mock('../api/accounts', () => ({ getOverview: vi.fn() }));

describe('dataset rows to UI types', () => {
  it('maps products: type, masked number, credit available and debt sign', () => {
    const card = toAccount(
      { product_id: 'P1', product_type: 'Tarjeta Crédito', product_number_last4: '2209', currency: 'MXN',
        current_balance: 1500, credit_limit: 10000 },
      'C1',
    );
    expect(card).toMatchObject({ type: 'credit', number: '****2209', balance: -1500, availableBalance: 8500 });
    expect(toAccount({ product_id: 'P2', product_type: 'Préstamo Hipotecario', current_balance: 9 }, 'C1'))
      .toMatchObject({ type: 'loan', balance: -9 });
    expect(toAccount({ product_id: 'P3', product_type: 'Cuenta Ahorro', current_balance: 50 }, 'C1'))
      .toMatchObject({ type: 'savings', balance: 50, availableBalance: 50 });
  });

  it('maps transactions: sign by type, status, category and a name when there is no merchant', () => {
    const declined = toTransaction(
      { transaction_at: '2026-06-12 10:05:00', transaction_type: 'Purchase', transaction_category: 'Food',
        amount: 120, currency: 'MXN', merchant_name: 'Café Luna', transaction_status: 'Declined',
        response_code: '51' },
      'es',
    );
    expect(declined).toMatchObject({
      merchant: 'Café Luna', amount: -120, status: 'failed', category: 'dining', date: '2026-06-12T10:05:00',
    });
    const deposit = toTransaction(
      { transaction_at: '2026-06-01 08:00:00', transaction_type: 'Deposit', amount: 500, transaction_status: 'Approved' },
      'pt',
    );
    expect(deposit).toMatchObject({ merchant: 'Depósito', amount: 500, status: 'completed', category: 'transfer' });
    expect(toTransaction({ transaction_at: '2026-06-01 08:00:00', transaction_type: 'Withdrawal', amount: 20 }, 'es'))
      .toMatchObject({ merchant: 'Retiro', category: 'atm', amount: -20 });
  });
});

function LoggedIn({ customer }: { customer: Customer }) {
  const { setCustomer } = useApp();
  useEffect(() => setCustomer(customer), [customer, setCustomer]);
  return <DashboardPage />;
}

const LUCIA: Customer = {
  id: 'CLI-1', name: 'Lucía', email: '', phone: '', language: 'es', memberSince: '', status: 'active',
  segment: 'standard', sessionId: 'session-1',
};

describe('home page with the real login', () => {
  beforeEach(() => vi.mocked(getOverview).mockReset());

  it("shows the customer's own accounts, transactions and notices, not the mock ones", async () => {
    vi.mocked(getOverview).mockResolvedValue({
      data_as_of: '2026-06-17',
      products: [{ product_id: 'P1', product_type: 'Cuenta Ahorro', product_number_last4: '7777',
                   currency: 'MXN', current_balance: 25000 }],
      recent_transactions: [{ transaction_at: '2026-06-12 10:05:00', transaction_type: 'Purchase',
                              amount: 120, currency: 'MXN', merchant_name: 'Café Luna',
                              transaction_status: 'Declined', response_code: '51' }],
      open_complaints: 2,
    });
    render(<AllProviders><LoggedIn customer={LUCIA} /></AllProviders>);

    expect(await screen.findByText('Cuenta de Ahorros')).toBeInTheDocument();
    expect(getOverview).toHaveBeenCalledWith('session-1');
    expect(screen.getAllByText('****7777').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Café Luna/).length).toBeGreaterThan(0);
    expect(screen.getByText(/datos al/i)).toBeInTheDocument();
    expect(screen.getByText(/2 queja/)).toBeInTheDocument();
    expect(screen.getByText('Pago rechazado')).toBeInTheDocument();
    expect(screen.queryByText('****4521')).not.toBeInTheDocument(); // the mock account
    expect(screen.queryByText(/Netflix/)).not.toBeInTheDocument(); // a mock transaction
  });
});
