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

  it('renderiza corretamente deliberação SIMBOLICA com matriz de orientações partidárias e aviso educativo (Regra 6.3)', async () => {
    getSplit.mockResolvedValue(response({
      deliberacoes: [
        {
          id: 'delib-simb-1',
          tipo_deliberacao: 'SIMBOLICA',
          data_hora: '2024-03-05T10:00:00',
          local_deliberacao: 'Plenário da Câmara dos Deputados',
          resumo_decisao: 'Aprovada a redação final em votação simbólica',
          aprovada: true,
          aviso_educativo: 'No regime de deliberação simbólica...',
          orientacoes_partidarias: [
            { partido_bancada: 'PT', orientacao: 'SIM' },
            { partido_bancada: 'PL', orientacao: 'LIBERADO' },
            { partido_bancada: 'Governo', orientacao: 'SIM' },
          ],
        },
      ],
    }));

    render(<PropositionVoteModal propId="p" onClose={() => {}} />);
    expect(await screen.findByTestId('simbolica-view')).toBeInTheDocument();

    // Aviso educativo
    expect(screen.getByText(/Como funciona a Votação Simbólica no Congresso Nacional?/i)).toBeInTheDocument();
    expect(screen.getByText(/sem acionamento do painel eletrônico/i)).toBeInTheDocument();

    // Matriz de orientações partidárias de bancada
    expect(screen.getByText('Matriz de Orientações Partidárias de Bancada')).toBeInTheDocument();
    expect(screen.getByText('PT')).toBeInTheDocument();
    expect(screen.getByText('PL')).toBeInTheDocument();
    expect(screen.getByText('Governo')).toBeInTheDocument();
    expect(screen.getByText('LIBERADO')).toBeInTheDocument();

    // Busca nominal individual deve estar OCULTA (Regra 6.3)
    expect(screen.queryByLabelText(/Buscar parlamentar/)).not.toBeInTheDocument();
  });

  it('renderiza corretamente deliberação em COMISSAO com ata e parecer do relator associado (Regra 6.3)', async () => {
    getSplit.mockResolvedValue(response({
      deliberacoes: [
        {
          id: 'delib-com-1',
          tipo_deliberacao: 'COMISSAO',
          data_hora: '2024-02-20T14:30:00',
          local_deliberacao: 'CCJC',
          nome_comissao: 'Comissão de Constituição e Justiça e de Cidadania - CCJC',
          resumo_decisao: 'Aprovado parecer pela constitucionalidade',
          link_ata_reuniao: 'https://camara.leg.br/atas/ccjc-2024',
          relator_nome: 'Dep. Caroline de Toni',
          parecer_relator_numero: 'Parecer nº 08/2024-CCJC',
          parecer_relator_texto: 'Parecer favorável pela ampla constitucionalidade e técnica legislativa.',
          link_parecer_relator: 'https://camara.leg.br/pareceres/8',
          aprovada: true,
        },
      ],
    }));

    render(<PropositionVoteModal propId="p" onClose={() => {}} />);
    expect(await screen.findByTestId('comissao-view')).toBeInTheDocument();

    // Nome da comissão
    expect(screen.getByText('Comissão de Constituição e Justiça e de Cidadania - CCJC')).toBeInTheDocument();

    // Link da ata da reunião
    const linkAta = screen.getByRole('link', { name: /Acessar Ata Oficial da Reunião/i });
    expect(linkAta).toHaveAttribute('href', 'https://camara.leg.br/atas/ccjc-2024');

    // Parecer do relator associado
    expect(screen.getByText('Parecer do Relator Associado')).toBeInTheDocument();
    expect(screen.getByText('Dep. Caroline de Toni')).toBeInTheDocument();
    expect(screen.getByText('Parecer nº 08/2024-CCJC')).toBeInTheDocument();
    expect(screen.getByText(/Parecer favorável pela ampla constitucionalidade/i)).toBeInTheDocument();

    const linkParecer = screen.getByRole('link', { name: /Ver Íntegra do Parecer Técnico/i });
    expect(linkParecer).toHaveAttribute('href', 'https://camara.leg.br/pareceres/8');

    // Busca nominal individual deve estar OCULTA (Regra 6.3)
    expect(screen.queryByLabelText(/Buscar parlamentar/)).not.toBeInTheDocument();
  });

  it('permite alternar entre deliberações de diferentes tipos no seletor histórico', async () => {
    getSplit.mockResolvedValue(response({
      deliberacoes: [
        {
          id: 'delib-nom',
          tipo_deliberacao: 'NOMINAL',
          data_hora: '2024-03-05T10:00:00',
          local_deliberacao: 'Plenário da Câmara',
          resumo_decisao: 'Aprovada em plenário',
          aprovada: true,
        },
        {
          id: 'delib-com',
          tipo_deliberacao: 'COMISSAO',
          data_hora: '2024-02-15T10:00:00',
          local_deliberacao: 'CCJC',
          nome_comissao: 'CCJC - Comissão de Constituição e Justiça',
          resumo_decisao: 'Aprovado parecer',
          link_ata_reuniao: 'https://camara.leg.br/ata',
          relator_nome: 'Relator Fulano',
          parecer_relator_numero: 'Parecer nº 01/2024',
          parecer_relator_texto: 'Fundamentação favorável',
          aprovada: true,
        },
      ],
    }));

    render(<PropositionVoteModal propId="p" onClose={() => {}} />);
    // Inicialmente carrega NOMINAL por prioridade
    expect(await screen.findByText('Quem votou SIM (A Favor)')).toBeInTheDocument();

    // Clica no botão de Deliberação em Comissão
    fireEvent.click(screen.getByRole('button', { name: /Deliberação em Comissão/i }));

    // Agora mostra view de Comissão
    expect(await screen.findByTestId('comissao-view')).toBeInTheDocument();
    expect(screen.getByText('CCJC - Comissão de Constituição e Justiça')).toBeInTheDocument();
    expect(screen.getByText('Relator Fulano')).toBeInTheDocument();

    // Alterna de volta para Votação Nominal
    fireEvent.click(screen.getByRole('button', { name: /Votação Nominal/i }));
    expect(await screen.findByText('Quem votou SIM (A Favor)')).toBeInTheDocument();
  });
});
