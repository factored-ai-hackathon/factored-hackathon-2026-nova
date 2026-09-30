import '@testing-library/jest-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PublicAssistant } from '../components/agent/PublicAssistant';
import { LoginPage } from '../pages/Login/LoginPage';
import { ApiError } from '../api/client';
import { AllProviders } from './testUtils';

const createPublicSession = vi.fn();
const sendMessage = vi.fn();

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  createPublicSession: (...args: unknown[]) => createPublicSession(...args),
  sendMessage: (...args: unknown[]) => sendMessage(...args),
}));

async function* reply(...texts: string[]) {
  for (const text of texts) yield { type: 'token' as const, text };
  yield { type: 'done' as const, messageId: 'm1' };
}

beforeEach(() => {
  createPublicSession.mockReset().mockResolvedValue('public-session');
  sendMessage.mockReset();
});

function renderAssistant() {
  render(
    <AllProviders>
      <PublicAssistant />
    </AllProviders>
  );
}

describe('Public assistant (outside the login)', () => {
  it('is on the login page', () => {
    render(
      <AllProviders>
        <LoginPage />
      </AllProviders>
    );
    expect(screen.getByLabelText(/abrir asistente de información/i)).toBeInTheDocument();
  });

  it('says what it can and cannot do before any question', async () => {
    renderAssistant();
    await userEvent.click(screen.getByLabelText(/abrir asistente de información/i));
    expect(screen.getByText(/no tiene acceso a datos de cuentas/i)).toBeInTheDocument();
    expect(screen.getByText(/cuáles son los horarios/i)).toBeInTheDocument();
  });

  it('streams the answer from the public endpoints, without a customer', async () => {
    sendMessage.mockImplementation(() => reply('Abrimos ', 'a las 9.'));
    renderAssistant();
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/abrir asistente de información/i));
    await user.type(screen.getByPlaceholderText(/escribe tu pregunta/i), 'Horarios?');
    await user.click(screen.getByLabelText(/^enviar$/i));

    await waitFor(() => expect(screen.getByText('Abrimos a las 9.')).toBeInTheDocument());
    expect(createPublicSession).toHaveBeenCalledWith('es');
    expect(sendMessage).toHaveBeenCalledWith(
      'public-session', 'Horarios?', 'es', undefined, '/v1/public/chat'
    );
  });

  it('quick questions send themselves', async () => {
    sendMessage.mockImplementation(() => reply('Hola'));
    renderAssistant();
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/abrir asistente de información/i));
    await user.click(screen.getByText(/no tengo cuenta, ¿cómo abro una/i));
    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(1));
    expect(sendMessage.mock.calls[0][1]).toMatch(/no tengo cuenta/i);
  });

  it('tells the visitor when limits are hit', async () => {
    sendMessage.mockImplementation(() => {
      throw new ApiError(429, 'send message failed: 429', 'rate_limited');
    });
    renderAssistant();
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/abrir asistente de información/i));
    await user.type(screen.getByPlaceholderText(/escribe tu pregunta/i), 'Hola');
    await user.click(screen.getByLabelText(/^enviar$/i));
    await waitFor(() => expect(screen.getByText(/muchos mensajes seguidos/i)).toBeInTheDocument());
  });
});
