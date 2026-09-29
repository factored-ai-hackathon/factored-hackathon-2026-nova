import '@testing-library/jest-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LoginPage } from '../pages/Login/LoginPage';
import { AllProviders } from './testUtils';
import { useApp } from '../context/AppContext';

// Mock react-router-dom navigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

function renderLogin() {
  return render(
    <AllProviders>
      <LoginPage />
    </AllProviders>
  );
}

function LanguageProbe() {
  const { language } = useApp();
  return <span data-testid="selected-language">{language}</span>;
}

describe('Login flow', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  it('renders the login form with all required elements', () => {
    renderLogin();
    expect(screen.getByLabelText(/correo/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^contraseña$/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /ingresar/i })).toBeInTheDocument();
  });

  it('shows demo hint text', () => {
    renderLogin();
    expect(screen.getByText(/modo demo/i)).toBeInTheDocument();
  });

  it('fills demo credentials when clicking the demo button', async () => {
    const user = userEvent.setup();
    renderLogin();
    const demoBtn = screen.getByText(/usar credenciales demo/i);
    await user.click(demoBtn);
    const emailInput = screen.getByLabelText(/correo/i) as HTMLInputElement;
    expect(emailInput.value).toContain('@');
  });

  it('shows error when submitting empty form', async () => {
    const user = userEvent.setup();
    renderLogin();
    await user.click(screen.getByRole('button', { name: /ingresar/i }));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });

  it('navigates to dashboard after successful login', async () => {
    const user = userEvent.setup();
    renderLogin();

    // Fill in credentials
    await user.type(screen.getByLabelText(/correo/i), 'test@novabank.lat');
    await user.type(screen.getByLabelText(/^contraseña$/i), 'demo1234');
    await user.click(screen.getByRole('button', { name: /ingresar/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true });
    }, { timeout: 3000 });
  });

  it('renders language selector with Español and Português options', () => {
    renderLogin();
    expect(screen.getByRole('button', { name: /español/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /português/i })).toBeInTheDocument();
  });

  it('changes language to Portuguese when clicking Português', async () => {
    const user = userEvent.setup();
    renderLogin();
    const ptBtn = screen.getByRole('button', { name: /português/i });
    await user.click(ptBtn);
    expect(ptBtn).toHaveAttribute('aria-pressed', 'true');
  });

  it('keeps Portuguese selected through mock login', async () => {
    const user = userEvent.setup();
    render(
      <AllProviders>
        <LoginPage />
        <LanguageProbe />
      </AllProviders>
    );

    await user.click(screen.getByRole('button', { name: /português/i }));
    expect(screen.getByRole('heading', { name: /bem-vindo ao novabank/i })).toBeInTheDocument();
    await user.type(screen.getByLabelText(/e-mail/i), 'demo@novabank.lat');
    await user.type(screen.getByLabelText(/^senha$/i), 'demo1234');
    await user.click(screen.getByRole('button', { name: /^entrar$/i }));

    await waitFor(() => {
      expect(screen.getByTestId('selected-language')).toHaveTextContent('pt');
      expect(document.documentElement.lang).toBe('pt-BR');
    });
  });
});
