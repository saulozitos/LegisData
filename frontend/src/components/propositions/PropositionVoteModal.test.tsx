import React from 'react';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PropositionVoteModal from './PropositionVoteModal';
import * as api from '@/services/api';

vi.mock('@/services/api', () => ({ getPropositionNominalVotesSplit: vi.fn() }));
const getSplit = api.getPropositionNominalVotesSplit as unknown as ReturnType<typeof vi.fn>;

const voter = (id: string, nome: string, partido: string, uf: string, decisao: string) => ({
  politico_id: id,
  nome_eleitoral: nome,
  nome_civil: nome,
  partido_sigla: partido,
  espectro_politico: 'CENTRO',
  uf,
  cargo: 'DEPUTADO_FEDERAL',
  foto_url: null,
  decisao,
});

const response = (over: Record<string, unknown> = {}) => ({
  proposicao: { id: 'p', titulo: 'PL 1/2024', numero: 1, ano: 2024, ementa: 'Ementa do PL', setor: 'Saúde', autor_nome: 'Autora', status: 'x', data_apresentacao: '2024-01-01', url_oficial: 'https://camara.leg.br/1' },
  sessao: { id: 's', titulo: 't', data_hora: '2024-03-05T10:00:00', casa_legislativa: 'CAMARA', aprovada: true, total_votos: 4 },
  placar: { sim: 2, nao: 1, abstencao: 1, obstrucao: 0, total: 4 },
  votos_sim: [voter('1', 'Ana', 'PT', 'SP', 'SIM'), voter('2', 'Bia', 'PL', 'RJ', 'SIM')],
  votos_nao: [voter('3', 'Caio', 'PSDB', 'MG', 'NAO')],
  votos_abstencao: [voter('4', 'Dani', 'MDB', 'PA', 'ABSTENCAO')],
  votos_obstrucao: [],
  ...over,
});

beforeEach(() => getSplit.mockReset());

