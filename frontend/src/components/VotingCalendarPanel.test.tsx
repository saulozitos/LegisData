import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, vi, expect, beforeEach } from 'vitest';
import VotingCalendarPanel from './VotingCalendarPanel';
import * as api from '@/services/api';

vi.mock('@/services/api', () => ({ getVotingCalendar: vi.fn() }));
vi.mock('@/components/propositions/PropositionVoteModal', () => ({
  default: ({ propId, onClose }: { propId: string; onClose: () => void }) => (
    <div data-testid="PropositionVoteModal" data-prop={propId}>
      <button onClick={onClose}>Fechar Modal</button>
    </div>
  ),
}));
const getCalendar = api.getVotingCalendar as unknown as ReturnType<typeof vi.fn>;

const session = (id: string, casa: string, aprovada: boolean, url: string | null = 'https://camara.leg.br/p/1') => ({
  sessao_id: id,
  casa,
  casa_nome: casa === 'CAMARA_DOS_DEPUTADOS' ? 'Câmara dos Deputados' : 'Senado Federal',
  hora: '14:30',
  titulo: `Sessão ${id}`,
  descricao: `Descrição ${id}`,
  aprovada,
  placar: { sim: 300, nao: 100, abstencao: 10, total: 410 },
  proposicao: { id: `p${id}`, titulo: `PL ${id}`, tipo: 'PL', numero: 1, ano: 2024, ementa: `Ementa ${id}`, setor: 'Saúde', autor_nome: 'Autora', status: 'x', url_oficial: url },
});

const day = (data: string, mes: number, sessoes: ReturnType<typeof session>[]) => ({
  data,
  dia: 1,
  mes,
  ano: 2024,
  dia_semana: 'Segunda',
  data_formatada: `${data}-fmt`,
  total_votacoes: sessoes.length,
  camara_count: sessoes.filter((s) => s.casa === 'CAMARA_DOS_DEPUTADOS').length,
  senado_count: sessoes.filter((s) => s.casa !== 'CAMARA_DOS_DEPUTADOS').length,
  sessoes,
});

const calendar = (year = 2024) => ({
  ano_selecionado: year,
  anos_disponiveis: [2023, 2024],
  estatisticas_anuais: { ano: year, total_dias_ano: 366, dias_com_votacao: 2, percentual_dias_ativos: 0.5, total_sessoes_ano: 3, texto_estatistica: 'O Congresso votou em 2 dias.' },
  dias: [
    day('2024-02-01', 2, [session('a', 'CAMARA_DOS_DEPUTADOS', true), session('b', 'SENADO_FEDERAL', false, 'javascript:alert(1)')]),
    day('2024-05-10', 5, [session('c', 'CAMARA_DOS_DEPUTADOS', true)]),
  ],
});

beforeEach(() => getCalendar.mockReset());

