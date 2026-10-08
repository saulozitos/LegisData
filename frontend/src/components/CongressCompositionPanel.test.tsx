import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import CongressCompositionPanel from './CongressCompositionPanel';

vi.mock('@/services/api', () => ({
  getParties: vi.fn().mockResolvedValue([]),
  getPartiesEvolution: vi.fn().mockResolvedValue([]),
  getColigacoes: vi.fn().mockResolvedValue([])
}));
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  AreaChart: ({ children }: any) => <div>{children}</div>,
  Area: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  Legend: () => <div />
}));
vi.mock('./PartiesPanel', () => ({
  default: () => <div>PartiesPanel</div>
}));

describe('CongressCompositionPanel', () => {
  it('renders without crashing', () => {
    render(<CongressCompositionPanel />);
  });
});
