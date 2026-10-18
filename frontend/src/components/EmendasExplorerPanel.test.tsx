import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import EmendasExplorerPanel from "./EmendasExplorerPanel";
import * as api from "@/services/api";

vi.mock("@/services/api", () => ({
  getEmendasResumo: vi.fn(),
  getEmendasPorLocalidade: vi.fn(),
  getEmendasPorAutor: vi.fn(),
}));

const mockResumo: api.EmendasResumoResponse = {
  estatisticas_gerais: {
    total_emendas: 54362,
    total_reservado_empenhado_brl: 274543195397.6,
    total_entregue_pago_brl: 165551611639.05,
    taxa_execucao_pago_pct: 60.3,
  },
  por_tipo_autor: {
    INDIVIDUAL: {
      total_empenhado: 130710746426.42,
      total_pago: 96008947883.37,
      quantidade: 51359,
      categoria: "Parlamentar Individual",
      icone: "👤",
      descricao: "Recurso da cota orçamentária individual de livre indicação.",
    },
    BANCADA_ESTADUAL: {
      total_empenhado: 58358572519.8,
      total_pago: 30619626299.68,
      quantidade: 2249,
      categoria: "Bancada Estadual",
      icone: "🗺️",
      descricao: "Recurso definido por votação coletiva de bancada.",
    },
    RELATOR_GERAL: {
      total_empenhado: 45030072866.92,
      total_pago: 20474123892.94,
      quantidade: 412,
      categoria: "Relator-Geral do Orçamento",
      icone: "⚖️",
      descricao: "Recurso alocado pela Comissão Mista de Orçamento.",
    },
    COMISSAO_INSTITUCIONAL: {
      total_empenhado: 40443803584.46,
      total_pago: 18448913563.06,
      quantidade: 342,
      categoria: "Comissão Temática",
      icone: "🏛️",
      descricao: "Verba institucional de comissões temáticas.",
    },
  },
  por_area_tematica: [
    {
      area: "Saúde",
      rotulo: "Saúde e Cuidados Básicos",
      icone: "🩺",
      total_empenhado: 139357011237.9,
      total_pago: 116097390704.42,
      quantidade: 21653,
    },
  ],
  por_ano: {
    "2023": { total_empenhado: 50000000, total_pago: 40000000, quantidade: 1000 },
  },
  top_ufs: [
    { uf: "PA", total_empenhado: 7386179502.26, total_pago: 3222718535.59, quantidade: 3785 },
  ],
  dicionario: {
    termos_orcamentarios: {
      empenhado: { termo_tecnico: "Empenhado", traducao: "Reservado", explicacao: "Dinheiro reservado." },
    },
    linha_do_tempo: [
      { etapa: 1, nome: "Empenho", status: "ok", descricao: "Dinheiro reservado em orçamento." },
    ],
    areas_tematicas: {},
  },
};

const mockLocalidade: api.EmendasLocalidadeResponse = {
  localidade_pesquisada: "Campinas",
  total_emendas_encontradas: 35,
  total_reservado_empenhado_brl: 30000000,
  total_entregue_pago_brl: 26022621,
  taxa_execucao_pct: 86.7,
  divisao_por_area: [],
  emendas: [
    {
      codigo_emenda: "201915270001",
      ano: 2019,
      area_tematica: "Educação",
      area_rotulo: "Educação e Escolas",
      area_icone: "🏫",
      valor_reservado_empenhado: 199989.69,
      valor_entregue_pago: 7497.0,
      estagio: "Dinheiro Entregue",
      autor: {
        tipo_autor: "INDIVIDUAL",
        categoria: "Parlamentar Individual",
        nome_tecnico: "CARLOS SAMPAIO",
        nome_amigavel: "Carlos Sampaio",
        descricao_amigavel: "Deputado Federal",
        icone: "👤",
      },
    },
  ],
  dicionario: mockResumo.dicionario,
};

