import React from 'react';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { describe, it, vi, expect, beforeEach } from 'vitest';
import DeepBrazilPanel from './DeepBrazilPanel';
import * as api from '@/services/api';
import type { MandateRange } from '@/lib/mandate';

vi.mock('recharts', async () => (await import('@/test/recharts')).rechartsMock);
vi.mock('@/services/api', () => ({
  getSocialElectionsCorrelation: vi.fn(),
  getSocialIndicators: vi.fn(),
}));
const getElections = api.getSocialElectionsCorrelation as unknown as ReturnType<typeof vi.fn>;
const getSocial = api.getSocialIndicators as unknown as ReturnType<typeof vi.fn>;

const state = (uf: string, nome: string, regiao: string, pobreza: number | null, analf: number | null, venc: number) => ({
  uf,
  estado_nome: nome,
  regiao,
  ano_eleicao: 2022,
  vencedor_nome: `Vencedor ${uf}`,
  vencedor_partido: uf === 'BA' ? 'PT' : uf === 'SP' ? 'PL' : 'PSDB',
  vencedor_votos_pct: venc,
  segundo_nome: `Segundo ${uf}`,
  segundo_partido: 'MDB',
  segundo_votos_pct: 30,
  taxa_analfabetismo_pct: analf,
  extrema_pobreza_pct: pobreza,
  inseguranca_alimentar_pct: null,
  indice_gini: null,
});

const elections = {
  ano_eleicao: 2022,
  total_estados: 3,
  anos_disponiveis: [2018, 2022],
  regioes_resumo: [
    { regiao: 'Nordeste', total_estados: 1, media_extrema_pobreza_pct: 9.5, media_analfabetismo_pct: 12, vencedores_contagem: {} },
    { regiao: 'Sudeste', total_estados: 1, media_extrema_pobreza_pct: 2, media_analfabetismo_pct: 2, vencedores_contagem: {} },
  ],
  estados: [
    state('BA', 'Bahia', 'Nordeste', 9.5, 12, 70),
    state('SP', 'São Paulo', 'Sudeste', 2, 2, 55),
    state('AC', 'Acre', 'Norte', null, null, 60),
  ],
};

const social = [
  { ano: 2018, analfabetismo_pct: 6.8, extrema_pobreza_pct: 5.4, extrema_pobreza_milhoes: 11, inseguranca_alimentar_pct: 4.2, inseguranca_alimentar_milhoes: 9, gini: 0.545 },
  { ano: 2022, analfabetismo_pct: 5.6, extrema_pobreza_pct: 5.9, extrema_pobreza_milhoes: null, inseguranca_alimentar_pct: null, inseguranca_alimentar_milhoes: null, gini: null },
];

const mandate: MandateRange = { id: 'm', label: 'Lula 3', start: 2022, end: 2022, electionYear: 2022 };

beforeEach(() => {
  getElections.mockReset();
  getSocial.mockReset();
});

const stateNames = () =>
  screen.getAllByRole('heading', { level: 4 }).map((h) => h.textContent);

