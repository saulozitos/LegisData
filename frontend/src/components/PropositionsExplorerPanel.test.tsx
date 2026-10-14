import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PropositionsExplorerPanel from './PropositionsExplorerPanel';
import * as api from '@/services/api';

vi.mock('@/services/api', () => ({
  getAuthorsProductivityRanking: vi.fn(),
  getLegislativeExplorer: vi.fn(),
  getParties: vi.fn(),
  getCoauthorshipNetwork: vi.fn().mockResolvedValue({
    nodes: [],
    edges: [],
    communities: [],
    stats: {
      total_nodes: 0,
      total_edges: 0,
      total_communities: 0,
      density: 0,
      tipo_filtro: 'ALL',
      top_articulators: [],
    },
  }),
}));
vi.mock('./propositions/PropositionVoteModal', () => ({
  default: ({ propId, onClose, onSelectPolitician }: { propId: string; onClose: () => void; onSelectPolitician?: (id: string) => void }) => (
    <div data-testid="vote-modal" data-prop={propId}>
      <button onClick={onClose}>fechar-modal</button>
      <button onClick={() => onSelectPolitician?.('pol-x')}>abrir-pol</button>
    </div>
  ),
}));

const getRanking = api.getAuthorsProductivityRanking as unknown as ReturnType<typeof vi.fn>;
const getExplorer = api.getLegislativeExplorer as unknown as ReturnType<typeof vi.fn>;
const getParties = api.getParties as unknown as ReturnType<typeof vi.fn>;

const author = (over: Record<string, unknown> = {}) => ({
  posicao: 1,
  politico_id: 'a1',
  nome_eleitoral: 'Baleia Rossi',
  nome_civil: 'Baleia Rossi',
  partido_sigla: 'MDB',
  espectro_politico: 'CENTRO',
  uf: 'SP',
  cargo: 'DEPUTADO_FEDERAL',
  foto_url: null,
  total_proposicoes: 10,
  proposicoes_aprovadas: 2,
  proposicoes_estruturantes: 1,
  score_produtividade: 80,
  classificacao_efetividade: 'Alta',
  principal_setor: 'Saúde',
  total_principal_setor: 5,
  distribuicao_setores: [],
  ...over,
});

const item = (over: Record<string, unknown> = {}) => ({
  id: 'p1',
  tipo: 'PL',
  numero: 1,
  ano: 2023,
  titulo: 'PL 1/2023',
  ementa: 'Ementa um',
  setor: 'Saúde',
  eixo_impacto: 'x',
  autor_nome: 'Fulano',
  autor_partido: 'PT',
  autor_uf: 'SP',
  autor_foto: null,
  status: 'Em tramitação',
  data_apresentacao: '2023-01-01',
  is_reforma_estrutural: true,
  iniciativa_executivo: false,
  tem_votacao: true,
  placar: { sim: 300, nao: 100, abstencao: 10, total: 410, resultado: 'APROVADA' },
  url_oficial: 'https://camara.leg.br/1',
  ...over,
});

const page = (over: Record<string, unknown> = {}) => ({
  total: 2,
  page: 1,
  limit: 15,
  total_pages: 1,
  setores_disponiveis: ['Saúde', 'Educação'],
  items: [item(), item({ id: 'p2', titulo: 'PEC 2/2022', tem_votacao: false, placar: { sim: 0, nao: 0, abstencao: 0, total: 0, resultado: 'REJEITADA' }, is_reforma_estrutural: false, url_oficial: 'javascript:alert(1)' })],
  ...over,
});

beforeEach(() => {
  getRanking.mockReset();
  getExplorer.mockReset();
  getParties.mockReset();
  getRanking.mockResolvedValue([author(), author({ posicao: 2, politico_id: 'a2', nome_eleitoral: 'Outro', total_proposicoes: 4, classificacao_efetividade: 'Volume Alto sem Leis Aprovadas', proposicoes_aprovadas: 0, proposicoes_estruturantes: 0 })]);
  getExplorer.mockResolvedValue(page());
  getParties.mockResolvedValue([{ sigla: 'PT' }, { sigla: 'MDB' }]);
});

