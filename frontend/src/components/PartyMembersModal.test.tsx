import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, vi, expect, beforeEach } from 'vitest';
import PartyMembersModal from './PartyMembersModal';
import * as api from '@/services/api';

vi.mock('@/services/api', () => ({
  searchPoliticians: vi.fn(),
  getParties: vi.fn(),
}));
const search = api.searchPoliticians as unknown as ReturnType<typeof vi.fn>;
const getParties = api.getParties as unknown as ReturnType<typeof vi.fn>;

const pol = (id: string, nome: string, uf: string, cargo = 'DEPUTADO_FEDERAL', foto: string | null = null) => ({
  id,
  nome_eleitoral: nome,
  nome_civil: `${nome} Civil`,
  cargo,
  partido_sigla: 'PT',
  partido_nome: 'Partido dos Trabalhadores',
  uf,
  foto_url: foto,
});

const catalog = [
  { id: '1', sigla: 'PT', nome_completo: 'Partido dos Trabalhadores', numero_eleitoral: 13, espectro_politico: 'ESQUERDA', ideologia: 'Socialismo', lema: 'Lema X', logo_url: null, total_deputados: 1, total_senadores: 1, total_parlamentares: 2, total_filiados_ativos: 1, cor_hex: '#f00' },
];

const baseProps = { partySigla: 'PT', isOpen: true, onClose: () => {}, onSelectPolitician: () => {} };

beforeEach(() => {
  search.mockReset();
  getParties.mockReset();
  getParties.mockResolvedValue(catalog);
});

describe('PartyMembersModal', () => {
  it('não renderiza nem busca quando fechado ou sem partido', () => {
    const { rerender } = render(<PartyMembersModal {...baseProps} isOpen={false} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    rerender(<PartyMembersModal {...baseProps} partySigla={null} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(search).not.toHaveBeenCalled();
  });

  it('mostra carregando, depois a bancada com dados do catálogo', async () => {
    search.mockResolvedValue({ politicos: [pol('1', 'Ana', 'SP'), pol('2', 'Bia', 'RJ', 'SENADOR', 'https://x.org/b.jpg')] });
    render(<PartyMembersModal {...baseProps} />);
    expect(screen.getByRole('dialog', { name: /Bancada: PT/ })).toBeInTheDocument();
    expect(screen.getByText('Carregando parlamentares...')).toBeInTheDocument();

    expect(await screen.findByText('Ana')).toBeInTheDocument();
    expect(await screen.findByText('(Partido dos Trabalhadores)')).toBeInTheDocument();
    expect(screen.getByText('Nº 13')).toBeInTheDocument();
    expect(screen.getByText('Socialismo')).toBeInTheDocument();
    expect(screen.getByText(/“Lema X”/)).toBeInTheDocument();
    expect(screen.getByText('Senador')).toBeInTheDocument();
    expect(screen.getByText('Todos (2)')).toBeInTheDocument();
    expect(search).toHaveBeenCalledWith(undefined, undefined, 'PT', undefined, 300, expect.any(AbortSignal));
  });

  it('filtra por Casa chamando a API com o cargo', async () => {
    search.mockResolvedValue({ politicos: [] });
    render(<PartyMembersModal {...baseProps} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Senadores' }));
    await waitFor(() => expect(search).toHaveBeenCalledWith(undefined, 'SENADOR', 'PT', undefined, 300, expect.any(AbortSignal)));
    expect(screen.getByRole('button', { name: 'Senadores' })).toHaveAttribute('aria-pressed', 'true');
    expect(await screen.findByText(/Nenhum membro ativo cadastrado no PT/)).toBeInTheDocument();
  });

  it('filtra localmente por nome/UF e informa quando nada confere', async () => {
    search.mockResolvedValue({ politicos: [pol('1', 'Ana', 'SP'), pol('2', 'Bia', 'RJ')] });
    render(<PartyMembersModal {...baseProps} />);
    await screen.findByText('Ana');
    const input = screen.getByLabelText(/Filtrar parlamentares do PT/);
    fireEvent.change(input, { target: { value: 'rj' } });
    expect(screen.queryByText('Ana')).not.toBeInTheDocument();
    expect(screen.getByText('Bia')).toBeInTheDocument();
    fireEvent.change(input, { target: { value: 'zzz' } });
    expect(screen.getByText(/Tente buscar por outro nome/)).toBeInTheDocument();
  });

  it('abre o Raio-X do parlamentar clicado', async () => {
    search.mockResolvedValue({ politicos: [pol('42', 'Ana', 'SP')] });
    const onSelect = vi.fn();
    render(<PartyMembersModal {...baseProps} onSelectPolitician={onSelect} />);
    fireEvent.click(await screen.findByTitle(/Raio-X de Ana/));
    expect(onSelect).toHaveBeenCalledWith('42');
  });

  it('fecha com o botão, com Esc e clicando fora', async () => {
    search.mockResolvedValue({ politicos: [] });
    const onClose = vi.fn();
    render(<PartyMembersModal {...baseProps} onClose={onClose} />);
    await screen.findByText(/Nenhum membro ativo/);
    fireEvent.click(screen.getByRole('button', { name: 'Fechar modal' }));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('erro mostra alerta e retry busca de novo', async () => {
    search.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce({ politicos: [pol('1', 'Ana', 'SP')] });
    render(<PartyMembersModal {...baseProps} />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('Ana')).toBeInTheDocument();
  });

  it('funciona mesmo sem o catálogo (falha do /parties)', async () => {
    getParties.mockRejectedValue(new Error('x'));
    search.mockResolvedValue({ politicos: [pol('1', 'Ana', 'SP')] });
    render(<PartyMembersModal {...baseProps} />);
    expect(await screen.findByText('Ana')).toBeInTheDocument();
    expect(screen.queryByText('Nº 13')).not.toBeInTheDocument();
  });
});
