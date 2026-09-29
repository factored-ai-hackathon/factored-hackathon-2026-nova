import '@testing-library/jest-dom';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AgentPanel } from '../components/agent/AgentPanel';
import { AgentFAB } from '../components/agent/AgentFAB';
import { AllProviders } from './testUtils';
import { pollHandoff } from '../services/agentService';
import { transcriptMailto, transcriptText } from '../utils/transcript';

const HANDED_OVER = 'Te comuniqué con un asesor humano. Tu caso es el **NB-ABC123**.';

vi.mock('../services/agentService', () => ({
  sendMessage: vi.fn(async (_request, onToken, onNotice) => {
    onToken?.(HANDED_OVER);
    onNotice?.('NB-ABC123', 'handoff');
    return {
      conversation_id: 'session-1', message: HANDED_OVER, message_id: 'm-1', intent: null,
      sentiment: 'neutral', confidence: 0, status: 'idle', requires_human: false,
      recommended_action: null, suggested_actions: [],
    };
  }),
  pollHandoff: vi.fn(),
  sendFeedback: vi.fn(),
  resetConversation: vi.fn(),
  startForCustomer: vi.fn(),
}));

afterEach(() => vi.useRealTimers());

async function openAndAsk() {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(<AllProviders><AgentFAB /><AgentPanel /></AllProviders>);
  await user.click(screen.getByLabelText(/abrir asistente nova/i));
  await user.type(screen.getByPlaceholderText(/escribe tu consulta/i), 'quiero un asesor');
  await user.click(screen.getByLabelText(/enviar/i));
  return user;
}

async function tick() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
}

describe('handoff to a human agent in the chat', () => {
  it("shows the case, then the agent's messages, until the case closes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(pollHandoff)
      .mockResolvedValueOnce({ status: 'waiting', case_id: 'NB-ABC123', agent_name: null, messages: [], next: 0 })
      .mockResolvedValueOnce({
        status: 'active', case_id: 'NB-ABC123', agent_name: 'Laura', next: 2,
        messages: [
          { from: 'system', text: 'Laura (asesor) tomó tu caso.', at: '2026-06-17T10:00:00Z' },
          { from: 'agent', text: 'Hola, ya reviso tu caso.', at: '2026-06-17T10:00:05Z' },
        ],
      })
      .mockResolvedValueOnce({
        status: 'closed', case_id: 'NB-ABC123', agent_name: 'Laura', next: 3,
        messages: [{ from: 'system', text: 'El asesor cerró el caso NB-ABC123.', at: '2026-06-17T10:05:00Z' }],
      });
    await openAndAsk();

    expect(await screen.findByText(/esperando a un asesor/i)).toBeInTheDocument();
    await tick(); // waiting
    await tick(); // active
    expect(await screen.findByText('Hola, ya reviso tu caso.')).toBeInTheDocument();
    expect(screen.getByText(/te atiende laura/i)).toBeInTheDocument();
    expect(screen.getByText(/laura · asesor/i)).toBeInTheDocument();
    expect(vi.mocked(pollHandoff)).toHaveBeenLastCalledWith(0);
    await tick(); // closed
    expect(await screen.findByText(/cerró el caso/i)).toBeInTheDocument();
    expect(vi.mocked(pollHandoff)).toHaveBeenLastCalledWith(2);
    expect(screen.queryByText(/te atiende laura/i)).not.toBeInTheDocument();
    await tick();
    expect(vi.mocked(pollHandoff)).toHaveBeenCalledTimes(3); // stops after closing
  });
});

describe('chat header', () => {
  it('minimizes without asking; closing asks and can be cancelled', async () => {
    const user = userEvent.setup();
    render(<AllProviders><AgentFAB /><AgentPanel /></AllProviders>);
    await user.click(screen.getByLabelText(/abrir asistente nova/i));
    await user.click(screen.getByRole('button', { name: 'Cerrar' }));
    const dialog = screen.getByRole('alertdialog', { name: /cerrar el chat/i });
    expect(within(dialog).getByRole('button', { name: /descargar/i })).toBeInTheDocument();
    expect(within(dialog).getByRole('link', { name: /enviar por correo/i })).toHaveAttribute(
      'href', expect.stringMatching(/^mailto:\?subject=/),
    );
    await user.click(within(dialog).getByRole('button', { name: /no, seguir/i }));
    expect(screen.getByRole('complementary', { name: /nova/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /minimizar/i }));
    expect(screen.queryByRole('complementary', { name: /nova/i })).not.toBeInTheDocument();
  });

  it('builds the transcript with who said what, and cuts long emails', () => {
    const messages = [
      { id: '1', role: 'user' as const, content: 'hola', timestamp: '2026-06-17T10:00:00Z' },
      { id: '2', role: 'agent' as const, content: 'Hola, ¿en qué te ayudo?', timestamp: '2026-06-17T10:00:01Z' },
      { id: '3', role: 'human' as const, content: 'Soy Laura', author: 'Laura', timestamp: '2026-06-17T10:01:00Z' },
    ];
    const text = transcriptText(messages, 'Lucía', 'es');
    expect(text).toContain('Lucía:\nhola');
    expect(text).toContain('Nova:\nHola, ¿en qué te ayudo?');
    expect(text).toContain('Laura (asesor):\nSoy Laura');
    const long = decodeURIComponent(transcriptMailto('x'.repeat(5000), 'es'));
    expect(long.length).toBeLessThan(2200);
    expect(long).toContain('recortada');
  });
});
