import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Home from './page';
import * as api from '@/services/api';

vi.mock('@/components/Header', () => ({ default: () => <div data-testid="Header" /> }));
vi.mock('@/components/LoadingSkeleton', () => ({ default: () => <div data-testid="LoadingSkeleton" /> }));
vi.mock('@/components/PresidentTimeline', () => ({
  default: ({ presidents, selectedId, onSelect }: { presidents: Array<{ id_referencia: string }>; selectedId: string | null; onSelect: (id: string | null) => void }) => (
    <div data-testid="PresidentTimeline" data-selected={String(selectedId)} data-count={presidents.length}>
      <button onClick={() => onSelect('fhc-1995')}>pick-fhc</button>
      <button onClick={() => onSelect(null)}>pick-all</button>
    </div>
  ),
}));
vi.mock('@/components/ExecutivoPanel', () => ({
  default: ({ mandateId, performance }: { mandateId: string | null; performance: { id_mandato: string } | null }) => (
    <div data-testid="ExecutivoPanel" data-mandate={String(mandateId)} data-perf={performance?.id_mandato ?? 'none'} />
  ),
}));
vi.mock('@/components/MacroeconomicChart', () => ({ default: ({ data }: { data: unknown[] }) => <div data-testid="MacroeconomicChart" data-rows={data.length} /> }));
vi.mock('@/components/LegislativePanel', () => ({
  default: ({ propositions, onSelectPolitician, onSelectParty }: { propositions: unknown[]; onSelectPolitician: (id: string) => void; onSelectParty: (s: string) => void }) => (
    <div data-testid="LegislativePanel" data-count={propositions.length}>
      <button onClick={() => onSelectPolitician('pol-9')}>open-politician</button>
      <button onClick={() => onSelectParty('PT')}>open-party</button>
    </div>
  ),
}));
vi.mock('@/components/PartyFidelityPanel', () => ({ default: ({ fidelityData }: { fidelityData: unknown }) => <div data-testid="PartyFidelityPanel" data-has={String(Boolean(fidelityData))} /> }));
vi.mock('@/components/WageDisparityPanel', () => ({ default: () => <div data-testid="WageDisparityPanel" /> }));
vi.mock('@/components/CongressCompositionPanel', () => ({ default: ({ mandateId }: { mandateId: string }) => <div data-testid="CongressCompositionPanel" data-mandate={mandateId} /> }));
vi.mock('@/components/FederalTransfersPanel', () => ({ default: ({ mandateId }: { mandateId: string }) => <div data-testid="FederalTransfersPanel" data-mandate={mandateId} /> }));
vi.mock('@/components/PoliticianProfile', () => ({ default: ({ selectedPoliticianId }: { selectedPoliticianId: string | null }) => <div data-testid="PoliticianProfile" data-selected={String(selectedPoliticianId)} /> }));
vi.mock('@/components/SocialClassesExplainer', () => ({ default: () => <div data-testid="SocialClassesExplainer" /> }));
vi.mock('@/components/DeepBrazilPanel', () => ({ default: ({ mandate }: { mandate: { id: string } | null }) => <div data-testid="DeepBrazilPanel" data-mandate={mandate?.id ?? 'none'} /> }));
vi.mock('@/components/PropositionsExplorerPanel', () => ({ default: () => <div data-testid="PropositionsExplorerPanel" /> }));
vi.mock('@/components/PartiesPanel', () => ({ default: ({ targetParty }: { targetParty: string | null }) => <div data-testid="PartiesPanel" data-target={String(targetParty)} /> }));
vi.mock('@/components/PartyMembersModal', () => ({
  default: ({ partySigla, isOpen, onSelectPolitician }: { partySigla: string | null; isOpen: boolean; onSelectPolitician: (id: string) => void }) =>
    isOpen ? (
      <div data-testid="PartyMembersModal" data-party={partySigla}>
        <button onClick={() => onSelectPolitician('pol-from-party')}>pick-member</button>
      </div>
    ) : null,
}));
vi.mock('@/components/VotingCalendarPanel', () => ({ default: () => <div data-testid="VotingCalendarPanel" /> }));
vi.mock('@/components/EmendasExplorerPanel', () => ({ default: () => <div data-testid="EmendasExplorerPanel" /> }));
vi.mock('@/services/api', () => ({
  getPresidentes: vi.fn(),
  getMandatesPerformance: vi.fn(),
  getAnnualMacroSummary: vi.fn(),
  getLegislativePropositions: vi.fn(),
  getPartyFidelity: vi.fn(),
}));

