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
  const [state, setState] = useState<AppState>({
    customer: null,
    language: 'es',
    isAuthenticated: false,
  });

  useEffect(() => {
    document.documentElement.lang = state.language === 'pt' ? 'pt-BR' : 'es';
  }, [state.language]);

  const setCustomer = useCallback((customer: Customer | null) => {
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
