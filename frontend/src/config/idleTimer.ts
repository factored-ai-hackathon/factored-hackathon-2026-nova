// Inactivity timer of the customer chat (decision 47). In memory only: a reload restarts it.
// Read at call time (not at import) so tests and the URL switch can change them.

import { KEYS, loadStored, saveStored } from '../utils/persist';

export const IDLE_PROMPT_MS = 5 * 60 * 1000; // silence before Nova asks "anything else?"
export const IDLE_CLOSE_MS = 2 * 60 * 1000; // more silence before the chat closes
export const MAX_KEEP_OPEN = 4; // "keep the chat open" presses; resets when the user writes
export const IDLE_NOTICE_MS = 3000; // how long "closed due to inactivity" shows before the panel closes

function seconds(raw: unknown, fallbackMs: number): number {
  const n = Number(raw);
  return raw !== undefined && raw !== '' && Number.isFinite(n) && n > 0 ? n * 1000 : fallbackMs;
}

/** Durations; VITE_IDLE_PROMPT_SECONDS and VITE_IDLE_CLOSE_SECONDS override them (testing, recording). */
export function idleDurations() {
  return {
    promptMs: seconds(import.meta.env.VITE_IDLE_PROMPT_SECONDS, IDLE_PROMPT_MS),
    closeMs: seconds(import.meta.env.VITE_IDLE_CLOSE_SECONDS, IDLE_CLOSE_MS),
  };
}

/**
 * Call ONCE at app start (main.tsx), before routing: ?idle=off or ?idle=on on any page of the app
 * is remembered for this browser tab in sessionStorage, so it survives the login navigation.
 */
export function initIdleSwitchFromUrl(): void {
  const param = new URLSearchParams(window.location.search).get('idle');
  if (param === 'off' || param === 'on') saveStored(KEYS.idle, param);
}

/** Off with VITE_IDLE_TIMER=off at build time, or when the tab's stored switch (see above) is off. */
export function idleTimerEnabled(): boolean {
  if (import.meta.env.VITE_IDLE_TIMER === 'off') return false;
  return loadStored<string>(KEYS.idle) !== 'off';
}
