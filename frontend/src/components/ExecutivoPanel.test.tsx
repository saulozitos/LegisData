import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ExecutivoPanel, { fmt, fmtBRL, deltaColor } from './ExecutivoPanel';
import type { MandatoPerformance, PresidenteHistorico, ResumoMacroeconomicoAnual } from '@/services/api';

vi.mock('recharts', async () => (await import('@/test/recharts')).rechartsMock);

describe('helpers', () => {
  it('fmt trata null/undefined/NaN/Infinity como "—" e preserva zero', () => {
    for (const bad of [null, undefined, NaN, Infinity]) expect(fmt(bad)).toBe('—');
    expect(fmt(0)).toBe('0.0');
    expect(fmt(1.234, 2, 'R$', '%')).toBe('R$1.23%');
  });

  it('fmtBRL formata em reais sem decimais e trata ausente', () => {
    expect(fmtBRL(null)).toBe('—');
    expect(fmtBRL(NaN)).toBe('—');
    expect(fmtBRL(1412).replace(/\s/g, ' ')).toBe('R$ 1.412');
  });

  it('deltaColor respeita a inversão (queda é boa)', () => {
    expect(deltaColor(null)).toBe('text-slate-400');
    expect(deltaColor(0)).toBe('text-slate-400');
    expect(deltaColor(2)).toBe('text-emerald-400');
    expect(deltaColor(-2)).toBe('text-rose-400');
    expect(deltaColor(2, true)).toBe('text-rose-400');
    expect(deltaColor(-2, true)).toBe('text-emerald-400');
  });
});

const perf = (over: Partial<MandatoPerformance> = {}): MandatoPerformance => ({
  id_mandato: 'lula-2023',
  presidente: 'Luiz Inácio Lula da Silva',
  partido: 'PT',
  data_inicio: '2023-01-01',
  data_fim: '2024-12-31',
  status_mandato: 'EM_EXERCICIO',
  anos_cobertos: '2023-2024',
  ipca_acumulado_pct: 9,
  ipca_pos_real_pct: 4.5,
  pib_crescimento_acumulado_pct: 6,
  pib_medio_anual_pct: 3,
  cambio_inicial_usd_brl: 5,
  cambio_final_usd_brl: 5.5,
  cambio_variacao_pct: 10,
  divida_liquida_inicial_pct_pib: 55,
  divida_liquida_final_pct_pib: 60,
  divida_liquida_delta_pct: 5,
  salario_minimo_inicial_brl: 1302,
  salario_minimo_final_brl: 1412,
  salario_minimo_inicial_usd: 250,
  salario_minimo_final_usd: 260,
  desemprego_inicial_pct: 8,
  desemprego_final_pct: 6,
  desmatamento_acumulado_km2: 15000,
  desmatamento_medio_anual_km2: 7500,
  fome_inicial_pct: 8,
  fome_final_pct: 4,
  homicidios_medio: 22,
  feminicidios_medio: 1.2,
  ministros_fazenda_principais: ['Haddad'],
  marcos_economicos_principais: [],
  ...over,
});

const meta = (over: Partial<PresidenteHistorico> = {}): PresidenteHistorico => ({
  id_referencia: 'lula-2023',
  nome_civil: 'Luiz Inácio Lula da Silva',
  nome_eleitoral: 'Lula',
  partido_sigla: 'PT',
  partido_nome: 'PT',
  mandato_numero: 3,
  ano_eleicao: 2022,
  data_inicio: '2023-01-01',
  data_fim: null,
  status_mandato: 'EM_EXERCICIO',
  ministros_fazenda_chave: [{ nome: 'Fernando Haddad', inicio: '2023-01-01', fim: null, papel: 'Fazenda' }],
  marcos_economicos: ['Marco A', 'Marco B'],
  ...over,
});

