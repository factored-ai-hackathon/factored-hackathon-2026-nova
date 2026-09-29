import '@testing-library/jest-dom';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AgentPanel } from '../components/agent/AgentPanel';
import { AgentFAB } from '../components/agent/AgentFAB';
import { ApiError, limitReason } from '../api/client';
import { AllProviders } from './testUtils';

const sendMessage = vi.fn();

vi.mock('../services/agentService', () => ({
  sendMessage: (...args: unknown[]) => sendMessage(...args),
  sendFeedback: vi.fn(),
  resetConversation: vi.fn(),
}));

async function ask() {
  const user = userEvent.setup();
  render(
    <AllProviders>
      <AgentFAB />
      <AgentPanel />
    </AllProviders>
  );
  await user.click(screen.getByLabelText(/abrir asistente nova/i));
  await user.type(screen.getByPlaceholderText(/escribe tu consulta/i), 'Hola');
  await user.click(screen.getByLabelText(/enviar/i));
}

describe('Spend limits', () => {
  it('maps API errors to a limit reason', () => {
    expect(limitReason(new ApiError(429, 'x', 'daily_budget_exhausted'))).toBe('daily_budget_exhausted');
    expect(limitReason(new ApiError(429, 'x', 'rate_limited'))).toBe('rate_limited');
    expect(limitReason(new ApiError(500, 'x'))).toBeNull();
    expect(limitReason(new Error('network'))).toBeNull();
  });

  it('tells the customer when the daily budget is used up', async () => {
    sendMessage.mockRejectedValueOnce(new ApiError(429, 'send message failed: 429', 'daily_budget_exhausted'));
    await ask();
    await waitFor(() => expect(screen.getByText(/límite de uso por hoy/i)).toBeInTheDocument());
  });

  it('tells the customer to slow down when rate limited', async () => {
    sendMessage.mockRejectedValueOnce(new ApiError(429, 'send message failed: 429', 'rate_limited'));
    await ask();
    await waitFor(() => expect(screen.getByText(/muchos mensajes seguidos/i)).toBeInTheDocument());
  });
});
