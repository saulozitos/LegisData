import React from 'react';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import PoliticianProfile from './PoliticianProfile';
import * as api from '@/services/api';

vi.mock('@/services/api', () => ({
  searchPoliticians: vi.fn(),
  getPoliticianDossier: vi.fn(),
  getParties: vi.fn(),
}));

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  BarChart: ({ children }: any) => <div>{children}</div>,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
  CartesianGrid: () => <div />,
  Cell: () => <div />,
  PieChart: ({ children }: any) => <div>{children}</div>,
  Pie: () => <div />,
}));

describe('PoliticianProfile component', () => {
  it('renders initial state without crashing', async () => {
    (api.getParties as any).mockResolvedValue([]);
    
    await act(async () => {
      render(<PoliticianProfile />);
    });
    
    expect(screen.getByPlaceholderText(/Digite o nome de um político para abrir o Raio-X/i)).toBeInTheDocument();
  });

  it('renders a politician dossier if selectedPoliticianId is provided', async () => {
    (api.getParties as any).mockResolvedValue([]);
    (api.getPoliticianDossier as any).mockResolvedValue({
      id: '123',
      nome_civil: 'Teste Silva',
      nome_eleitoral: 'Teste',
      foto_url: 'http://example.com/foto.jpg',
      estado_origem: 'SP',
      escolaridade: 'Superior Completo',
      ocupacao: 'Advogado',
      idade: 45,
      trajetoria_mandatos: [
        { cargo: 'DEPUTADO FEDERAL', legislatura: 57, ano_inicio: 2023, partido: 'PT', uf: 'SP', titular: true, status: 'ELEITO', ano_eleicao: 2022, numero_mandato: 1, esfera: 'Federal' }
      ],
      projetos_autoria_recente: [
        { id: '1', ementa: 'Proj 1', ano: 2023, siglaTipo: 'PL', numero: 100 }
      ],
      projetos_autoria_historico: [
        { id: '2', ementa: 'Proj 2', ano: 2020, siglaTipo: 'PL', numero: 200 }
      ],
      processos_judiciais: [
        { numero: '1234', tribunal: 'STF', assunto: 'Corrupção', status: 'Em andamento', descricao_resumida: 'Teste' }
      ],
      certidoes: [
        { tipo: 'Criminal', tribunal: 'TJSP', status: 'Nada Consta' }
      ],
      filiacoes_partidarias: [
        { sigla: 'PT', data_filiacao: '2010-01-01' }
      ],
      fidelidade_partidaria: { trocas: 0, media_trocas_camara: 1 },
      partido_atual: {
        sigla: 'PT',
        nome_completo: 'Partido dos Trabalhadores'
      },
      mandato_atual: {
        cargo: 'DEPUTADO FEDERAL',
        uf: 'SP',
        legislatura: 57,
        presencas_plenario: 100,
        ausencias_justificadas: 2,
        ausencias_nao_justificadas: 1
      },
      performance_kpis: {
        produtividade_legislativa: 80,
        alinhamento_governo: 90,
        fidelidade_partidaria: 95
      },
      doacoes_campanha: [
        { doador_nome: 'Empresa', valor: 100000, tipo: 'PJ' }
      ],
      despesas_gabinete: {
        total: 1000,
        limite: 2000,
        por_categoria: [{ categoria: 'Passagens', valor: 1000 }]
      }
    });

    await act(async () => {
      render(<PoliticianProfile selectedPoliticianId="123" />);
    });
    
    expect(api.getPoliticianDossier).toHaveBeenCalledWith('123');
    
    const tabs = [
      'Visão Geral',
      'Análise AI',
      'Proposições',
      'Financiamento',
      'Despesas (CEAP)',
      'Emendas',
      'Justiça',
      'Assiduidade',
      'Remuneração',
      'Votações'
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