const year = (ano: number, over: Partial<ResumoMacroeconomicoAnual> = {}): ResumoMacroeconomicoAnual => ({
  ano,
  presidente_dominante: 'Lula',
  ipca_acumulado_ano_pct: 4.5,
  pib_crescimento_real_pct: 3,
  taxa_desemprego_anual: 7,
  taxa_desmatamento_amazonia: 9000,
  salario_minimo_nominal_brl: 1412,
  cambio_dolar_medio: 5,
  divida_liquida_pct_pib: 60,
  ...over,
});

const annual = [year(2020), year(2023), year(2024)];

describe('ExecutivoPanel', () => {
  it('sem seleção pede para escolher um presidente', () => {
    render(<ExecutivoPanel performance={null} presidentMeta={null} annualData={[]} mandateId={null} allPerformances={[]} />);
    expect(screen.getByText('Selecione um presidente na Linha do Tempo')).toBeInTheDocument();
  });

  it('mostra KPIs do mandato com deltas e marca "Em exercício"', () => {
    render(<ExecutivoPanel performance={perf()} presidentMeta={meta()} annualData={annual} mandateId="lula-2023" allPerformances={[perf()]} />);
    expect(screen.getByRole('heading', { level: 2, name: 'Luiz Inácio Lula da Silva' })).toBeInTheDocument();
    expect(screen.getByText('Em exercício')).toBeInTheDocument();
    expect(screen.getByText('3.0%')).toBeInTheDocument(); // PIB médio
    expect(screen.getByText('4.5%/a')).toBeInTheDocument();
    expect(screen.getByText('R$5.50')).toBeInTheDocument();
    expect(screen.getByText('+0.5 pp (início→fim)')).toBeInTheDocument(); // câmbio
    expect(screen.getByText('-2.0 pp (início→fim)')).toBeInTheDocument(); // desemprego
    expect(screen.getByText('Fernando Haddad')).toBeInTheDocument();
    expect(screen.getByText('Marcos Estruturantes do Mandato')).toBeInTheDocument();
  });

  it.each(['IMPEACHMENT', 'CONCLUIDO', 'RENUNCIA'])('status %s NÃO é "Em exercício"', (status) => {
    render(<ExecutivoPanel performance={perf({ status_mandato: status })} presidentMeta={meta()} annualData={annual} mandateId="lula-2023" allPerformances={[perf()]} />);
    expect(screen.queryByText('Em exercício')).not.toBeInTheDocument();
  });

  it('valores ausentes viram "—" (nunca null/NaN/undefined) e seções opcionais somem', () => {
    const sparse = perf({
      pib_medio_anual_pct: null as unknown as number,
      ipca_pos_real_pct: null as unknown as number,
      ipca_acumulado_pct: null as unknown as number,
      cambio_final_usd_brl: null,
      cambio_inicial_usd_brl: null,
      divida_liquida_final_pct_pib: null,
      divida_liquida_delta_pct: null,
      salario_minimo_final_brl: null,
      salario_minimo_inicial_brl: null,
      desemprego_final_pct: null,
      desemprego_inicial_pct: null,
      desmatamento_acumulado_km2: null,
      fome_final_pct: null,
      homicidios_medio: null,
      feminicidios_medio: null,
    });
    render(<ExecutivoPanel performance={sparse} presidentMeta={null} annualData={[]} mandateId="lula-2023" allPerformances={[]} />);
    expect(document.body.textContent).not.toMatch(/NaN|undefined|null/);
    expect(screen.getAllByText(/—/).length).toBeGreaterThan(3);
    expect(screen.queryByText('Desmatamento Amazônia')).not.toBeInTheDocument();
    expect(screen.queryByText('Insegurança Alimentar')).not.toBeInTheDocument();
    expect(screen.queryByText('Homicídios')).not.toBeInTheDocument();
  });

  it('hiperinflação acumulada não é impressa como percentual', () => {
    render(<ExecutivoPanel performance={perf({ ipca_acumulado_pct: 1_000_000 })} presidentMeta={meta()} annualData={annual} mandateId="lula-2023" allPerformances={[]} />);
    expect(screen.getByText('Acum.: hiperinfl.')).toBeInTheDocument();
  });

  it('usa os ministros do mandato quando não há meta e informa quando não há nenhum', () => {
    const { rerender } = render(<ExecutivoPanel performance={perf()} presidentMeta={null} annualData={annual} mandateId="lula-2023" allPerformances={[]} />);
    expect(screen.getByText('Haddad')).toBeInTheDocument();
    rerender(<ExecutivoPanel performance={perf({ ministros_fazenda_principais: [] })} presidentMeta={meta({ ministros_fazenda_chave: [] })} annualData={annual} mandateId="lula-2023" allPerformances={[]} />);
    expect(screen.getByText('Informação não disponível para este mandato.')).toBeInTheDocument();
  });

  it('ranking só aparece com mais de um mandato e destaca o selecionado', () => {
    const others = [perf(), perf({ id_mandato: 'fhc-1995', presidente: 'Fernando Cardoso', anos_cobertos: '1995-1998', pib_medio_anual_pct: 2.5 })];
    const { rerender } = render(<ExecutivoPanel performance={perf()} presidentMeta={meta()} annualData={annual} mandateId="lula-2023" allPerformances={[perf()]} />);
    expect(screen.queryByText('Ranking: PIB Médio Anual por Mandato')).not.toBeInTheDocument();
    rerender(<ExecutivoPanel performance={perf()} presidentMeta={meta()} annualData={annual} mandateId="lula-2023" allPerformances={others} />);
    expect(screen.getByText('Ranking: PIB Médio Anual por Mandato')).toBeInTheDocument();
  });

  it('filtra a série anual aos anos do mandato', () => {
    render(<ExecutivoPanel performance={perf()} presidentMeta={meta()} annualData={annual} mandateId="lula-2023" allPerformances={[]} />);
    const charts = screen.getAllByTestId('chart');
    expect(charts.length).toBeGreaterThan(0);
  });

  it('tooltip dos KPIs é acessível por botão', () => {
    render(<ExecutivoPanel performance={perf()} presidentMeta={meta()} annualData={annual} mandateId="lula-2023" allPerformances={[]} />);
    const btn = screen.getAllByRole('button', { name: /Sobre PIB/ })[0];
    fireEvent.focus(btn);
    expect(within(btn.parentElement as HTMLElement).getByRole('tooltip')).toHaveTextContent(/Crescimento médio anual/);
  });

  it('erro de imagem cai para a foto local e depois esconde', () => {
    const { container } = render(<ExecutivoPanel performance={perf()} presidentMeta={meta({ foto_url: 'https://x.org/l.jpg' })} annualData={annual} mandateId="lula-2023" allPerformances={[]} />);
    const img = container.querySelector('img[alt="Luiz Inácio Lula da Silva"]') as HTMLImageElement;
    fireEvent.error(img);
    expect(img.src).toContain('/presidents/lula.jpg');
    fireEvent.error(img);
    expect(img.style.display).toBe('none');
  });

  it("renderiza a seção de IPLE quando o mandato possui os indicadores de poder legislativo", () => {
    const mockIple = {
      mandato_id: "lula-2023",
      presidente: "Luiz Inácio Lula da Silva",
      periodo: "2023 - 2027",
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
        tmv: { score: 0.6875, corte: 0.7, crisp_val: 0, classificacao: "Manutenção Baixa" },
        iple: { score: 0.7545, corte: 0.785, crisp_val: 0, classificacao: "Executivo Fraco" },
        oposicao_x1: { score: 0.2359, corte: 0.334, crisp_val: 0, classificacao: "Oposição Fraca" },
        fragmentacao_x2: { score: 9.93, corte: 8.45, crisp_val: 1, classificacao: "Parlamento Fragmentado" },
        polarizacao_x3: { score: 4.55, corte: 2.2, crisp_val: 1, classificacao: "Parlamento Polarizado" },
      },
      classificacao_geral: "Executivo Fraco",
    };

    render(
      <ExecutivoPanel
        performance={perf({ iple: mockIple })}
        presidentMeta={meta()}
        annualData={annual}
        mandateId="lula-2023"
        allPerformances={[]}
      />
    );

    expect(screen.getByText("Índice de Poder Legislativo do Executivo (IPLE)")).toBeInTheDocument();
    expect(screen.getByText(/0\.754/)).toBeInTheDocument();
    expect(screen.getByText("82.1%")).toBeInTheDocument();
    expect(screen.getByText("68.8%")).toBeInTheDocument();
    expect(screen.getByText(/X₁: Tamanho da Oposição/)).toBeInTheDocument();
    expect(screen.getByText(/X₂: Fragmentação \(NEP\)/)).toBeInTheDocument();
    expect(screen.getByText(/X₃: Polarização \(IPP\)/)).toBeInTheDocument();
  });

  it("permite alternar entre ranking de PIB e ranking de IPLE", () => {
    const mockIple1 = {
      mandato_id: "lula-2023",
      presidente: "Lula",
      periodo: "2023-2027",
      indicadores_base: {
        proposicoes_executivo_total: 80,
        proposicoes_executivo_aprovadas: 65,
        vetos_total_apreciados: 40,
        vetos_mantidos: 28,
        vetos_pendentes_pauta: 0,
        taxa_sucesso_ts: 0.82,
        taxa_manutencao_vetos_tmv: 0.68,
        iple_score: 0.7545,
      },
      variaveis_contextuais: {
        tamanho_oposicao_x1: 0.23,
        oposicao_cadeiras: 120,
        total_cadeiras: 513,
        fragmentacao_nep_x2: 9.9,
        polarizacao_ipp_x3: 4.5,
      },
      calibragem_crisp_set: {
        ts: { score: 0.82, corte: 0.87, crisp_val: 0, classificacao: "Sucesso Baixo" },
        tmv: { score: 0.68, corte: 0.7, crisp_val: 0, classificacao: "Manutenção Baixa" },
        iple: { score: 0.7545, corte: 0.785, crisp_val: 0, classificacao: "Executivo Fraco" },
        oposicao_x1: { score: 0.23, corte: 0.334, crisp_val: 0, classificacao: "Oposição Fraca" },
        fragmentacao_x2: { score: 9.9, corte: 8.45, crisp_val: 1, classificacao: "Parlamento Fragmentado" },
        polarizacao_x3: { score: 4.5, corte: 2.2, crisp_val: 1, classificacao: "Parlamento Polarizado" },
      },
      classificacao_geral: "Executivo Fraco",
    };
    const mockIple2 = {
      ...mockIple1,
      mandato_id: "fhc-1995",
      presidente: "FHC",
      indicadores_base: { ...mockIple1.indicadores_base, iple_score: 0.9036 },
      calibragem_crisp_set: {
        ...mockIple1.calibragem_crisp_set,
        iple: { score: 0.9036, corte: 0.785, crisp_val: 1, classificacao: "Executivo Forte / Poderoso" },
      },
    };

    const others = [
      perf({ id_mandato: "lula-2023", presidente: "Lula", iple: mockIple1 }),
      perf({ id_mandato: "fhc-1995", presidente: "FHC", anos_cobertos: "1995-1998", pib_medio_anual_pct: 2.5, iple: mockIple2 }),
    ];

    render(
      <ExecutivoPanel
        performance={others[0]}
        presidentMeta={meta()}
        annualData={annual}
        mandateId="lula-2023"
        allPerformances={others}
      />
    );

    expect(screen.getByText("Ranking: PIB Médio Anual por Mandato")).toBeInTheDocument();
    const btnIple = screen.getByRole("button", { name: "IPLE (Governabilidade)" });
    fireEvent.click(btnIple);
    expect(screen.getByText("Ranking: Poder Legislativo (IPLE)")).toBeInTheDocument();
    expect(screen.getByText(/Linha tracejada em 0.785/)).toBeInTheDocument();
  });
});