describe('DeepBrazilPanel', () => {
  it('mostra carregando e depois os estados ordenados por pobreza (ausentes por último)', async () => {
    getElections.mockResolvedValue(elections);
    getSocial.mockResolvedValue(social);
    render(<DeepBrazilPanel />);
    expect(screen.getByText(/Carregando dados eleitorais/)).toBeInTheDocument();
    await screen.findByText('Bahia');
    expect(stateNames()).toEqual(['Bahia', 'São Paulo', 'Acre']);
    expect(screen.getAllByText('N/D').length).toBeGreaterThanOrEqual(2);
  });

  it('exibe os cartões do ano com N/D para valores ausentes (nunca 0)', async () => {
    getElections.mockResolvedValue(elections);
    getSocial.mockResolvedValue(social);
    render(<DeepBrazilPanel />);
    await screen.findByText('Bahia');
    expect(screen.getByText('Extrema Pobreza Nacional (2022)')).toBeInTheDocument();
    expect(screen.getByText('5,9%')).toBeInTheDocument();
    expect(screen.getByText('IBGE / IPEA')).toBeInTheDocument(); // milhões ausentes
    expect(screen.getByText('FAO / Penssan')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/NaN|undefined|null/);
  });

  it('reordena por analfabetismo e por voto do vencedor', async () => {
    getElections.mockResolvedValue(elections);
    getSocial.mockResolvedValue(social);
    render(<DeepBrazilPanel />);
    await screen.findByText('Bahia');
    fireEvent.change(screen.getByLabelText('Ordenar por:'), { target: { value: 'analfabetismo' } });
    expect(stateNames()[0]).toBe('Bahia');
    fireEvent.change(screen.getByLabelText('Ordenar por:'), { target: { value: 'votos_vencedor' } });
    expect(stateNames()).toEqual(['Bahia', 'Acre', 'São Paulo']);
  });

  it('filtra por região (botão e card regional) e por texto', async () => {
    getElections.mockResolvedValue(elections);
    getSocial.mockResolvedValue(social);
    render(<DeepBrazilPanel />);
    await screen.findByText('Bahia');

    fireEvent.click(screen.getByRole('button', { name: 'SUDESTE' }));
    expect(stateNames()).toEqual(['São Paulo']);
    expect(screen.getByRole('button', { name: 'SUDESTE' })).toHaveAttribute('aria-pressed', 'true');

    // card regional alterna o filtro
    fireEvent.click(screen.getByRole('button', { name: /Nordeste/ }));
    expect(stateNames()).toEqual(['Bahia']);
    fireEvent.click(screen.getByRole('button', { name: /Nordeste/ }));
    expect(stateNames()).toHaveLength(3);

    fireEvent.change(screen.getByLabelText(/Buscar estado/), { target: { value: 'vencedor ac' } });
    expect(stateNames()).toEqual(['Acre']);
    fireEvent.change(screen.getByLabelText(/Buscar estado/), { target: { value: 'zzz' } });
    expect(screen.getByText(/Nenhum estado encontrado/)).toBeInTheDocument();
  });

  it('troca o ano eleitoral chamando a API com o ano escolhido', async () => {
    getElections.mockResolvedValue(elections);
    getSocial.mockResolvedValue(social);
    render(<DeepBrazilPanel />);
    await screen.findByText('Bahia');
    expect(getElections).toHaveBeenCalledWith(undefined, expect.any(AbortSignal));
    fireEvent.click(screen.getByRole('button', { name: '2018' }));
    await waitFor(() => expect(getElections).toHaveBeenCalledWith(2018, expect.any(AbortSignal)));
  });

  it('usa a eleição do mandato e dá zoom na série social do período', async () => {
    getElections.mockResolvedValue(elections);
    getSocial.mockResolvedValue(social);
    render(<DeepBrazilPanel mandate={mandate} />);
    await screen.findByText('Bahia');
    expect(getElections).toHaveBeenCalledWith(2022, expect.any(AbortSignal));
    expect(screen.getByText('Zoom: Lula 3 (2022 - 2022)')).toBeInTheDocument();
    expect(screen.getByTestId('chart')).toBeInTheDocument();
  });

  it('série completa mostra o intervalo de anos', async () => {
    getElections.mockResolvedValue(elections);
    getSocial.mockResolvedValue(social);
    render(<DeepBrazilPanel />);
    expect(await screen.findByText('Série Histórica Completa (2018 - 2022)')).toBeInTheDocument();
  });

  it('erro na série social não derruba o painel e permite retry', async () => {
    getElections.mockResolvedValue(elections);
    getSocial.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(social);
    render(<DeepBrazilPanel />);
    await screen.findByText('Bahia');
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText(/série de indicadores sociais/)).toBeInTheDocument();
    fireEvent.click(within(alert).getByRole('button', { name: /tentar novamente/i }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });

  it('série social vazia mostra estado vazio', async () => {
    getElections.mockResolvedValue(elections);
    getSocial.mockResolvedValue([]);
    render(<DeepBrazilPanel />);
    await screen.findByText('Bahia');
    expect(await screen.findByText(/Não há indicadores sociais/)).toBeInTheDocument();
  });

  it('erro eleitoral mostra alerta com retry; resposta nula mostra vazio', async () => {
    getSocial.mockResolvedValue(social);
    getElections.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(elections);
    render(<DeepBrazilPanel />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('Bahia')).toBeInTheDocument();
  });

  it('resposta eleitoral nula mostra estado indisponível', async () => {
    getSocial.mockResolvedValue(social);
    getElections.mockResolvedValue(null);
    render(<DeepBrazilPanel />);
    expect(await screen.findByText('Dados eleitorais e sociais indisponíveis')).toBeInTheDocument();
  });
});
