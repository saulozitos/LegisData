import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import VotingCalendarPanel from './VotingCalendarPanel';

vi.mock('@/services/api', () => ({
  getVotingCalendar: vi.fn().mockResolvedValue({ 
    items: [
      { id: '1', siglaTipo: 'PL', numero: 1, ano: 2023, dataVotacao: '2023-01-01', resumoVotacao: 'Aprovado', orientacao_governo: 'Sim', votos_sim: 100, votos_nao: 50, votos_abstencao: 5, autor_nome: 'Teste', ementa: 'Ementa teste' }
    ], total: 1 
  }),
}));
vi.mock('./propositions/PropositionVoteModal', () => ({
  default: () => <div />
}));

describe('VotingCalendarPanel', () => {
  it('renders without crashing', () => {
    render(<VotingCalendarPanel />);
  });
});
