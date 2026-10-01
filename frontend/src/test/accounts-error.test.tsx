import '@testing-library/jest-dom';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useEffect } from 'react';
import { AllProviders } from './testUtils';
import { useApp } from '../context/AppContext';
import { DashboardPage } from '../pages/Dashboard/DashboardPage';
import type { Customer } from '../types';

// Separate file: the backend answers with an error (real fetch path, no module mock).
// A 401 is different: the session expired, and the customer goes back to the login (see
// session-persistence.test.tsx).

function LoggedIn({ customer }: { customer: Customer }) {
  const { setCustomer } = useApp();
  useEffect(() => setCustomer(customer), [customer, setCustomer]);
  return <DashboardPage />;
}

describe('home page when the accounts cannot be loaded', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('says so, without showing mock data', async () => {
    const fetchMock = vi.fn(async () => new Response('{"detail":"boom"}', { status: 500 }));
    vi.stubGlobal('fetch', fetchMock);
    const customer: Customer = {
      id: 'CLI-1', name: 'Lucía', email: '', phone: '', language: 'es', memberSince: '',
      status: 'active', segment: 'standard', sessionId: 'session-1',
    };
    render(<AllProviders><LoggedIn customer={customer} /></AllProviders>);
    expect(await screen.findByText(/no pudimos cargar/i)).toHaveAttribute('role', 'alert');
    expect(fetchMock).toHaveBeenCalledWith('/v1/accounts/overview', expect.objectContaining({ method: 'POST' }));
    expect(screen.queryByText('****4521')).not.toBeInTheDocument();
  });
});
