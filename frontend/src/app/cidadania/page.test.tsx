import React from 'react';
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react';
import { describe, it, vi, expect, beforeEach } from 'vitest';
import CidadaniaPage from './page';
import * as api from '@/services/api';

vi.mock('@/components/Header', () => ({ default: () => <div data-testid="Header" /> }));
vi.mock('@/services/api', () => ({ getConsultasPublicas: vi.fn() }));
const getConsultas = api.getConsultasPublicas as unknown as ReturnType<typeof vi.fn>;

const item = (over: Record<string, unknown>) => ({
  id_externo: '1',
  casa: 'Senado',
  sigla_projeto: 'PL 100/2024',
  ementa: 'Ementa sobre escala de trabalho',
  link_oficial_votacao: 'https://www12.senado.leg.br/ecidadania/1',
  link_tramitacao_oficial: 'https://www25.senado.leg.br/web/atividade/1',
  em_votacao_aberta: true,
  votos_sim: 700,
  votos_nao: 300,
  total_votos: 1000,
  percentual_sim: 70,
  percentual_nao: 30,
  tema: 'Trabalho',
  status: 'Em tramitação',
  autor: 'Senadora Ana',
  data_apresentacao: '2024-01-10',
  destaque: true,
  ...over,
});

const data = [
  item({}),
  item({ id_externo: '2', casa: 'Câmara', sigla_projeto: 'PEC 7/2023', ementa: 'Reforma tributária', em_votacao_aberta: false, votos_sim: null, votos_nao: null, total_votos: null, percentual_sim: null, percentual_nao: null, tema: null, autor: null, destaque: false, status: 'Promulgada', link_oficial_votacao: 'javascript:alert(1)', link_tramitacao_oficial: null }),
  item({ id_externo: '3', casa: 'Câmara', sigla_projeto: 'PL 5/2022', ementa: 'Outra', em_votacao_aberta: false, votos_sim: 10, votos_nao: 30, total_votos: 40, percentual_sim: null, percentual_nao: null, destaque: false, link_tramitacao_oficial: null }),
];

beforeEach(() => {
  getConsultas.mockReset();
  vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
});

