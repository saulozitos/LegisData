import React from 'react';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import LegislativePanel from './LegislativePanel';

vi.mock('@/services/api', () => ({
  getPropositionVotes: vi.fn().mockResolvedValue({
    total_sim: 1,
    total_nao: 0,
    total_abstencao: 0,
    total_votos: 1,
    votos: [
      {
        id_parlamentar: '1',
        nome_eleitoral: 'Teste',
        nome_civil: 'Teste Civil',
        partido_sigla: 'PT',
        uf: 'SP',
        decisao: 'SIM',
        alinhamento_governo: 'SIM'
      }
    ]
  }),
}));

const mockPropositions = [
  {
    id: '1',
    siglaTipo: 'PL',
    numero: 1,
    ano: 2023,
    ementa: 'Teste 1',
    area_tematica: 'Saúde',
    is_reforma_estrutural: true,
    placar_camara: { SIM: 1, NAO: 0, ABSTENCAO: 0, TOTAL: 1, OBSTRUCAO: 0, ARTIGO_17: 0, BRANCO: 0 },
    placar_senado: { SIM: 0, NAO: 0, ABSTENCAO: 0, TOTAL: 0, OBSTRUCAO: 0, ARTIGO_17: 0, BRANCO: 0 }
  },
  {
    id: '2',
    siglaTipo: 'PEC',
    numero: 2,
    ano: 2022,
    ementa: 'Teste 2',
    area_tematica: 'Economia',
    is_reforma_estrutural: false,
    placar_camara: { SIM: 0, NAO: 0, ABSTENCAO: 0, TOTAL: 0, OBSTRUCAO: 0, ARTIGO_17: 0, BRANCO: 0 },
    placar_senado: { SIM: 1, NAO: 0, ABSTENCAO: 0, TOTAL: 1, OBSTRUCAO: 0, ARTIGO_17: 0, BRANCO: 0 }
  }
];

describe('LegislativePanel', () => {
  it('renders initial state without crashing', async () => {
    await act(async () => {
      render(<LegislativePanel propositions={[]} activeMandateMeta={null as any} />);
    });
  });
  
  it('navigates houses and applies filters', async () => {
    await act(async () => {
      render(<LegislativePanel propositions={mockPropositions as any} />);
    });
    
    // Switch to Senado
    const btnSenado = screen.getByText('Senado Federal');
    await act(async () => {
      fireEvent.click(btnSenado);
    });

    // Switch back to Camara
    const btnCamara = screen.getByText('Câmara dos Deputados');
    await act(async () => {
      fireEvent.click(btnCamara);
    });

    // Check Reforms
    // Replaced checkbox with finding button for reforms since it is a button
    const btnReforms = screen.getByText('Apenas Reformas');
    await act(async () => {
      fireEvent.click(btnReforms);
    });

    // Open modal
    const btnOpen = screen.queryAllByText('Votação Nominal')[0];
    if (btnOpen) {
      await act(async () => {
        fireEvent.click(btnOpen);
      });
      // Close modal
      const btnClose = screen.getAllByRole('button').find(b => b.className.includes('top-4'));
      if (btnClose) {
        await act(async () => {
          fireEvent.click(btnClose);
        });
      }
    }
  });
});