const mockAutor: api.EmendasAutorResponse = {
  autor_pesquisado: "RELATOR GERAL",
  perfil_autor: {
    tipo_autor: "RELATOR_GERAL",
    categoria: "Relator-Geral do Orçamento",
    nome_tecnico: "RELATOR GERAL",
    nome_amigavel: "Relator-Geral do Orçamento",
    descricao_amigavel: "Recurso da CMO",
    icone: "⚖️",
  },
  total_emendas_enviadas: 412,
  total_reservado_empenhado_brl: 45030072866.92,
  total_entregue_pago_brl: 20474123892.94,
  taxa_execucao_pct: 45.5,
  top_destinos: [
    { localidade: "Nacional", total_empenhado: 10000000, total_pago: 5000000, quantidade: 50 },
  ],
  por_area_tematica: [
    { area: "Saúde", rotulo: "Saúde", icone: "🩺", total_empenhado: 20000000, total_pago: 10000000, quantidade: 100 },
  ],
  emendas: [
    {
      codigo_emenda: "20200001",
      ano: 2020,
      localidade_destino: "Nacional",
      area_tematica: "Saúde",
      area_rotulo: "Saúde e Cuidados Básicos",
      area_icone: "🩺",
      valor_reservado_empenhado: 1000000,
      valor_entregue_pago: 500000,
      estagio: "Dinheiro Entregue",
    },
  ],
};

