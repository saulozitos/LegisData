import React from 'react';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PropositionsExplorerPanel from './PropositionsExplorerPanel';
import * as api from '@/services/api';

vi.mock('@/services/api', () => ({
  getAuthorsProductivityRanking: vi.fn(),
  getLegislativeExplorer: vi.fn(),
}));

vi.mock('./propositions/PropositionVoteModal', () => ({
  default: ({ isOpen, onClose }: any) => isOpen ? <div data-testid="mock-modal"><button onClick={onClose}>Close</button></div> : null
}));

describe('PropositionsExplorerPanel component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.getAuthorsProductivityRanking as any).mockResolvedValue([{
      id: '1',
      nome_eleitoral: 'Baleia Rossi',
      sigla_partido: 'MDB',
      uf: 'SP',
      cargo: 'DEPUTADO FEDERAL',
      total_apresentadas: 10,
      total_aprovadas: 2,
      taxa_sucesso: 20,
      impacto_socioeconomico_score: 80,
      setores_foco: ['Saúde']
    }]);

    (api.getLegislativeExplorer as any).mockResolvedValue({
      total: 1,
      setores_disponiveis: ['Saúde', 'Educação'],
      items: [{
        id: '100',
        sigla_tipo: 'PL',
        numero: 1234,
        ano: 2023,
        ementa: 'Teste de projeto de lei',
        temas: ['Saúde', 'Economia'],
        autor_principal: {
          id: '1',
          nome: 'Baleia Rossi',
          sigla_partido: 'MDB',
          uf: 'SP'
        },
        status_tramitacao: 'Em Tramitação',
        aprovado_camara: true,
        aprovado_senado: false,
        is_executive_initiative: false,
        placar: {
          resultado: 'APROVADA',
          sim: 300,
          nao: 150,
          abstencao: 10
        },
        total_votos_sim: 300,
        total_votos_nao: 150,
        total_votos_abstencao: 10,
        data_apresentacao: '2023-01-01T00:00:00Z',
        url_oficial: 'http://camara.leg.br'
      }]
    });
  });

  it('renders initial tabs and fetches data', async () => {
    await act(async () => {
      render(<PropositionsExplorerPanel />);
    });
    
    expect(screen.getByText(/Ranking de Produtividade/i)).toBeInTheDocument();
  });
});
