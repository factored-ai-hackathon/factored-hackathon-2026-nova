import '@testing-library/jest-dom';
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { act, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AgentPanel } from '../components/agent/AgentPanel';
import { AgentFAB } from '../components/agent/AgentFAB';
import { AllProviders } from './testUtils';
import { useIdleTimer } from '../hooks/useIdleTimer';
import { IDLE_CLOSE_MS, IDLE_NOTICE_MS, IDLE_PROMPT_MS, MAX_KEEP_OPEN, idleTimerEnabled } from '../config/idleTimer';
import * as agentService from '../services/agentService';
import { mockConversation } from '../data/mockData';
import { KEYS, saveStored } from '../utils/persist';

vi.mock('../services/agentService', () => ({
  sendMessage: vi.fn(),
  pollHandoff: vi.fn().mockResolvedValue(null),
  sendFeedback: vi.fn(),
  resetConversation: vi.fn(),
  startForCustomer: vi.fn(),
}));

const QUESTION = '¿Hay algo más en lo que pueda ayudarte?';
const KEEP = 'Mantener el chat abierto';
const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  sessionStorage.clear();
  window.history.pushState({}, '', '/');
  vi.mocked(agentService.sendMessage).mockReset();
  vi.mocked(agentService.resetConversation).mockReset();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
});

describe('useIdleTimer', () => {
  const setup = (active = true, key: unknown = 0) => {
    const onTimeout = vi.fn();
    const hook = renderHook((p: { active: boolean; key: unknown }) =>
      useIdleTimer({ active: p.active, activityKey: p.key, onTimeout }), { initialProps: { active, key } });
    return { onTimeout, ...hook };
  };

  it('prompts after 5 minutes of silence and not before', () => {
    const { result } = setup();
    act(() => { vi.advanceTimersByTime(IDLE_PROMPT_MS - 1); });
    expect(result.current.phase).toBe('idle');
    act(() => { vi.advanceTimersByTime(1); });
    expect(result.current.phase).toBe('prompt');
  });

  it('shows the notice after 2 more minutes and calls onTimeout 3 seconds later', () => {
    const { result, onTimeout } = setup();
    act(() => { vi.advanceTimersByTime(IDLE_PROMPT_MS + IDLE_CLOSE_MS); });
    expect(result.current.phase).toBe('closing');
    expect(onTimeout).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(IDLE_NOTICE_MS); });
    expect(onTimeout).toHaveBeenCalledTimes(1);
  });

  it('keep-open restarts the timers', () => {
    const { result, onTimeout } = setup();
    act(() => { vi.advanceTimersByTime(IDLE_PROMPT_MS + IDLE_CLOSE_MS - 1000); });
    act(() => result.current.keepOpen());
    expect(result.current.phase).toBe('idle');
    act(() => { vi.advanceTimersByTime(IDLE_PROMPT_MS + IDLE_CLOSE_MS - 1000); });
    expect(onTimeout).not.toHaveBeenCalled();
    expect(result.current.phase).toBe('prompt');
  });

  it('allows 4 keep-opens, then no more; writing resets the counter', () => {
    const { result, rerender } = setup();
    for (let i = 0; i < MAX_KEEP_OPEN; i++) {
      act(() => { vi.advanceTimersByTime(IDLE_PROMPT_MS); });
      expect(result.current.canKeepOpen).toBe(true);
      act(() => result.current.keepOpen());
    }
    act(() => { vi.advanceTimersByTime(IDLE_PROMPT_MS); });
    expect(result.current.phase).toBe('prompt');
    expect(result.current.canKeepOpen).toBe(false);
    rerender({ active: true, key: 1 }); // the user wrote
    expect(result.current.canKeepOpen).toBe(true);
    expect(result.current.phase).toBe('idle');
  });

  it('with no keep-opens left it still closes after the same 2 minutes', () => {
    const { result, onTimeout } = setup();
    for (let i = 0; i < MAX_KEEP_OPEN; i++) {
      act(() => { vi.advanceTimersByTime(IDLE_PROMPT_MS); });
      act(() => result.current.keepOpen());
    }
    act(() => { vi.advanceTimersByTime(IDLE_PROMPT_MS + IDLE_CLOSE_MS + IDLE_NOTICE_MS); });
    expect(onTimeout).toHaveBeenCalledTimes(1);
  });

  it('does not run while inactive and restarts when it becomes active again', () => {
    const { result, rerender, onTimeout } = setup(false);
    act(() => { vi.advanceTimersByTime(IDLE_PROMPT_MS * 3); });
    expect(result.current.phase).toBe('idle');
    rerender({ active: true, key: 0 });
    act(() => { vi.advanceTimersByTime(IDLE_PROMPT_MS - 1); });
    expect(result.current.phase).toBe('idle');
    rerender({ active: false, key: 0 });
    act(() => { vi.advanceTimersByTime(IDLE_PROMPT_MS * 3); });
    expect(onTimeout).not.toHaveBeenCalled();
  });

  it('clears its timers on unmount', () => {
    const { unmount, onTimeout } = setup();
    unmount();
    expect(vi.getTimerCount()).toBe(0);
    act(() => { vi.advanceTimersByTime(IDLE_PROMPT_MS + IDLE_CLOSE_MS + IDLE_NOTICE_MS); });
    expect(onTimeout).not.toHaveBeenCalled();
  });
});

