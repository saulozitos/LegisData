import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import WageDisparityPanel from './WageDisparityPanel';

vi.mock('@/services/api', () => ({
  getWageData: vi.fn().mockResolvedValue([])
}));
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  BarChart: ({ children }: any) => <div>{children}</div>,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  Legend: () => <div />,
  Cell: () => <div />
}));

describe('WageDisparityPanel', () => {
  it('renders without crashing', () => {
    render(<WageDisparityPanel />);
  });
});