describe('VotingCalendarPanel', () => {
  it('mostra estatísticas anuais e a primeira data selecionada por padrão', async () => {
    getCalendar.mockResolvedValue(calendar());
    render(<VotingCalendarPanel />);
    expect(screen.getByText('Carregando calendário...')).toBeInTheDocument();

    expect(await screen.findByText(/O Congresso votou em 2 dias/)).toBeInTheDocument();
    expect(screen.getByText('0,5%')).toBeInTheDocument();
    expect(screen.getByText('364 dias sem votações nominais')).toBeInTheDocument();
    expect(screen.getByText('1.5')).toBeInTheDocument(); // 3 votações / 2 dias
    expect(screen.getByRole('heading', { level: 3, name: '2024-02-01-fmt' })).toBeInTheDocument();
    expect(screen.getByText('Sessão a')).toBeInTheDocument();
    expect(screen.getByText('Aprovada')).toBeInTheDocument();
    expect(screen.getByText('Rejeitada')).toBeInTheDocument();
  });

  it('só renderiza links oficiais seguros', async () => {
    getCalendar.mockResolvedValue(calendar());
    render(<VotingCalendarPanel />);
    await screen.findByText('Sessão a');
    const links = screen.getAllByRole('link', { name: /Ler Proposição na Íntegra/ });
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', 'https://camara.leg.br/p/1');
    expect(links[0]).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('seleciona outra data e filtra por mês (meses sem votação ficam desabilitados)', async () => {
    getCalendar.mockResolvedValue(calendar());
    render(<VotingCalendarPanel />);
    await screen.findByText('Sessão a');

    fireEvent.click(screen.getByRole('button', { name: /2024-05-10-fmt/ }));
    expect(screen.getByText('Sessão c')).toBeInTheDocument();
    expect(screen.queryByText('Sessão a')).not.toBeInTheDocument();

    expect(screen.getByRole('button', { name: 'Jan' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /Fev/ }));
    expect(screen.getByRole('button', { name: /Fev/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('button', { name: /2024-05-10-fmt/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Todos os Meses' }));
    expect(screen.getByRole('button', { name: /2024-05-10-fmt/ })).toBeInTheDocument();
  });

  it('troca o ano chamando a API com o ano escolhido via botão ou combobox', async () => {
    getCalendar.mockImplementation((year?: number) => Promise.resolve(calendar(year ?? 2024)));
    render(<VotingCalendarPanel />);
    await screen.findByText('Sessão a');
    fireEvent.click(screen.getByRole('button', { name: '2023' }));
    await waitFor(() => expect(getCalendar).toHaveBeenCalledWith(2023, expect.any(AbortSignal)));
    await waitFor(() => expect(screen.getByRole('button', { name: '2023' })).toHaveAttribute('aria-pressed', 'true'));

    // Seleção de ano via combobox
    const select = screen.getByRole('combobox', { name: /Selecionar ano do calendário/i });
    expect(select).toBeInTheDocument();
    fireEvent.change(select, { target: { value: '2025' } });
    await waitFor(() => expect(getCalendar).toHaveBeenCalledWith(2025, expect.any(AbortSignal)));
  });

  it('falha ao trocar de ano não mostra os dias do ano anterior e mantém o seletor', async () => {
    getCalendar.mockImplementation((year?: number) =>
      year === 2023 ? Promise.reject(new Error('x')) : Promise.resolve(calendar())
    );
    render(<VotingCalendarPanel />);
    await screen.findByText('Sessão a');
    fireEvent.click(screen.getByRole('button', { name: '2023' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('Sessão a')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '2024' })).toBeInTheDocument();
  });

  it('erro inicial mostra alerta e retry recarrega', async () => {
    getCalendar.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(calendar());
    render(<VotingCalendarPanel />);
    const alert = await screen.findByRole('alert');
    fireEvent.click(within(alert).getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('Sessão a')).toBeInTheDocument();
  });

  it('ano sem sessões mostra estado vazio e "Indisponível" na média', async () => {
    getCalendar.mockResolvedValue({
      ...calendar(),
      estatisticas_anuais: { ...calendar().estatisticas_anuais, dias_com_votacao: 0, total_sessoes_ano: 0 },
      dias: [],
    });
    render(<VotingCalendarPanel />);
    expect(await screen.findByText(/Nenhuma sessão de votação nominal/)).toBeInTheDocument();
    expect(screen.getByText('Nenhuma deliberação para exibir')).toBeInTheDocument();
    expect(screen.getByText('Indisponível')).toBeInTheDocument();
  });

  it('abre o modal de votos nominais ao clicar no botão da deliberação', async () => {
    getCalendar.mockResolvedValue(calendar());
    render(<VotingCalendarPanel />);
    await screen.findByText('Sessão a');
    const btnVotos = screen.getAllByRole('button', { name: /Ver Votos Nominais dos Parlamentares/i })[0];
    expect(btnVotos).toBeInTheDocument();
    fireEvent.click(btnVotos);
    expect(screen.getByTestId('PropositionVoteModal')).toHaveAttribute('data-prop', 'pa');
    fireEvent.click(screen.getByText('Fechar Modal'));
    expect(screen.queryByTestId('PropositionVoteModal')).not.toBeInTheDocument();
  });
});
