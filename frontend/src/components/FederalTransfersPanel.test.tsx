import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, vi, expect, beforeEach } from 'vitest';
import FederalTransfersPanel from './FederalTransfersPanel';
import * as api from '@/services/api';

vi.mock('recharts', async () => (await import('@/test/recharts')).rechartsMock);
vi.mock('@/services/api', () => ({ getFederalTransfers: vi.fn() }));

const uf = (sigla: string, nome: string, regiao: string, valor: number, pop: number, area = 'Saúde') => ({
  uf: sigla,
  estado_nome: nome,
  regiao,
  area_tematica: area,
  valor_pago_brl: valor,
  populacao_estimada: pop,
  valor_per_capita_brl: valor / pop,
});

const all = {
  mandato_id: 'm1',
  periodo: '2023-2026',
  total_repassado_brl: 3_000_000_000,
  areas_resumo: { 'Saúde': 2_000_000_000, 'Educação': 1_000_000_000, 'Cultura': 5 },
  regioes_resumo: {},
  por_uf: [
    uf('SP', 'São Paulo', 'Sudeste', 2_000_000_000, 44_000_000),
    uf('AC', 'Acre', 'Norte', 1_000_000_000, 1_000_000),
  ],
};

const getTransfers = api.getFederalTransfers as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  getTransfers.mockReset();
});

describe('FederalTransfersPanel', () => {
  it('mostra carregando e depois a tabela ordenada por volume', async () => {
    getTransfers.mockResolvedValue(all);
    render(<FederalTransfersPanel mandateId="m1" />);
    expect(screen.getByRole('status')).toBeInTheDocument();

    expect(await screen.findByText('São Paulo')).toBeInTheDocument();
    const rows = screen.getAllByRole('row');
    expect(rows[1]).toHaveTextContent('São Paulo');
    expect(screen.getByText(/R\$ 3,0 Bilhões/)).toBeInTheDocument();
  });

  it('reordena por per capita', async () => {
    getTransfers.mockResolvedValue(all);
    render(<FederalTransfersPanel mandateId="m1" />);
    await screen.findByText('Acre');
    fireEvent.click(screen.getByRole('button', { name: /Per Capita/ }));
    expect(screen.getAllByRole('row')[1]).toHaveTextContent('Acre');
  });

  it('filtra por texto sem refazer requisição', async () => {
    getTransfers.mockResolvedValue(all);
    render(<FederalTransfersPanel mandateId="m1" />);
    await screen.findByText('Acre');
    fireEvent.change(screen.getByLabelText(/Buscar estado/i), { target: { value: 'norte' } });
    expect(screen.queryByText('São Paulo')).not.toBeInTheDocument();
    expect(screen.getByText('Acre')).toBeInTheDocument();
    expect(getTransfers).toHaveBeenCalledTimes(1);
  });

  it('botões de área vêm da API e filtrar chama a API com a área', async () => {
    getTransfers.mockImplementation((_id: string, area?: string) =>
      Promise.resolve(area ? { ...all, por_uf: [uf('SP', 'São Paulo', 'Sudeste', 500, 10, area)] } : all)
    );
    render(<FederalTransfersPanel mandateId="m1" />);
    await screen.findByText('Acre');
    expect(screen.getByRole('button', { name: 'Cultura' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Saúde' }));
    await waitFor(() => expect(screen.queryByText('Acre')).not.toBeInTheDocument());
    expect(getTransfers).toHaveBeenCalledWith('m1', 'Saúde', expect.any(AbortSignal));
    expect(screen.getByRole('button', { name: 'Saúde' })).toHaveAttribute('aria-pressed', 'true');
    // os botões de filtro não desaparecem durante a filtragem
    expect(screen.getByRole('button', { name: 'Educação' })).toBeInTheDocument();
  });

  it('erro mostra alerta e permite tentar de novo', async () => {
    getTransfers.mockRejectedValueOnce(new Error('falha')).mockResolvedValueOnce(all);
    render(<FederalTransfersPanel mandateId="m1" />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('São Paulo')).toBeInTheDocument();
  });

  it('erro ao filtrar mantém os botões e mostra alerta', async () => {
    getTransfers.mockImplementation((_id: string, area?: string) =>
      area ? Promise.reject(new Error('x')) : Promise.resolve(all)
    );
    render(<FederalTransfersPanel mandateId="m1" />);
    await screen.findByText('Acre');
    fireEvent.click(screen.getByRole('button', { name: 'Educação' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Educação' })).toBeInTheDocument();
  });

  it('resposta nula mostra estado vazio', async () => {
    getTransfers.mockResolvedValue(null);
    render(<FederalTransfersPanel mandateId="m1" />);
    expect(await screen.findByText('Repasses federais indisponíveis')).toBeInTheDocument();
  });

  it('refaz a busca ao trocar o mandato', async () => {
    getTransfers.mockResolvedValue(all);
    const { rerender } = render(<FederalTransfersPanel mandateId="m1" />);
    await screen.findByText('Acre');
    rerender(<FederalTransfersPanel mandateId="m2" />);
    await waitFor(() => expect(getTransfers).toHaveBeenCalledWith('m2', undefined, expect.any(AbortSignal)));
  });
});
