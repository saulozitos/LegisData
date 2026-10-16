import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ExecutivoDashboard from './page';
import * as api from '@/services/api';

vi.mock('@/components/Header', () => ({ default: () => <div data-testid="Header" /> }));
vi.mock('recharts', async () => (await import('@/test/recharts')).rechartsMock);
vi.mock('@/services/api', () => ({
  getPresidentialMandates: vi.fn(),
  getMandateIndicators: vi.fn(),
  getMandateSummary: vi.fn(),
}));
const getMandates = api.getPresidentialMandates as unknown as ReturnType<typeof vi.fn>;
const getIndicators = api.getMandateIndicators as unknown as ReturnType<typeof vi.fn>;
const getSummary = api.getMandateSummary as unknown as ReturnType<typeof vi.fn>;

const mandates = [
  { id: 'fhc', nome: 'Fernando Henrique Cardoso', inicio: '1995-01-01', fim: '1998-12-31', partido: 'PSDB', foto_url: null },
  { id: 'lula', nome: 'Luiz Inácio Lula da Silva', inicio: '2023-01-01', fim: null, partido: 'PT', foto_url: null },
];

const stat = (v: number | null) => ({ primeiro: v, ultimo: v, minimo: v, maximo: v, media: v, variacao_pp: v == null ? null : 0.7 });
const summary = (id: string, nome: string) => ({
  mandate_id: id,
  nome,
  partido: 'PT',
  inicio: '2023-01-01',
  fim: null,
  foto_url: null,
  total_meses: 12,
  kpis: {
    inflacao_ipca: stat(5),
    desemprego_pnad: { primeiro: 9, ultimo: 7, minimo: 7, maximo: 9, media: 8 },
    cambio_usd_brl: stat(5.1),
    selic_meta: stat(null),
  },
});

const indicators = [{ data: '2023-01-01', inflacao_ipca: 5, desemprego_pnad: 8, cambio_usd_brl: 5, selic_meta: 11 }];

beforeEach(() => {
  getMandates.mockReset();
  getIndicators.mockReset();
  getSummary.mockReset();
});

describe('ExecutivoDashboard', () => {
  it('seleciona por padrão o mandato mais recente e mostra KPIs reais', async () => {
    getMandates.mockResolvedValue(mandates);
    getIndicators.mockResolvedValue(indicators);
    getSummary.mockResolvedValue(summary('lula', 'Luiz Inácio Lula da Silva'));
    render(<ExecutivoDashboard />);
    expect(screen.getByText('Carregando mandatos...')).toBeInTheDocument();

    expect(await screen.findByRole('heading', { level: 2, name: 'Luiz Inácio Lula da Silva' })).toBeInTheDocument();
    expect(getSummary).toHaveBeenCalledWith('lula', expect.any(AbortSignal));
    expect(screen.getByRole('button', { name: /Silva/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/Governo atual · 12 meses de dados/)).toBeInTheDocument();
    expect(screen.getByText('Inflação (IPCA em 12 meses)')).toBeInTheDocument();
    expect(screen.queryByText(/Aprovação|Emendas/)).not.toBeInTheDocument();
    expect(screen.getByText('Câmbio (USD/BRL) × Selic')).toBeInTheDocument();
  });

  it('KPI sem dado mostra "—", nunca 0 nem NaN', async () => {
    getMandates.mockResolvedValue(mandates);
    getIndicators.mockResolvedValue(indicators);
    getSummary.mockResolvedValue(summary('lula', 'Lula'));
    render(<ExecutivoDashboard />);
    await screen.findByRole('heading', { level: 2, name: 'Luiz Inácio Lula da Silva' });
    const selic = screen.getByText('Selic', { selector: 'p' }).closest('div')!.parentElement as HTMLElement;
    expect(within(selic).getByText('—')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/NaN|undefined|null/);
  });

  it('o delta do KPI mostra o sinal e a variação em pp', async () => {
    getMandates.mockResolvedValue(mandates);
    getIndicators.mockResolvedValue(indicators);
    getSummary.mockResolvedValue(summary('lula', 'Lula'));
    render(<ExecutivoDashboard />);
    await screen.findByRole('heading', { level: 2, name: 'Luiz Inácio Lula da Silva' });
    expect(screen.getByText('+0.7 pp vs. início')).toBeInTheDocument();
    expect(screen.getByText('-2.0 pp vs. início')).toBeInTheDocument(); // desemprego: ultimo - primeiro
  });

  it('troca de mandato busca os dados do mandato escolhido', async () => {
    getMandates.mockResolvedValue(mandates);
    getIndicators.mockResolvedValue(indicators);
    getSummary.mockImplementation((id: string) => Promise.resolve(summary(id, id === 'fhc' ? 'FHC' : 'Lula')));
    render(<ExecutivoDashboard />);
    await screen.findByRole('heading', { level: 2, name: 'Luiz Inácio Lula da Silva' });
    fireEvent.click(screen.getByRole('button', { name: /Cardoso/ }));
    expect(await screen.findByRole('heading', { level: 2, name: 'Fernando Henrique Cardoso' })).toBeInTheDocument();
    expect(getIndicators).toHaveBeenCalledWith('fhc', expect.any(AbortSignal));
  });

  it('erro nos mandatos mostra alerta e retry recarrega', async () => {
    getMandates.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(mandates);
    getIndicators.mockResolvedValue(indicators);
    getSummary.mockResolvedValue(summary('lula', 'Lula'));
    render(<ExecutivoDashboard />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByRole('heading', { level: 2, name: 'Luiz Inácio Lula da Silva' })).toBeInTheDocument();
  });

  it('erro nos indicadores do mandato mostra alerta e mantém o seletor', async () => {
    getMandates.mockResolvedValue(mandates);
    getIndicators.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(indicators);
    getSummary.mockResolvedValue(summary('lula', 'Lula'));
    render(<ExecutivoDashboard />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Cardoso/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    await waitFor(() => expect(screen.getByRole('heading', { level: 2, name: 'Luiz Inácio Lula da Silva' })).toBeInTheDocument());
  });

  it('sem mandatos cadastrados mostra estado vazio', async () => {
    getMandates.mockResolvedValue([]);
    render(<ExecutivoDashboard />);
    expect(await screen.findByText('Nenhum mandato cadastrado')).toBeInTheDocument();
    expect(getSummary).not.toHaveBeenCalled();
  });

  it('mandato sem resumo mostra mensagem de indisponibilidade', async () => {
    getMandates.mockResolvedValue(mandates);
    getIndicators.mockResolvedValue([]);
    getSummary.mockResolvedValue(null);
    render(<ExecutivoDashboard />);
    expect(await screen.findByText(/Não há indicadores disponíveis para este mandato/)).toBeInTheDocument();
  });
});
