import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PoliticianProfile from './PoliticianProfile';
import * as api from '@/services/api';
import { fullDossier, sparseDossier } from '@/test/dossier';

vi.mock('@/services/api', () => ({
  searchPoliticians: vi.fn(),
  getPoliticianDossier: vi.fn(),
  getParties: vi.fn(),
  getPoliticianProductivity: vi.fn().mockResolvedValue(null),
}));
vi.mock('recharts', async () => (await import('@/test/recharts')).rechartsMock);

const search = api.searchPoliticians as unknown as ReturnType<typeof vi.fn>;
const getDossier = api.getPoliticianDossier as unknown as ReturnType<typeof vi.fn>;
const getParties = api.getParties as unknown as ReturnType<typeof vi.fn>;

/** Contêiner como na página inicial: guarda o ID e recebe as mudanças de seleção do componente. */
function Host({ initial, onChange }: { initial: string | null; onChange?: (id: string | null) => void }) {
  const [id, setId] = React.useState<string | null>(initial);
  return (
    <PoliticianProfile
      selectedPoliticianId={id}
      onSelectionChange={(next) => {
        setId(next);
        onChange?.(next);
      }}
    />
  );
}

const item = (id: string, nome: string) => ({ id, nome_eleitoral: nome, nome_civil: `${nome} Civil`, cargo: 'DEPUTADO_FEDERAL', partido_sigla: 'PT', partido_nome: 'PT', uf: 'SP', foto_url: null });

beforeEach(() => {
  search.mockReset();
  getDossier.mockReset();
  getParties.mockReset();
  getParties.mockResolvedValue([]);
  search.mockResolvedValue({ politicos: [item('pol-1', 'Ana Silva'), item('pol-2', 'Beto Souza')] });
  getDossier.mockImplementation((id: string) => Promise.resolve(id === 'pol-2' ? sparseDossier() : fullDossier()));
});

