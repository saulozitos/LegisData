import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, vi, expect, beforeEach } from 'vitest';
import CongressCompositionPanel from './CongressCompositionPanel';
import * as api from '@/services/api';

vi.mock('recharts', async () => (await import('@/test/recharts')).rechartsMock);
vi.mock('@/services/api', () => ({
  getCongressComposition: vi.fn(),
  searchPoliticians: vi.fn(),
}));
const getComposition = api.getCongressComposition as unknown as ReturnType<typeof vi.fn>;
const search = api.searchPoliticians as unknown as ReturnType<typeof vi.fn>;

const house = (total: number, parties: string[]) => ({
  total_cadeiras: total,
  presidentes: [
    { nome: 'Presidente Casa', partido: 'PP', uf: 'AL', periodo: '2023 - 2025', foto_url: 'https://x.org/p.jpg' },
    { nome: 'Sem Foto', partido: 'MDB', uf: 'PA', periodo: '2025 - 2027', foto_url: 'javascript:x' },
  ],
  bancadas: parties.map((p, i) => ({ partido: p, cadeiras: 10 - i, percentual: 10, alinhamento: 'BASE_GOVERNO', cor_hex: '#123456' })),
  governabilidade: {
    base_aliada_cadeiras: 100,
    base_aliada_pct: 20,
    centro_cadeiras: 200,
    centro_pct: 40,
    oposicao_cadeiras: 200,
    oposicao_pct: 40,
    maioria_simples_atingida: false,
    maioria_pec_atingida: true,
  },
});

const composition = {
  mandato_id: 'm1',
  presidente_republica: 'Fulano da Silva',
  periodo: '2023-2026',
  camara: house(513, ['PT', 'PL']),
  senado: house(81, ['MDB']),
};

const politician = (id: string, nome: string, uf: string, party: string = 'PT') => ({
  id,
  nome_eleitoral: nome,
  nome_civil: `${nome} Civil`,
  cargo: 'DEPUTADO_FEDERAL',
  partido_sigla: party,
  uf,
  foto_url: null,
});

beforeEach(() => {
  getComposition.mockReset();
  search.mockReset();
});

