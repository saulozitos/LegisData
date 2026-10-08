import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import PropositionVoteModal from './PropositionVoteModal';

vi.mock('@/services/api', () => ({
  getPropositionVotes: vi.fn().mockResolvedValue([])
}));
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  PieChart: ({ children }: any) => <div>{children}</div>,
  Pie: () => <div />,
  Cell: () => <div />,
  Tooltip: () => <div />
}));

describe('PropositionVoteModal', () => {
  it('renders without crashing', () => {
    render(<PropositionVoteModal isOpen={true} onClose={() => {}} propositionId="123" />);
  });
});
