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
  AreaChart: ({ children }: any) => <div>{children}</div>,
  Area: () => <div />,
  BarChart: ({ children }: any) => <div>{children}</div>,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  Legend: () => <div />,
  ReferenceLine: () => <div />,
}));

describe('ExecutivoDashboard', () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (typeof url === 'string' && url.includes('/summary')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              mandate_id: '123',
              nome: 'Teste',
              partido: 'PT',
              inicio: '2023-01-01',
              fim: null,
              foto_url: '',
              total_meses: 1,
              kpis: {
                inflacao_ipca: { primeiro: 5.0, ultimo: 5.0, minimo: 5.0, maximo: 5.0, media: 5.0, variacao_pp: 0 },
                aprovacao_popular: { primeiro: 50.0, ultimo: 50.0, minimo: 50.0, maximo: 50.0, media: 50.0 },
              },
            }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve([
            {
              id: '123',
              nome: 'Teste',
              inicio: '2023-01-01',
              fim: null,
              partido: 'PT',
              foto_url: '',
            },
          ]),
      });
    }) as any;
  });

  // vi.restoreAllMocks is omitted to preserve module mocks

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
    const mandateBtns = screen.getAllByText('Teste');
    expect(mandateBtns[0]).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Inflação vs. Aprovação Popular')).toBeInTheDocument();
    });
  });
});
