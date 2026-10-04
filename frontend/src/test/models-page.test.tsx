import '@testing-library/jest-dom';
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ModelsPage, { MODELS_PASSWORD } from '../pages/Models/ModelsPage';

function renderPage() {
  render(
    <MemoryRouter>
      <ModelsPage />
    </MemoryRouter>,
  );
}

async function enter() {
  renderPage();
  await userEvent.type(screen.getByLabelText('Password'), MODELS_PASSWORD);
  await userEvent.click(screen.getByRole('button', { name: 'Enter' }));
}

describe('models page', () => {
  beforeEach(() => {
    sessionStorage.clear();
    // The live section's endpoint is down: the static sections must still render.
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 503 })));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('asks for the demo password, shown in the field, with a link to the agent console', async () => {
    renderPage();
    expect(screen.getByLabelText('Password')).toHaveAttribute('placeholder', MODELS_PASSWORD);
    expect(screen.getByRole('link', { name: /human agent console/ })).toHaveAttribute('href', '/console');
    await userEvent.type(screen.getByLabelText('Password'), 'otra');
    await userEvent.click(screen.getByRole('button', { name: 'Enter' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Wrong password');
    expect(screen.queryByRole('heading', { name: 'Intent classifier' })).not.toBeInTheDocument();
  });

  it('shows the measured numbers and the cost per token once in', async () => {
    await enter();
    expect(screen.getByRole('heading', { name: 'Intent classifier' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Knowledge search/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Cost per token' })).toBeInTheDocument();
    expect(screen.getByText('0.85')).toBeInTheDocument(); // intent macro-F1
    expect(screen.getAllByText('87%').length).toBeGreaterThan(0); // RAG recall@1
    expect(screen.getByText('$0.0041')).toBeInTheDocument(); // cost per conversation
    expect(screen.getByText('$0.000001')).toBeInTheDocument(); // input price per token
    expect(await screen.findByText(/live numbers are not available/)).toBeInTheDocument();
  });

  it('signs out: back to the password gate, and a reload stays out', async () => {
    await enter();
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Intent classifier' })).not.toBeInTheDocument();
    document.body.innerHTML = '';
    renderPage();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
  });

  it('remembers the password after a reload', async () => {
    await enter();
    document.body.innerHTML = '';
    renderPage();
    expect(screen.getByRole('heading', { name: 'Intent classifier' })).toBeInTheDocument();
  });

  it('switches the recall chart by language', async () => {
    await enter();
    await userEvent.click(screen.getByRole('radio', { name: 'Portuguese' }));
    expect(screen.getByRole('radio', { name: 'Portuguese' })).toHaveAttribute('aria-checked', 'true');
    // Hybrid search in Portuguese: 17 of 19 at recall@1.
    expect(screen.getByText('(17/19)')).toBeInTheDocument();
  });
});
