import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, vi, expect, beforeEach } from 'vitest';
import WageDisparityPanel from './WageDisparityPanel';
import * as api from '@/services/api';

vi.mock('recharts', async () => (await import('@/test/recharts')).rechartsMock);
vi.mock('@/services/api', () => ({ getWageDisparity: vi.fn() }));
const getWage = api.getWageDisparity as unknown as ReturnType<typeof vi.fn>;

const response = {
  serie_historica: [
    { ano: 1994, presidente_dominante: 'Itamar', salario_minimo_brl: 70, salario_parlamentar_brl: 1000, multiplo_salarios_minimos: 14, ipca_acumulado_ano_pct: null, indice_salario_minimo_base100: 100, indice_salario_parlamentar_base100: 100, indice_ipca_base100: 100 },
    { ano: 2010, presidente_dominante: 'Lula', salario_minimo_brl: 510, salario_parlamentar_brl: 16000, multiplo_salarios_minimos: 31, ipca_acumulado_ano_pct: 5.9, indice_salario_minimo_base100: 700, indice_salario_parlamentar_base100: 1600, indice_ipca_base100: 400 },
  ],
  votacao_salario_minimo: {
    proposicao_titulo: 'MPV 1234/2024',
    ementa: 'Reajusta o salário mínimo',
    data_votacao: '2024-05-01',
    casa: 'Câmara',
    placar: { SIM: 300, NAO: 100, ABSTENCAO: 5, TOTAL: 405 },
    votos_amostra: [
      { deputado_nome: 'Ana Silva', partido_sigla: 'PT', uf: 'SP', cargo: 'Deputado', voto: 'SIM', foto_url: 'https://x.org/a.jpg' },
      { deputado_nome: 'Bruno Costa', partido_sigla: 'PL', uf: 'RJ', cargo: 'Deputado', voto: 'NAO', foto_url: null },
      { deputado_nome: 'Caio Lima', partido_sigla: 'MDB', uf: 'MG', cargo: 'Deputado', voto: 'ABSTENCAO', foto_url: 'javascript:x' },
    ],
  },
  estatisticas_disparidade: {
    ano_referencia_inicial: 1995,
    ano_referencia_atual: 2024,
    salario_minimo_inicial: 70,
    salario_minimo_atual: 1412,
    salario_parlamentar_inicial: 1000,
    salario_parlamentar_atual: 44008.52,
    multiplo_medio_historico: 25,
    pico_multiplo_ano: 2010,
    pico_multiplo_valor: 31.4,
    multiplo_atual: 31.17,
    crescimento_acumulado_salario_minimo_pct: 1917,
    crescimento_acumulado_salario_parlamentar_pct: 4301,
  },
};

beforeEach(() => getWage.mockReset());

describe('WageDisparityPanel', () => {
  it('mostra carregando e depois os indicadores vindos da API', async () => {
    getWage.mockResolvedValue(response);
    render(<WageDisparityPanel />);
    expect(screen.getByRole('status')).toBeInTheDocument();

    expect(await screen.findByText(/Salário Mínimo do Trabalhador vs Salário Parlamentar \(1994 - 2010\)/)).toBeInTheDocument();
    expect(screen.getByText('R$ 44.008,52')).toBeInTheDocument();
    expect(screen.getByText('+4.301% desde 1994 (R$ 1.000,00)')).toBeInTheDocument();
    expect(screen.getByText('+1.917% desde 1994 (R$ 70,00)')).toBeInTheDocument();
    expect(screen.getByText('31,2x')).toBeInTheDocument();
    expect(screen.getByText(/1 salário parlamentar = ~31 salários mínimos/)).toBeInTheDocument();
    expect(screen.getByText(/Atingido em 2010 \(Lula\)/)).toBeInTheDocument();
    expect(screen.getByText('MPV 1234/2024')).toBeInTheDocument();
  });

  it('alterna entre valores nominais e índices base 100', async () => {
    getWage.mockResolvedValue(response);
    render(<WageDisparityPanel />);
    await screen.findByText('MPV 1234/2024');
    expect(screen.getByRole('button', { name: /Valores Nominais/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('tooltip-fmt')).toHaveTextContent('R$ 1.500,00|Salário Mínimo (BRL)');

    fireEvent.click(screen.getByRole('button', { name: /Índices Base 100 \(1994\)/ }));
    expect(screen.getByText(/Trajetória Indexada/)).toBeInTheDocument();
    expect(screen.queryByTestId('tooltip-fmt')).not.toBeInTheDocument();
  });

  it('filtra a votação por texto e por voto', async () => {
    getWage.mockResolvedValue(response);
    render(<WageDisparityPanel />);
    await screen.findByText('Ana Silva');
    expect(screen.getByRole('button', { name: 'Todos (3)' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Votaram SIM' }));
    expect(screen.queryByText('Bruno Costa')).not.toBeInTheDocument();
    expect(screen.getByText('Ana Silva')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Votaram NÃO' }));
    expect(screen.getByText('Bruno Costa')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Todos/ }));
    fireEvent.change(screen.getByLabelText(/Buscar deputado/), { target: { value: 'mdb' } });
    expect(screen.getByText('Caio Lima')).toBeInTheDocument();
    expect(screen.getByText('ABSTENCAO')).toBeInTheDocument();
    expect(screen.queryByText('Ana Silva')).not.toBeInTheDocument();
  });

  it('só renderiza fotos com URL segura', async () => {
    getWage.mockResolvedValue(response);
    const { container } = render(<WageDisparityPanel />);
    await screen.findByText('Ana Silva');
    expect(container.querySelectorAll('img')).toHaveLength(1);
    expect(container.querySelector('img')).toHaveAttribute('src', 'https://x.org/a.jpg');
  });

  it('dados ausentes viram "Indisponível", nunca null/NaN', async () => {
    getWage.mockResolvedValue({
      ...response,
      estatisticas_disparidade: { ...response.estatisticas_disparidade, multiplo_atual: null, salario_parlamentar_atual: null, crescimento_acumulado_salario_minimo_pct: null },
      votacao_salario_minimo: { ...response.votacao_salario_minimo, placar: undefined },
    });
    render(<WageDisparityPanel />);
    await screen.findByText('MPV 1234/2024');
    expect(screen.getByText('Múltiplo atual indisponível')).toBeInTheDocument();
    expect(screen.getByText(/Variação indisponível/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/NaN|null|undefined/);
    expect(screen.getAllByText('—').length).toBe(3);
  });

  it('votação sem data (indisponível na API) mostra "data indisponível"', async () => {
    getWage.mockResolvedValue({
      ...response,
      votacao_salario_minimo: { ...response.votacao_salario_minimo, data_votacao: null, placar: null, dados_indisponiveis: true },
    });
    render(<WageDisparityPanel />);
    await screen.findByText('MPV 1234/2024');
    expect(screen.getByText(/data indisponível/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/NaN|null|undefined/);
  });

  it('erro mostra alerta e retry recarrega', async () => {
    getWage.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(response);
    render(<WageDisparityPanel />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('MPV 1234/2024')).toBeInTheDocument();
  });

  it('série vazia mostra estado indisponível', async () => {
    getWage.mockResolvedValue({ ...response, serie_historica: [] });
    render(<WageDisparityPanel />);
    expect(await screen.findByText('Disparidade salarial indisponível')).toBeInTheDocument();
  });
});
