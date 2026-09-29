import '@testing-library/jest-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AllProviders } from './testUtils';
import { useApp } from '../context/AppContext';
import { useAgent } from '../context/AgentContext';
import { startForCustomer } from '../services/agentService';
import { createSession, sendMessage, type StreamEvent } from '../api/client';
import type { Customer } from '../types';

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return { ...actual, createSession: vi.fn(), sendMessage: vi.fn() };
});

function customer(id: string, name: string, sessionId?: string): Customer {
  return {
    id, name, email: '', phone: '', language: 'es', memberSince: '', status: 'active', segment: 'standard',
    sessionId,
  };
}

// Logs in as a customer and chats, like the login page and the Nova panel do.
function Harness() {
  const { setCustomer } = useApp();
  const { sendMessage: send, resetConversation } = useAgent();
  return (
    <>
      <button onClick={() => setCustomer(customer('C-ANA', 'Ana', 'login-ana'))}>ana</button>
      <button onClick={() => setCustomer(customer('C-LUIS', 'Luis', 'login-luis'))}>luis</button>
      <button onClick={() => setCustomer(customer('C-OLD', 'Old'))}>no-login-session</button>
      <button onClick={() => void send('hola')}>send</button>
      <button onClick={resetConversation}>new</button>
    </>
  );
}

const sessionsUsed = () => vi.mocked(sendMessage).mock.calls.map((call) => call[0]);

describe('chat session of the logged-in customer', () => {
  beforeEach(() => {
    startForCustomer(undefined);
    vi.mocked(createSession).mockReset();
    vi.mocked(createSession).mockImplementation(async (_lang, id) => `new-session-of-${id}`);
    vi.mocked(sendMessage).mockReset();
    vi.mocked(sendMessage).mockImplementation(async function* (): AsyncGenerator<StreamEvent> {
      yield { type: 'token', text: 'ok' };
      yield { type: 'done', messageId: 'm1' };
    });
  });

  it('chats in the session the login created, and switches with the customer', async () => {
    const user = userEvent.setup();
    render(<AllProviders><Harness /></AllProviders>);

    await user.click(screen.getByText('ana'));
    await user.click(screen.getByText('send'));
    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(1));
    await user.click(screen.getByText('send'));
    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(2));
    await user.click(screen.getByText('luis'));
    await user.click(screen.getByText('send'));
    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(3));

    expect(sessionsUsed()).toEqual(['login-ana', 'login-ana', 'login-luis']);
    expect(createSession).not.toHaveBeenCalled(); // the login already created them
  });

  it('a new conversation asks the backend to carry over the login verification', async () => {
    const user = userEvent.setup();
    render(<AllProviders><Harness /></AllProviders>);
    await user.click(screen.getByText('ana'));
    await user.click(screen.getByText('new'));
    await user.click(screen.getByText('send'));
    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(1));
    expect(createSession).toHaveBeenCalledWith('es', 'C-ANA', 'login-ana');
    expect(sessionsUsed()).toEqual(['new-session-of-C-ANA']);
  });

  it('without a login session, creates one bound to the customer', async () => {
    const user = userEvent.setup();
    render(<AllProviders><Harness /></AllProviders>);
    await user.click(screen.getByText('no-login-session'));
    await user.click(screen.getByText('send'));
    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(1));
    expect(createSession).toHaveBeenCalledWith('es', 'C-OLD', undefined);
  });
});
