import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, vi, expect } from 'vitest';
import PartyFidelityPanel from './PartyFidelityPanel';
import PartyLink from './PartyLink';
import type { PartyFidelityResponse } from '@/services/api';

vi.mock('recharts', async () => (await import('@/test/recharts')).rechartsMock);

const nomad = (over: Partial<PartyFidelityResponse['top_nomads'][number]>) => ({
  id: '1',
  nome_eleitoral: 'Fulano',
  nome_civil: 'Fulano de Tal',
  cargo: 'DEPUTADO_FEDERAL',
  uf: 'SP',
  foto_url: null,
  partido_atual: 'PT',
  total_trocas: 2,
  total_partidos: 3,
  siglas_sequencia: ['PSDB', 'MDB', 'PT'],
  historico: [
    { partido: 'PSDB', data_filiacao: '2000-01-01', data_desfiliacao: '2005-01-01', motivo: 'TROCA_PARTIDARIA', is_atual: false },
    { partido: 'PT', data_filiacao: '2010-01-01', data_desfiliacao: null, motivo: null, is_atual: true },
  ],
  ...over,
});

const data: PartyFidelityResponse = {
  summary: {
    total_parlamentares: 100,
    total_nomades: 25,
    taxa_migracao_pct: 25,
    partido_maior_ganho: 'PT',
    saldo_maior_ganho: 5,
    partido_maior_perda: 'PSDB',
    saldo_maior_perda: -5,
  },
  party_balance: [
    { partido: 'PT', bancada_atual: 10, bancada_inicial: 5, ganhos: 5, perdas: 0, saldo_liquido: 5 },
    { partido: 'PSDB', bancada_atual: 0, bancada_inicial: 5, ganhos: 0, perdas: 5, saldo_liquido: -5 },
    { partido: 'PL', bancada_atual: 3, bancada_inicial: 3, ganhos: 0, perdas: 0, saldo_liquido: 0 },
  ],
  top_nomads: [
    nomad({}),
    nomad({ id: '2', nome_eleitoral: 'Ciclano', partido_atual: 'PL', uf: 'RJ', cargo: 'SENADOR', siglas_sequencia: ['DEM', 'PL'], foto_url: 'javascript:alert(1)' }),
  ],
};

describe('PartyFidelityPanel', () => {
  it('mostra estado vazio (não some) quando não há dados', () => {
    render(<PartyFidelityPanel fidelityData={null} />);
    expect(screen.getByText('Fidelidade partidária indisponível')).toBeInTheDocument();
  });

  it('mostra estado vazio quando listas estão vazias e summary é {}', () => {
    render(<PartyFidelityPanel fidelityData={{ summary: {}, party_balance: [], top_nomads: [] } as unknown as PartyFidelityResponse} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('não quebra ao passar de null para dados (ordem dos hooks estável)', () => {
    const { rerender } = render(<PartyFidelityPanel fidelityData={null} />);
    rerender(<PartyFidelityPanel fidelityData={data} />);
    expect(screen.getByText(/Ranking dos/)).toBeInTheDocument();
    rerender(<PartyFidelityPanel fidelityData={null} />);
    expect(screen.getByText('Fidelidade partidária indisponível')).toBeInTheDocument();
  });

  it('exibe o resumo calculado e o ranking de nômades', () => {
    render(<PartyFidelityPanel fidelityData={data} />);
    expect(screen.getByText('25,0%')).toBeInTheDocument();
    expect(screen.getByText('(25/100)')).toBeInTheDocument();
    expect(screen.getAllByText('+5').length).toBeGreaterThan(0); // selo de resumo (+ tooltip)
    expect(screen.getAllByText('-5').length).toBeGreaterThan(0);
    expect(screen.getByTestId('tooltip-content')).toHaveTextContent('+5 cadeiras');
    expect(screen.getByTestId('tooltip-content')).toHaveTextContent('Bancada Atual:10');
    expect(screen.getByText('Fulano')).toBeInTheDocument();
    expect(screen.getByText('Ciclano')).toBeInTheDocument();
    expect(screen.getByText(/Senador • RJ/)).toBeInTheDocument();
    expect(screen.getByText(/Deputado • SP/)).toBeInTheDocument();
  });

  it('com summary {} não imprime "undefined" nem "NaN"', () => {
    render(<PartyFidelityPanel fidelityData={{ ...data, summary: {} } as unknown as PartyFidelityResponse} />);
    expect(document.body.textContent).not.toMatch(/undefined|NaN|null/);
    expect(screen.getAllByText('Indisponível').length).toBeGreaterThan(0);
  });

  it('não renderiza foto com esquema perigoso', () => {
    const { container } = render(<PartyFidelityPanel fidelityData={data} />);
    expect(container.querySelector('img[src^="javascript"]')).toBeNull();
  });

  it('alterna o filtro do gráfico com aria-pressed', () => {
    render(<PartyFidelityPanel fidelityData={data} />);
    const top20 = screen.getByRole('button', { name: 'Top 20' });
    const destaques = screen.getByRole('button', { name: 'Destaques' });
    expect(destaques).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(top20);
    expect(top20).toHaveAttribute('aria-pressed', 'true');
    expect(destaques).toHaveAttribute('aria-pressed', 'false');
  });

  it('filtra nômades pela busca e mostra mensagem sem resultado', () => {
    render(<PartyFidelityPanel fidelityData={data} />);
    const input = screen.getByLabelText(/Buscar nômade/i);
    fireEvent.change(input, { target: { value: 'ciclano' } });
    expect(screen.queryByText('Fulano')).not.toBeInTheDocument();
    expect(screen.getByText('Ciclano')).toBeInTheDocument();
    fireEvent.change(input, { target: { value: 'zzz' } });
    expect(screen.getByText(/Nenhum parlamentar encontrado/)).toBeInTheDocument();
    fireEvent.change(input, { target: { value: 'dem' } });
    expect(screen.getByText('Ciclano')).toBeInTheDocument();
  });

  it('expande e recolhe o histórico cronológico', () => {
    render(<PartyFidelityPanel fidelityData={data} />);
    const btn = screen.getByRole('button', { name: /Detalhes das filiações de Fulano/ });
    expect(btn).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(btn);
    expect(btn).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(/Histórico Cronológico/)).toBeInTheDocument();
    expect(screen.getByText(/Ativo \(Atual\)/)).toBeInTheDocument();
    expect(screen.getByText('TROCA PARTIDARIA')).toBeInTheDocument();
    fireEvent.click(btn);
    expect(screen.queryByText(/Histórico Cronológico/)).not.toBeInTheDocument();
  });

  it('siglas viram botões quando há onSelectParty', () => {
    const onSelect = vi.fn();
    render(<PartyFidelityPanel fidelityData={data} onSelectParty={onSelect} />);
    const first = screen.getAllByRole('button', { name: 'PSDB' })[0];
    fireEvent.click(first);
    expect(onSelect).toHaveBeenCalledWith('PSDB');
  });
});

describe('PartyLink', () => {
  it('sem sigla mostra "Indisponível"', () => {
    render(<PartyLink sigla={null} />);
    expect(screen.getByText('Indisponível')).toBeInTheDocument();
  });

  it('sem callback é texto simples; com callback é botão', () => {
    const { rerender } = render(<PartyLink sigla="PT" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    const onSelect = vi.fn();
    rerender(<PartyLink sigla="PT" onSelectParty={onSelect}>rótulo</PartyLink>);
    const btn = within(document.body).getByRole('button', { name: 'rótulo' });
    fireEvent.click(btn);
    expect(onSelect).toHaveBeenCalledWith('PT');
  });
});
