import '@testing-library/jest-dom';
import { beforeEach, describe, it, expect } from 'vitest';
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
  await userEvent.type(screen.getByLabelText('Contraseña'), MODELS_PASSWORD);
  await userEvent.click(screen.getByRole('button', { name: 'Entrar' }));
}

describe('models page', () => {
  beforeEach(() => sessionStorage.clear());

  it('asks for the demo password, shown in the field, with a link to the agent console', async () => {
    renderPage();
    expect(screen.getByLabelText('Contraseña')).toHaveAttribute('placeholder', MODELS_PASSWORD);
    expect(screen.getByRole('link', { name: /consola del asesor/ })).toHaveAttribute('href', '/asesor');
    await userEvent.type(screen.getByLabelText('Contraseña'), 'otra');
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Contraseña incorrecta');
    expect(screen.queryByRole('heading', { name: 'Clasificador de intención' })).not.toBeInTheDocument();
  });

  it('shows the measured numbers and the cost per token once in', async () => {
    await enter();
    expect(screen.getByRole('heading', { name: 'Clasificador de intención' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Búsqueda de conocimiento/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Coste por token' })).toBeInTheDocument();
    expect(screen.getByText('0.85')).toBeInTheDocument(); // intent macro-F1
    expect(screen.getAllByText('87%').length).toBeGreaterThan(0); // RAG recall@1
    expect(screen.getByText('$0.0041')).toBeInTheDocument(); // cost per conversation
    expect(screen.getByText('$0.000001')).toBeInTheDocument(); // input price per token
  });

  it('remembers the password after a reload', async () => {
    await enter();
    document.body.innerHTML = '';
    renderPage();
    expect(screen.getByRole('heading', { name: 'Clasificador de intención' })).toBeInTheDocument();
  });

  it('switches the recall chart by language', async () => {
    await enter();
    await userEvent.click(screen.getByRole('radio', { name: 'Portugués' }));
    expect(screen.getByRole('radio', { name: 'Portugués' })).toHaveAttribute('aria-checked', 'true');
    // Hybrid search in Portuguese: 17 of 19 at recall@1.
    expect(screen.getByText('(17/19)')).toBeInTheDocument();
  });
});
