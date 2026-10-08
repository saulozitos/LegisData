import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import DeepBrazilPanel from './DeepBrazilPanel';

vi.mock('@/services/api', () => ({
  getDemographics: vi.fn().mockResolvedValue({ estados: [
    { uf: 'SP', populacao: 40000000, idh: 0.8, pib_per_capita: 50000, taxa_analfabetismo: 2, gini: 0.5 }
  ] }),
  getElectoralData: vi.fn().mockResolvedValue({ votos_historico: [
    { uf: 'SP', ano: 2022, candidato: 'Lula', votos_validos: 15000000, percentual: 45 },
    { uf: 'SP', ano: 2022, candidato: 'Bolsonaro', votos_validos: 18000000, percentual: 55 }
  ] })
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
  Cell: () => <div />,
  ComposedChart: ({ children }: any) => <div>{children}</div>,
  Line: () => <div />
}));

describe('DeepBrazilPanel', () => {
  it('renders without crashing', () => {
    render(<DeepBrazilPanel />);
  });
});
