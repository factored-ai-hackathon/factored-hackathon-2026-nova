import '@testing-library/jest-dom';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useEffect } from 'react';
import { DashboardPage } from '../pages/Dashboard/DashboardPage';
import { AllProviders } from './testUtils';
import { useApp } from '../context/AppContext';
import { mockCustomer } from '../data/mockData';

function PortugueseDashboard() {
  const { setCustomer, setLanguage } = useApp();

  useEffect(() => {
    setLanguage('pt');
    setCustomer(mockCustomer);
  }, [setCustomer, setLanguage]);

  return <DashboardPage />;
}

describe('Portuguese UI', () => {
  it('localizes the dashboard, assistant, and transaction detail', async () => {
    const user = userEvent.setup();
    render(
      <AllProviders>
        <PortugueseDashboard />
      </AllProviders>
    );

    expect(await screen.findByText('Ações rápidas')).toBeInTheDocument();
    expect(screen.getByText('Conta corrente')).toBeInTheDocument();
    expect(screen.getByText('Notificações')).toBeInTheDocument();
    expect(document.documentElement.lang).toBe('pt-BR');

    await user.click(screen.getAllByRole('button', { name: 'Abrir assistente Nova' }).at(-1)!);
    expect(screen.getByText(/Olá Miguel 👋 Sou a Nova/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Digite sua mensagem...')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Transação: Supermercado Central/i }));
    expect(screen.getByRole('heading', { name: 'Detalhes da transação' })).toBeInTheDocument();
    expect(screen.getByText('Estabelecimento / Descrição')).toBeInTheDocument();
    expect(screen.getByText('Supermercado')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Perguntar à Nova/i })).toBeInTheDocument();
  });
});