describe("EmendasExplorerPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza estado de carregamento inicialmente", () => {
    vi.mocked(api.getEmendasResumo).mockReturnValue(new Promise(() => {}));
    render(<EmendasExplorerPanel />);
    expect(screen.getByText(/Carregando acervo de emendas orçamentárias/i)).toBeInTheDocument();
  });

  it("renderiza estado de erro com botão de tentar novamente", async () => {
    vi.mocked(api.getEmendasResumo).mockRejectedValue(new Error("Falha de rede"));
    render(<EmendasExplorerPanel />);
    expect(await screen.findByText(/Falha ao carregar emendas orçamentárias/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /tentar novamente/i })).toBeInTheDocument();
  });

  it("renderiza dados e KPIs consolidados com sucesso", async () => {
    vi.mocked(api.getEmendasResumo).mockResolvedValue(mockResumo);
    render(<EmendasExplorerPanel />);

    expect(await screen.findByText(/Explorador Nacional de Emendas Orçamentárias/i)).toBeInTheDocument();
    expect(screen.getByText(/Transparência Orçamentária • Ponto 2.7/i)).toBeInTheDocument();
    expect(screen.getAllByText(/54.362/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/60,3%/)).toBeInTheDocument();

    // 4 categorias institucionais
    expect(screen.getByText("Parlamentar Individual")).toBeInTheDocument();
    expect(screen.getByText("Bancada Estadual")).toBeInTheDocument();
    expect(screen.getByText("Relator-Geral do Orçamento")).toBeInTheDocument();
    expect(screen.getByText("Comissão Temática")).toBeInTheDocument();
  });

  it("expande e recolhe o Dicionário Cidadão", async () => {
    vi.mocked(api.getEmendasResumo).mockResolvedValue(mockResumo);
    render(<EmendasExplorerPanel />);
    await screen.findByText(/Explorador Nacional de Emendas Orçamentárias/i);

    const btnDic = screen.getByRole("button", { name: /Dicionário Cidadão/i });
    expect(screen.queryByText(/Glossário Cidadão: Entendendo o Ciclo/i)).not.toBeInTheDocument();

    fireEvent.click(btnDic);
    expect(await screen.findByText(/Glossário Cidadão: Entendendo o Ciclo/i)).toBeInTheDocument();
    expect(screen.getByText(/Linha do Tempo Oficial da Verba Pública/i)).toBeInTheDocument();

    fireEvent.click(btnDic);
    expect(screen.queryByText(/Glossário Cidadão: Entendendo o Ciclo/i)).not.toBeInTheDocument();
  });

  it("permite navegar para a aba de busca por cidade e exibe resultados locais", async () => {
    vi.mocked(api.getEmendasResumo).mockResolvedValue(mockResumo);
    vi.mocked(api.getEmendasPorLocalidade).mockResolvedValue(mockLocalidade);

    render(<EmendasExplorerPanel />);
    await screen.findByText(/Explorador Nacional de Emendas Orçamentárias/i);

    fireEvent.click(screen.getByRole("button", { name: /Busca por Cidade\/UF/i }));
    expect(await screen.findByText(/Pesquisa Territorial de Recursos Públicos/i)).toBeInTheDocument();
    expect(await screen.findByText("Carlos Sampaio")).toBeInTheDocument();
    expect(screen.getByText(/Cód. 201915270001/i)).toBeInTheDocument();
  });

  it("permite navegar para a aba de autores institucionais e exibe dados do Relator-Geral", async () => {
    vi.mocked(api.getEmendasResumo).mockResolvedValue(mockResumo);
    vi.mocked(api.getEmendasPorAutor).mockResolvedValue(mockAutor);

    render(<EmendasExplorerPanel />);
    await screen.findByText(/Explorador Nacional de Emendas Orçamentárias/i);

    fireEvent.click(screen.getByRole("button", { name: /Bancadas & Relator/i }));
    expect(await screen.findByText(/Auditoria de Autores Coletivos & Relator-Geral/i)).toBeInTheDocument();
    expect(await screen.findByText(/Recurso da CMO/i)).toBeInTheDocument();
    expect(screen.getByText(/Emendas deste Autor \(1\)/i)).toBeInTheDocument();
  });

  it("termo com menos de 2 letras não consulta a API e pede mais letras", async () => {
    vi.mocked(api.getEmendasResumo).mockResolvedValue(mockResumo);
    vi.mocked(api.getEmendasPorLocalidade).mockResolvedValue(mockLocalidade);

    render(<EmendasExplorerPanel />);
    await screen.findByText(/Explorador Nacional de Emendas Orçamentárias/i);
    fireEvent.click(screen.getByRole("button", { name: /Busca por Cidade\/UF/i }));
    await screen.findByText("Carlos Sampaio");
    vi.mocked(api.getEmendasPorLocalidade).mockClear();

    fireEvent.change(screen.getByLabelText(/Pesquisar por município ou estado/i), { target: { value: "C" } });
    expect(await screen.findByText(/Digite ao menos 2 letras/i)).toBeInTheDocument();
    expect(api.getEmendasPorLocalidade).not.toHaveBeenCalled();
  });

  it("o campo de busca limita o termo a 100 caracteres, como o backend", async () => {
    vi.mocked(api.getEmendasResumo).mockResolvedValue(mockResumo);
    vi.mocked(api.getEmendasPorLocalidade).mockResolvedValue(mockLocalidade);

    render(<EmendasExplorerPanel />);
    await screen.findByText(/Explorador Nacional de Emendas Orçamentárias/i);
    fireEvent.click(screen.getByRole("button", { name: /Busca por Cidade\/UF/i }));
    expect(screen.getByLabelText(/Pesquisar por município ou estado/i)).toHaveAttribute("maxlength", "100");
  });

  it("avisa quando a busca por autor reuniu mais de um autor", async () => {
    vi.mocked(api.getEmendasResumo).mockResolvedValue(mockResumo);
    vi.mocked(api.getEmendasPorAutor).mockResolvedValue({
      ...mockAutor,
      quantidade_autores: 2,
      autores_encontrados: [
        { nome_amigavel: "Bancada da Bahia", categoria: "Bancada Estadual", quantidade: 3 },
        { nome_amigavel: "Bancada de Goiás", categoria: "Bancada Estadual", quantidade: 1 },
      ],
    });

    render(<EmendasExplorerPanel />);
    await screen.findByText(/Explorador Nacional de Emendas Orçamentárias/i);
    fireEvent.click(screen.getByRole("button", { name: /Bancadas & Relator/i }));
    expect(await screen.findByText(/reuniu 2 autores/i)).toBeInTheDocument();
    expect(screen.getByText(/Bancada da Bahia, Bancada de Goiás/i)).toBeInTheDocument();
  });

  it("autor único não mostra o aviso de vários autores", async () => {
    vi.mocked(api.getEmendasResumo).mockResolvedValue(mockResumo);
    vi.mocked(api.getEmendasPorAutor).mockResolvedValue({ ...mockAutor, quantidade_autores: 1 });

    render(<EmendasExplorerPanel />);
    await screen.findByText(/Explorador Nacional de Emendas Orçamentárias/i);
    fireEvent.click(screen.getByRole("button", { name: /Bancadas & Relator/i }));
    await screen.findByText(/Recurso da CMO/i);
    expect(screen.queryByText(/reuniu/i)).not.toBeInTheDocument();
  });
});
