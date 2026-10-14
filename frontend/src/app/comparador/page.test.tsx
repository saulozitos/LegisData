import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ComparadorPage from './page';
import * as api from '@/services/api';

vi.mock('@/components/Header', () => ({ default: () => <div data-testid="mock-header" /> }));
vi.mock('recharts', async () => (await import('@/test/recharts')).rechartsMock);
vi.mock('@/services/api', () => ({
  getMandatesPerformance: vi.fn(),
  getCompareMandates: vi.fn(),
  getPresidentes: vi.fn(),
}));
const getMandates = api.getMandatesPerformance as unknown as ReturnType<typeof vi.fn>;
const getCompare = api.getCompareMandates as unknown as ReturnType<typeof vi.fn>;
const getPresidentes = api.getPresidentes as unknown as ReturnType<typeof vi.fn>;

const mandate = (id: string, presidente: string, anos: string, over: Record<string, unknown> = {}) => ({
  id_mandato: id,
  presidente,
  partido: 'PT',
  data_inicio: '2023-01-01',
  data_fim: null,
  status_mandato: 'CONCLUIDO',
  anos_cobertos: anos,
  ipca_acumulado_pct: 10,
  ipca_pos_real_pct: 4,
  pib_crescimento_acumulado_pct: 6,
  pib_medio_anual_pct: 2,
  cambio_inicial_usd_brl: 5,
  cambio_final_usd_brl: 5.5,
  cambio_variacao_pct: 10,
  divida_liquida_inicial_pct_pib: 50,
  divida_liquida_final_pct_pib: 55,
  divida_liquida_delta_pct: 5,
  salario_minimo_inicial_brl: 1000,
  salario_minimo_final_brl: 1400,
  salario_minimo_inicial_usd: 200,
  salario_minimo_final_usd: 250,
  ministros_fazenda_principais: [],
  marcos_economicos_principais: [],
  ...over,
});

const list = [
  mandate('bolsonaro-2019', 'Jair Bolsonaro', '2019-2022'),
  mandate('lula-2023', 'Luiz Inácio Lula da Silva', '2023-2026'),
];

const comparison = (over: Record<string, unknown> = {}) => ({
  mandate1: mandate('bolsonaro-2019', 'Jair Bolsonaro', '2019-2022'),
  mandate2: mandate('lula-2023', 'Luiz Inácio Lula da Silva', '2023-2026'),
  deltas: {
    ipca_acumulado_diff_pp: -5,
    ipca_acumulado_relative_pct: -50,
    pib_medio_diff_pp: 1,
    pib_medio_relative_pct: 50,
    pib_acumulado_diff_pp: 2,
    cambio_variacao_diff_pp: null,
    salario_minimo_usd_diff: null,
    salario_minimo_usd_relative_pct: null,
  },
  normalized_trajectory: [{ year: 1, m1_pib: 1, m2_pib: 2, m1_ipca: 4, m2_ipca: 5 }],
  repasses_comparison: {
    by_area: {},
    by_uf: [
      { uf: 'SP', estado_nome: 'São Paulo', regiao: 'Sudeste', m1_total: 2e9, m2_total: 3e9, diff_brl: 1e9, growth_pct: 50, m1_per_capita: 10, m2_per_capita: 20, diff_per_capita: 10, areas: {} },
      { uf: 'BA', estado_nome: 'Bahia', regiao: 'Nordeste', m1_total: 1e9, m2_total: 2e9, diff_brl: 1e9, growth_pct: 100, m1_per_capita: 5, m2_per_capita: 15, diff_per_capita: 10, areas: {} },
    ],
    summary: { m1_total_geral: 3e9, m2_total_geral: 5e9, diff_total_brl: 2e9, growth_total_pct: 66 },
  },
  scores_prosperidade: {
    mandate1: { score_geral: 55, subscore_economico: 50, subscore_social: 60, subscore_estabilidade: 55, classificacao: 'Regular', destaque_positivo: 'Emprego em alta', destaque_atencao: 'Inflação' },
    mandate2: { score_geral: 70, subscore_economico: 75, subscore_social: 65, subscore_estabilidade: 70, classificacao: 'Bom', destaque_positivo: 'PIB forte', destaque_atencao: 'Dívida' },
    delta_score_geral: 15,
    delta_economico: 25,
    delta_social: 5,
    delta_estabilidade: 15,
  },
  ...over,
});