describe('PropositionVoteModal', () => {
  it('carrega e mostra matéria, placar e colunas SIM/NÃO lado a lado', async () => {
    getSplit.mockResolvedValue(response());
    render(<PropositionVoteModal propId="p" onClose={() => {}} />);
    expect(screen.getByText('Carregando proposição...')).toBeInTheDocument();

    expect(await screen.findByRole('dialog', { name: 'PL 1/2024' })).toBeInTheDocument();
    expect(screen.getByText('Nº 1/2024')).toBeInTheDocument();
    expect(screen.getByText('Aprovada em Plenário')).toBeInTheDocument();
    expect(screen.getByText('2024-03-05')).toBeInTheDocument();
    expect(screen.getByText('Ementa do PL')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Ler na Íntegra/ })).toHaveAttribute('href', 'https://camara.leg.br/1');
    expect(screen.getByText('Quem votou SIM (A Favor)')).toBeInTheDocument();
    expect(screen.getByText('Quem votou NÃO (Contra)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apenas SIM (2)' })).toBeInTheDocument();
    expect(getSplit).toHaveBeenCalledWith('p', undefined, expect.any(AbortSignal));
  });

  it('exibe abstenções e obstruções nas abas próprias (não são descartadas)', async () => {
    getSplit.mockResolvedValue(response({ votos_obstrucao: [voter('5', 'Edu', 'NOVO', 'SC', 'OBSTRUCAO')], placar: { sim: 2, nao: 1, abstencao: 1, obstrucao: 1, total: 5 } }));
    render(<PropositionVoteModal propId="p" onClose={() => {}} />);
    await screen.findByText('Quem votou SIM (A Favor)');

    fireEvent.click(screen.getByRole('button', { name: 'Abstenções (1)' }));
    expect(screen.getByText('Dani')).toBeInTheDocument();
    expect(screen.queryByText('Ana')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Obstruções (1)' }));
    expect(screen.getByText('Edu')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Obstruções (1)' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('filtra por nome, partido ou UF (com debounce) e limpa a busca', async () => {
    getSplit.mockResolvedValue(response());
    render(<PropositionVoteModal propId="p" onClose={() => {}} />);
    await screen.findByText('Quem votou SIM (A Favor)');
    fireEvent.change(screen.getByLabelText(/Buscar parlamentar/), { target: { value: 'rj' } });
    await waitFor(() => expect(screen.queryByText('Ana')).not.toBeInTheDocument());
    expect(screen.getByText('Bia')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apenas SIM (1)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apenas NÃO (0)' })).toBeInTheDocument();
    expect(screen.getByText('Nenhum voto NÃO encontrado para a busca.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Limpar busca' }));
    await waitFor(() => expect(screen.getByText('Ana')).toBeInTheDocument());
  });

  it('cartões abrem Raio-X/partido e fecham o modal', async () => {
    getSplit.mockResolvedValue(response());
    const onClose = vi.fn();
    const onSelectPolitician = vi.fn();
    const onSelectParty = vi.fn();
    render(<PropositionVoteModal propId="p" onClose={onClose} onSelectPolitician={onSelectPolitician} onSelectParty={onSelectParty} />);
    await screen.findByText('Quem votou SIM (A Favor)');
    fireEvent.click(screen.getByRole('button', { name: 'Ana' }));
    expect(onSelectPolitician).toHaveBeenCalledWith('1');
    fireEvent.click(screen.getByRole('button', { name: 'PL' }));
    expect(onSelectParty).toHaveBeenCalledWith('PL');
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('sem votação nominal informa que não há placar (sem afirmar que foi simbólica)', async () => {
    getSplit.mockResolvedValue(response({ placar: { sim: 0, nao: 0, abstencao: 0, obstrucao: 0, total: 0 }, votos_sim: [], votos_nao: [], votos_abstencao: [], votos_obstrucao: [] }));
    render(<PropositionVoteModal propId="p" onClose={() => {}} />);
    expect(await screen.findByText('Sem votação nominal registrada')).toBeInTheDocument();
  });

  it('falha da API mostra erro (não "tramita nas comissões") e permite tentar de novo', async () => {
    getSplit.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(response());
    render(<PropositionVoteModal propId="p" onClose={() => {}} />);
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Não foi possível carregar os votos')).toBeInTheDocument();
    expect(screen.queryByText('Sem votação nominal registrada')).not.toBeInTheDocument();
    fireEvent.click(within(alert).getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByText('Quem votou SIM (A Favor)')).toBeInTheDocument();
  });

  it('proposição ausente mostra "Dados da matéria indisponíveis."', async () => {
    getSplit.mockResolvedValue(response({ proposicao: null }));
    render(<PropositionVoteModal propId="p" onClose={() => {}} />);
    expect(await screen.findByText('Dados da matéria indisponíveis.')).toBeInTheDocument();
  });

  it('rejeitada em plenário e link oficial inseguro não vira href', async () => {
    getSplit.mockResolvedValue(response({
      sessao: { id: 's', titulo: 't', data_hora: '2024-03-05T10:00:00', casa_legislativa: 'CAMARA', aprovada: false, total_votos: 4 },
      proposicao: { ...response().proposicao, url_oficial: 'javascript:alert(1)', autor_nome: '' },
    }));
    render(<PropositionVoteModal propId="p" onClose={() => {}} />);
    expect(await screen.findByText('Rejeitada em Plenário')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByText('Não informado')).toBeInTheDocument();
  });

  it('fecha com Esc e com o botão Fechar', async () => {
    getSplit.mockResolvedValue(response());
    const onClose = vi.fn();
    render(<PropositionVoteModal propId="p" onClose={onClose} />);
    await screen.findByText('Quem votou SIM (A Favor)');
    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.click(screen.getAllByRole('button', { name: 'Fechar' })[0]);
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