describe('CongressCompositionPanel', () => {
  it('calcula os quóruns a partir do total de cadeiras da API e troca de casa', async () => {
    getComposition.mockResolvedValue(composition);
    render(<CongressCompositionPanel mandateId="m1" />);
    expect(screen.getByRole('status')).toBeInTheDocument();

    expect(await screen.findByText(/Maioria Simples \(257 votos\)/)).toBeInTheDocument();
    expect(screen.getByText(/Quórum de PEC \(308 votos - 3\/5\)/)).toBeInTheDocument();
    expect(screen.getByText(/Dependente de negociação/)).toBeInTheDocument();
    expect(screen.getByText(/Alcançado pela coalizão/)).toBeInTheDocument();
    expect(screen.getByText('Fulano da Silva')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Senado Federal' }));
    expect(screen.getByText(/Maioria Simples \(41 votos\)/)).toBeInTheDocument();
    expect(screen.getByText(/Quórum de PEC \(49 votos - 3\/5\)/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Senado Federal' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('sem bancadas classificadas não mostra barra nem quóruns como "não atingido"', async () => {
    const semClassificacao = {
      ...composition,
      camara: {
        ...composition.camara,
        governabilidade: {
          base_aliada_cadeiras: null,
          base_aliada_pct: null,
          centro_cadeiras: null,
          centro_pct: null,
          oposicao_cadeiras: null,
          oposicao_pct: null,
          maioria_simples_atingida: null,
          maioria_pec_atingida: null,
        },
      },
    };
    getComposition.mockResolvedValue(semClassificacao);
    const { container } = render(<CongressCompositionPanel mandateId="m1" />);
    expect(await screen.findByText(/ainda não foram classificadas como base, centro ou oposição/)).toBeInTheDocument();
    expect(screen.queryByText(/Dependente de negociação/)).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/null/);
  });

  it('com classificação parcial mostra a maioria como indeterminada', async () => {
    const parcial = {
      ...composition,
      camara: {
        ...composition.camara,
        governabilidade: {
          ...composition.camara.governabilidade,
          nao_classificadas_cadeiras: 40,
          maioria_simples_atingida: null,
          maioria_pec_atingida: null,
        },
      },
    };
    getComposition.mockResolvedValue(parcial);
    render(<CongressCompositionPanel mandateId="m1" />);
    expect(await screen.findAllByText(/Indetermin.*40 cadeiras ainda sem classificação/)).toHaveLength(2);
    expect(screen.queryByText(/Dependente de negociação/)).not.toBeInTheDocument();
  });

  it('exibe presidentes da casa, usando sigla quando a foto é insegura', async () => {
    getComposition.mockResolvedValue(composition);
    const { container } = render(<CongressCompositionPanel mandateId="m1" />);
    await screen.findByText('Presidente Casa');
    expect(container.querySelectorAll('img')).toHaveLength(1);
    expect(screen.getByText('Sem Foto')).toBeInTheDocument();
  });

  it('abre o modal da bancada, lista parlamentares e filtra', async () => {
    getComposition.mockResolvedValue(composition);
    search.mockResolvedValue({ politicos: [politician('1', 'Ana', 'SP'), politician('2', 'Bia', 'RJ')] });
    render(<CongressCompositionPanel mandateId="m1" />);
    await screen.findByText('Presidente Casa');

    fireEvent.click(screen.getByRole('button', { name: 'PT · 10' }));
    const dialog = await screen.findByRole('dialog');
    expect(search).toHaveBeenCalledWith(undefined, 'DEPUTADO_FEDERAL', 'PT', undefined, 200, 'm1', expect.any(AbortSignal));
    expect(await within(dialog).findByText('Ana')).toBeInTheDocument();
    expect(within(dialog).getByText('2 parlamentares')).toBeInTheDocument();

    fireEvent.change(within(dialog).getByLabelText(/Buscar parlamentar do PT/), { target: { value: 'rj' } });
    expect(within(dialog).queryByText('Ana')).not.toBeInTheDocument();
    expect(within(dialog).getByText('1 parlamentares')).toBeInTheDocument();

    fireEvent.change(within(dialog).getByLabelText(/Buscar parlamentar do PT/), { target: { value: 'zzz' } });
    expect(within(dialog).getByText('Nenhum parlamentar encontrado')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Limpar busca' }));
    expect(within(dialog).getByText('Ana')).toBeInTheDocument();
  });

  it('seleciona um parlamentar, fecha o modal e notifica (ambos os callbacks)', async () => {
    getComposition.mockResolvedValue(composition);
    search.mockResolvedValue({ politicos: [politician('1', 'Ana', 'SP')] });
    const onSelect = vi.fn();
    render(<CongressCompositionPanel mandateId="m1" onSelectPolitician={onSelect} />);
    await screen.findByText('Presidente Casa');
    fireEvent.click(screen.getByRole('button', { name: 'PT · 10' }));
    fireEvent.click(await screen.findByTitle(/Raio-X de Ana/));
    expect(onSelect).toHaveBeenCalledWith('1');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('usa onPoliticianSelect como alternativa', async () => {
    getComposition.mockResolvedValue(composition);
    search.mockResolvedValue({ politicos: [politician('7', 'Caio', 'MG')] });
    const alt = vi.fn();
    render(<CongressCompositionPanel mandateId="m1" onPoliticianSelect={alt} />);
    await screen.findByText('Presidente Casa');
    fireEvent.click(screen.getByRole('button', { name: 'PL · 9' }));
    fireEvent.click(await screen.findByTitle(/Raio-X de Caio/));
    expect(alt).toHaveBeenCalledWith('7');
  });

  it('ao selecionar uma legenda menor (ex: NOVO), busca exatamente os parlamentares daquele partido', async () => {
    const compPartidos = {
      ...composition,
      camara: {
        ...composition.camara,
        bancadas: [
          { partido: 'PT', cadeiras: 10, percentual: 50, alinhamento: 'BASE_GOVERNO', cor_hex: '#ef4444' },
          { partido: 'PL', cadeiras: 6, percentual: 30, alinhamento: 'OPOSICAO', cor_hex: '#1d4ed8' },
          { partido: 'NOVO', cadeiras: 4, percentual: 20, alinhamento: 'OPOSICAO', cor_hex: '#f97316' },
        ],
      },
    };
    getComposition.mockResolvedValue(compPartidos);
    search.mockResolvedValue({
      politicos: [
        politician('2', 'Deputado Novo 1', 'RS', 'NOVO'),
        politician('3', 'Deputado Novo 2', 'SP', 'NOVO'),
      ],
    });

    render(<CongressCompositionPanel mandateId="m1" />);
    await screen.findByText('Presidente Casa');

    fireEvent.click(screen.getByRole('button', { name: 'NOVO · 4' }));
    const dialog = await screen.findByRole('dialog');
    expect(search).toHaveBeenCalledWith(undefined, 'DEPUTADO_FEDERAL', 'NOVO', undefined, 200, 'm1', expect.any(AbortSignal));
    expect(within(dialog).getByRole('heading', { name: /Parlamentares do NOVO/ })).toBeInTheDocument();
    expect(within(dialog).getByText('Deputado Novo 1')).toBeInTheDocument();
    expect(within(dialog).getByText('Deputado Novo 2')).toBeInTheDocument();
    expect(within(dialog).getByText('2 parlamentares')).toBeInTheDocument();
  });

  it('onSelectParty substitui o modal interno', async () => {
    getComposition.mockResolvedValue(composition);
    const onParty = vi.fn();
    render(<CongressCompositionPanel mandateId="m1" onSelectParty={onParty} />);
    await screen.findByText('Presidente Casa');
    fireEvent.click(screen.getByRole('button', { name: 'PT · 10' }));
    expect(onParty).toHaveBeenCalledWith('PT');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(search).not.toHaveBeenCalled();
  });

  it('fecha o modal com Esc e botão Fechar', async () => {
    getComposition.mockResolvedValue(composition);
    search.mockResolvedValue({ politicos: [] });
    render(<CongressCompositionPanel mandateId="m1" />);
    await screen.findByText('Presidente Casa');
    fireEvent.click(screen.getByRole('button', { name: 'PT · 10' }));
    expect(await screen.findByText(/Nenhum membro registrado para o PT/)).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'PL · 9' }));
    const closeButtons = await screen.findAllByRole('button', { name: 'Fechar' });
    expect(closeButtons).toHaveLength(2); // X do cabeçalho e botão do rodapé
    fireEvent.click(closeButtons[1]);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('erro ao carregar parlamentares mostra alerta com retry', async () => {
    getComposition.mockResolvedValue(composition);
    search.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce({ politicos: [politician('1', 'Ana', 'SP')] });
    render(<CongressCompositionPanel mandateId="m1" />);
    await screen.findByText('Presidente Casa');
    fireEvent.click(screen.getByRole('button', { name: 'PT · 10' }));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByRole('alert')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: /tentar novamente/i }));
    expect(await within(dialog).findByText('Ana')).toBeInTheDocument();
  });

  it('erro principal mostra alerta e retry; resposta nula mostra vazio', async () => {
    getComposition.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(composition);
    render(<CongressCompositionPanel mandateId="m1" />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('Presidente Casa')).toBeInTheDocument();
  });

  it('resposta nula mostra estado indisponível', async () => {
    getComposition.mockResolvedValue(null);
    render(<CongressCompositionPanel mandateId="m1" />);
    expect(await screen.findByText('Composição do Congresso indisponível')).toBeInTheDocument();
  });

  it('o tooltip descreve a bancada sem imprimir undefined', async () => {
    getComposition.mockResolvedValue(composition);
    render(<CongressCompositionPanel mandateId="m1" />);
    await screen.findByText('Presidente Casa');
    expect(screen.getByTestId('tooltip-fmt').textContent).toContain('cadeiras');
    expect(document.body.textContent).not.toMatch(/undefined|NaN/);
  });

  it("renderiza o painel do IPLE e permite alternar a metodologia científica", async () => {
    const mockIple = {
      mandato_id: "m1",
      presidente: "Fulano da Silva",
      periodo: "2023-2026",
      indicadores_base: {
        proposicoes_executivo_total: 100,
        proposicoes_executivo_aprovadas: 85,
        vetos_total_apreciados: 20,
        vetos_mantidos: 16,
        vetos_pendentes_pauta: 2,
        taxa_sucesso_ts: 0.85,
        taxa_manutencao_vetos_tmv: 0.80,
        iple_score: 0.825,
      },
      variaveis_contextuais: {
        tamanho_oposicao_x1: 0.25,
        oposicao_cadeiras: 128,
        total_cadeiras: 513,
        fragmentacao_nep_x2: 9.5,
        polarizacao_ipp_x3: 3.2,
      },
      calibragem_crisp_set: {
        ts: { score: 0.85, corte: 0.87, crisp_val: 0, classificacao: "Sucesso Baixo" },
        tmv: { score: 0.80, corte: 0.70, crisp_val: 1, classificacao: "Manutenção Alta" },
        iple: { score: 0.825, corte: 0.785, crisp_val: 1, classificacao: "Executivo Forte / Poderoso" },
        oposicao_x1: { score: 0.25, corte: 0.334, crisp_val: 0, classificacao: "Oposição Fraca" },
        fragmentacao_x2: { score: 9.5, corte: 8.45, crisp_val: 1, classificacao: "Parlamento Fragmentado" },
        polarizacao_x3: { score: 3.2, corte: 2.2, crisp_val: 1, classificacao: "Parlamento Polarizado" },
      },
      classificacao_geral: "Executivo Forte / Poderoso",
    };

    getComposition.mockResolvedValue({
      ...composition,
      iple: mockIple,
    });

    render(<CongressCompositionPanel mandateId="m1" />);
    expect(await screen.findByText("Índice de Poder Legislativo do Executivo (IPLE)")).toBeInTheDocument();
    expect(screen.getByText("0.825")).toBeInTheDocument();
    expect(screen.getByText("85.0%")).toBeInTheDocument();
    expect(screen.getByText("80.0%")).toBeInTheDocument();
    expect(screen.getByText("Executivo Forte / Poderoso")).toBeInTheDocument();

    const toggleBtn = screen.getByRole("button", { name: /Entenda a Metodologia IPLE/i });
    expect(screen.queryByText(/Fórmulas & Calibragem Crisp-Set QCA/i)).not.toBeInTheDocument();
    fireEvent.click(toggleBtn);
    expect(screen.getByText(/Fórmulas & Calibragem Crisp-Set QCA/i)).toBeInTheDocument();
  });
});
