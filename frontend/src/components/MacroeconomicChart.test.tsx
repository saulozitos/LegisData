import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, vi, expect } from 'vitest';
import MacroeconomicChart from './MacroeconomicChart';
import type { ResumoMacroeconomicoAnual } from '@/services/api';
import type { MandateRange } from '@/lib/mandate';

vi.mock('recharts', async () => (await import('@/test/recharts')).rechartsMock);

const row = (ano: number, over: Partial<ResumoMacroeconomicoAnual> = {}): ResumoMacroeconomicoAnual => ({
  ano,
  presidente_dominante: 'Fulano',
  ipca_acumulado_ano_pct: 5,
  pib_crescimento_real_pct: 2.5,
  cambio_dolar_medio: 4.5,
  divida_liquida_pct_pib: null,
  salario_minimo_nominal_brl: null,
  ibovespa_fechamento: 120000,
  ...over,
});

const data = [row(1993, { ipca_acumulado_ano_pct: 2477, cambio_dolar_medio: 19323 }), row(1995), row(2010), row(2023)];
const mandates: MandateRange[] = [
  { id: 'fhc-1995', label: 'Cardoso 1', start: 1995, end: 1998, electionYear: 1994 },
  { id: 'lula-2023', label: 'Silva 3', start: 2023, end: 2026, electionYear: 2022 },
  { id: 'futuro', label: 'Futuro', start: 2030, end: 2034, electionYear: 2029 },
];

describe('MacroeconomicChart', () => {
  it('sem dados mostra "Dado indisponível" em vez de gráfico vazio', () => {
    render(<MacroeconomicChart data={[]} />);
    expect(screen.getByRole('status')).toHaveTextContent(/Dado indisponível/);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('por padrão recorta o pós-Plano Real e rotula os intervalos', () => {
    render(<MacroeconomicChart data={data} mandates={mandates} />);
    expect(screen.getByRole('button', { name: 'Pós-Plano Real (1995-2023)' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Histórico Completo (1993-2023)' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByText(/Atenção: a inflação do período pré-Real/)).not.toBeInTheDocument();
    expect(screen.getByRole('img')).toBeInTheDocument();
  });

  it('histórico completo exibe o aviso do pré-Real', () => {
    render(<MacroeconomicChart data={data} />);
    fireEvent.click(screen.getByRole('button', { name: /Histórico Completo/ }));
    expect(screen.getByText(/Atenção: a inflação do período pré-Real/)).toBeInTheDocument();
  });

  it('delimita zonas presidenciais dentro do intervalo exibido', () => {
    render(<MacroeconomicChart data={data} mandates={mandates} />);
    const areas = screen.getAllByTestId('ref-area');
    // o mandato futuro (2030+) fica fora da série e não vira zona
    expect(areas.map((a) => [a.dataset.x1, a.dataset.x2])).toEqual([
      ['1995', '1998'],
      ['2023', '2023'],
    ]);
  });

  it('botão de zoom só existe com mandato selecionado e alterna', () => {
    const { rerender } = render(<MacroeconomicChart data={data} mandates={mandates} />);
    expect(screen.queryByRole('button', { name: /Zoom:/ })).not.toBeInTheDocument();

    rerender(<MacroeconomicChart data={data} mandates={mandates} selectedMandateId="lula-2023" />);
    const zoom = screen.getByRole('button', { name: /Zoom: Silva 3 \(2023-2026\)/ });
    expect(zoom).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(zoom);
    expect(zoom).toHaveAttribute('aria-pressed', 'true');
  });

  it('mandato desconhecido não mostra zoom', () => {
    render(<MacroeconomicChart data={data} mandates={mandates} selectedMandateId="nao-existe" />);
    expect(screen.queryByRole('button', { name: /Zoom:/ })).not.toBeInTheDocument();
  });

  it('Ibovespa liga/desliga título, eixo e tooltip', () => {
    render(<MacroeconomicChart data={data} />);
    const toggle = screen.getByRole('button', { name: /Ibovespa \(Pontos B3\)/ });
    expect(screen.queryByText(/vs\. Ibovespa/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Ibovespa \(Fechamento\)/)).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/vs\. Ibovespa/)).toBeInTheDocument();
    expect(screen.getByText(/Ibovespa \(Fechamento\)/)).toBeInTheDocument();
    expect(screen.getByText('120.000 pts')).toBeInTheDocument();
  });

  it('tooltip formata PIB/IPCA/câmbio e usa N/D quando falta dado', () => {
    const { unmount } = render(<MacroeconomicChart data={[row(1995)]} />);
    const tip = screen.getByTestId('tooltip-content');
    expect(tip).toHaveTextContent('Ano 1995');
    expect(tip).toHaveTextContent('+2.50%');
    expect(tip).toHaveTextContent('5.00%');
    expect(tip).toHaveTextContent('R$ 4.50');
    unmount();

    render(<MacroeconomicChart data={[row(1995, { pib_crescimento_real_pct: null, ipca_acumulado_ano_pct: null, cambio_dolar_medio: null })]} />);
    const tip2 = screen.getByTestId('tooltip-content');
    expect(tip2.textContent?.match(/N\/D/g)).toHaveLength(2);
    expect(tip2).not.toHaveTextContent('Câmbio Médio');
  });

  it('câmbio em moeda pré-Real não é mostrado como R$', () => {
    render(<MacroeconomicChart data={[row(1993, { cambio_dolar_medio: 19323 })]} />);
    fireEvent.click(screen.getByRole('button', { name: /Histórico Completo/ }));
    expect(screen.getByTestId('tooltip-content')).toHaveTextContent('moeda pré-Real (não comparável)');
    expect(screen.getByTestId('tooltip-content')).not.toHaveTextContent('R$ 19323');
  });
});
