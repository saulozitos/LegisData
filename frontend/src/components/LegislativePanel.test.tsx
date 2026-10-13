import React from 'react';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import LegislativePanel from './LegislativePanel';
import * as api from '@/services/api';
import type { ProposicaoLegislativa } from '@/services/api';

vi.mock('@/services/api', () => ({ getPropositionVotes: vi.fn() }));
const getVotes = api.getPropositionVotes as unknown as ReturnType<typeof vi.fn>;

const placar = (sim: number, nao: number, abst: number) => ({ SIM: sim, NAO: nao, ABSTENCAO: abst, TOTAL: sim + nao + abst });
const none = placar(0, 0, 0);

const prop = (over: Partial<ProposicaoLegislativa>): ProposicaoLegislativa => ({
  id: '1',
  camara_id: 1,
  tipo: 'PL',
  numero: 1,
  ano: 2023,
  titulo: 'PL 1/2023 - Saúde',
  ementa: 'Ementa 1',
  area_tematica: 'Saúde',
  data_apresentacao: '2023-01-01',
  status: 'x',
  is_reforma_estrutural: true,
  iniciativa_executivo: false,
  placar: none,
  placar_camara: placar(300, 100, 10),
  placar_senado: none,
  sessao_camara: { sessao_id: 's1', data_hora: '2023-05-01', descricao: 'd', aprovada: true },
  url_oficial: 'https://camara.leg.br/1',
  ...over,
});

const props = [
  prop({}),
  prop({ id: '2', tipo: 'PEC', numero: 2, ano: 2022, titulo: 'PEC 2/2022 - Economia', area_tematica: 'Economia', is_reforma_estrutural: false, autor_nome: 'Dep. Fulano', placar_camara: none, placar_senado: placar(50, 20, 1), sessao_senado: { sessao_id: 's2', data_hora: '2022-05-01', descricao: 'd', aprovada: false }, sessao_camara: null, url_oficial: 'javascript:alert(1)' }),
  prop({ id: '3', numero: 3, titulo: 'PL 3/2023 - Sem resultado', area_tematica: 'Saúde', sessao_camara: null, placar_camara: placar(260, 200, 0), iniciativa_executivo: true, is_reforma_estrutural: false }),
];

const vote = (id: string, nome: string, partido: string, uf: string, decisao: string, polId: string | null = `pol-${id}`) => ({
  voto_id: id,
  politico_id: polId,
  nome_eleitoral: nome,
  nome_civil: `${nome} Civil`,
  partido_sigla: partido,
  uf,
  cargo: 'DEPUTADO_FEDERAL',
  foto_url: null,
  decisao,
  sessao_id: 's1',
  sessao_titulo: 't',
  casa_legislativa: 'CAMARA',
  data_sessao: '2023-05-01',
});

const votesResponse = (over: Record<string, unknown> = {}) => ({
  proposicao: null,
  total: 3,
  votos: [vote('v1', 'Ana', 'PT', 'SP', 'SIM'), vote('v2', 'Bia', 'PL', 'RJ', 'NAO'), vote('v3', 'Caio', 'MDB', 'MG', 'OBSTRUCAO', null)],
  sessoes_disponiveis: [],
  sessao_ativa: null,
  ...over,
});

beforeEach(() => {
  getVotes.mockReset();
  getVotes.mockResolvedValue(votesResponse());
});

