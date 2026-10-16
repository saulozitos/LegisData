import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, vi, expect, beforeEach } from 'vitest';
import SocialClassesExplainer, { parseIncome } from './SocialClassesExplainer';
import * as api from '@/services/api';

vi.mock('@/services/api', () => ({ getSocialClasses: vi.fn() }));
const getClasses = api.getSocialClasses as unknown as ReturnType<typeof vi.fn>;

const cls = (classe: string, min: number, max: number | null, pct: number) => ({
  classe,
  faixa_salarios_minimos: max === null ? `Acima de ${min} SM` : `${min} a ${max} SM`,
  faixa_salarios_minimos_min: min,
  faixa_salarios_minimos_max: max,
  renda_familiar_min_brl: min * 1000,
  renda_familiar_max_brl: max === null ? null : max * 1000,
  faixa_renda_formatada: `R$ faixa ${classe}`,
  percentual_populacao: pct,
  descricao: `Descrição da ${classe}`,
  cor: '#112233',
  destaque: `Destaque ${classe}`,
});

const response = {
  salario_minimo_referencia_brl: 1000,
  ano_referencia: 2024,
  fonte: 'IBGE',
  resumo_populacional: { maioria_populacao_acumulada_d_e_pct: 55, texto_educativo: 'Texto educativo da API.' },
  classes: [cls('Classe A', 15, null, 3), cls('Classe B', 5, 15, 12), cls('Classe C', 3, 5, 30), cls('Classe D', 1, 3, 40), cls('Classe E', 0, 1, 15)],
};

beforeEach(() => getClasses.mockReset());

describe('parseIncome', () => {
  it.each([
    ['5000', 5000],
    ['5000,50', 5000.5],
    ['5.000,50', 5000.5],
    ['5000.50', 5000.5],
    ['5.000', 5000],
    ['R$ 1.234,56', 1234.56],
    ['0', 0],
  ])('interpreta %s', (raw, expected) => {
    expect(parseIncome(raw)).toBe(expected);
  });

  it.each([[''], ['  '], ['abc'], ['1e5'], ['-10'], ['1,2,3']])('rejeita %j', (raw) => {
    expect(parseIncome(raw)).toBeNull();
  });
});