const m = (name: keyof typeof api) => api[name] as unknown as ReturnType<typeof vi.fn>;

const presidents = [
  { id_referencia: 'fhc-1995', status_mandato: 'CONCLUIDO', data_inicio: '1995-01-01', data_fim: '1998-12-31', nome_eleitoral: 'FHC', mandato_numero: 1, ano_eleicao: 1994 },
  { id_referencia: 'lula-2023', status_mandato: 'EM_EXERCICIO', data_inicio: '2023-01-01', data_fim: null, nome_eleitoral: 'Lula', mandato_numero: 3, ano_eleicao: 2022 },
];
const performances = [
  { id_mandato: 'fhc-1995', status_mandato: 'CONCLUIDO' },
  { id_mandato: 'lula-2023', status_mandato: 'EM_EXERCICIO' },
];

const tab = (name: string) => screen.getByRole('tab', { name });

beforeEach(() => {
  Object.values(api).forEach((fn) => (fn as unknown as ReturnType<typeof vi.fn>).mockReset?.());
  m('getPresidentes').mockResolvedValue(presidents);
  m('getMandatesPerformance').mockResolvedValue(performances);
  m('getAnnualMacroSummary').mockResolvedValue([{ ano: 2023 }, { ano: 2024 }]);
  m('getLegislativePropositions').mockResolvedValue([{ id: 1 }, { id: 2 }]);
  m('getPartyFidelity').mockResolvedValue({ party_balance: [], top_nomads: [], summary: {} });
});

