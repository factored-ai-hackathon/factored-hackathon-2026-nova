import '@testing-library/jest-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LoginPage } from '../pages/Login/LoginPage';
import { AllProviders } from './testUtils';
import { useApp } from '../context/AppContext';
import { ApiError, demoCustomer, demoScenarios, login, verifyLogin } from '../api/client';

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return {
    ...actual,
    login: vi.fn(),
    verifyLogin: vi.fn(),
    demoScenarios: vi.fn(),
    demoCustomer: vi.fn(),
  };
});

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const LUCIA = {
  customer_id: 'CUST-000123',
  first_name: 'Lucía',
  country: 'Colombia',
  document_type: 'Pasaporte',
  document_number: 'AB12345',
  birth_date: '1988-03-09',
  phone_last4: '5521',
};

function Probe() {
  const { customer, language } = useApp();
  return (
    <>
      <span data-testid="customer">{customer ? JSON.stringify(customer) : ''}</span>
      <span data-testid="selected-language">{language}</span>
    </>
  );
}

function renderLogin() {
  return render(
    <AllProviders>
      <LoginPage />
      <Probe />
    </AllProviders>,
  );
}

async function fillCredentials(user: ReturnType<typeof userEvent.setup>) {
  await user.selectOptions(screen.getByLabelText(/país/i), 'Colombia');
  await user.selectOptions(screen.getByLabelText(/tipo de documento/i), 'Pasaporte');
  await user.type(screen.getByLabelText(/número de documento/i), 'AB12345');
  await user.type(screen.getByLabelText(/^clave$/i), 'Nova2026');
}

