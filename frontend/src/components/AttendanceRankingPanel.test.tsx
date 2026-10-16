import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AttendanceRankingPanel from "./AttendanceRankingPanel";
import * as api from "@/services/api";
import { anoInicioLegislatura } from "@/lib/legislatura";

vi.mock("@/services/api", () => ({
  getAttendanceRanking: vi.fn(),
  getAttendancePartyRanking: vi.fn(),
}));

const politicos: api.AttendanceRankingResponse = {
  criterio: "faltas",
  minimo_dias_para_taxa: 20,
  aviso: "Aviso de metodologia do ranking.",
  itens: [
    {
      politico_id: "p1",
      nome_eleitoral: "Fulano de Tal",
      foto_url: null,
      partido_sigla: "PT",
      casas: ["CAMARA_DOS_DEPUTADOS"],
      dias_registrados: 200,
      presencas: 120,
      faltas: 80,
      faltas_justificadas: 30,
      faltas_nao_justificadas: 50,
      faltas_inferidas: 0,
      taxa_ausencia_pct: 40,
      pontos_ialp: 12.5,
      indice_baixa_producao: 0.36,
    },
  ],
};

const partidos: api.AttendancePartyResponse = {
  minimo_dias: 2000,
  dias_sem_partido_identificado: 12,
  dias_com_partido_aproximado: 3,
  aviso: "Aviso de partidos.",
  itens: [
    {
      sigla: "XYZ",
      parlamentares: 10,
      dias_registrados: 3000,
      faltas: 600,
      faltas_justificadas: 400,
      faltas_nao_justificadas: 200,
      faltas_inferidas: 0,
      taxa_ausencia_pct: 20,
    },
  ],
};

const legislatura = anoInicioLegislatura(new Date());