describe('SocialClassesExplainer', () => {
  it('mostra dados da API e destaca por padrão a classe mais populosa', async () => {
    getClasses.mockResolvedValue(response);
    render(<SocialClassesExplainer />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(await screen.findByText(/Salário Mínimo de 2024: R\$ 1\.000,00/)).toBeInTheDocument();
    expect(screen.getByText('Texto educativo da API.')).toBeInTheDocument();
    expect(screen.getByText('Descrição da Classe D')).toBeInTheDocument(); // 40% = mais populosa
    expect(screen.getByText('55,0% em Classes D/E')).toBeInTheDocument();
  });

  it('com microdados da PNAD mostra origem, domicílios e permite trocar o ano', async () => {
    const pnad = (ano: number) => ({
      ...response,
      origem: 'pnad',
      ano_referencia: ano,
      anos_disponiveis: [2023, 2024],
      fonte: `IBGE — PNAD Contínua anual ${ano}`,
      classes: response.classes.map((c) => ({ ...c, percentual_domicilios: 11.1 })),
    });
    getClasses.mockImplementation(async (_signal: AbortSignal, ano?: number) => pnad(ano ?? 2024));
    render(<SocialClassesExplainer />);
    expect(await screen.findByText(/Microdados da PNAD Contínua \(IBGE\)/)).toBeInTheDocument();
    expect(screen.getByText(/Fonte: IBGE — PNAD Contínua anual 2024/)).toBeInTheDocument();
    expect(screen.getAllByText(/11,1% dos domicílios/).length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText('Ano da PNAD'), { target: { value: '2023' } });
    expect(await screen.findByText(/Fonte: IBGE — PNAD Contínua anual 2023/)).toBeInTheDocument();
    expect(getClasses).toHaveBeenLastCalledWith(expect.anything(), 2023);
  });

  it('seleciona uma classe pela pirâmide e pela barra agregada', async () => {
    getClasses.mockResolvedValue(response);
    render(<SocialClassesExplainer />);
    await screen.findByText('Descrição da Classe D');
    fireEvent.click(screen.getByRole('button', { name: /Classe B/ , pressed: false }));
    expect(screen.getByText('Descrição da Classe B')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Classe A: 3,0% da população' }));
    expect(screen.getByText('Descrição da Classe A')).toBeInTheDocument();
  });

  it('simulador enquadra a renda nas faixas vindas da API', async () => {
    getClasses.mockResolvedValue(response);
    render(<SocialClassesExplainer />);
    await screen.findByText('Descrição da Classe D');
    const input = screen.getByLabelText(/Renda familiar mensal/);

    fireEvent.change(input, { target: { value: '5.000,00' } });
    fireEvent.click(screen.getByRole('button', { name: /Identificar Minha Classe/ }));
    const result = screen.getByText('Seu enquadramento oficial:').parentElement as HTMLElement;
    expect(within(result).getByText('Classe B')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Ver detalhes desta classe/ }));
    expect(screen.getByText('Descrição da Classe B')).toBeInTheDocument();

    // limite superior exclusivo: 15 SM já é Classe A
    fireEvent.change(input, { target: { value: '15000' } });
    fireEvent.click(screen.getByRole('button', { name: /Identificar Minha Classe/ }));
    const result2 = screen.getByText('Seu enquadramento oficial:').parentElement as HTMLElement;
    expect(within(result2).getByText('Classe A')).toBeInTheDocument();
  });

  it('valor inválido mostra erro acessível e limpa o resultado', async () => {
    getClasses.mockResolvedValue(response);
    render(<SocialClassesExplainer />);
    await screen.findByText('Descrição da Classe D');
    const input = screen.getByLabelText(/Renda familiar mensal/);
    fireEvent.change(input, { target: { value: 'abc' } });
    fireEvent.click(screen.getByRole('button', { name: /Identificar Minha Classe/ }));
    expect(screen.getByRole('alert')).toHaveTextContent(/valor válido/);
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.queryByText('Seu enquadramento oficial:')).not.toBeInTheDocument();
  });

  it('renda fora das faixas informa que não foi possível enquadrar', async () => {
    getClasses.mockResolvedValue({ ...response, classes: [cls('Classe B', 5, 15, 50), cls('Classe C', 3, 5, 50)] });
    render(<SocialClassesExplainer />);
    await screen.findByText('Descrição da Classe B');
    fireEvent.change(screen.getByLabelText(/Renda familiar mensal/), { target: { value: '100' } });
    fireEvent.click(screen.getByRole('button', { name: /Identificar Minha Classe/ }));
    expect(screen.getByRole('alert')).toHaveTextContent(/Não foi possível enquadrar/);
  });

  it('sem texto educativo da API não mostra o banner vazio', async () => {
    getClasses.mockResolvedValue({ ...response, resumo_populacional: { maioria_populacao_acumulada_d_e_pct: null, texto_educativo: null } });
    render(<SocialClassesExplainer />);
    await screen.findByText(/Salário Mínimo de 2024/);
    expect(screen.queryByText(/A Ilusão da/)).not.toBeInTheDocument();
  });

  it('funciona com menos de 3 classes (sem índice fixo) e soma D/E quando o resumo falta', async () => {
    getClasses.mockResolvedValue({
      ...response,
      resumo_populacional: { maioria_populacao_acumulada_d_e_pct: null, texto_educativo: 'x' },
      classes: [cls('Classe D', 1, 3, 40), cls('Classe E', 0, 1, 15)],
    });
    render(<SocialClassesExplainer />);
    expect(await screen.findByText('55,0% em Classes D/E')).toBeInTheDocument();
  });

  it('erro mostra alerta com retry; vazio mostra indisponível', async () => {
    getClasses.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(response);
    render(<SocialClassesExplainer />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('Texto educativo da API.')).toBeInTheDocument();
  });

  it('lista vazia mostra estado indisponível', async () => {
    getClasses.mockResolvedValue({ ...response, classes: [] });
    render(<SocialClassesExplainer />);
    expect(await screen.findByText('Classes sociais indisponíveis')).toBeInTheDocument();
  });
});