describe('PropositionsExplorerPanel', () => {
  it('mostra o ranking (IPLE por padrão) e a tabela de proposições', async () => {
    render(<PropositionsExplorerPanel />);
    expect(screen.getByText('Carregando ranking...')).toBeInTheDocument();
    expect(await screen.findByText('Baleia Rossi')).toBeInTheDocument();
    expect(screen.getByText('Score IPLE Ativo')).toBeInTheDocument();
    expect(screen.getByText('Volume s/ Leis')).toBeInTheDocument();
    expect(await screen.findByText('PL 1/2023')).toBeInTheDocument();
    expect(screen.getByText('2 matérias')).toBeInTheDocument();
    expect(getRanking).toHaveBeenCalledWith(20, undefined, undefined, 'efetividade', expect.any(AbortSignal));
  });

  it('a tabela distingue votada, rejeitada sem votação e links inseguros', async () => {
    render(<PropositionsExplorerPanel />);
    await screen.findByText('PL 1/2023');
    expect(screen.getByText('Sim: 300')).toBeInTheDocument();
    expect(screen.getByText('Sem votação em plenário')).toBeInTheDocument();
    expect(screen.getByText('Aprovada')).toBeInTheDocument();
    expect(screen.getByText('Rejeitada')).toBeInTheDocument();
    expect(screen.getByText('Reforma')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /Íntegra/ })).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Ver Votos' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Detalhes' })).toBeInTheDocument();
  });

  it('alterna o critério para volume e filtra por partido/setor do ranking com opção de limpar', async () => {
    render(<PropositionsExplorerPanel />);
    await screen.findByText('Baleia Rossi');
    fireEvent.click(screen.getByRole('button', { name: /Volume Bruto/ }));
    await waitFor(() => expect(getRanking).toHaveBeenLastCalledWith(20, undefined, undefined, 'volume', expect.any(AbortSignal)));
    expect(await screen.findByText('Volume Bruto', { selector: 'span.text-\\[10px\\]' })).toBeInTheDocument();

    await waitFor(() => expect(within(screen.getByLabelText('Partido:')).getByRole('option', { name: 'PT' })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Partido:'), { target: { value: 'PT' } });
    await waitFor(() => expect(getRanking).toHaveBeenLastCalledWith(20, 'PT', undefined, 'volume', expect.any(AbortSignal)));

    fireEvent.click(screen.getByRole('button', { name: /Limpar/ , description: undefined }));
    await waitFor(() => expect(getRanking).toHaveBeenLastCalledWith(20, undefined, undefined, 'efetividade', expect.any(AbortSignal)));
  });

  it('ranking vazio oferece restaurar filtros', async () => {
    getRanking.mockResolvedValueOnce([author()]).mockResolvedValue([]);
    render(<PropositionsExplorerPanel />);
    await screen.findByText('Baleia Rossi');
    await waitFor(() => expect(within(screen.getByLabelText('Partido:')).getByRole('option', { name: 'PT' })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Partido:'), { target: { value: 'PT' } });
    expect(await screen.findByText(/Nenhum parlamentar encontrado para os filtros/)).toBeInTheDocument();
    getRanking.mockResolvedValue([author()]);
    fireEvent.click(screen.getByRole('button', { name: 'Restaurar todos os parlamentares' }));
    expect(await screen.findByText('Baleia Rossi')).toBeInTheDocument();
  });

  it('navegação para parlamentar e partido a partir do ranking', async () => {
    const onPol = vi.fn();
    const onParty = vi.fn();
    render(<PropositionsExplorerPanel onSelectPolitician={onPol} onSelectParty={onParty} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Baleia Rossi' }));
    expect(onPol).toHaveBeenCalledWith('a1');
    fireEvent.click(screen.getAllByRole('button', { name: 'MDB' })[0]);
    expect(onParty).toHaveBeenCalledWith('MDB');
  });

  it('busca textual com debounce, filtros de setor/tipo e votação nominal chamam a API', async () => {
    render(<PropositionsExplorerPanel />);
    await screen.findByText('PL 1/2023');
    fireEvent.change(screen.getByLabelText('Buscar por título, ementa ou autor'), { target: { value: 'saúde' } });
    await waitFor(() => expect(getExplorer).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'saúde', page: 1 }), expect.any(AbortSignal)));

    fireEvent.change(screen.getByLabelText('Filtrar por partido do autor'), { target: { value: 'PT' } });
    await waitFor(() => expect(getExplorer).toHaveBeenLastCalledWith(expect.objectContaining({ partido: 'PT' }), expect.any(AbortSignal)));

    fireEvent.change(screen.getByLabelText('Filtrar por setor'), { target: { value: 'Educação' } });
    await waitFor(() => expect(getExplorer).toHaveBeenLastCalledWith(expect.objectContaining({ setor: 'Educação' }), expect.any(AbortSignal)));
    fireEvent.change(screen.getByLabelText('Filtrar por tipo de proposição'), { target: { value: 'PEC' } });
    await waitFor(() => expect(getExplorer).toHaveBeenLastCalledWith(expect.objectContaining({ tipo: 'PEC' }), expect.any(AbortSignal)));
    fireEvent.click(screen.getByLabelText('Apenas com votação nominal'));
    await waitFor(() => expect(getExplorer).toHaveBeenLastCalledWith(expect.objectContaining({ apenas_votadas: true }), expect.any(AbortSignal)));

    fireEvent.click(screen.getByRole('button', { name: 'Limpar busca' }));
    await waitFor(() => expect(getExplorer).toHaveBeenLastCalledWith(expect.objectContaining({ search: undefined }), expect.any(AbortSignal)));
  });

  it('paginação avança e volta para a página 1 ao mudar um filtro (sem requisição com página antiga)', async () => {
    getExplorer.mockImplementation((params: { page?: number }) => Promise.resolve(page({ page: params.page ?? 1, total_pages: 3, items: [item({ id: `p${params.page}`, titulo: `Matéria página ${params.page}` })] })));
    render(<PropositionsExplorerPanel />);
    await screen.findByText('Matéria página 1');
    expect(screen.getByRole('button', { name: /Anterior/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /Próxima/ }));
    expect(await screen.findByText('Matéria página 2')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Anterior/ }));
    expect(await screen.findByText('Matéria página 1')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Próxima/ }));
    await screen.findByText('Matéria página 2');
    getExplorer.mockClear();
    fireEvent.click(screen.getByLabelText('Apenas com votação nominal'));
    await screen.findByText('Matéria página 1');
    const pagesRequested = getExplorer.mock.calls.map((c) => c[0].page);
    expect(pagesRequested).toEqual([1]); // nunca pediu a página 2 com o filtro novo
  });

  it('abre o modal de votos pelo título e pelo botão, repassa navegação e fecha', async () => {
    const onPol = vi.fn();
    render(<PropositionsExplorerPanel onSelectPolitician={onPol} />);
    fireEvent.click(await screen.findByRole('button', { name: 'PL 1/2023' }));
    expect(screen.getByTestId('vote-modal')).toHaveAttribute('data-prop', 'p1');
    fireEvent.click(screen.getByText('abrir-pol'));
    expect(onPol).toHaveBeenCalledWith('pol-x');
    fireEvent.click(screen.getByText('fechar-modal'));
    expect(screen.queryByTestId('vote-modal')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Detalhes' }));
    expect(screen.getByTestId('vote-modal')).toHaveAttribute('data-prop', 'p2');
  });

  it('erros do ranking e da lista mostram alertas independentes com retry', async () => {
    getRanking.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce([author()]);
    getExplorer.mockRejectedValueOnce(new Error('y')).mockResolvedValueOnce(page());
    render(<PropositionsExplorerPanel />);
    const alerts = await screen.findAllByRole('alert');
    expect(alerts).toHaveLength(2);
    fireEvent.click(within(alerts[0]).getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('Baleia Rossi')).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole('alert')).getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('PL 1/2023')).toBeInTheDocument();
  });

  it('lista vazia mostra orientação para ajustar filtros', async () => {
    getExplorer.mockResolvedValue(page({ items: [], total: 0 }));
    render(<PropositionsExplorerPanel />);
    expect(await screen.findByText('Nenhuma proposição encontrada')).toBeInTheDocument();
  });

  it('alterna para critério de liderança e apoio político chamando a API com os parâmetros certos', async () => {
    render(<PropositionsExplorerPanel />);
    await screen.findByText('Baleia Rossi');
    fireEvent.click(screen.getByRole('button', { name: /Liderança/ }));
    await waitFor(() => expect(getRanking).toHaveBeenLastCalledWith(20, undefined, undefined, 'lideranca', expect.any(AbortSignal)));
    expect(await screen.findByText('Liderança (Autor Principal)')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Apoio Político/ }));
    await waitFor(() => expect(getRanking).toHaveBeenLastCalledWith(20, undefined, undefined, 'coautoria', expect.any(AbortSignal)));
    expect(await screen.findByText('Apoio Político (Coautor)')).toBeInTheDocument();
  });

  it('exibe e oculta o banner explicativo dos 4 pilares da metodologia', async () => {
    render(<PropositionsExplorerPanel />);
    await screen.findByText('Baleia Rossi');
    expect(screen.queryByText('Metodologia de Atividade Legislativa Ponderada')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Entenda a Pontuação/ }));
    expect(screen.getByText('Metodologia de Atividade Legislativa Ponderada')).toBeInTheDocument();
    expect(screen.getByText(/Autor Principal \(1.0 pt\)/)).toBeInTheDocument();
    expect(screen.getByText(/Alta \(3.0 pts\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Ocultar Metodologia/ }));
    expect(screen.queryByText('Metodologia de Atividade Legislativa Ponderada')).not.toBeInTheDocument();
  });
});