describe('CidadaniaPage', () => {
  it('mostra carregando e depois estatísticas e cartões', async () => {
    getConsultas.mockResolvedValue(data);
    render(<CidadaniaPage />);
    expect(screen.getByText(/Consultando as APIs/)).toBeInTheDocument();
    expect(await screen.findByRole('heading', { level: 2, name: 'PL 100/2024' })).toBeInTheDocument();
    expect(screen.getByText('Senado (1) e Câmara (2)')).toBeInTheDocument();
    expect(screen.getByText('1k+')).toBeInTheDocument(); // total de votos 1000 + 40, em milhares
    expect(getConsultas).toHaveBeenCalledWith(undefined, false, expect.any(AbortSignal));
  });

  it('cartão com placar mostra percentuais; sem percentuais calcula a partir dos votos', async () => {
    getConsultas.mockResolvedValue(data);
    render(<CidadaniaPage />);
    await screen.findByText('PL 100/2024');
    expect(screen.getByText('Placar Parcial em Tempo Real:')).toBeInTheDocument();
    expect(screen.getByText(/SIM: 70%/)).toBeInTheDocument();
    expect(screen.getByText('Placar Final Apurado:')).toBeInTheDocument();
    expect(screen.getByText(/SIM: 25%/)).toBeInTheDocument(); // 10 de 40
    expect(screen.getByText(/NÃO: 75%/)).toBeInTheDocument();
  });

  it('sem placar nunca imprime "null%" nem barra inventada', async () => {
    getConsultas.mockResolvedValue(data);
    render(<CidadaniaPage />);
    await screen.findByText('PEC 7/2023');
    expect(screen.getByText('Matéria em tramitação legislativa no Congresso Nacional.')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/null|undefined|NaN/);
  });

  it('links oficiais inseguros não viram href', async () => {
    getConsultas.mockResolvedValue(data);
    render(<CidadaniaPage />);
    await screen.findByText('PEC 7/2023');
    expect(screen.getByText('Link oficial indisponível')).toBeInTheDocument();
    const vote = screen.getByRole('link', { name: /Votar no Site Oficial/ });
    expect(vote).toHaveAttribute('href', 'https://www12.senado.leg.br/ecidadania/1');
    expect(vote).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('filtra por status, casa, placar e texto; limpa todos os filtros', async () => {
    getConsultas.mockResolvedValue(data);
    render(<CidadaniaPage />);
    await screen.findByText('PL 100/2024');

    fireEvent.click(screen.getByRole('button', { name: /Votação Aberta \(1\)/ }));
    expect(screen.queryByText('PEC 7/2023')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Encerradas \(2\)/ }));
    expect(screen.queryByText('PL 100/2024')).not.toBeInTheDocument();
    expect(screen.getByText('PEC 7/2023')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Todas \(3\)/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Senado' }));
    expect(screen.queryByText('PEC 7/2023')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Câmara' }));
    expect(screen.getByText('PEC 7/2023')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Apenas com placar'));
    expect(screen.queryByText('PEC 7/2023')).not.toBeInTheDocument();
    expect(screen.getByText('PL 5/2022')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Buscar consultas/), { target: { value: 'inexistente' } });
    expect(screen.getByText('Nenhuma consulta encontrada')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Limpar todos os filtros' }));
    expect(screen.getAllByRole('article')).toHaveLength(3);
  });

  it('busca por tema, autor e sigla e botão "Limpar"', async () => {
    getConsultas.mockResolvedValue(data);
    render(<CidadaniaPage />);
    await screen.findByText('PL 100/2024');
    const input = screen.getByLabelText(/Buscar consultas/);
    fireEvent.change(input, { target: { value: 'ana' } }); // autoria dos itens 1 e 3
    expect(screen.getAllByRole('article')).toHaveLength(2);
    fireEvent.change(input, { target: { value: 'tributária' } }); // ementa
    expect(screen.getAllByRole('article')).toHaveLength(1);
    fireEvent.change(input, { target: { value: 'pec 7' } }); // sigla
    expect(screen.getAllByRole('article')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Limpar' }));
    expect(screen.getAllByRole('article')).toHaveLength(3);
  });

  it('copia o link oficial e informa sucesso; avisa quando a cópia falha', async () => {
    getConsultas.mockResolvedValue([item({})]);
    render(<CidadaniaPage />);
    const share = await screen.findByRole('button', { name: /Copiar link oficial da consulta PL 100\/2024/ });
    fireEvent.click(share);
    await waitFor(() => expect(within(share).getByText('Link copiado')).toBeInTheDocument());
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('https://www12.senado.leg.br/ecidadania/1');

    (navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('denied'));
    fireEvent.click(share);
    await waitFor(() => expect(within(share).getByText('Não foi possível copiar o link')).toBeInTheDocument());
  });

  it('atualização forçada usa force_refresh e respeita o intervalo mínimo', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    getConsultas.mockResolvedValue(data);
    render(<CidadaniaPage />);
    await screen.findByText('PL 100/2024');
    const refresh = screen.getByRole('button', { name: /Atualizar/ });
    fireEvent.click(refresh);
    await waitFor(() => expect(getConsultas).toHaveBeenLastCalledWith(undefined, true, expect.any(AbortSignal)));
    await waitFor(() => expect(refresh).toBeDisabled());
    // mantém os dados anteriores durante a atualização
    expect(screen.getByText('PL 100/2024')).toBeInTheDocument();
    const calls = getConsultas.mock.calls.length;
    fireEvent.click(refresh);
    expect(getConsultas).toHaveBeenCalledTimes(calls);

    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    await waitFor(() => expect(refresh).not.toBeDisabled());
  });

  it('erro na primeira carga mostra alerta e retry', async () => {
    getConsultas.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(data);
    render(<CidadaniaPage />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('PL 100/2024')).toBeInTheDocument();
  });

  it('total de votos pequeno e zero são exibidos sem "0k+"', async () => {
    getConsultas.mockResolvedValue([item({ total_votos: 0, votos_sim: null, votos_nao: null })]);
    const { unmount } = render(<CidadaniaPage />);
    await screen.findByText('PL 100/2024');
    expect(screen.getByText('Indisponível')).toBeInTheDocument();
    unmount();

    getConsultas.mockResolvedValue([item({ total_votos: 850 })]);
    render(<CidadaniaPage />);
    await screen.findByText('PL 100/2024');
    expect(screen.getAllByText('850').length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toMatch(/0k\+/);
  });
});
