import '@testing-library/jest-dom';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useEffect } from 'react';
import { AllProviders } from './testUtils';
import { useApp } from '../context/AppContext';
import { useAgent } from '../context/AgentContext';
import { DashboardPage } from '../pages/Dashboard/DashboardPage';
import { AgentConsolePage } from '../pages/AgentConsole/AgentConsolePage';
import { KEYS, loadStored } from '../utils/persist';
import type { Customer } from '../types';

// A page reload keeps the logged-in customer, their conversation and the human agent console
// signed in, until they log out (or the backend stops accepting the session).

const miguel: Customer = {
  id: 'CLI-1', name: 'Miguel', email: '', phone: '', language: 'es', memberSince: '',
  status: 'active', segment: 'standard', sessionId: 'session-1',
};
const ana: Customer = { ...miguel, id: 'CLI-2', name: 'Ana', sessionId: 'session-2' };

function Probe({ login }: { login?: Customer }) {
  const { customer, setCustomer, logout, language, setLanguage } = useApp();
  const { conversation, openAgent } = useAgent();
  useEffect(() => {
    if (login) setCustomer(login);
  }, [login, setCustomer]);
  return (
    <div>
      <span data-testid="who">{customer?.name ?? 'nobody'}</span>
      <span data-testid="lang">{language}</span>
      <span data-testid="messages">{conversation.messages.length}</span>
      <button onClick={logout}>logout</button>
      <button onClick={() => setLanguage('pt')}>pt</button>
      <button onClick={() => openAgent()}>open</button>
    </div>
  );
}

describe('the customer session survives a reload', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('keeps the logged-in customer and the language', async () => {
    const first = render(<AllProviders><Probe login={miguel} /></AllProviders>);
    await userEvent.click(screen.getByText('pt'));
    expect(screen.getByTestId('who')).toHaveTextContent('Miguel');
    first.unmount(); // the page is reloaded

    render(<AllProviders><Probe /></AllProviders>);
    expect(screen.getByTestId('who')).toHaveTextContent('Miguel');
    expect(screen.getByTestId('lang')).toHaveTextContent('pt');
  });

  it('logging out forgets the customer, the conversation and the chat session', async () => {
    const first = render(<AllProviders><Probe login={miguel} /></AllProviders>);
    await userEvent.click(screen.getByText('logout'));
    expect(screen.getByTestId('who')).toHaveTextContent('nobody');
    first.unmount();

    render(<AllProviders><Probe /></AllProviders>);
    expect(screen.getByTestId('who')).toHaveTextContent('nobody');
    expect(loadStored(KEYS.customer)).toBeNull();
  });

  it('restores the same customer\'s conversation, but never another one\'s', async () => {
    const first = render(<AllProviders><Probe login={miguel} /></AllProviders>);
    await waitFor(() => expect(loadStored(KEYS.chat)).not.toBeNull());
    // A conversation with more messages than the greeting, as the chat would have saved it.
    const saved = loadStored<{ conversation: { messages: unknown[] } }>(KEYS.chat)!;
    const long = { ...saved, conversation: { ...saved.conversation, messages: [...saved.conversation.messages, ...saved.conversation.messages, ...saved.conversation.messages] } };
    sessionStorage.setItem('nb.chat', JSON.stringify(long));
    first.unmount();

    const same = render(<AllProviders><Probe /></AllProviders>);
    expect(screen.getByTestId('messages')).toHaveTextContent('3');
    same.unmount();

    // The customer changed in storage (another login): the old conversation is not shown.
    sessionStorage.setItem('nb.customer', JSON.stringify(ana));
    render(<AllProviders><Probe /></AllProviders>);
    expect(screen.getByTestId('who')).toHaveTextContent('Ana');
    expect(screen.getByTestId('messages')).toHaveTextContent('1');
  });

  it('goes back to the login when the backend no longer accepts the session', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{"detail":"not_verified"}', { status: 401 })));
    function Both() {
      return (<><Probe login={miguel} /><DashboardPage /></>);
    }
    render(<AllProviders><Both /></AllProviders>);
    await waitFor(() => expect(screen.getByTestId('who')).toHaveTextContent('nobody'));
    expect(loadStored(KEYS.customer)).toBeNull();
  });
});

describe('the human agent console survives a reload', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('stays signed in until the agent logs out', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ cases: [], stats: { waiting: 0, active: 0, closed: 0, faithfulness_avg: null } }), { status: 200 })
    );
    vi.stubGlobal('fetch', fetchMock);
    const first = render(<AllProviders><AgentConsolePage /></AllProviders>);
    await userEvent.type(screen.getByLabelText(/clave/i), 'Asesor2026');
    await userEvent.click(screen.getByRole('button', { name: /entrar|ingresar/i }));
    expect(await screen.findByText(/cerrar sesión|salir/i)).toBeInTheDocument();
    first.unmount(); // reload

    render(<AllProviders><AgentConsolePage /></AllProviders>);
    const logout = await screen.findByText(/cerrar sesión|salir/i);
    expect(screen.queryByLabelText(/clave/i)).not.toBeInTheDocument();
    await userEvent.click(logout);
    expect(await screen.findByLabelText(/clave/i)).toBeInTheDocument();
    expect(loadStored(KEYS.console)).toBeNull();
  });

  it('asks for the key again if it no longer works', async () => {
    sessionStorage.setItem('nb.console', JSON.stringify({ key: 'old', agentName: '' }));
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{"detail":"invalid_key"}', { status: 401 })));
    render(<AllProviders><AgentConsolePage /></AllProviders>);
    expect(await screen.findByLabelText(/clave/i)).toBeInTheDocument();
    await waitFor(() => expect(loadStored(KEYS.console)).toBeNull());
  });
});