describe('PoliticianProfile', () => {
  it('sem seleção mostra a busca e o catálogo (Home do Raio-X)', async () => {
    render(<PoliticianProfile />);
    expect(screen.getByRole('combobox', { name: 'Buscar político pelo nome' })).toBeInTheDocument();
    expect(await screen.findByText('Catálogo de Parlamentares: Home do Raio-X')).toBeInTheDocument();
    expect(getDossier).not.toHaveBeenCalled();
  });

  it('abre o dossiê pelo ID externo, mostra a visão geral e busca com AbortSignal', async () => {
    render(<PoliticianProfile selectedPoliticianId="pol-1" />);
    expect(screen.getByText('Carregando dossiê do político...')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { level: 2, name: 'Ana Silva' })).toBeInTheDocument();
    expect(getDossier).toHaveBeenCalledWith('pol-1', expect.any(AbortSignal));
    expect(screen.getByRole('tab', { name: /Visão Geral/ })).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByRole('link', { name: /Enviar mensagem/ })).toBeInTheDocument();
  });

  it('seleciona pela busca com debounce, notifica o contêiner e carrega o dossiê', async () => {
    const onSelectionChange = vi.fn();
    render(<PoliticianProfile onSelectionChange={onSelectionChange} />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Buscar político pelo nome' }), { target: { value: 'ana' } });
    await waitFor(() => expect(search).toHaveBeenCalledWith('ana', undefined, undefined, undefined, 40, expect.any(AbortSignal)));
    const suggestions = await screen.findByRole('listbox', { name: 'Sugestões de políticos' });
    fireEvent.click(within(suggestions).getByRole('button', { name: /Ana Silva Civil/ }));
    expect(onSelectionChange).toHaveBeenCalledWith('pol-1');
    expect(await screen.findByRole('heading', { level: 2, name: 'Ana Silva' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Buscar político pelo nome' })).toHaveValue('Ana Silva');
  });

  it('troca de aba carrega a seção sob demanda e volta à visão geral ao trocar de político', async () => {
    const { rerender } = render(<PoliticianProfile selectedPoliticianId="pol-1" />);
    await screen.findByRole('heading', { level: 2, name: 'Ana Silva' });
    fireEvent.click(screen.getByRole('tab', { name: /Custos do Mandato/ }));
    expect(screen.getByRole('tab', { name: /Custos do Mandato/ })).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText('Custos do Mandato & Cota Parlamentar (CEAP)')).toBeInTheDocument();
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', 'dossier-tab-ceap');

    rerender(<PoliticianProfile selectedPoliticianId="pol-2" />);
    expect(await screen.findByRole('heading', { level: 2, name: 'Beto Souza' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Visão Geral/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('não mostra o político anterior sob o ID novo enquanto carrega', async () => {
    const { rerender } = render(<PoliticianProfile selectedPoliticianId="pol-1" />);
    await screen.findByRole('heading', { level: 2, name: 'Ana Silva' });
    getDossier.mockImplementation(() => new Promise(() => {}));
    rerender(<PoliticianProfile selectedPoliticianId="pol-3" />);
    expect(screen.getByText('Carregando dossiê do político...')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 2, name: 'Ana Silva' })).not.toBeInTheDocument();
  });

  it('dossiê esparso (backend com dados insuficientes) abre todas as abas sem derrubar a página', async () => {
    render(<PoliticianProfile selectedPoliticianId="pol-2" />);
    await screen.findByRole('heading', { level: 2, name: 'Beto Souza' });
    const names = [/Inteligência Cívica/, /Proposições/, /Quem Paga a Conta/, /Custos do Mandato/, /Destino das Emendas/, /Justiça/, /Presenças/, /Remuneração/, /Votações Nominais/, /Visão Geral/];
    for (const name of names) {
      fireEvent.click(screen.getByRole('tab', { name }));
      await waitFor(() => expect(screen.getByRole('tab', { name })).toHaveAttribute('aria-selected', 'true'));
      await waitFor(() => expect(screen.queryByText('Carregando seção...')).not.toBeInTheDocument());
      expect(screen.getByRole('tabpanel').textContent).not.toMatch(/\bnull\b|undefined|NaN/);
    }
  });

  it('erro mostra alerta com retry e botão de voltar; voltar limpa a seleção', async () => {
    const onSelectionChange = vi.fn();
    getDossier.mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(fullDossier());
    render(<Host initial="pol-1" onChange={onSelectionChange} />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Não foi possível carregar o dossiê');
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByRole('heading', { level: 2, name: 'Ana Silva' })).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: /Voltar ao Catálogo/ })[0]);
    expect(onSelectionChange).toHaveBeenCalledWith(null);
    expect(await screen.findByText('Catálogo de Parlamentares: Home do Raio-X')).toBeInTheDocument();
  });

  it('dossiê vazio mostra estado indisponível com opção de voltar', async () => {
    getDossier.mockResolvedValue(null);
    render(<PoliticianProfile selectedPoliticianId="pol-1" />);
    expect(await screen.findByText('Dossiê indisponível')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Voltar ao Catálogo/ })).toBeInTheDocument();
  });

  it('funciona sem contêiner controlando a seleção: escolher na busca não é desfeito', async () => {
    render(<PoliticianProfile />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Buscar político pelo nome' }), { target: { value: 'ana' } });
    const suggestions = await screen.findByRole('listbox', { name: 'Sugestões de políticos' });
    fireEvent.click(within(suggestions).getByRole('button', { name: /Ana Silva Civil/ }));
    expect(await screen.findByRole('heading', { level: 2, name: 'Ana Silva' })).toBeInTheDocument();
    // mesmo após novas renderizações, o dossiê permanece e "voltar" leva ao catálogo
    fireEvent.click(screen.getAllByRole('button', { name: /Voltar ao Catálogo/ })[0]);
    expect(await screen.findByText('Catálogo de Parlamentares: Home do Raio-X')).toBeInTheDocument();
  });

  it('com a prop fixa (contêiner que não atualiza), voltar não reabre o político automaticamente', async () => {
    render(<PoliticianProfile selectedPoliticianId="pol-1" />);
    await screen.findByRole('heading', { level: 2, name: 'Ana Silva' });
    fireEvent.click(screen.getAllByRole('button', { name: /Voltar ao Catálogo/ })[0]);
    expect(await screen.findByText('Catálogo de Parlamentares: Home do Raio-X')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 2, name: 'Ana Silva' })).not.toBeInTheDocument();
  });

  it('repassa onSelectParty ao cabeçalho do dossiê', async () => {
    const onSelectParty = vi.fn();
    render(<PoliticianProfile selectedPoliticianId="pol-1" onSelectParty={onSelectParty} />);
    await screen.findByRole('heading', { level: 2, name: 'Ana Silva' });
    fireEvent.click(screen.getAllByRole('button', { name: 'PT' })[0]);
    expect(onSelectParty).toHaveBeenCalledWith('PT');
  });
});
