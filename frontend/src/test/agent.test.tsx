import '@testing-library/jest-dom';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AgentPanel } from '../components/agent/AgentPanel';
import { AgentFAB } from '../components/agent/AgentFAB';
import { AllProviders } from './testUtils';

// Mock the agent service to control responses
vi.mock('../services/agentService', () => ({
  sendMessage: vi.fn().mockResolvedValue({
    conversation_id: 'conv-test-001',
    message: 'Entiendo que hay una transacción que no reconoces.',
    intent: 'unknown_transaction',
    sentiment: 'concerned',
    confidence: 0.92,
    status: 'resolved',
    requires_human: false,
    recommended_action: 'Verificar transacción',
    suggested_actions: ['Ver detalle', 'Continuar con Nova'],
  }),
  getConversation: vi.fn(),
  getAgentStatus: vi.fn(),
  resetConversation: vi.fn(),
}));

describe('Agent FAB and panel', () => {
  it('renders the FAB button', () => {
    render(
      <AllProviders>
        <AgentFAB />
      </AllProviders>
    );
    expect(screen.getByLabelText(/abrir asistente nova/i)).toBeInTheDocument();
  });

  it('opens the agent panel when FAB is clicked', async () => {
    const user = userEvent.setup();
    render(
      <AllProviders>
        <AgentFAB />
        <AgentPanel />
      </AllProviders>
    );
    const fabBtn = screen.getByLabelText(/abrir asistente nova/i);
    await user.click(fabBtn);
    await waitFor(() => {
      expect(screen.getByRole('complementary', { name: /nova/i })).toBeInTheDocument();
    });
  });

  it('shows initial greeting message from Nova', async () => {
    const user = userEvent.setup();
    render(
      <AllProviders>
        <AgentFAB />
        <AgentPanel />
      </AllProviders>
    );
    await user.click(screen.getByLabelText(/abrir asistente nova/i));
    expect(screen.getByText(/hola miguel/i)).toBeInTheDocument();
  });

  it('sends a message and displays agent response', async () => {
    const user = userEvent.setup();
    render(
      <AllProviders>
        <AgentFAB />
        <AgentPanel />
      </AllProviders>
    );

    await user.click(screen.getByLabelText(/abrir asistente nova/i));

    const input = screen.getByPlaceholderText(/escribe tu consulta/i);
    await user.type(input, 'No reconozco una transacción');

    const sendBtn = screen.getByLabelText(/enviar/i);
    await user.click(sendBtn);

    await waitFor(
      () => {
        expect(screen.getByText(/transacción que no reconoces/i)).toBeInTheDocument();
      },
      { timeout: 3000 }
    );
  });

  it('shows escalation options when agent requires human handoff', async () => {
    const { sendMessage } = await import('../services/agentService');
    vi.mocked(sendMessage).mockResolvedValueOnce({
      conversation_id: 'conv-test-esc',
      message: 'Para ayudarte, puedo transferir a un especialista.',
      intent: 'general_inquiry',
      sentiment: 'neutral',
      confidence: 0.7,
      status: 'escalation',
      requires_human: true,
      recommended_action: 'Preparar escalamiento',
      suggested_actions: ['Transferir a especialista', 'Continuar con Nova'],
    });

    const user = userEvent.setup();
    render(
      <AllProviders>
        <AgentFAB />
        <AgentPanel />
      </AllProviders>
    );

    await user.click(screen.getByLabelText(/abrir asistente nova/i));
    const input = screen.getByPlaceholderText(/escribe tu consulta/i);
    await user.type(input, 'Quiero hablar con un agente');
    await user.click(screen.getByLabelText(/enviar/i));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/transferir a especialista/i);
    }, { timeout: 3000 });
  });

  it('closes the agent panel when close button is clicked', async () => {
    const user = userEvent.setup();
    render(
      <AllProviders>
        <AgentFAB />
        <AgentPanel />
      </AllProviders>
    );
    await user.click(screen.getByLabelText(/abrir asistente nova/i));
    const closeBtn = screen.getAllByRole('button', { name: /cerrar/i }).at(-1)!;
    await user.click(closeBtn);
    // Closing asks first (and offers to save the conversation).
    const dialog = screen.getByRole('alertdialog', { name: /cerrar el chat/i });
    await user.click(within(dialog).getByRole('button', { name: /sí, cerrar/i }));
    expect(screen.queryByRole('complementary', { name: /nova/i })).not.toBeInTheDocument();
  });
});
