import React from 'react';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import PerformanceKpis from './PerformanceKpis';

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  LineChart: ({ children }: any) => <div>{children}</div>,
  Line: () => <div />,
  BarChart: ({ children }: any) => <div>{children}</div>,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
  CartesianGrid: () => <div />,
  Cell: () => <div />,
}));

describe('PerformanceKpis component', () => {
  const mockPerformance = {
    id_mandato: 'lula-2023',
    presidente_nome: 'Lula',
    partido_sigla: 'PT',
    anos_cobertos: '2023-2026',
    pib_medio_anual_pct: 2.9,
    ipca_acumulado_pct: 4.62,
    ipca_pos_real_pct: 4.62,
    salario_minimo_inicial_usd: 250,
    salario_minimo_final_usd: 280,
    desemprego_medio_pct: 7.8,
    fome_media_pct: 4.5,
    desmatamento_medio_anual_km2: 5000,
    taxa_homicidios_100k: 19.5,
    feminicidios_total: 1000,
    valores_anuais: [
      { ano: 2023, pib_crescimento_pct: 2.9, ipca_anual_pct: 4.62 }
    ]
  };

  const mockMeta = {
    id_mandato: 'lula-2023',
    nome: 'Luiz Inácio Lula da Silva',
    partido_sigla: 'PT',
    data_inicio: '2023-01-01',
    imagem_url: 'https://exemplo.com/lula.jpg'
  };

  it('renders without crashing with full props', () => {
    render(
      <PerformanceKpis 
        performance={mockPerformance} 
        presidentMeta={mockMeta as any} 
      />
    );
    
    expect(screen.getByText('Crescimento do PIB')).toBeInTheDocument();
  });

  it('renders without crashing with null props', () => {
    render(
      <PerformanceKpis 
        performance={null} 
        presidentMeta={null} 
      />
    );
    
    expect(screen.getByText('Crescimento do PIB')).toBeInTheDocument();
  });


});
