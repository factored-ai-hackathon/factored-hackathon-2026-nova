import '@testing-library/jest-dom';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AgentPanel } from '../components/agent/AgentPanel';
import { AgentFAB } from '../components/agent/AgentFAB';
import { AllProviders } from './testUtils';

vi.mock('../services/agentService', () => ({
  sendMessage: vi.fn(async (_request, onToken, onNotice) => {
    onToken?.('Te enviamos un código de 6 dígitos por SMS.');
    onNotice?.('SMS (demo) al celular terminado en 0192: tu código de verificación NovaBank es 123456');
    return {
      conversation_id: 'session-1',
      message: 'Te enviamos un código de 6 dígitos por SMS.',
      message_id: 'm-1',
      intent: null,
      sentiment: 'neutral',
      confidence: 0,
      status: 'idle',
      requires_human: false,
      recommended_action: null,
      suggested_actions: [],
    };
  }),
  sendFeedback: vi.fn(),
  resetConversation: vi.fn(),
}));

describe('Identity verification notices', () => {
  it('shows the demo SMS as a system message in the chat', async () => {
    const user = userEvent.setup();
    render(
      <AllProviders>
        <AgentFAB />
        <AgentPanel />
      </AllProviders>
    );
    await user.click(screen.getByLabelText(/abrir asistente nova/i));
    await user.type(screen.getByPlaceholderText(/escribe tu consulta/i), '14/05/1990');
    await user.click(screen.getByLabelText(/enviar/i));
    await waitFor(() => expect(screen.getByText(/SMS \(demo\).*123456/)).toBeInTheDocument());
    expect(screen.getByText(/Te enviamos un código/)).toBeInTheDocument();
  });
});
