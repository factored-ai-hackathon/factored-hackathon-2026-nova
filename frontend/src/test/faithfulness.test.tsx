import '@testing-library/jest-dom';
import { describe, it, expect } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { FaithfulnessPanel } from '../components/console/FaithfulnessPanel';
import type { Faithfulness } from '../api/agentConsole';

const DATA: Faithfulness = {
  evidence: [
    { tool: 'get_my_transactions', args: { status: 'declined' }, at: '2026-06-17T10:00:00Z' },
    { tool: 'get_my_products', args: {}, at: '2026-06-17T10:00:01Z' },
  ],
  answers: [
    {
      index: 1,
      text: 'Te rechazaron la compra en **TecnoMundo** por USD 301.05. Tu tarjeta 9999 está bloqueada.',
      claims: [
        { token: 'tecnomundo', text: 'TecnoMundo', supported: true },
        { token: '301', text: '301.05', supported: true },
        { token: '9999', text: '9999', supported: false },
      ],
      score: 0.667,
      sentences: [
        { text: 'Te rechazaron la compra en TecnoMundo por USD 301.05.', similarity: [0.62, 0.1], shared: [['301', 'tecnomundo'], []] },
        { text: 'Tu tarjeta 9999 está bloqueada.', similarity: [0, 0], shared: [[], []] },
      ],
    },
  ],
  overall: 0.667,
};

describe('faithfulness panel', () => {
  it('shows the score and marks each claim as found or not found in the data', () => {
    render(<FaithfulnessPanel data={DATA} language="es" />);
    expect(screen.getAllByText('67%').length).toBeGreaterThan(0);
    const found = screen.getByText('TecnoMundo').closest('mark')!;
    const invented = screen.getByText('9999').closest('mark')!;
    expect(found).toHaveClass('supported');
    expect(found).toHaveTextContent('✓');
    expect(invented).toHaveClass('unsupported');
    expect(invented).toHaveTextContent(/✗.*no aparece en ningún dato/);
  });

  it('draws one heatmap cell per sentence and evidence item, with the shared tokens on hover', () => {
    const { container } = render(<FaithfulnessPanel data={DATA} language="es" />);
    const cells = container.querySelectorAll('.faith-heatmap rect');
    expect(cells).toHaveLength(4);
    fireEvent.mouseMove(cells[0], { clientX: 10, clientY: 10 });
    expect(screen.getByRole('tooltip')).toHaveTextContent('0.62');
    expect(screen.getByRole('tooltip')).toHaveTextContent('301, tecnomundo');
    // Table view with the same numbers (not color alone).
    expect(screen.getByText('Ver como tabla')).toBeInTheDocument();
    expect(screen.getAllByText('0.62').length).toBeGreaterThan(0);
  });

  it('says when there was nothing to check', () => {
    render(<FaithfulnessPanel data={{ evidence: [], answers: [], overall: null }} language="es" />);
    expect(screen.getByText(/no hizo afirmaciones verificables/i)).toBeInTheDocument();
    expect(screen.getByText(/no hay evidencia/i)).toBeInTheDocument();
  });
});
