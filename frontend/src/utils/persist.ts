// Session persistence across page reloads (sessionStorage: it survives a reload, and closing the
// tab ends the session). Reads and writes never throw: if the browser blocks storage the app just
// behaves as before and starts clean.

const PREFIX = 'nb.';

export const KEYS = {
  customer: 'customer', // the logged-in customer, with the chat session the login created
  language: 'language',
  chat: 'chat', // the conversation on screen and an open handoff
  chatSession: 'chatSession', // the backend chat session ids (services/agentService.ts)
  console: 'console', // the human agent console's key and open case
} as const;

export function loadStored<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(PREFIX + key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function saveStored(key: string, value: unknown): void {
  try {
    sessionStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // storage full or blocked: the session just won't survive a reload
  }
}

export function clearStored(...keys: string[]): void {
  for (const key of keys) {
    try {
      sessionStorage.removeItem(PREFIX + key);
    } catch {
      // nothing to clear
    }
  }
}

/** Everything of a customer's session (logout, or a session the backend no longer accepts). */
export function clearCustomerSession(): void {
  clearStored(KEYS.customer, KEYS.chat, KEYS.chatSession);
}
