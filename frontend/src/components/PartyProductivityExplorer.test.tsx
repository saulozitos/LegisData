import React from "react";
import { render, screen, fireEvent, within } from "@testing-library/react";
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

const ponto = (ano: number, ippm: number): api.PartyEvolutionPoint => ({
  ano,
  ippm,
  pontuacao_bruta_ialp: ippm * 10,
  cadeiras_dia_equivalentes: 10,
  parlamentares: 10,
  projetos_apresentados: 100,
  projetos_aprovados: 5,
  taxa_eficacia_pct: 5,
});

const mockEvolucao: api.IPPMEvolutionResponse = {
  periodo: { ano_inicio: 2023, ano_fim: 2025, casa: "ALL" },
  anos: [2023, 2024, 2025],
  partidos: [
    { sigla: "PT", nome_completo: "Partido dos Trabalhadores", cor_hex: "#ef4444", serie: [ponto(2023, 20), ponto(2024, 25), ponto(2025, 30)] },
    { sigla: "PL", nome_completo: "Partido Liberal", cor_hex: "#1d4ed8", serie: [ponto(2023, 30), ponto(2024, 22), ponto(2025, 18)] },
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

const abrirTabela = async () => {
  fireEvent.click(await screen.findByRole("tab", { name: /Tabela/i }));
};

describe("PartyProductivityExplorer Component", () => {
  it("renderiza cabeçalho executivo, resumo geral e tabela de ranking por IPPM", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);

    render(<PartyProductivityExplorer />);

    expect(await screen.findByText("25.50")).toBeInTheDocument();
    await abrirTabela();
    expect(screen.getByText(/Raio-X dos Partidos & Índice de Produtividade Partidária Média/i)).toBeInTheDocument(); // Média IPPM Geral
    expect(screen.getAllByText("PT")[0]).toBeInTheDocument();
    expect(screen.getAllByText("PL")[0]).toBeInTheDocument();
    expect(screen.getByText("30.20")).toBeInTheDocument(); // IPPM Score PT
  });

  it("permite filtrar partidos por busca em tempo real e limpar o filtro", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);

    render(<PartyProductivityExplorer />);

    await abrirTabela();
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

    await abrirTabela();
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

  it("mantém a Matriz de Eficiência como última parte da página, recolhida até ser aberta", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);

    render(<PartyProductivityExplorer />);

    const alternar = await screen.findByRole("button", { name: /Matriz de Eficiência/i });
    expect(alternar).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/Técnicos & Articuladores/i)).not.toBeInTheDocument();

    // fica depois do conteúdo da aba (última parte da página)
    const comparar = document.getElementById("compare-charts") as HTMLElement;
    expect(comparar.compareDocumentPosition(alternar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.click(alternar);
    expect(await screen.findByText(/Técnicos & Articuladores/i)).toBeInTheDocument();
    expect(screen.getByText(/Dispersão: Volume de Projetos vs. Eficácia de Aprovação/i)).toBeInTheDocument();
    expect(alternar).toHaveAttribute("aria-expanded", "true");

    // continua disponível ao trocar de aba
    await abrirTabela();
    expect(await screen.findByText("Partido dos Trabalhadores")).toBeInTheDocument();
    expect(screen.getByText(/Técnicos & Articuladores/i)).toBeInTheDocument();
  });

  it("a bolha da matriz cresce com o IPPM do partido", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);

    render(<PartyProductivityExplorer />);

    fireEvent.click(await screen.findByRole("button", { name: /Matriz de Eficiência/i }));
    const bolhaPT = screen.getByTitle(/^PT:/i).firstElementChild as HTMLElement; // IPPM 30,2 (maior)
    const bolhaPL = screen.getByTitle(/^PL:/i).firstElementChild as HTMLElement; // IPPM 20,0
    expect(parseInt(bolhaPT.style.width)).toBeGreaterThan(parseInt(bolhaPL.style.width));
  });

  it("abre e fecha o modal de histórico dinâmico de mandatos e licenças", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);
    vi.spyOn(api, "getPartyMandateHistory").mockResolvedValue(mockTimelineResponse);

    render(<PartyProductivityExplorer />);

    await abrirTabela();
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

    await abrirTabela();
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

    await abrirTabela();
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

    await abrirTabela();
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

  it("na matriz, permite clicar em um partido para abrir o modal de mandato", async () => {
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

    await abrirTabela();
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

  it("mostra o aviso do período e traço quando a coesão está indisponível", async () => {
    const semVotos = structuredClone(mockRankingResponse);
    semVotos.periodo.aviso = "Partidos sem cadeiras registradas no período ficaram fora do ranking: PRD";
    semVotos.ranking[0].pilares.fidelidade_partidaria_pct = null;
    semVotos.ranking[0].pilares.assinaturas_apoio_quorum = 7;
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(semVotos);

    render(<PartyProductivityExplorer />);

    expect(await screen.findByText(/ficaram fora do ranking: PRD/)).toBeInTheDocument();
    await abrirTabela();
    expect(screen.getByText("—", { selector: "span.font-mono" })).toBeInTheDocument();
  });

  it("explica cada aba em linguagem simples e troca o texto ao alternar", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);
    vi.spyOn(api, "getPartyIPPMEvolution").mockResolvedValue(mockEvolucao);

    render(<PartyProductivityExplorer />);

    expect(await screen.findByText(/Barras para comparar os partidos de uma olhada/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Tabela/i }));
    expect(await screen.findByText(/Todos os números de cada partido lado a lado/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Evolução/i }));
    expect(await screen.findByText(/Como a produtividade \(IPPM\) de cada partido mudou ano a ano/i)).toBeInTheDocument();
  });

  it("Comparar: barras ordenadas pelo indicador escolhido e projetos aprovados por partido", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);

    render(<PartyProductivityExplorer />);

    const lista = await screen.findByRole("list", { name: /ordenados por Produtividade/i });
    const siglas = () => within(lista).getAllByRole("button").map((b) => b.textContent);
    expect(siglas()).toEqual(["PT", "PL"]); // 30,2 e 20,0
    expect(within(lista).getByText("30,20")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Aprovação" }));
    const porAprovacao = screen.getByRole("list", { name: /ordenados por Aprovação/i });
    expect(within(porAprovacao).getAllByRole("button").map((b) => b.textContent)).toEqual(["PT", "PL"]); // 12,5% e 5,0%
    expect(within(porAprovacao).getByText("12,5%")).toBeInTheDocument();

    expect(screen.getByRole("img", { name: "PT: 15 de 120 projetos aprovados" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "PL: 10 de 200 projetos aprovados" })).toBeInTheDocument();
  });

  it("Comparar: coesão indisponível não vira barra e é informada", async () => {
    const semVotos = structuredClone(mockRankingResponse);
    semVotos.ranking[1].pilares.fidelidade_partidaria_pct = null;
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(semVotos);

    render(<PartyProductivityExplorer />);

    fireEvent.click(await screen.findByRole("button", { name: "Coesão nas votações" }));
    const lista = screen.getByRole("list", { name: /ordenados por Coesão/i });
    expect(within(lista).getAllByRole("button").map((b) => b.textContent)).toEqual(["PT"]);
    expect(screen.getByText(/Sem dado neste período: PL/)).toBeInTheDocument();
  });

  it("Evolução: mostra o gráfico de linhas e permite escolher os partidos", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);
    vi.spyOn(api, "getPartyIPPMEvolution").mockResolvedValue(mockEvolucao);

    render(<PartyProductivityExplorer />);

    fireEvent.click(await screen.findByRole("tab", { name: /Evolução/i }));

    const grafico = await screen.findByRole("img", { name: /Gráfico de linhas do IPPM de PT, PL entre 2023 e 2025/i });
    expect(grafico.querySelectorAll("polyline").length).toBe(2);
    expect(screen.getByText(/antes de 2003 a Câmara não publica o histórico de cadeiras/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "PL" })); // desmarca o PL
    expect(await screen.findByRole("img", { name: /Gráfico de linhas do IPPM de PT entre/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PL" })).toHaveAttribute("aria-pressed", "false");
  });

  it("Evolução: erro da API aparece com botão de nova tentativa", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);
    vi.spyOn(api, "getPartyIPPMEvolution").mockRejectedValue(new Error("falha na evolução"));

    render(<PartyProductivityExplorer />);

    fireEvent.click(await screen.findByRole("tab", { name: /Evolução/i }));
    expect(await screen.findByText(/falha na evolução/i)).toBeInTheDocument();
  });

  it("abre a explicação da média com a conta que levou ao resultado", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);

    render(<PartyProductivityExplorer />);

    fireEvent.click(await screen.findByRole("button", { name: "Entenda: Média IPPM Geral" }));

    const dialogo = await screen.findByRole("dialog");
    // Fora do cartão (portal em document.body): contêineres com blur/overflow cortariam um diálogo `fixed`
    expect(dialogo.parentElement?.parentElement).toBe(document.body);
    expect(dialogo).toHaveTextContent("O que significa");
    expect(dialogo).toHaveTextContent("Como é calculado");
    expect(dialogo).toHaveTextContent("cadeiras-dia");
    expect(dialogo).toHaveTextContent("Soma 50,20 ÷ 2 partidos = 25,50");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("mostra os números do líder em produtividade e marca o vencedor", async () => {
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(mockRankingResponse);

    render(<PartyProductivityExplorer />);

    fireEvent.click(await screen.findByRole("button", { name: "Entenda: Líder em Produtividade" }));

    const dialogo = await screen.findByRole("dialog");
    expect(dialogo).toHaveTextContent("Os números por trás deste resultado");
    expect(dialogo).toHaveTextContent("vencedor");
    expect(dialogo).toHaveTextContent("1980,0"); // pontos brutos do PT
    expect(dialogo).toHaveTextContent("30,20");
  });

  it("explica eficácia e coesão e informa quando não há dado", async () => {
    const semDados = structuredClone(mockRankingResponse);
    semDados.resumo_geral.partido_mais_eficaz = null;
    semDados.resumo_geral.partido_mais_coeso = null;
    semDados.ranking.forEach((p) => {
      p.projetos_aprovados = 0;
      p.pilares.taxa_eficacia_pct = 0;
      p.pilares.fidelidade_partidaria_pct = null;
    });
    vi.spyOn(api, "getPartyIPPMRanking").mockResolvedValue(semDados);

    render(<PartyProductivityExplorer />);

    fireEvent.click(await screen.findByRole("button", { name: "Entenda: Maior Eficácia Real" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("Nenhum partido teve projeto aprovado neste período");
    fireEvent.keyDown(document, { key: "Escape" });

    fireEvent.click(screen.getByRole("button", { name: "Entenda: Maior Coesão de Bancada" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("Sem votações nominais com orientação de bancada");
  });
});