describe('switch and durations', () => {
  it('is on by default', () => expect(idleTimerEnabled()).toBe(true));

  it('VITE_IDLE_TIMER=off turns it off', () => {
    vi.stubEnv('VITE_IDLE_TIMER', 'off');
    expect(idleTimerEnabled()).toBe(false);
  });

  it('?idle=off turns it off and is remembered for the tab; ?idle=on turns it on', () => {
    window.history.pushState({}, '', '/?idle=off');
    expect(idleTimerEnabled()).toBe(false);
    window.history.pushState({}, '', '/dashboard');
    expect(idleTimerEnabled()).toBe(false);
    window.history.pushState({}, '', '/?idle=on');
    expect(idleTimerEnabled()).toBe(true);
    window.history.pushState({}, '', '/');
    expect(idleTimerEnabled()).toBe(true);
  });

  it('the Vite env variables override the durations', () => {
    vi.stubEnv('VITE_IDLE_PROMPT_SECONDS', '10');
    vi.stubEnv('VITE_IDLE_CLOSE_SECONDS', '8');
    const onTimeout = vi.fn();
    const { result } = renderHook(() => useIdleTimer({ active: true, activityKey: 0, onTimeout }));
    act(() => { vi.advanceTimersByTime(10_000); });
    expect(result.current.phase).toBe('prompt');
    act(() => { vi.advanceTimersByTime(8_000 + IDLE_NOTICE_MS); });
    expect(onTimeout).toHaveBeenCalledTimes(1);
  });
});

