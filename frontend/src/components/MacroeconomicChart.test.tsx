import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import MacroeconomicChart from './MacroeconomicChart';

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  LineChart: ({ children }: any) => <div>{children}</div>,
  Line: () => <div />,
  BarChart: ({ children }: any) => <div>{children}</div>,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  Legend: () => <div />,
  ComposedChart: ({ children }: any) => <div>{children}</div>,
  ReferenceArea: () => <div />,
  ReferenceLine: () => <div />
}));

describe('MacroeconomicChart', () => {
  it('renders without crashing', () => {
    render(<MacroeconomicChart mandates={[]} data={[]} metric="PIB" />);
  });
});
