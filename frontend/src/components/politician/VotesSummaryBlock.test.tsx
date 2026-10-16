import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import VotesSummaryBlock from "./VotesSummaryBlock";
import type { ResumoVotos } from "@/services/api";

const item = (id: string, numero: string) => ({
  proposicao_id: id,
  proposicao_titulo: `Título ${numero}`,
  proposicao_numero: numero,
  data: "01/03/2024",
  casa_legislativa: "CAMARA_DOS_DEPUTADOS",
  url_oficial: "https://www.camara.leg.br/x",
});

const resumo: ResumoVotos = {
  sim: { total: 120, recentes: [item("a", "PL 1/2024"), item("b", "PEC 2/2024")] },
  nao: { total: 1, recentes: [item("c", "PL 9/2023")] },
  ausente: { total: 0, recentes: [] },
};

describe("VotesSummaryBlock", () => {
  it("lista Sim, Não e Ausente com o total de cada grupo", () => {
    render(<VotesSummaryBlock resumo={resumo} />);
    const sim = screen.getByRole("region", { name: "Votou Sim" });
    expect(within(sim).getByText("120")).toBeInTheDocument();
    expect(within(sim).getByText("PL 1/2024")).toBeInTheDocument();
    expect(within(sim).getByText(/Mostrando as 2 mais recentes de 120/)).toBeInTheDocument();
    const nao = screen.getByRole("region", { name: "Votou Não" });
    expect(within(nao).getByText("PL 9/2023")).toBeInTheDocument();
    expect(within(nao).queryByText(/Mostrando/)).not.toBeInTheDocument();
  });

  it("grupo sem registro mostra mensagem, não lista vazia", () => {
    render(<VotesSummaryBlock resumo={resumo} />);
    const ausente = screen.getByRole("region", { name: "Ausente" });
    expect(within(ausente).getByText(/Nenhuma ausência registrada/)).toBeInTheDocument();
  });

  it("sem resumo da API não renderiza o bloco", () => {
    const { container } = render(<VotesSummaryBlock resumo={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
});