describe('Home (dashboard)', () => {
  it('mostra o esqueleto enquanto carrega e depois a aba Economia com o mandato atual', async () => {
    render(<Home />);
    expect(screen.getByTestId('LoadingSkeleton')).toBeInTheDocument();
    const exec = await screen.findByTestId('ExecutivoPanel');
    expect(exec).toHaveAttribute('data-mandate', 'lula-2023');
    expect(exec).toHaveAttribute('data-perf', 'lula-2023');
    expect(await screen.findByTestId('MacroeconomicChart')).toHaveAttribute('data-rows', '2');
    expect(tab('Economia & Mandato')).toHaveAttribute('aria-selected', 'true');
  });

  it('só busca proposições e fidelidade quando a aba é aberta (carregamento sob demanda)', async () => {
    render(<Home />);
    await screen.findByTestId('ExecutivoPanel');
    expect(m('getLegislativePropositions')).not.toHaveBeenCalled();
    expect(m('getPartyFidelity')).not.toHaveBeenCalled();

    fireEvent.click(tab('Monitor do Congresso'));
    expect(await screen.findByTestId('LegislativePanel')).toHaveAttribute('data-count', '2');
    expect(m('getLegislativePropositions')).toHaveBeenCalledTimes(1);

    fireEvent.click(tab('Fidelidade Partidária (TSE)'));
    expect(await screen.findByTestId('PartyFidelityPanel')).toHaveAttribute('data-has', 'true');
    expect(m('getPartyFidelity')).toHaveBeenCalledTimes(1);
  });

  it('o filtro global de mandato chega às abas (e "todos" usa o mandato atual onde é obrigatório)', async () => {
    render(<Home />);
    await screen.findByTestId('ExecutivoPanel');
    fireEvent.click(screen.getByText('pick-fhc'));
    expect(screen.getByTestId('ExecutivoPanel')).toHaveAttribute('data-mandate', 'fhc-1995');

    fireEvent.click(tab('Composição de Governo'));
    expect(await screen.findByTestId('CongressCompositionPanel')).toHaveAttribute('data-mandate', 'fhc-1995');

    fireEvent.click(screen.getByText('pick-all'));
    expect(screen.getByTestId('CongressCompositionPanel')).toHaveAttribute('data-mandate', 'lula-2023');
    fireEvent.click(tab('Orçamento Federal por UF'));
    expect(await screen.findByTestId('FederalTransfersPanel')).toHaveAttribute('data-mandate', 'lula-2023');
  });

  it('aba Sociedade recebe o intervalo do mandato selecionado', async () => {
    render(<Home />);
    await screen.findByTestId('ExecutivoPanel');
    fireEvent.click(tab('Sociedade & Eleições'));
    expect(await screen.findByTestId('DeepBrazilPanel')).toHaveAttribute('data-mandate', 'lula-2023');
    expect(screen.getByTestId('SocialClassesExplainer')).toBeInTheDocument();
  });

  it('renda, partidos, produtividade e calendário renderizam suas seções', async () => {
    render(<Home />);
    await screen.findByTestId('ExecutivoPanel');
    fireEvent.click(tab('Renda & Classes Sociais'));
    expect(await screen.findByTestId('WageDisparityPanel')).toBeInTheDocument();
    fireEvent.click(tab('Partidos'));
    expect(await screen.findByTestId('PartiesPanel')).toHaveAttribute('data-target', 'null');
    fireEvent.click(tab('Produtividade & Votações'));
    expect(await screen.findByTestId('PropositionsExplorerPanel')).toBeInTheDocument();
    fireEvent.click(tab('Calendário de Votações'));
    expect(await screen.findByTestId('VotingCalendarPanel')).toBeInTheDocument();
  });

  it('navegação universal: partido abre a aba Partidos e o modal; membro abre o Raio-X', async () => {
    render(<Home />);
    await screen.findByTestId('ExecutivoPanel');
    fireEvent.click(tab('Monitor do Congresso'));
    fireEvent.click(await screen.findByText('open-party'));

    expect(tab('Partidos')).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByTestId('PartiesPanel')).toHaveAttribute('data-target', 'PT');
    expect(screen.getByTestId('PartyMembersModal')).toHaveAttribute('data-party', 'PT');

    fireEvent.click(screen.getByText('pick-member'));
    expect(screen.queryByTestId('PartyMembersModal')).not.toBeInTheDocument();
    expect(tab('Raio-X do Político')).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByTestId('PoliticianProfile')).toHaveAttribute('data-selected', 'pol-from-party');
  });

  it('abrir um parlamentar pelo Monitor leva ao Raio-X', async () => {
    render(<Home />);
    await screen.findByTestId('ExecutivoPanel');
    fireEvent.click(tab('Monitor do Congresso'));
    fireEvent.click(await screen.findByText('open-politician'));
    expect(await screen.findByTestId('PoliticianProfile')).toHaveAttribute('data-selected', 'pol-9');
  });

  it('erro nos dados essenciais mostra alerta e retry refaz as duas buscas', async () => {
    m('getPresidentes').mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(presidents);
    render(<Home />);
    const alert = await screen.findByRole('alert');
    expect(alert).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByTestId('ExecutivoPanel')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });

  it('erro nas proposições mostra alerta dentro da aba (e não derruba o resto)', async () => {
    m('getLegislativePropositions').mockRejectedValue(new Error('x'));
    render(<Home />);
    await screen.findByTestId('ExecutivoPanel');
    fireEvent.click(tab('Monitor do Congresso'));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByTestId('LegislativePanel')).not.toBeInTheDocument();
    expect(tab('Economia & Mandato')).toBeInTheDocument();
  });

  it('erro na série anual mostra alerta no gráfico mantendo o painel do executivo', async () => {
    m('getAnnualMacroSummary').mockRejectedValue(new Error('x'));
    render(<Home />);
    expect(await screen.findByTestId('ExecutivoPanel')).toBeInTheDocument();
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByTestId('MacroeconomicChart')).not.toBeInTheDocument();
  });

  it('sem nenhum mandato, abas que exigem mandato informam a indisponibilidade', async () => {
    m('getPresidentes').mockResolvedValue([]);
    m('getMandatesPerformance').mockResolvedValue([]);
    render(<Home />);
    await screen.findByTestId('ExecutivoPanel');
    fireEvent.click(tab('Composição de Governo'));
    expect(await screen.findByText('Mandato indisponível')).toBeInTheDocument();
    expect(screen.queryByTestId('CongressCompositionPanel')).not.toBeInTheDocument();
  });

  it('o presidente atual é o ativo, mesmo que não seja o último da lista', async () => {
    m('getPresidentes').mockResolvedValue([presidents[1], { ...presidents[0], status_mandato: 'IMPEACHMENT' }]);
    render(<Home />);
    expect(await screen.findByTestId('ExecutivoPanel')).toHaveAttribute('data-mandate', 'lula-2023');
  });
});
