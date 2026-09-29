import '@testing-library/jest-dom';
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AllProviders } from './testUtils';
import { AgentConsolePage } from '../pages/AgentConsole/AgentConsolePage';
import * as consoleApi from '../api/agentConsole';
import type { CaseDetail } from '../api/agentConsole';
import { ApiError } from '../api/client';

vi.mock('../api/agentConsole', () => ({
  listCases: vi.fn(), getCase: vi.fn(), takeCase: vi.fn(), replyCase: vi.fn(), closeCase: vi.fn(),
}));

const CASE: CaseDetail = {
  case_id: 'NB-ABC123', status: 'waiting', created_at: '2026-06-17T10:00:00Z', reason: 'dispute',
  summary: 'Quiere disputar un rechazo en TecnoMundo', lang: 'es', agent_name: null, customer: 'Miguel',
  session_id: 's1', open_questions: ['¿Reconoce el comercio?'],
  verified_facts: { identity_verified: true, customer_id: 'demo-001', first_name: 'Miguel', logged_in_customer_id: 'demo-001' },
  evidence: [{ tool: 'get_my_transactions', args: { status: 'declined' }, result: '{"total_found": 1}', at: '2026-06-17T09:59:00Z' }],
  transcript: [{ role: 'customer', text: 'me rechazaron una compra' }],
  messages: [],
};

describe('agent console', () => {
  beforeEach(() => {
    vi.mocked(consoleApi.listCases).mockReset().mockResolvedValue({ cases: [{ ...CASE, faithfulness: null }] });
    vi.mocked(consoleApi.getCase).mockReset().mockResolvedValue(CASE);
    vi.mocked(consoleApi.takeCase).mockReset().mockResolvedValue({ ...CASE, status: 'active', agent_name: 'Laura' });
    vi.mocked(consoleApi.replyCase).mockReset();
    vi.mocked(consoleApi.closeCase).mockReset();
  });

  it('asks for the key and refuses a wrong one', async () => {
    vi.mocked(consoleApi.listCases).mockRejectedValueOnce(new ApiError(401, 'x', 'invalid_key'));
    const user = userEvent.setup();
    render(<AllProviders><AgentConsolePage /></AllProviders>);
    await user.type(screen.getByLabelText(/clave de asesor/i), 'nope');
    await user.click(screen.getByRole('button', { name: /entrar/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/clave incorrecta/i);
  });

  it("shows the case with Nova's summary, the verified facts and evidence, and takes it", async () => {
    const user = userEvent.setup();
    render(<AllProviders><AgentConsolePage /></AllProviders>);
    await user.type(screen.getByLabelText(/clave de asesor/i), 'Asesor2026');
    await user.click(screen.getByRole('button', { name: /entrar/i }));
    await user.click(await screen.findByRole('button', { name: /NB-ABC123/ }));

    expect(await screen.findByText('Quiere disputar un rechazo en TecnoMundo')).toBeInTheDocument();
    expect(screen.getByText('¿Reconoce el comercio?')).toBeInTheDocument();
    expect(screen.getByText(/identidad verificada/i)).toBeInTheDocument();
    expect(screen.getByText('get_my_transactions')).toBeInTheDocument();
    expect(consoleApi.getCase).toHaveBeenCalledWith('Asesor2026', 'NB-ABC123');

    await user.type(screen.getByLabelText(/tu nombre/i), 'Laura');
    await user.click(screen.getByRole('button', { name: /tomar caso/i }));
    expect(consoleApi.takeCase).toHaveBeenCalledWith('Asesor2026', 'NB-ABC123', 'Laura');
    expect(await screen.findByLabelText(/responder al cliente/i)).toBeInTheDocument();
  });
});
