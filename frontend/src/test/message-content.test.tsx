import '@testing-library/jest-dom';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageContent } from '../components/agent/MessageContent';

describe('MessageContent', () => {
  it('renders Markdown in agent replies', () => {
    const { container } = render(
      <MessageContent role="agent" content={'Opciones:\n\n1. **Llamar** al centro\n2. Visitar una sucursal'} />
    );
    expect(screen.getByText('Llamar').tagName).toBe('STRONG');
    expect(container.querySelectorAll('ol li')).toHaveLength(2);
  });

  it('does not render raw HTML from the model', () => {
    const { container } = render(<MessageContent role="agent" content={'<img src=x onerror="alert(1)">hola'} />);
    expect(container.querySelector('img')).toBeNull();
  });

  it('keeps user messages as plain text', () => {
    render(<MessageContent role="user" content="**no es negrita**" />);
    expect(screen.getByText('**no es negrita**')).toBeInTheDocument();
  });
});