describe("AttendanceRankingPanel", () => {
  beforeEach(() => {
    vi.mocked(api.getAttendanceRanking).mockResolvedValue(politicos);
    vi.mocked(api.getAttendancePartyRanking).mockResolvedValue(partidos);
  });

  it("lista os parlamentares com mais faltas e abre o perfil ao clicar", async () => {
    const onSelect = vi.fn();
    render(<AttendanceRankingPanel onSelectPolitician={onSelect} />);
    const nome = await screen.findByText("Fulano de Tal");
    expect(screen.getByText("Aviso de metodologia do ranking.")).toBeTruthy();
    fireEvent.click(nome);
    expect(onSelect).toHaveBeenCalledWith("p1");
    expect(api.getAttendanceRanking).toHaveBeenCalledWith(
      { casa: "ALL", ordenar: "faltas", anoInicio: legislatura, limit: 30 },
      expect.anything()
    );
  });

  it("refaz a consulta ao trocar o critério para falta com baixa produção", async () => {
    render(<AttendanceRankingPanel />);
    await screen.findByText("Fulano de Tal");
    fireEvent.change(screen.getByLabelText("Ordenar por"), { target: { value: "baixa_producao" } });
    await waitFor(() =>
      expect(api.getAttendanceRanking).toHaveBeenCalledWith(
        { casa: "ALL", ordenar: "baixa_producao", anoInicio: legislatura, limit: 30 },
        expect.anything()
      )
    );
  });

  it("mostra o ranking de partidos", async () => {
    const onParty = vi.fn();
    render(<AttendanceRankingPanel onSelectParty={onParty} />);
    await screen.findByText("Fulano de Tal");
    fireEvent.click(screen.getByRole("button", { name: /Partidos/ }));
    const sigla = await screen.findByText("XYZ");
    fireEvent.click(sigla);
    expect(onParty).toHaveBeenCalledWith("XYZ");
  });

  it("mostra estado vazio quando não há registros", async () => {
    vi.mocked(api.getAttendanceRanking).mockResolvedValue({ ...politicos, itens: [] });
    render(<AttendanceRankingPanel />);
    expect(await screen.findByText(/Sem registros de presença/)).toBeTruthy();
  });

  it("marca a visão escolhida com aria-pressed", async () => {
    render(<AttendanceRankingPanel />);
    await screen.findByText("Fulano de Tal");
    expect(screen.getByRole("button", { name: /Parlamentares/ }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: /Partidos/ }));
    expect(screen.getByRole("button", { name: /Partidos/ }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: /Parlamentares/ }).getAttribute("aria-pressed")).toBe("false");
    await screen.findByText("XYZ");
  });

  it("mostra erro e tenta de novo ao clicar em Tentar novamente", async () => {
    vi.mocked(api.getAttendanceRanking).mockRejectedValueOnce(new Error("falhou"));
    render(<AttendanceRankingPanel />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Tentar novamente/ }));
    expect(await screen.findByText("Fulano de Tal")).toBeTruthy();
    expect(api.getAttendanceRanking).toHaveBeenCalledTimes(2);
  });

  it("mostra n/d, e não zero, para taxa e contagens que a fonte não publica", async () => {
    vi.mocked(api.getAttendanceRanking).mockResolvedValue({
      ...politicos,
      itens: [
        {
          ...politicos.itens[0],
          faltas_justificadas: null,
          faltas_nao_justificadas: null,
          faltas_inferidas: null,
          taxa_ausencia_pct: null,
        },
      ],
    });
    render(<AttendanceRankingPanel />);
    await screen.findByText("Fulano de Tal");
    // taxa + justificadas + sem justificativa + inferidas
    expect(screen.getAllByText("n/d")).toHaveLength(4);
    expect(screen.getAllByLabelText(/não disponível/)).toHaveLength(3);
  });

  it("mostra a contagem quando a fonte publica o número, inclusive zero", async () => {
    vi.mocked(api.getAttendanceRanking).mockResolvedValue({
      ...politicos,
      itens: [{ ...politicos.itens[0], faltas_inferidas: 0 }],
    });
    render(<AttendanceRankingPanel />);
    await screen.findByText("Fulano de Tal");
    expect(screen.queryByText("n/d")).toBeNull();
  });

  it("refaz a consulta com SENADO ao trocar a casa", async () => {
    render(<AttendanceRankingPanel />);
    await screen.findByText("Fulano de Tal");
    fireEvent.change(screen.getByLabelText("Casa"), { target: { value: "SENADO" } });
    await waitFor(() =>
      expect(api.getAttendanceRanking).toHaveBeenCalledWith(
        { casa: "SENADO", ordenar: "faltas", anoInicio: legislatura, limit: 30 },
        expect.anything()
      )
    );
  });

  it("refaz a consulta com os anos do período escolhido", async () => {
    render(<AttendanceRankingPanel />);
    await screen.findByText("Fulano de Tal");
    fireEvent.change(screen.getByLabelText("Período"), { target: { value: "oficial" } });
    await waitFor(() =>
      expect(api.getAttendanceRanking).toHaveBeenCalledWith(
        { casa: "ALL", ordenar: "faltas", anoInicio: 2020, limit: 30 },
        expect.anything()
      )
    );
    fireEvent.change(screen.getByLabelText("Período"), { target: { value: "tudo" } });
    await waitFor(() =>
      expect(api.getAttendanceRanking).toHaveBeenCalledWith(
        { casa: "ALL", ordenar: "faltas", anoInicio: undefined, limit: 30 },
        expect.anything()
      )
    );
  });

  it("rotula a legislatura atual pela data, sem ano fixo", async () => {
    render(<AttendanceRankingPanel />);
    await screen.findByText("Fulano de Tal");
    expect(screen.getByRole("option", { name: `Legislatura atual (${legislatura} em diante)` })).toBeTruthy();
  });

  it("explica o mínimo de dias quando nenhum partido entra no ranking", async () => {
    vi.mocked(api.getAttendancePartyRanking).mockResolvedValue({ ...partidos, itens: [] });
    render(<AttendanceRankingPanel />);
    await screen.findByText("Fulano de Tal");
    fireEvent.click(screen.getByRole("button", { name: /Partidos/ }));
    expect(await screen.findByText(/Nenhum partido atinge o mínimo de 2\.000 dias registrados neste recorte\./)).toBeTruthy();
  });

  it("não usa o jargão NCom na ajuda da ordenação", async () => {
    render(<AttendanceRankingPanel />);
    await screen.findByText("Fulano de Tal");
    fireEvent.change(screen.getByLabelText("Ordenar por"), { target: { value: "nao_justificadas" } });
    await waitFor(() =>
      expect(api.getAttendanceRanking).toHaveBeenCalledWith(
        expect.objectContaining({ ordenar: "nao_justificadas" }),
        expect.anything()
      )
    );
    await screen.findByText("Fulano de Tal");
    expect(screen.queryByText(/NCom/)).toBeNull();
    expect(screen.getByText(/não compareceu, sem justificativa/)).toBeTruthy();
  });
});