describe('idle timer in the customer chat', () => {
  async function openChat() {
    render(<AllProviders><AgentFAB /><AgentPanel /></AllProviders>);
    await act(async () => { screen.getByLabelText(/abrir asistente nova/i).click(); });
  }

  const storeChat = (handoffStatus: 'waiting' | 'active' | 'closed' | null) =>
    saveStored(KEYS.chat, {
      customerId: null,
      conversation: mockConversation,
      handoff: handoffStatus && { caseId: 'NB-1', status: handoffStatus, agentName: null, next: 0 },
      isOpen: true,
    });

  it('asks, keeps the chat open on the button, and closes it with the close flow', async () => {
    await openChat();
    await advance(IDLE_PROMPT_MS - 1000);
    expect(screen.queryByText(QUESTION)).not.toBeInTheDocument();
    await advance(1000);
    expect(screen.getByText(QUESTION)).toBeInTheDocument();
    const keep = screen.getByRole('button', { name: KEEP });

    await act(async () => { keep.click(); });
    expect(screen.queryByText(QUESTION)).not.toBeInTheDocument();
    expect(agentService.resetConversation).not.toHaveBeenCalled();

    await advance(IDLE_PROMPT_MS + IDLE_CLOSE_MS);
    expect(screen.getByText('Chat cerrado por inactividad.')).toBeInTheDocument();
    expect(screen.getByRole('complementary')).toBeInTheDocument(); // still visible during the notice
    await advance(IDLE_NOTICE_MS);
    expect(agentService.resetConversation).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument(); // panel closed
  });

  it('a user message restarts the silence', async () => {
    vi.mocked(agentService.sendMessage).mockResolvedValue({
      conversation_id: 'c', message: 'ok', message_id: 'm', intent: null, sentiment: 'neutral',
      confidence: 1, status: 'idle', requires_human: false, recommended_action: null, suggested_actions: [],
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await openChat();
    await advance(IDLE_PROMPT_MS - 1000);
    await user.type(screen.getByPlaceholderText(/escribe tu consulta/i), 'hola');
    await user.click(screen.getByLabelText(/enviar/i));
    await advance(IDLE_PROMPT_MS - 1000);
    expect(screen.queryByText(QUESTION)).not.toBeInTheDocument();
    await advance(1000);
    expect(screen.getByText(QUESTION)).toBeInTheDocument();
  });

  it.each(['waiting', 'active'] as const)('never runs while a handoff case is %s', async (status) => {
    storeChat(status);
    render(<AllProviders><AgentPanel /></AllProviders>);
    await advance(IDLE_PROMPT_MS + IDLE_CLOSE_MS + IDLE_NOTICE_MS);
    expect(screen.queryByText(QUESTION)).not.toBeInTheDocument();
    expect(agentService.resetConversation).not.toHaveBeenCalled();
  });

  it('runs after the handoff case is closed', async () => {
    storeChat('closed');
    render(<AllProviders><AgentPanel /></AllProviders>);
    await advance(IDLE_PROMPT_MS);
    expect(screen.getByText(QUESTION)).toBeInTheDocument();
  });

  it('never runs while Nova is answering', async () => {
    vi.mocked(agentService.sendMessage).mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await openChat();
    await user.type(screen.getByPlaceholderText(/escribe tu consulta/i), 'hola');
    await user.click(screen.getByLabelText(/enviar/i));
    await advance(IDLE_PROMPT_MS + IDLE_CLOSE_MS + IDLE_NOTICE_MS);
    expect(screen.queryByText(QUESTION)).not.toBeInTheDocument();
    expect(agentService.resetConversation).not.toHaveBeenCalled();
  });

  it('does not run while the panel is closed', async () => {
    render(<AllProviders><AgentFAB /><AgentPanel /></AllProviders>);
    await advance(IDLE_PROMPT_MS + IDLE_CLOSE_MS + IDLE_NOTICE_MS);
    expect(agentService.resetConversation).not.toHaveBeenCalled();
  });

  it('does not run with ?idle=off', async () => {
    window.history.pushState({}, '', '/?idle=off');
    await openChat();
    await advance(IDLE_PROMPT_MS + IDLE_CLOSE_MS + IDLE_NOTICE_MS);
    expect(screen.queryByText(QUESTION)).not.toBeInTheDocument();
    expect(agentService.resetConversation).not.toHaveBeenCalled();
  });

  it('shows the last prompt without a button after 4 keep-opens', async () => {
    await openChat();
    for (let i = 0; i < MAX_KEEP_OPEN; i++) {
      await advance(IDLE_PROMPT_MS);
      await act(async () => { screen.getByRole('button', { name: KEEP }).click(); });
    }
    await advance(IDLE_PROMPT_MS);
    expect(screen.getByText(QUESTION)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: KEEP })).not.toBeInTheDocument();
  });
});
