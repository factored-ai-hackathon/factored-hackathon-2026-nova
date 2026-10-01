// ============================================================
// App-wide context: Auth + Language
// ============================================================

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react';
import type { Customer, Language } from '../types';
import { KEYS, clearCustomerSession, loadStored, saveStored } from '../utils/persist';

interface AppState {
  customer: Customer | null;
  language: Language;
  isAuthenticated: boolean;
}

interface AppContextValue extends AppState {
  setCustomer: (customer: Customer | null) => void;
  setLanguage: (lang: Language) => void;
  logout: () => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  // A reload keeps the logged-in customer and the language until they log out.
  const [state, setState] = useState<AppState>(() => {
    const customer = loadStored<Customer>(KEYS.customer);
    return {
      customer,
      language: loadStored<Language>(KEYS.language) ?? 'es',
      isAuthenticated: customer !== null,
    };
  });

  useEffect(() => {
    if (state.customer) saveStored(KEYS.customer, state.customer);
    saveStored(KEYS.language, state.language);
  }, [state.customer, state.language]);

  useEffect(() => {
    document.documentElement.lang = state.language === 'pt' ? 'pt-BR' : 'es';
  }, [state.language]);

  const setCustomer = useCallback((customer: Customer | null) => {
    if (customer === null) clearCustomerSession();
    setState((prev) => ({
      ...prev,
      customer,
      isAuthenticated: customer !== null,
    }));
  }, []);

  const setLanguage = useCallback((language: Language) => {
    setState((prev) => ({ ...prev, language }));
  }, []);

  const logout = useCallback(() => {
    clearCustomerSession();
    setState((prev) => ({ ...prev, customer: null, isAuthenticated: false }));
  }, []);

  return (
    <AppContext.Provider value={{ ...state, setCustomer, setLanguage, logout }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
