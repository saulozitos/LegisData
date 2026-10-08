import React from 'react';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ComparadorPage from './page';
import * as api from '@/services/api';

vi.mock('@/components/Header', () => ({
  default: () => <div data-testid="mock-header">Header</div>
}));

vi.mock('@/services/api', () => ({
  getMandatesPerformance: vi.fn(),
  getCompareMandates: vi.fn(),
  getPresidentes: vi.fn(),
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
  Legend: () => <div />,
  ReferenceLine: () => <div />,
  ReferenceArea: () => <div />,
  ComposedChart: ({ children }: any) => <div>{children}</div>
}));

describe('ComparadorPage component', () => {
  it('renders and fetches initial data', async () => {
    (api.getMandatesPerformance as any).mockResolvedValue([{
      id_mandato: 'lula-2023',
      presidente_nome: 'Lula'
    }]);
    
    (api.getPresidentes as any).mockResolvedValue([{
      id_mandato: 'lula-2023',
      nome: 'Lula'
    }]);
    
    (api.getCompareMandates as any).mockResolvedValue({
      mandate1: { 
        id_mandato: 'bolsonaro-2019',
        presidente_nome: 'Bolsonaro',
        presidente: 'Jair Bolsonaro',
        pib_crescimento_acumulado_pct: 5,
        ipca_acumulado_pct: 10,
        ipca_pos_real_pct: 0,
        salario_minimo_real_crescimento_pct: 2,
        desemprego_media_pct: 10,
        risco_brasil_media: 200,
        dolar_crescimento_pct: 15,
        ideb_anos_iniciais_crescimento: 0.5,
        homicidios_taxa_100k_crescimento_pct: -5,
        desmatamento_amazonia_km2_crescimento_pct: 10,
        gini_crescimento_pct: -1,
        projetos_aprovados: 50,
        vetos_derrubados: 2,
        medidas_provisorias_aprovadas: 10,
        taxa_governabilidade: 60,
        custo_legislativo_bi: 2
      },
      mandate2: { 
        id_mandato: 'lula-2023',
        presidente_nome: 'Lula',
        presidente: 'Luiz Inácio Lula da Silva',
        pib_crescimento_acumulado_pct: 6,
        ipca_acumulado_pct: 5,
        ipca_pos_real_pct: 0,
        salario_minimo_real_crescimento_pct: 4,
        desemprego_media_pct: 8,
        risco_brasil_media: 150,
        dolar_crescimento_pct: -5,
        ideb_anos_iniciais_crescimento: 0.6,
        homicidios_taxa_100k_crescimento_pct: -10,
        desmatamento_amazonia_km2_crescimento_pct: -20,
        gini_crescimento_pct: -2,
        projetos_aprovados: 80,
        vetos_derrubados: 1,
        medidas_provisorias_aprovadas: 15,
        taxa_governabilidade: 70,
        custo_legislativo_bi: 1.5
      },
      deltas: {
        pib_crescimento_diff_pp: 1,
        ipca_acumulado_diff_pp: -5,
        salario_minimo_diff_pp: 2,
        desemprego_media_diff_pp: -2,
        risco_brasil_diff: -50,
        dolar_diff_pp: -20,
        ideb_anos_iniciais_diff: 0.1,
        homicidios_taxa_diff_pp: -5,
        desmatamento_diff_pp: -30,
        gini_diff_pp: -1
      },
      normalized_trajectory: [
        { year: 1, m1_pib: 1, m2_pib: 2, m1_ipca: 4, m2_ipca: 5 }
      ],
      repasses_comparison: {
        by_uf: [
          { uf: 'SP', estado_nome: 'São Paulo', regiao: 'Sudeste', m1_total: 100, m2_total: 200, m1_per_capita: 10, m2_per_capita: 20, is_m1_aligned: true, is_m2_aligned: false }
        ]
      },
      scores_prosperidade: {
        mandate1: { score_geral: 80, subscore_economico: 80, subscore_social: 80, subscore_estabilidade: 80, components: {} },
        mandate2: { score_geral: 90, subscore_economico: 90, subscore_social: 90, subscore_estabilidade: 90, components: {} },
        delta_score_geral: 10
      },
      termometro_repasses_apoio: {
        mandato1: { alinhados_per_capita: 10, opositores_per_capita: 5, razao_favorecimento: 2 },
        mandato2: { alinhados_per_capita: 20, opositores_per_capita: 10, razao_favorecimento: 2 },
        m1_lider_per_capita: { estado: 'São Paulo', uf: 'SP', valor_per_capita: 100 },
        m2_lider_per_capita: { estado: 'Rio de Janeiro', uf: 'RJ', valor_per_capita: 200 }
      }
    });

    await act(async () => {
      render(<ComparadorPage />);
    });
    
    expect(screen.getByTestId('mock-header')).toBeInTheDocument();
    
    const tabs = [
      'Visão Geral',
      'Desempenho',
      'Votações',
      'Proposições',
      'Despesas',
      'Justiça',
      'Legislativo',
      'Partidos',
      'Executivo',
      'Judiciário',
      'Perfil'
    ];
    
    for (const tab of tabs) {
      const el = screen.queryByText(tab);
      if (el) {
        const btn = el.closest('button') || el;
        await act(async () => {
          fireEvent.click(btn);
        });
      }
    }
  });
});
