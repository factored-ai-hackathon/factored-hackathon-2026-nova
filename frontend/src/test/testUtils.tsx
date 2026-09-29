import { AgentProvider } from '../context/AgentContext';
import { AppProvider } from '../context/AppContext';
import { BrowserRouter } from 'react-router-dom';
import { type ReactNode } from 'react';

// Shared test wrapper providing all required context providers
export function AllProviders({ children }: { children: ReactNode }) {
  return (
    <BrowserRouter>
      <AppProvider>
        <AgentProvider>{children}</AgentProvider>
      </AppProvider>
    </BrowserRouter>
  );
}
