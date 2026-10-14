import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CoauthorshipNetworkGraph from './CoauthorshipNetworkGraph';
import * as api from '@/services/api';

vi.mock('@/services/api', () => ({
  getCoauthorshipNetwork: vi.fn(),
}));

const mockGetNetwork = api.getCoauthorshipNetwork as unknown as ReturnType<typeof vi.fn>;

const sampleNetworkData: api.CoauthorshipNetworkResponse = {
  nodes: [
    {
      id: 'pol-1',
      name: 'Senador Silva',
      party: 'PSD',
      uf: 'MG',
      house: 'SENADO',
      photo_url: null,
      community: 1,
      betweenness_centrality: 0.25,
      degree: 8,
    },
    {
      id: 'pol-2',
      name: 'Deputada Santos',
      party: 'PL',
      uf: 'SP',
      house: 'CAMARA',
      photo_url: null,
      community: 2,
      betweenness_centrality: 0.05,
      degree: 4,
    },
  ],
  edges: [
    {
      source: 'pol-1',
      target: 'pol-2',
      weight: 3,
    },
  ],
  communities: [
    {
      community_id: 1,
      total_parlamentares: 1,
      partidos_predominantes: 'PSD (1)',
      color: '#22d3ee',
      label: 'Bancada Informal 1 (PSD)',
    },
    {
      community_id: 2,
      total_parlamentares: 1,
      partidos_predominantes: 'PL (1)',
      color: '#a855f7',
      label: 'Bancada Informal 2 (PL)',
    },
  ],
  stats: {
    total_nodes: 2,
    total_edges: 1,
    total_communities: 2,
    density: 1.0,
    tipo_filtro: 'ALL',
    top_articulators: ['Senador Silva', 'Deputada Santos'],
  },
};

describe('CoauthorshipNetworkGraph', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetNetwork.mockResolvedValue(sampleNetworkData);
  });

  it('renderiza o grafo, estatísticas e bancadas informais com sucesso', async () => {
    render(<CoauthorshipNetworkGraph />);

    expect(screen.getByText('Grafo de Redes & Análise de Coautoria')).toBeInTheDocument();
    expect(await screen.findByText('Senador Silva')).toBeInTheDocument();
    expect(screen.getByText('Bancada Informal 1 (PSD)')).toBeInTheDocument();
    expect(screen.getByText('Bancada Informal 2 (PL)')).toBeInTheDocument();
    expect(screen.getByText('100.0%')).toBeInTheDocument(); // densidade
  });

  it('permite alternar filtros de proposição chamando a API com tipo específico', async () => {
    render(<CoauthorshipNetworkGraph />);
    await screen.findByText('Senador Silva');

    const pecsBtn = screen.getByRole('button', { name: /PECs \(Ideológica\)/i });
    fireEvent.click(pecsBtn);

    await waitFor(() => {
      expect(mockGetNetwork).toHaveBeenLastCalledWith('PEC', 1, 'ALL', 60);
    });
  });

  it('abre e fecha a explicação metodológica de Louvain e Betweenness Centrality', async () => {
    render(<CoauthorshipNetworkGraph />);
    await screen.findByText('Senador Silva');

    const infoBtn = screen.getByRole('button', { name: /Entenda os Algoritmos/i });
    fireEvent.click(infoBtn);

    expect(screen.getByText('Metodologia de Modelagem de Redes Políticas')).toBeInTheDocument();
    expect(screen.getByText(/Comunidades de Louvain/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Betweenness Centrality/i).length).toBeGreaterThanOrEqual(1);

    const hideBtn = screen.getByRole('button', { name: /Ocultar Metodologia/i });
    fireEvent.click(hideBtn);
    expect(screen.queryByText('Metodologia de Modelagem de Redes Políticas')).not.toBeInTheDocument();
  });

  it('seleciona um nó e aciona callback de navegação para o parlamentar', async () => {
    const onSelectPolitician = vi.fn();
    render(<CoauthorshipNetworkGraph onSelectPolitician={onSelectPolitician} />);
    await screen.findByText('Senador Silva');

    // Clica no card de pontes de articulação para selecionar
    const cardArticulador = screen.getByText('#1 Ponte').closest('button');
    expect(cardArticulador).not.toBeNull();
    fireEvent.click(cardArticulador!);

    // O flyout lateral deve exibir o botão para ver dossiê completo
    const dossierBtn = await screen.findByRole('button', { name: /Ver Dossiê Completo/i });
    fireEvent.click(dossierBtn);

    expect(onSelectPolitician).toHaveBeenCalledWith('pol-1');
  });

  it('controles de zoom, pan e busca textual interagem com o visualizador', async () => {
    render(<CoauthorshipNetworkGraph />);
    await screen.findByText('Senador Silva');

    // Zoom in, zoom out, reset
    fireEvent.click(screen.getByTitle('Aproximar'));
    fireEvent.click(screen.getByTitle('Afastar'));
    fireEvent.click(screen.getByTitle('Resetar Câmera'));

    // Busca textual no grafo
    const searchInput = screen.getByPlaceholderText('Buscar no grafo...');
    fireEvent.change(searchInput, { target: { value: 'Silva' } });
    expect(searchInput).toHaveValue('Silva');
    fireEvent.change(searchInput, { target: { value: '' } });

    // Drag / Pan no SVG
    const svg = screen.getByLabelText('Grafo interativo de coautoria política');
    fireEvent.mouseDown(svg, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(svg, { clientX: 150, clientY: 120 });
    fireEvent.mouseUp(svg);
  });

  it('permite filtrar por bancada informal (Louvain), selecionar nó no SVG e fechar o card lateral', async () => {
    render(<CoauthorshipNetworkGraph />);
    await screen.findByText('Senador Silva');

    // Filtra por comunidade clicando na legenda
    const commBtn = screen.getByRole('button', { name: /Bancada Informal 1/i });
    fireEvent.click(commBtn);
    // Clica de novo para desmarcar
    fireEvent.click(commBtn);

    // Clica no card de articulador para abrir o card lateral
    const cardArticulador = screen.getByText('#1 Ponte').closest('button');
    fireEvent.click(cardArticulador!);

    // Card lateral aberto
    expect(screen.getByLabelText('Fechar detalhes')).toBeInTheDocument();

    // Hover e drag no SVG
    const nodeText = screen.getByText('PSD');
    fireEvent.mouseEnter(nodeText.closest('g')!);
    fireEvent.mouseLeave(nodeText.closest('g')!);

    // Fecha o card pelo botão X
    const closeBtn = screen.getByLabelText('Fechar detalhes');
    fireEvent.click(closeBtn);
    expect(screen.queryByLabelText('Fechar detalhes')).not.toBeInTheDocument();
  });

  it('permite alternar filtros de casa legislativa, peso mínimo e nós', async () => {
    render(<CoauthorshipNetworkGraph />);
    await screen.findByText('Senador Silva');

    // Alterna filtros
    const casaSelect = screen.getByLabelText('Casa:');
    fireEvent.change(casaSelect, { target: { value: 'SENADO' } });

    const slider = screen.getByRole('slider');
    fireEvent.change(slider, { target: { value: '3' } });

    const limitSelect = screen.getByLabelText('Amostra:');
    fireEvent.change(limitSelect, { target: { value: '150' } });

    await waitFor(() => {
      expect(mockGetNetwork).toHaveBeenLastCalledWith('ALL', 3, 'SENADO', 150);
    });
  });
});