describe('LegislativePanel', () => {
  it('sem proposições mostra estado vazio explicativo', () => {
    render(<LegislativePanel propositions={[]} />);
    expect(screen.getByText('Proposições indisponíveis')).toBeInTheDocument();
  });

  it('lista só matérias com votos na casa ativa e alterna para o Senado', () => {
    render(<LegislativePanel propositions={props} />);
    expect(screen.getByText('PL 1/2023 - Saúde')).toBeInTheDocument();
    expect(screen.queryByText('PEC 2/2022 - Economia')).not.toBeInTheDocument();
    expect(screen.getByText('Placar na Câmara (410 votos):')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Senado Federal/ }));
    expect(screen.getByText('PEC 2/2022 - Economia')).toBeInTheDocument();
    expect(screen.queryByText('PL 1/2023 - Saúde')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Senado Federal/ })).toHaveAttribute('aria-pressed', 'true');
  });

  it('o resultado vem da sessão; sem sessão NÃO se infere aprovação pela maioria simples', () => {
    render(<LegislativePanel propositions={props} />);
    expect(screen.getByText('Aprovada')).toBeInTheDocument();
    // PL 3: 260 SIM x 200 NÃO, sem sessão => indisponível (nunca "Aprovada")
    const card = screen.getByText('PL 3/2023 - Sem resultado').closest('article') as HTMLElement;
    expect(within(card).getByText('Resultado indisponível')).toBeInTheDocument();
    expect(within(card).queryByText('Aprovada')).not.toBeInTheDocument();
  });

  it('PEC rejeitada pela sessão aparece como Rejeitada', () => {
    render(<LegislativePanel propositions={props} />);
    fireEvent.click(screen.getByRole('button', { name: /Senado Federal/ }));
    expect(screen.getByText('Rejeitada')).toBeInTheDocument();
    expect(screen.getByText('Dep. Fulano')).toBeInTheDocument();
  });

  it('autor ausente cai para Executivo ou Congresso conforme a iniciativa', () => {
    render(<LegislativePanel propositions={props} />);
    const card = screen.getByText('PL 3/2023 - Sem resultado').closest('article') as HTMLElement;
    expect(within(card).getByText('Poder Executivo Federal')).toBeInTheDocument();
    const card1 = screen.getByText('PL 1/2023 - Saúde').closest('article') as HTMLElement;
    expect(within(card1).getByText('Congresso Nacional')).toBeInTheDocument();
  });

  it('filtros de tema, ano e reformas', () => {
    render(<LegislativePanel propositions={props} />);
    fireEvent.change(screen.getByLabelText('Filtrar por tema'), { target: { value: 'Economia' } });
    expect(screen.getByText(/Nenhuma proposição com votação registrada/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Filtrar por tema'), { target: { value: 'TODOS' } });

    fireEvent.change(screen.getByLabelText('Filtrar por ano'), { target: { value: '2022' } });
    expect(screen.getByText(/Nenhuma proposição com votação registrada/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Filtrar por ano'), { target: { value: 'TODOS' } });

    fireEvent.click(screen.getByRole('button', { name: 'Apenas Reformas' }));
    expect(screen.getByText('PL 1/2023 - Saúde')).toBeInTheDocument();
    expect(screen.queryByText('PL 3/2023 - Sem resultado')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apenas Reformas' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('só renderiza link da íntegra quando a URL é segura', () => {
    render(<LegislativePanel propositions={props} />);
    expect(screen.getAllByRole('link', { name: /Íntegra/ })[0]).toHaveAttribute('href', 'https://camara.leg.br/1');
    fireEvent.click(screen.getByRole('button', { name: /Senado Federal/ }));
    expect(screen.queryByRole('link', { name: /Íntegra/ })).not.toBeInTheDocument();
  });

  it('abre o modal com votos nominais, filtra por decisão e busca; Obstrução não vira Ausente', async () => {
    render(<LegislativePanel propositions={props} />);
    fireEvent.click(screen.getByRole('button', { name: 'PL 1/2023 - Saúde' }));
    const dialog = await screen.findByRole('dialog', { name: 'PL 1/2023 - Saúde' });
    expect(getVotes).toHaveBeenCalledWith('1', 'CAMARA', undefined, undefined, undefined, expect.any(AbortSignal));
    expect(await within(dialog).findByText('Ana')).toBeInTheDocument();
    expect(within(dialog).getByText('Obstrução')).toBeInTheDocument();
    expect(within(dialog).queryByText('Ausente')).not.toBeInTheDocument();
    expect(within(dialog).getByText('Mostrando 3 de 3 votos')).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Sim' }));
    expect(within(dialog).queryByText('Bia')).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: /Todos/ }));
    fireEvent.change(within(dialog).getByLabelText(/Buscar parlamentar/), { target: { value: 'rj' } });
    expect(within(dialog).getByText('Bia')).toBeInTheDocument();
    expect(within(dialog).queryByText('Ana')).not.toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText(/Buscar parlamentar/), { target: { value: 'zzz' } });
    expect(within(dialog).getByText(/Nenhum parlamentar encontrado/)).toBeInTheDocument();
  });

  it('parlamentar e partido do modal navegam e fecham; sem politico_id não é clicável', async () => {
    const onSelectPolitician = vi.fn();
    const onSelectParty = vi.fn();
    render(<LegislativePanel propositions={props} onSelectPolitician={onSelectPolitician} onSelectParty={onSelectParty} />);
    fireEvent.click(screen.getByRole('button', { name: 'PL 1/2023 - Saúde' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Ana' }));
    expect(onSelectPolitician).toHaveBeenCalledWith('pol-v1');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'PL 1/2023 - Saúde' }));
    const dialog2 = await screen.findByRole('dialog');
    expect(within(dialog2).queryByRole('button', { name: 'Caio' })).not.toBeInTheDocument();
    fireEvent.click(await within(dialog2).findByRole('button', { name: 'PL' }));
    expect(onSelectParty).toHaveBeenCalledWith('PL');
  });

  it('seletor de sessão/turno refaz a busca com a sessão escolhida', async () => {
    getVotes.mockResolvedValue(votesResponse({
      sessoes_disponiveis: [
        { id: 'sa', titulo: '1º turno', data_hora: 'x', casa: 'CAMARA', aprovada: true },
        { id: 'sb', titulo: '', data_hora: 'y', casa: 'CAMARA', aprovada: true },
      ],
      sessao_ativa: { id: 'sa', titulo: '1º turno', data_hora: 'x', casa: 'CAMARA', aprovada: true },
    }));
    render(<LegislativePanel propositions={props} />);
    fireEvent.click(screen.getByRole('button', { name: 'PL 1/2023 - Saúde' }));
    const dialog = await screen.findByRole('dialog');
    const first = await within(dialog).findByRole('button', { name: '1º turno' });
    expect(first).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Turno 2' }));
    await waitFor(() => expect(getVotes).toHaveBeenLastCalledWith('1', 'CAMARA', 'sb', undefined, undefined, expect.any(AbortSignal)));
  });

  it('falha ao buscar votos mostra erro (não afirma que a matéria não foi votada) e permite retry', async () => {
    getVotes.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(votesResponse());
    render(<LegislativePanel propositions={props} />);
    fireEvent.click(screen.getByRole('button', { name: 'PL 1/2023 - Saúde' }));
    const dialog = await screen.findByRole('dialog');
    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent('Isso não significa que a matéria não tenha sido votada');
    fireEvent.click(within(alert).getByRole('button', { name: /tentar novamente/i }));
    expect(await within(dialog).findByText('Ana')).toBeInTheDocument();
  });

  it('fecha o modal com Esc e botão; trocar de matéria não mostra votos da anterior', async () => {
    render(<LegislativePanel propositions={props} />);
    fireEvent.click(screen.getByRole('button', { name: 'PL 1/2023 - Saúde' }));
    await screen.findByText('Ana');
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    getVotes.mockImplementation(() => new Promise(() => {}));
    fireEvent.click(screen.getByRole('button', { name: 'PL 3/2023 - Sem resultado' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Carregando lista nominal de votos...')).toBeInTheDocument();
    expect(within(dialog).queryByText('Ana')).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Fechar' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it("sessão com votação secreta exibe aviso oficial e apuração agregada", async () => {
    getVotes.mockResolvedValueOnce({
      ...votesResponse(),
      is_votacao_secreta: true,
      aviso: "Votação secreta oficial do Senado",
      placar: { SIM: 45, NAO: 12, ABSTENCAO: 3, TOTAL: 60 },
      votos: [],
    });
    render(<LegislativePanel propositions={props} />);
    fireEvent.click(screen.getByRole("button", { name: "PL 1/2023 - Saúde" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/Votação Secreta Oficial/)).toBeInTheDocument();
    expect(within(dialog).getByText("Votação secreta oficial do Senado")).toBeInTheDocument();
    expect(within(dialog).getByText("45")).toBeInTheDocument();
    expect(within(dialog).getByText("12")).toBeInTheDocument();
    expect(within(dialog).queryByText("Ana")).not.toBeInTheDocument();
  });
});
