import '@testing-library/jest-dom';
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AllProviders } from './testUtils';
import { SatisfactionPrompt } from '../components/agent/SatisfactionPrompt';
import { AgentConsolePage } from '../pages/AgentConsole/AgentConsolePage';
import { rateAdvisor } from '../services/agentService';
import { ApiError } from '../api/client';
import * as consoleApi from '../api/agentConsole';
import type { CaseDetail } from '../api/agentConsole';
import type { HandoffState } from '../context/AgentContext';
import { KEYS, saveStored } from '../utils/persist';

vi.mock('../services/agentService', () => ({ rateAdvisor: vi.fn() }));
vi.mock('../api/agentConsole', () => ({
  listCases: vi.fn(), getCase: vi.fn(), takeCase: vi.fn(), replyCase: vi.fn(), closeCase: vi.fn(),
}));

const handoff = (status: HandoffState['status'], caseId = 'NB-ABC123'): HandoffState => ({
  caseId, status, agentName: 'Laura', next: 3,
});

beforeEach(() => {
  sessionStorage.clear();
  vi.mocked(rateAdvisor).mockReset().mockResolvedValue(undefined);
});

describe('advisor satisfaction prompt in the chat', () => {
  it.each(['waiting', 'active'] as const)('does not appear while the case is %s', (status) => {
    render(<SatisfactionPrompt handoff={handoff(status)} language="es" />);
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
  });

  it('does not appear without a handoff', () => {
    render(<SatisfactionPrompt handoff={null} language="es" />);
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
  });

  it('does not appear when the poll says the case was already rated', () => {
    render(<SatisfactionPrompt handoff={{ ...handoff('closed'), rated: true }} language="es" />);
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
  });

  it('appears once the case is closed and submits the rating once', async () => {
    const user = userEvent.setup();
    render(<SatisfactionPrompt handoff={handoff('closed')} language="es" />);
    expect(screen.getByRole('group', { name: '¿Cómo fue tu experiencia con el asesor?' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '4 de 5' }));
    expect(rateAdvisor).toHaveBeenCalledTimes(1);
    expect(rateAdvisor).toHaveBeenCalledWith(4);
    expect(await screen.findByText('¡Gracias por tu opinión!')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '5 de 5' })).not.toBeInTheDocument();
  });

  it('is shown once per closed case: not again after answering, after a dismissal or a reload', async () => {
    const user = userEvent.setup();
    const { unmount } = render(<SatisfactionPrompt handoff={handoff('closed')} language="es" />);
    await user.click(screen.getByRole('button', { name: 'Ahora no' }));
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
    expect(rateAdvisor).not.toHaveBeenCalled();
    unmount();
    render(<SatisfactionPrompt handoff={handoff('closed')} language="es" />);
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
    // a different case asks again
    render(<SatisfactionPrompt handoff={handoff('closed', 'NB-OTHER1')} language="es" />);
    expect(screen.getByRole('group')).toBeInTheDocument();
  });

  it('treats "already rated" as done and lets the customer retry after a failure', async () => {
    const user = userEvent.setup();
    vi.mocked(rateAdvisor).mockRejectedValueOnce(new Error('network'));
    render(<SatisfactionPrompt handoff={handoff('closed')} language="es" />);
    await user.click(screen.getByRole('button', { name: '2 de 5' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/inténtalo de nuevo/i);
    vi.mocked(rateAdvisor).mockRejectedValueOnce(new ApiError(409, 'x'));
    await user.click(screen.getByRole('button', { name: '2 de 5' }));
    expect(await screen.findByText('¡Gracias por tu opinión!')).toBeInTheDocument();
  });

  it('shows the thanks state on 409 already_rated', async () => {
    const user = userEvent.setup();
    vi.mocked(rateAdvisor).mockRejectedValueOnce(new ApiError(409, 'already_rated', 'already_rated'));
    render(<SatisfactionPrompt handoff={handoff('closed')} language="es" />);
    await user.click(screen.getByRole('button', { name: '3 de 5' }));
    expect(await screen.findByText('¡Gracias por tu opinión!')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it.each([
    ['es', '¿Cómo fue tu experiencia con el asesor?', /inténtalo de nuevo/i, '4 de 5', '¡Gracias por tu opinión!'],
    ['pt', 'Como foi sua experiência com o atendente?', /tente novamente/i, '4 de 5', 'Obrigado pela sua avaliação!'],
    ['en', 'How was your experience with the advisor?', /please try again/i, '4 out of 5', 'Thanks for your feedback!'],
  ] as const)('keeps the prompt and offers a retry on 409 rating_conflict (%s)', async (lang, question, retry, star, thanks) => {
    const user = userEvent.setup();
    vi.mocked(rateAdvisor).mockRejectedValueOnce(new ApiError(409, 'rating_conflict', 'rating_conflict'));
    render(<SatisfactionPrompt handoff={handoff('closed')} language={lang} />);
    await user.click(screen.getByRole('button', { name: star }));
    expect(await screen.findByRole('alert')).toHaveTextContent(retry);
    expect(screen.getByRole('group', { name: question })).toBeInTheDocument();
    expect(screen.queryByText(thanks)).not.toBeInTheDocument();
    for (const b of screen.getAllByRole('button')) expect(b).toBeEnabled();
    await user.click(screen.getByRole('button', { name: star }));
    expect(rateAdvisor).toHaveBeenCalledTimes(2);
    expect(await screen.findByText(thanks)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('follows the session language, with an English fallback', () => {
    const { unmount } = render(<SatisfactionPrompt handoff={handoff('closed')} language="pt" />);
    expect(screen.getByText('Como foi sua experiência com o atendente?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '5 de 5' })).toBeInTheDocument();
    unmount();
    render(<SatisfactionPrompt handoff={handoff('closed')} language="fr" />);
    expect(screen.getByText('How was your experience with the advisor?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '5 out of 5' })).toBeInTheDocument();
  });
});

describe('customer rating in the agent console', () => {
  const CASE: CaseDetail = {
    case_id: 'NB-ABC123', status: 'closed', created_at: '2026-06-17T10:00:00Z', reason: 'dispute',
    summary: 'x', lang: 'es', agent_name: 'Laura', customer: 'Miguel', open_questions: [], intent: null,
    verified_facts: { identity_verified: true, customer_id: null, first_name: 'Miguel', logged_in_customer_id: null },
    evidence: [], transcript: [], messages: [], rating: 4,
  };

  async function open(detail: CaseDetail, summary: Partial<CaseDetail>) {
    saveStored(KEYS.console, { key: 'k', agentName: 'Laura' });
    vi.mocked(consoleApi.listCases).mockReset().mockResolvedValue({
      cases: [{ ...CASE, ...summary, faithfulness: null, intent: null }],
      stats: { waiting: 0, active: 0, closed: 2, faithfulness_avg: null, satisfaction_avg: 4.5, rated: 2 },
    });
    vi.mocked(consoleApi.getCase).mockReset().mockResolvedValue(detail);
    const user = userEvent.setup();
    render(<AllProviders><AgentConsolePage /></AllProviders>);
    return user;
  }

  it('shows the average, the value in the queue and the rating in the case', async () => {
    const user = await open(CASE, { rating: 4 });
    expect(await screen.findByText('4.5/5')).toBeInTheDocument();
    expect(screen.getByText(/Customer rating \(2\)/)).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: /NB-ABC123/ }));
    expect(await screen.findByText('Customer rating: 4/5')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Rating 4\/5/ })).toBeInTheDocument();
  });

  it('says "Not rated" for an unrated case', async () => {
    const user = await open({ ...CASE, rating: null }, { rating: null });
    await user.click(await screen.findByRole('button', { name: /NB-ABC123/ }));
    expect(await screen.findByText('Not rated')).toBeInTheDocument();
  });
});
