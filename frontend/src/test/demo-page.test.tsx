import '@testing-library/jest-dom';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { DemoPage } from '../pages/Demo/DemoPage';

describe('demo entry page', () => {
  it('links the three parts of the demo, each with what it is and its demo key', () => {
    render(
      <MemoryRouter>
        <DemoPage />
      </MemoryRouter>,
    );
    const links = screen.getAllByRole('link');
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/login', '/console', '/models']);
    expect(screen.getByRole('heading', { name: 'Customer app' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Human agent console' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Do the models work?' })).toBeInTheDocument();
    expect(screen.getByText(/password Nova2026/)).toBeInTheDocument();
    expect(screen.getByText(/Key Asesor2026/)).toBeInTheDocument();
    expect(screen.getByText(/Password Modelos2026/)).toBeInTheDocument();
  });

  it.each(['/', '/demo'])('the real app shows it at %s, with the URL at the bare host name', (path) => {
    window.history.pushState({}, '', path);
    render(<App />);
    expect(screen.getByRole('heading', { name: 'Nova' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/');
  });
});
