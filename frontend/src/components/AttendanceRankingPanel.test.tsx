import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AttendanceRankingPanel from "./AttendanceRankingPanel";
import * as api from "@/services/api";

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
  dias_sem_partido_identificado: 0,
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
    expect(api.getAttendanceRanking).toHaveBeenCalledWith("ALL", "faltas", 2023, undefined, 30, expect.anything());
  });

  it("refaz a consulta ao trocar o critério para falta com baixa produção", async () => {
    render(<AttendanceRankingPanel />);
    await screen.findByText("Fulano de Tal");
    fireEvent.change(screen.getByLabelText("Ordenar por"), { target: { value: "baixa_producao" } });
    await waitFor(() =>
      expect(api.getAttendanceRanking).toHaveBeenCalledWith("ALL", "baixa_producao", 2023, undefined, 30, expect.anything())
    );
  });

  it("mostra o ranking de partidos", async () => {
    const onParty = vi.fn();
    render(<AttendanceRankingPanel onSelectParty={onParty} />);
    await screen.findByText("Fulano de Tal");
    fireEvent.click(screen.getByRole("tab", { name: /Partidos/ }));
    const sigla = await screen.findByText("XYZ");
    fireEvent.click(sigla);
    expect(onParty).toHaveBeenCalledWith("XYZ");
  });

  it("mostra estado vazio quando não há registros", async () => {
    vi.mocked(api.getAttendanceRanking).mockResolvedValue({ ...politicos, itens: [] });
    render(<AttendanceRankingPanel />);
    expect(await screen.findByText(/Sem registros de presença/)).toBeTruthy();
  });
});
