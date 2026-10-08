import React from 'react';
import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ExecutivoDashboard from './page';

vi.mock('@/components/Header', () => ({ default: () => <div data-testid="Header" /> }));
vi.mock('@/services/api', () => ({
  getPresidentialMandates: vi.fn().mockResolvedValue([
    {
      id: '123',
      nome: 'Teste',
      inicio: '2023-01-01',
      fim: null,
      partido: 'PT',
      foto_url: ''
    }
  ]),
  getMandateIndicators: vi.fn().mockResolvedValue([
    {
      data: '2023-01-01',
      inflacao_ipca: 5.0,
      aprovacao_popular: 50.0,
      taxa_sucesso_congresso: 60.0,
      volume_emendas: 200.0
    }
  ])
}));

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
  Legend: () => <div />
}));

describe('ExecutivoDashboard', () => {
  it('renders loading state initially', async () => {
    render(<ExecutivoDashboard />);
    expect(screen.getByRole('main')).toBeInTheDocument();
  });

  it('renders data and handles click', async () => {
    await act(async () => {
      render(<ExecutivoDashboard />);
    });
    
    await waitFor(() => {
      expect(screen.getByText('Raio-X do Executivo')).toBeInTheDocument();
    });

    // Check mandate loaded
    const mandateBtn = screen.getByText('Teste');
    expect(mandateBtn).toBeInTheDocument();

    // Click it to trigger indicator load
    await act(async () => {
      fireEvent.click(mandateBtn);
    });

    expect(screen.getByText('Aprovação Popular vs Inflação')).toBeInTheDocument();
  });
});