const presidents = [{ id_referencia: 'lula-2023', nome_eleitoral: 'Lula', foto_url: null }];

beforeEach(() => {
  getMandates.mockReset();
  getCompare.mockReset();
  getPresidentes.mockReset();
  getMandates.mockResolvedValue(list);
  getPresidentes.mockResolvedValue(presidents);
  getCompare.mockResolvedValue(comparison());
});

describe('ComparadorPage', () => {
  it('compara por padrão os dois mandatos mais recentes', async () => {
    render(<ComparadorPage />);
    expect(screen.getByTestId('mock-header')).toBeInTheDocument();
    expect(screen.getByText('Carregando mandatos...')).toBeInTheDocument();
    await waitFor(() => expect(getCompare).toHaveBeenCalledWith('bolsonaro-2019', 'lula-2023', expect.any(AbortSignal)));
    expect(await screen.findByText('Score Sintético de Prosperidade Presidencial')).toBeInTheDocument();
    expect((screen.getByLabelText('Selecione o Primeiro Mandato:') as HTMLSelectElement).value).toBe('bolsonaro-2019');
    expect((screen.getByLabelText('Selecione o Segundo Mandato:') as HTMLSelectElement).value).toBe('lula-2023');
    expect(screen.getByText('+15,0 pts (Luiz)')).toBeInTheDocument();
  });

  it('trocar os seletores e inverter refazem a comparação com os ids certos', async () => {
    getMandates.mockResolvedValue([mandate('fhc-1995', 'Fernando Henrique Cardoso', '1995-1998'), ...list]);
    render(<ComparadorPage />);
    await screen.findByText('Score Sintético de Prosperidade Presidencial');

    fireEvent.change(screen.getByLabelText('Selecione o Primeiro Mandato:'), { target: { value: 'fhc-1995' } });
    await waitFor(() => expect(getCompare).toHaveBeenLastCalledWith('fhc-1995', 'lula-2023', expect.any(AbortSignal)));

    fireEvent.click(screen.getByRole('button', { name: 'Inverter Mandatos' }));
    await waitFor(() => expect(getCompare).toHaveBeenLastCalledWith('lula-2023', 'fhc-1995', expect.any(AbortSignal)));
  });

  it('presets só aparecem quando os dois mandatos existem e aplicam a seleção', async () => {
    render(<ComparadorPage />);
    await screen.findByText('Score Sintético de Prosperidade Presidencial');
    const preset = screen.getByRole('button', { name: 'Bolsonaro vs Lula 3' });
    expect(screen.queryByRole('button', { name: 'FHC 1 vs Lula 1' })).not.toBeInTheDocument();
    getCompare.mockClear();
    fireEvent.click(preset);
    expect(getCompare).not.toHaveBeenCalled(); // já era a seleção atual: sem nova chamada
  });

  it('delta nulo não imprime "null" e a diferença negativa aponta para o primeiro mandato', async () => {
    getCompare.mockResolvedValue(comparison({
      scores_prosperidade: { ...comparison().scores_prosperidade, delta_score_geral: -8 },
    }));
    render(<ComparadorPage />);
    expect(await screen.findByText('+8,0 pts (Jair)')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/null|undefined|NaN/);
  });

  it('alternar a métrica do gráfico marca o botão correspondente', async () => {
    render(<ComparadorPage />);
    await screen.findByText('Score Sintético de Prosperidade Presidencial');
    const pressed = screen.getAllByRole('button').filter((b) => b.getAttribute('aria-pressed') === 'true');
    expect(pressed.length).toBeGreaterThan(0);
    const inflation = screen.getAllByRole('button').find((b) => /Inflação|IPCA/.test(b.textContent ?? '') && b.hasAttribute('aria-pressed'));
    expect(inflation).toBeDefined();
    fireEvent.click(inflation!);
    expect(inflation).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Inflação Anual IPCA (%)')).toBeInTheDocument();
  });

  it('filtra a tabela de repasses por região e por texto', async () => {
    render(<ComparadorPage />);
    await screen.findByText('Score Sintético de Prosperidade Presidencial');
    expect(screen.getAllByText('São Paulo').length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText('Filtrar estado ou UF'), { target: { value: 'bahia' } });
    await waitFor(() => expect(screen.getAllByRole('row').filter((r) => /São Paulo/.test(r.textContent ?? ''))).toHaveLength(0));
    expect(screen.getAllByRole('row').some((r) => /Bahia/.test(r.textContent ?? ''))).toBe(true);

    fireEvent.change(screen.getByLabelText('Filtrar estado ou UF'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sudeste' }));
    expect(screen.getByRole('button', { name: 'Sudeste' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getAllByRole('row').some((r) => /Bahia/.test(r.textContent ?? ''))).toBe(false);
  });

  it('falha na lista de mandatos mostra alerta com retry', async () => {
    getMandates.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(list);
    render(<ComparadorPage />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('Score Sintético de Prosperidade Presidencial')).toBeInTheDocument();
  });

  it('falha na comparação mostra mensagem própria e retry refaz a chamada', async () => {
    getCompare.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(comparison());
    render(<ComparadorPage />);
    expect(await screen.findByText('Não foi possível comparar os mandatos')).toBeInTheDocument();
    expect(screen.queryByText('Score Sintético de Prosperidade Presidencial')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('Score Sintético de Prosperidade Presidencial')).toBeInTheDocument();
  });

  it('sem mandatos mostra estado vazio e não chama a comparação', async () => {
    getMandates.mockResolvedValue([]);
    render(<ComparadorPage />);
    expect(await screen.findByText('Nenhum mandato disponível')).toBeInTheDocument();
    expect(getCompare).not.toHaveBeenCalled();
  });

  it('resposta sem scores/repasses opcionais não quebra a página', async () => {
    getCompare.mockResolvedValue(comparison({ scores_prosperidade: undefined, repasses_comparison: undefined, normalized_trajectory: undefined }));
    render(<ComparadorPage />);
    await waitFor(() => expect(getCompare).toHaveBeenCalled());
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('Comparador Lado a Lado');
    expect(screen.queryByText('Score Sintético de Prosperidade Presidencial')).not.toBeInTheDocument();
  });
});

const richComparison = () => {
  const base = comparison();
  const social = (a: number, b: number) => ({
    extrema_pobreza_inicial_pct: a,
    extrema_pobreza_final_pct: b,
    analfabetismo_inicial_pct: a,
    analfabetismo_final_pct: b,
    inseguranca_alimentar_inicial_pct: a,
    inseguranca_alimentar_final_pct: b,
    gini_inicial: 0.5,
    gini_final: 0.48,
  });
  return {
    ...base,
    mandate1: { ...base.mandate1, sociais: social(6, 5), desemprego_final_pct: 10, desmatamento_medio_anual_km2: 11000, homicidios_medio: 22, feminicidios_medio: 1.4 },
    mandate2: { ...base.mandate2, sociais: social(4, 3), desemprego_final_pct: 7, desmatamento_medio_anual_km2: 7000, homicidios_medio: 19, feminicidios_medio: 1.2 },
    deltas: {
      ...base.deltas,
      cambio_variacao_diff_pp: -3,
      salario_minimo_brl_diff: 100,
      salario_minimo_brl_relative_pct: 7,
      salario_minimo_usd_diff: 20,
      salario_minimo_usd_relative_pct: 8,
      extrema_pobreza_diff_pp: -2,
      analfabetismo_diff_pp: -2,
      inseguranca_alimentar_diff_pp: -2,
      gini_diff: -0.02,
      homicidios_medio_diff: -3,
      feminicidios_medio_diff: -0.2,
      desmatamento_medio_diff: -4000,
    },
    repasses_comparison: {
      ...base.repasses_comparison,
      by_area: {
        'Saúde': { area: 'Saúde', sublabel: 'SUS', m1_total: 2e9, m2_total: 3e9, diff_brl: 1e9, growth_pct: 50 },
        'Educação': { area: 'Educação', sublabel: 'FNDE', m1_total: 3e9, m2_total: 2e9, diff_brl: -1e9, growth_pct: -33 },
      },
    },
    termometro_repasses_apoio: {
      m1_lider_per_capita: { uf: 'AC', estado: 'Acre', valor_per_capita: 1500 },
      m2_lider_per_capita: { uf: 'RR', estado: 'Roraima', valor_per_capita: 1800 },
      diagnostico: 'Diagnóstico do termômetro.',
    },
  };
};

describe('ComparadorPage — comparação completa', () => {
  it('mostra métricas sociais, ambientais e de segurança com sinais corretos (queda de pobreza não é "N/D")', async () => {
    getCompare.mockResolvedValue(richComparison());
    render(<ComparadorPage />);
    await screen.findByText('Score Sintético de Prosperidade Presidencial');
    expect(screen.getAllByText(/-2,0 p\.p\./).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Inicial: 6%/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/11\.000 km²\/ano/).length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toMatch(/null|undefined|NaN/);
  });

  it('cartões por área e termômetro de repasses aparecem só quando a API os retorna', async () => {
    getCompare.mockResolvedValue(richComparison());
    render(<ComparadorPage />);
    await screen.findByText('Termômetro de Repasses & Disparidade Regional Per Capita');
    expect(screen.getByText('Saúde (SUS & FNS)')).toBeInTheDocument();
    expect(screen.getByText('Educação (FUNDEB & FNDE)')).toBeInTheDocument();
    expect(screen.queryByText('Infraestrutura & Cidades')).not.toBeInTheDocument();
    expect(screen.getByText('Diagnóstico do termômetro.')).toBeInTheDocument();
    expect(screen.getByText(/Acre \(AC\)/)).toBeInTheDocument();
    expect(screen.getByText('+50,0%')).toBeInTheDocument();
  });

  it('percorre todas as métricas do gráfico e marca cada uma como ativa', async () => {
    getCompare.mockResolvedValue(richComparison());
    render(<ComparadorPage />);
    await screen.findByText('Score Sintético de Prosperidade Presidencial');
    const group = screen.getByRole('button', { name: 'PIB (%)' }).parentElement as HTMLElement;
    const buttons = within(group).getAllByRole('button');
    expect(buttons.length).toBe(10);
    for (const btn of buttons) {
      fireEvent.click(btn);
      expect(btn).toHaveAttribute('aria-pressed', 'true');
      expect(buttons.filter((b) => b.getAttribute('aria-pressed') === 'true')).toHaveLength(1);
    }
  });

  it('valores ausentes viram "N/D" (nunca 0 nem null)', async () => {
    const data = richComparison();
    data.mandate1 = { ...data.mandate1, sociais: {}, desmatamento_medio_anual_km2: null as unknown as number, homicidios_medio: null as unknown as number };
    data.deltas = { ...data.deltas, extrema_pobreza_diff_pp: null as unknown as number, homicidios_medio_diff: null as unknown as number };
    getCompare.mockResolvedValue(data);
    render(<ComparadorPage />);
    await screen.findByText('Score Sintético de Prosperidade Presidencial');
    expect(screen.getAllByText('N/D').length).toBeGreaterThan(2);
    expect(document.body.textContent).not.toMatch(/null|undefined|NaN/);
  });

  it('valores monetários grandes usam bi/mi', async () => {
    getCompare.mockResolvedValue(richComparison());
    render(<ComparadorPage />);
    await screen.findByText('Score Sintético de Prosperidade Presidencial');
    expect(screen.getAllByText(/R\$ 3,00 bi/).length).toBeGreaterThan(0);
  });

  it("renderiza Dimensão 4: Governabilidade & Poder Legislativo (IPLE) quando os mandatos contêm iple", async () => {
    const mockIple1 = {
      mandato_id: "bolsonaro-2019",
      presidente: "Jair Bolsonaro",
      periodo: "2019-2022",
      indicadores_base: {
        proposicoes_executivo_total: 242,
        proposicoes_executivo_aprovadas: 179,
        vetos_total_apreciados: 158,
        vetos_mantidos: 99,
        vetos_pendentes_pauta: 0,
        taxa_sucesso_ts: 0.7397,
        taxa_manutencao_vetos_tmv: 0.6266,
        iple_score: 0.6832,
      },
      variaveis_contextuais: {
        tamanho_oposicao_x1: 0.2827,
        oposicao_cadeiras: 145,
        total_cadeiras: 513,
        fragmentacao_nep_x2: 16.41,
        polarizacao_ipp_x3: 4.40,
      },
      calibragem_crisp_set: {
        ts: { score: 0.7397, corte: 0.87, crisp_val: 0, classificacao: "Sucesso Baixo" },
        tmv: { score: 0.6266, corte: 0.70, crisp_val: 0, classificacao: "Manutenção Baixa" },
        iple: { score: 0.6832, corte: 0.785, crisp_val: 0, classificacao: "Executivo Fraco" },
        oposicao_x1: { score: 0.2827, corte: 0.334, crisp_val: 0, classificacao: "Oposição Fraca" },
        fragmentacao_x2: { score: 16.41, corte: 8.45, crisp_val: 1, classificacao: "Parlamento Fragmentado" },
        polarizacao_x3: { score: 4.40, corte: 2.2, crisp_val: 1, classificacao: "Parlamento Polarizado" },
      },
      classificacao_geral: "Executivo Fraco",
    };
    const mockIple2 = {
      mandato_id: "lula-2023",
      presidente: "Luiz Inácio Lula da Silva",
      periodo: "2023-2026",
      indicadores_base: {
        proposicoes_executivo_total: 84,
        proposicoes_executivo_aprovadas: 69,
        vetos_total_apreciados: 48,
        vetos_mantidos: 33,
        vetos_pendentes_pauta: 12,
        taxa_sucesso_ts: 0.8214,
        taxa_manutencao_vetos_tmv: 0.6875,
        iple_score: 0.7545,
      },
      variaveis_contextuais: {
        tamanho_oposicao_x1: 0.2359,
        oposicao_cadeiras: 121,
        total_cadeiras: 513,
        fragmentacao_nep_x2: 9.93,
        polarizacao_ipp_x3: 4.55,
      },
      calibragem_crisp_set: {
        ts: { score: 0.8214, corte: 0.87, crisp_val: 0, classificacao: "Sucesso Baixo" },
        tmv: { score: 0.6875, corte: 0.70, crisp_val: 0, classificacao: "Manutenção Baixa" },
        iple: { score: 0.7545, corte: 0.785, crisp_val: 0, classificacao: "Executivo Fraco" },
        oposicao_x1: { score: 0.2359, corte: 0.334, crisp_val: 0, classificacao: "Oposição Fraca" },
        fragmentacao_x2: { score: 9.93, corte: 8.45, crisp_val: 1, classificacao: "Parlamento Fragmentado" },
        polarizacao_x3: { score: 4.55, corte: 2.2, crisp_val: 1, classificacao: "Parlamento Polarizado" },
      },
      classificacao_geral: "Executivo Fraco",
    };

    getMandates.mockResolvedValue(list);
    getCompare.mockResolvedValue({
      ...comparison(),
      mandate1: { ...comparison().mandate1, iple: mockIple1 },
      mandate2: { ...comparison().mandate2, iple: mockIple2 },
    });

    render(<ComparadorPage />);
    expect(await screen.findByText(/Dimensão 4: Governabilidade & Poder Legislativo/i)).toBeInTheDocument();
    expect(screen.getByText("0.683")).toBeInTheDocument();
    expect(screen.getByText(/0\.754/)).toBeInTheDocument();
    expect(screen.getByText("74.0%")).toBeInTheDocument();
    expect(screen.getByText("82.1%")).toBeInTheDocument();
  });
});
