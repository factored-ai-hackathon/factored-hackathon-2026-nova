import '@testing-library/jest-dom';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AgentPanel } from '../components/agent/AgentPanel';
import { AgentFAB } from '../components/agent/AgentFAB';
import { AllProviders } from './testUtils';

const sendFeedback = vi.fn().mockResolvedValue(undefined);

vi.mock('../services/agentService', () => ({
  sendMessage: vi.fn().mockResolvedValue({
    conversation_id: 'session-1',
    message: 'Claro, te ayudo con eso.',
    message_id: 'msg-server-1',
    intent: null,
    sentiment: 'neutral',
    confidence: 0,
    status: 'idle',
    requires_human: false,
    recommended_action: null,
    suggested_actions: [],
  }),
  sendFeedback: (...args: unknown[]) => sendFeedback(...args),
  resetConversation: vi.fn(),
}));

describe('Feedback on agent replies', () => {
  it('rates a backend reply and sends its message_id', async () => {
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
    await waitFor(() => expect(screen.getByText(/te ayudo con eso/i)).toBeInTheDocument());

    // Only the backend reply can be rated, not the local greeting.
    const up = screen.getByRole('button', { name: /respuesta útil/i });
    await user.click(up);

    expect(sendFeedback).toHaveBeenCalledWith('session-1', 'msg-server-1', 'up');
    expect(up).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/gracias por tu opinión/i)).toBeInTheDocument();
  });
});
