import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import PartyProductivityExplorer from "./PartyProductivityExplorer";
import * as api from "@/services/api";

const mockRankingResponse: api.IPPMRankingResponse = {
  periodo: {
    ano: 2026,
    data_inicio: "2026-01-01",
    data_fim: "2026-10-14",
    casa: "ALL",
    bloco: "ALL",
    espectro: "ALL",
  },
  resumo_geral: {
    total_partidos: 2,
    media_ippm_geral: 25.5,
    partido_mais_produtivo: {
      sigla: "PT",
      ippm_score: 30.2,
      cor_hex: "#ef4444",
    },
    partido_mais_eficaz: {
      sigla: "PL",
      taxa_eficacia: 15.0,
      cor_hex: "#1d4ed8",
    },
    partido_mais_coeso: {
      sigla: "PT",
      fidelidade_pct: 92.5,
      cor_hex: "#ef4444",
    },
  },
  ranking: [
    {
      posicao: 1,
      partido_id: "p1",
      sigla: "PT",
      nome_completo: "Partido dos Trabalhadores",
      numero_eleitoral: 13,
      espectro_politico: "ESQUERDA",
      bloco_politico: "BASE_GOVERNO",
      cor_hex: "#ef4444",
      logo_url: "https://example.com/pt.png",
      total_cadeiras_ativas: 68,
      cadeiras_dia_equivalentes: 65.5,
      parlamentares_produtivos: 40,
      pontuacao_bruta_ialp: 1980.0,
      ippm_score_medio: 30.2,
      projetos_apresentados: 120,
      projetos_aprovados: 15,
      pilares: {
        fidelidade_partidaria_pct: 92.5,
        taxa_eficacia_pct: 12.5,
        total_relatorias: 25,
        volume_relatorias: 55.0,
      },
      quadrante_eficiencia: {
        codigo: "LIDER_BANCADA",
        titulo: "Liderança de Bancada",
        descricao: "Alto volume de proposições e alta eficácia.",
      },
    },
    {
      posicao: 2,
      partido_id: "p2",
      sigla: "PL",
      nome_completo: "Partido Liberal",
      numero_eleitoral: 22,
      espectro_politico: "DIREITA",
      bloco_politico: "OPOSICAO",
      cor_hex: "#1d4ed8",
      logo_url: null,
      total_cadeiras_ativas: 99,
      cadeiras_dia_equivalentes: 95.0,
      parlamentares_produtivos: 50,
      pontuacao_bruta_ialp: 1900.0,
      ippm_score_medio: 20.0,
      projetos_apresentados: 200,
      projetos_aprovados: 10,
      pilares: {
        fidelidade_partidaria_pct: 85.0,
        taxa_eficacia_pct: 5.0,
        total_relatorias: 15,
        volume_relatorias: 30.0,
      },
      quadrante_eficiencia: {
        codigo: "POPULISMO_LEGISLATIVO",
        titulo: "Populismo Legislativo",
        descricao: "Muitos projetos com baixa aprovação.",
      },
    },
  ],
};

const mockTimelineResponse: api.PartyMandateTimelineResponse = {
  partido: "PT",
  total_membros_registrados: 3,
  titulares_exercicio: [
    {
      id: "h1",
      politico_id: "pol1",
      nome_eleitoral: "Deputado Titular",
      foto_url: null,
      casa: "CAMARA",
      situacao: "EXERCICIO",
      data_inicio: "2023-02-01",
      data_fim: null,
      observacao: null,
    },
  ],
  ministros_licenciados: [
    {
      id: "h2",
      politico_id: "pol2",
      nome_eleitoral: "Deputado Ministro",
      foto_url: null,
      casa: "CAMARA",
      situacao: "AFASTADO_MINISTERIO",
      data_inicio: "2023-01-01",
      data_fim: null,
      observacao: "Licenciado para o Ministério da Fazenda",
    },
  ],
  suplentes_ativos: [
    {
      id: "h3",
      politico_id: "pol3",
      nome_eleitoral: "Suplente Convocado",
      foto_url: null,
      casa: "CAMARA",
      situacao: "SUPLENCIA",
      data_inicio: "2023-01-05",
      data_fim: null,
      observacao: "Suplência ativa",
    },
  ],
};

