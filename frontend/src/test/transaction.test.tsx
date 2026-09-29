import '@testing-library/jest-dom';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TransactionModal } from '../components/banking/TransactionModal';
import { AllProviders } from './testUtils';
import { mockTransactions } from '../data/mockData';

const mockOpenAgent = vi.fn();
const mockSendMessage = vi.fn();

vi.mock('../context/AgentContext', async () => {
  const actual = await vi.importActual('../context/AgentContext');
  return {
    ...actual,
    useAgent: () => ({
      isOpen: false,
      isFullView: false,
      conversation: { id: 'test', messages: [], agentContext: {}, startedAt: '' },
      isTyping: false,
      openAgent: mockOpenAgent,
      closeAgent: vi.fn(),
      openFullView: vi.fn(),
      closeFullView: vi.fn(),
      sendMessage: mockSendMessage,
      resetConversation: vi.fn(),
    }),
  };
});

describe('Transaction → Agent contextual flow', () => {
  const txn = mockTransactions[4]; // disputed transaction

  it('renders transaction modal with merchant and amount', () => {
    render(
      <AllProviders>
        <TransactionModal transaction={txn} onClose={vi.fn()} />
      </AllProviders>
    );
    expect(screen.getByText(txn.merchant)).toBeInTheDocument();
  });

  it('shows the Ask Nova button', () => {
    render(
      <AllProviders>
        <TransactionModal transaction={txn} onClose={vi.fn()} />
      </AllProviders>
    );
    expect(screen.getByText(/consultar a nova/i)).toBeInTheDocument();
  });

  it('calls openAgent with the transaction when Ask Nova is clicked', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <AllProviders>
        <TransactionModal transaction={txn} onClose={onClose} />
      </AllProviders>
    );
    await user.click(screen.getByText(/consultar a nova/i));
    await waitFor(() => {
      expect(mockOpenAgent).toHaveBeenCalledWith(txn);
      expect(mockSendMessage).toHaveBeenCalledWith(
        expect.stringContaining(txn.merchant),
        txn,
      );
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('shows the transaction status badge', () => {
    render(
      <AllProviders>
        <TransactionModal transaction={txn} onClose={vi.fn()} />
      </AllProviders>
    );
    // disputed badge should be visible
    expect(screen.getByText(/en disputa/i)).toBeInTheDocument();
  });
});
