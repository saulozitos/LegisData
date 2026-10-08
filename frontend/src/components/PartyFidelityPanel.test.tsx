import React from 'react';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, vi, expect } from 'vitest';
import PartyFidelityPanel from './PartyFidelityPanel';

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  BarChart: ({ children }: any) => <div>{children}</div>,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  ReferenceLine: () => <div />,
  Legend: () => <div />,
  Cell: () => <div />
}));

const mockFidelityData = {
  summary: { total_migracoes: 10, total_parlamentares_nômades: 5, partido_mais_ganhou: 'PT', partido_mais_perdeu: 'PSDB' },
  party_balance: [
    { sigla_partido: 'PT', saldo_liquido: 5, ganhos: 5, perdas: 0 },
    { sigla_partido: 'PSDB', saldo_liquido: -5, ganhos: 0, perdas: 5 },
    { sigla_partido: 'PL', saldo_liquido: 0, ganhos: 0, perdas: 0 }, // no movement
  ],
  top_nomads: [
    {
      id: '1',
      nome_eleitoral: 'Fulano',
      partido_atual: 'PT',
      uf: 'SP',
      total_migracoes: 2,
      siglas_sequencia: ['PSDB', 'MDB', 'PT']
    },
    {
      id: '2',
      nome_eleitoral: 'Ciclano',
      partido_atual: 'PL',
      uf: 'RJ',
      total_migracoes: 3,
      siglas_sequencia: ['DEM', 'PSL', 'PL']
    }
  ]
};

describe('PartyFidelityPanel', () => {
  it('renders null when fidelityData is null', () => {
    const { container } = render(<PartyFidelityPanel fidelityData={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders and interacts with fidelityData', async () => {
    await act(async () => {
      render(<PartyFidelityPanel fidelityData={mockFidelityData as any} />);
    });
    
    // Switch chart filter
    const btnAll = screen.getByText('Top 20');
    await act(async () => {
      fireEvent.click(btnAll);
    });

    const btnTop = screen.getByText('Destaques');
    await act(async () => {
      fireEvent.click(btnTop);
    });

    // Search
    const searchInput = screen.getByPlaceholderText(/Buscar por nome ou partido.../i);
    await act(async () => {
      fireEvent.change(searchInput, { target: { value: 'Fulano' } });
    });
    
    // Toggle expand
    const btnExpand = screen.queryAllByRole('button').find(b => b.className.includes('bg-slate-800'));
    if (btnExpand) {
      await act(async () => {
        fireEvent.click(btnExpand);
      });
      await act(async () => {
        fireEvent.click(btnExpand); // collapse
      });
    }
  });
});