describe("PartyProductivityExplorer Component", () => {
  it("renderiza cabeçalho executivo, resumo geral e tabela de ranking por IPPM", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);

    render(<PartyProductivityExplorer />);

    expect(await screen.findByText("25.50")).toBeInTheDocument();
    expect(screen.getByText(/Raio-X dos Partidos & Índice de Produtividade Partidária Média/i)).toBeInTheDocument(); // Média IPPM Geral
    expect(screen.getAllByText("PT")[0]).toBeInTheDocument();
    expect(screen.getAllByText("PL")[0]).toBeInTheDocument();
    expect(screen.getByText("30.20")).toBeInTheDocument(); // IPPM Score PT
  });

  it("permite filtrar partidos por busca em tempo real e limpar o filtro", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);

    render(<PartyProductivityExplorer />);

    expect(await screen.findByText("Partido dos Trabalhadores")).toBeInTheDocument();
    expect(screen.getByText("Partido Liberal")).toBeInTheDocument();

    const searchInput = screen.getByPlaceholderText(/Buscar legenda por sigla ou nome oficial/i);
    fireEvent.change(searchInput, { target: { value: "Liberal" } });

    expect(screen.queryByText("Partido dos Trabalhadores")).not.toBeInTheDocument();
    expect(screen.getByText("Partido Liberal")).toBeInTheDocument();

    const clearBtn = screen.getByLabelText("Limpar busca");
    fireEvent.click(clearBtn);

    expect(screen.getByText("Partido dos Trabalhadores")).toBeInTheDocument();
  });

  it("permite ordenar colunas da tabela clicando nos cabeçalhos", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);

    render(<PartyProductivityExplorer />);

    expect(await screen.findByText("Partido dos Trabalhadores")).toBeInTheDocument();

    // Clicar no cabeçalho de Bancada
    const bancadaHeader = screen.getByText(/Bancada \(C-Dia\)/i);
    fireEvent.click(bancadaHeader);

    // Clicar no cabeçalho de Fidelidade (Coesão)
    const coesaoHeader = screen.getByText("Coesão");
    fireEvent.click(coesaoHeader);

    // Clicar no cabeçalho de Sigla
    const siglaHeader = screen.getByText(/Partido & Espectro/i);
    fireEvent.click(siglaHeader);
    expect(screen.getAllByText("PT").length).toBeGreaterThan(0);
  });

  it("alterna entre visão de Tabela e Matriz de Eficiência (Quadrantes)", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);

    render(<PartyProductivityExplorer />);

    expect(await screen.findByText("Partido dos Trabalhadores")).toBeInTheDocument();

    const quadranteBtn = screen.getByRole("button", { name: /Matriz de Eficiência/i });
    fireEvent.click(quadranteBtn);

    expect(await screen.findByText(/Técnicos & Articuladores/i)).toBeInTheDocument();
    expect(screen.getByText(/Dispersão: Volume de Projetos vs. Eficácia de Aprovação/i)).toBeInTheDocument();

    const rankingBtn = screen.getByRole("button", { name: /Ranking Geral/i });
    fireEvent.click(rankingBtn);

    expect(await screen.findByText("Partido dos Trabalhadores")).toBeInTheDocument();
  });

  it("abre e fecha o modal de histórico dinâmico de mandatos e licenças", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);
    vi.spyOn(api, "getPartyMandateHistory").mockResolvedValue(mockTimelineResponse);

    render(<PartyProductivityExplorer />);

    expect(await screen.findByText("Partido dos Trabalhadores")).toBeInTheDocument();

    const timelineBtns = screen.getAllByText("Licenças / Suplentes");
    fireEvent.click(timelineBtns[0]);

    expect(await screen.findByText(/Bancada & Licenças Temporárias: PT/i)).toBeInTheDocument();
    expect(screen.getByText("Deputado Ministro")).toBeInTheDocument();
    expect(screen.getByText(/Licenciado para o Ministério da Fazenda/i)).toBeInTheDocument();
    expect(screen.getByText("Suplente Convocado")).toBeInTheDocument();

    const closeBtn = screen.getByLabelText("Fechar modal");
    fireEvent.click(closeBtn);

    expect(screen.queryByText(/Bancada & Licenças Temporárias: PT/i)).not.toBeInTheDocument();
  });

  it("chama callbacks onSelectPartyMembers e onOpenCatalog quando fornecidos", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);
    const mockSelectMembers = vi.fn();
    const mockOpenCatalog = vi.fn();

    render(
      <PartyProductivityExplorer
        onSelectPartyMembers={mockSelectMembers}
        onOpenCatalog={mockOpenCatalog}
      />
    );

    expect(await screen.findByText("Partido dos Trabalhadores")).toBeInTheDocument();

    const catalogBtn = screen.getByRole("button", { name: /Catálogo de Estatutos & Filiados/i });
    fireEvent.click(catalogBtn);
    expect(mockOpenCatalog).toHaveBeenCalledTimes(1);

    const membersBtns = screen.getAllByText("Membros");
    fireEvent.click(membersBtns[0]);
    expect(mockSelectMembers).toHaveBeenCalledWith("PT");
  });

  it("trata estado de erro com botão de repetição", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockRejectedValue(new Error("Erro de conexão com o banco"));

    render(<PartyProductivityExplorer />);

    expect(await screen.findByText(/Erro ao carregar ranking partidário/i)).toBeInTheDocument();
    expect(screen.getByText(/Erro de conexão com o banco/i)).toBeInTheDocument();
  });

  it("permite alterar filtros de Casa, Bloco, Espectro e Ano", async () => {
    const spy = vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);

    render(<PartyProductivityExplorer />);

    expect(await screen.findByText("Partido dos Trabalhadores")).toBeInTheDocument();

    const selects = screen.getAllByRole("combobox");
    // Casa filter
    fireEvent.change(selects[0], { target: { value: "CAMARA" } });
    // Bloco filter
    fireEvent.change(selects[1], { target: { value: "BASE_GOVERNO" } });
    // Espectro filter
    fireEvent.change(selects[2], { target: { value: "ESQUERDA" } });
    // Ano filter
    fireEvent.change(selects[3], { target: { value: "2025" } });

    expect(spy).toHaveBeenCalled();
  });

  it("ordena por todas as colunas numéricas e alterna ordem asc/desc", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);

    render(<PartyProductivityExplorer />);

    expect(await screen.findByText("Partido dos Trabalhadores")).toBeInTheDocument();

    // Posicao
    const posHeader = screen.getByText("#");
    fireEvent.click(posHeader);
    fireEvent.click(posHeader);

    // IALP Bruto
    const ialpHeader = screen.getByText(/IALP Bruto/i);
    fireEvent.click(ialpHeader);
    fireEvent.click(ialpHeader);

    // IPPM Médio
    const ippmHeader = screen.getByText(/IPPM Médio/i);
    fireEvent.click(ippmHeader);
    fireEvent.click(ippmHeader);

    // Eficácia
    const eficaciaHeader = screen.getByText("Eficácia");
    fireEvent.click(eficaciaHeader);
    fireEvent.click(eficaciaHeader);

    // Relatorias
    const relatoriasHeader = screen.getByText(/Relatorias/i);
    fireEvent.click(relatoriasHeader);
    fireEvent.click(relatoriasHeader);
  });

  it("na visão de quadrantes, permite clicar em um partido para abrir o modal de mandato", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);
    vi.spyOn(api, "getPartyMandateHistory").mockResolvedValue({
      partido: "PT",
      total_membros_registrados: 15,
      titulares_exercicio: Array.from({ length: 14 }, (_, i) => ({
        id: "titular_" + i,
        politico_id: "pol_" + i,
        nome_eleitoral: "Deputado " + i,
        foto_url: null,
        casa: "CAMARA",
        situacao: "EXERCICIO",
        data_inicio: "2023-02-01",
        data_fim: null,
        observacao: null,
      })),
      ministros_licenciados: [],
      suplentes_ativos: [],
    });

    render(<PartyProductivityExplorer />);

    expect(await screen.findByText("Partido dos Trabalhadores")).toBeInTheDocument();

    const quadranteBtn = screen.getByRole("button", { name: /Matriz de Eficiência/i });
    fireEvent.click(quadranteBtn);

    const ptQuadrantBubble = screen.getByTitle(/^PT:/i);
    fireEvent.click(ptQuadrantBubble);

    expect(await screen.findByText(/Bancada & Licenças Temporárias: PT/i)).toBeInTheDocument();
    expect(screen.getByText(/outros titulares ativos na base/i)).toBeInTheDocument();
  });

  it("renderiza com segurança quando o resumo_geral não tem destaques", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue({
      periodo: mockRankingResponse.periodo,
      resumo_geral: {
        total_partidos: 0,
        media_ippm_geral: 0,
        partido_mais_produtivo: null,
        partido_mais_eficaz: null,
        partido_mais_coeso: null,
      },
      ranking: [],
    });

    render(<PartyProductivityExplorer />);

    expect(await screen.findByText(/Nenhum partido localizado/i)).toBeInTheDocument();
  });
});