describe('Login: document + password, then the SMS code', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    vi.mocked(login).mockReset().mockResolvedValue({
      login_id: 'login-1',
      phone_last4: '5521',
      code_expires_in: 300,
      demo_sms: 'SMS (demo) al celular terminado en 5521: tu código de verificación NovaBank es 654321',
    });
    vi.mocked(verifyLogin).mockReset().mockResolvedValue({
      session_id: 'login-1',
      customer: {
        customer_id: 'CUST-000123',
        first_name: 'Lucía',
        country: 'Colombia',
        document_type: 'Pasaporte',
        document_last4: '2345',
      },
    });
    vi.mocked(demoScenarios).mockReset();
    vi.mocked(demoCustomer).mockReset();
  });

  it('asks for country, document type, document and password, like a bank', () => {
    renderLogin();
    expect(screen.getByLabelText(/país/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/tipo de documento/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/número de documento/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^clave$/i)).toHaveAttribute('type', 'password');
  });

  it('offers the document types of the chosen country', async () => {
    const user = userEvent.setup();
    renderLogin();
    await user.selectOptions(screen.getByLabelText(/país/i), 'Colombia');
    const types = within(screen.getByLabelText(/tipo de documento/i)).getAllByRole('option');
    expect(types.map((o) => o.textContent)).toEqual([
      'Cédula de ciudadanía', 'Cédula de extranjería', 'Pasaporte',
    ]);
    await user.selectOptions(screen.getByLabelText(/país/i), 'Argentina');
    expect(screen.getByLabelText(/tipo de documento/i)).toHaveValue('DNI');
  });

  it('logs in with the code from the demo SMS and keeps the chat session', async () => {
    const user = userEvent.setup();
    renderLogin();
    await fillCredentials(user);
    await user.click(screen.getByRole('button', { name: /^ingresar$/i }));

    expect(login).toHaveBeenCalledWith({
      country: 'Colombia', document_type: 'Pasaporte', document_number: 'AB12345',
      password: 'Nova2026', lang: 'es',
    });
    expect(await screen.findByRole('status')).toHaveTextContent('654321');
    expect(screen.getByText(/te enviamos un código.*terminado en 5521/i)).toBeInTheDocument();

    const verify = screen.getByRole('button', { name: /verificar/i });
    expect(verify).toBeDisabled();
    await user.type(screen.getByLabelText(/código de verificación/i), '65a4321');
    expect(screen.getByLabelText(/código de verificación/i)).toHaveValue('654321');
    await user.click(verify);

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true }));
    expect(verifyLogin).toHaveBeenCalledWith('login-1', '654321');
    const customer = JSON.parse(screen.getByTestId('customer').textContent!);
    expect(customer).toMatchObject({ id: 'CUST-000123', name: 'Lucía', sessionId: 'login-1' });
  });

  it('shows one message for wrong credentials', async () => {
    vi.mocked(login).mockRejectedValue(new ApiError(401, 'x', 'invalid_credentials'));
    const user = userEvent.setup();
    renderLogin();
    await fillCredentials(user);
    await user.click(screen.getByRole('button', { name: /^ingresar$/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/no son correctos/i);
    expect(screen.queryByLabelText(/código de verificación/i)).not.toBeInTheDocument();
  });

  it('stays on the code step after a wrong code, and goes back when the login expires', async () => {
    vi.mocked(verifyLogin)
      .mockRejectedValueOnce(new ApiError(401, 'x', 'wrong_code'))
      .mockRejectedValueOnce(new ApiError(401, 'x', 'login_expired'));
    const user = userEvent.setup();
    renderLogin();
    await fillCredentials(user);
    await user.click(screen.getByRole('button', { name: /^ingresar$/i }));
    const codeInput = await screen.findByLabelText(/código de verificación/i);

    await user.type(codeInput, '111111');
    await user.click(screen.getByRole('button', { name: /verificar/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/no es correcto/i);

    await user.clear(codeInput);
    await user.type(codeInput, '222222');
    await user.click(screen.getByRole('button', { name: /verificar/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/venció/i);
    expect(screen.getByLabelText(/número de documento/i)).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('keeps Portuguese through the login', async () => {
    const user = userEvent.setup();
    renderLogin();
    await user.click(screen.getByRole('button', { name: /português/i }));
    expect(screen.getByRole('heading', { name: /bem-vindo ao novabank/i })).toBeInTheDocument();
    await user.type(screen.getByLabelText(/número do documento/i), '30123456');
    await user.type(screen.getByLabelText(/^senha$/i), 'Nova2026');
    await user.click(screen.getByRole('button', { name: /^entrar$/i }));
    expect(login).toHaveBeenCalledWith(expect.objectContaining({ lang: 'pt' }));
    expect(await screen.findByRole('heading', { name: /confirme que é você/i })).toBeInTheDocument();
    expect(screen.getByTestId('selected-language')).toHaveTextContent('pt');
  });
});

describe('Demo panel', () => {
  beforeEach(() => {
    vi.mocked(demoScenarios).mockReset().mockResolvedValue({
      password: 'Nova2026',
      scenarios: [
        { key: 'random', customer: LUCIA },
        { key: 'open_complaint', customer: { ...LUCIA, customer_id: 'CUST-9', first_name: 'Raúl', country: 'Argentina', document_type: 'DNI', document_number: '30999888' } },
      ],
    });
    vi.mocked(demoCustomer).mockReset();
  });

  it('is closed until asked, then lists scenarios and fills the form', async () => {
    const user = userEvent.setup();
    renderLogin();
    expect(screen.queryByText(/queja abierta/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /modo demo/i }));

    expect(await screen.findByText(/queja abierta/i)).toBeInTheDocument();
    expect(screen.getByText('Nova2026')).toBeInTheDocument();
    const raul = screen.getByText('Raúl').closest('li')!;
    await user.click(within(raul).getByRole('button', { name: /usar este cliente/i }));

    expect(screen.getByLabelText(/país/i)).toHaveValue('Argentina');
    expect(screen.getByLabelText(/tipo de documento/i)).toHaveValue('DNI');
    expect(screen.getByLabelText(/número de documento/i)).toHaveValue('30999888');
    expect(screen.getByLabelText(/^clave$/i)).toHaveValue('Nova2026');
    expect(screen.queryByText(/queja abierta/i)).not.toBeInTheDocument(); // closed again
  });

  it('finds any customer by ID, and says when it does not exist', async () => {
    vi.mocked(demoCustomer)
      .mockResolvedValueOnce({ ...LUCIA, customer_id: 'CUST-77', first_name: 'Sofía', phone_last4: '' })
      .mockRejectedValueOnce(new ApiError(404, 'x', 'customer_not_found'));
    const user = userEvent.setup();
    renderLogin();
    await user.click(screen.getByRole('button', { name: /modo demo/i }));
    await screen.findByText(/queja abierta/i);

    await user.type(screen.getByLabelText(/buscar por id/i), 'CUST-77');
    await user.click(screen.getByRole('button', { name: /^buscar$/i }));
    expect(await screen.findByText('Sofía')).toBeInTheDocument();
    expect(demoCustomer).toHaveBeenCalledWith('CUST-77');
    expect(screen.getByText(/sin celular registrado/i)).toBeInTheDocument(); // can't log in

    await user.clear(screen.getByLabelText(/buscar por id/i));
    await user.type(screen.getByLabelText(/buscar por id/i), 'nobody');
    await user.click(screen.getByRole('button', { name: /^buscar$/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/no encontramos/i);
  });
});
