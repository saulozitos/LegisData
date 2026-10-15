import { describe, expect, it } from "vitest";
import type { PartyIPPMRankingItem } from "@/services/api";
import {
  MIN_BANCADA_LIDERANCA,
  evidenciaCoeso,
  evidenciaEficaz,
  evidenciaLider,
  evidenciaMedia,
} from "./ippmExplicacoes";

const partido = (sigla: string, over: Partial<PartyIPPMRankingItem> = {}, fidelidade: number | null = 80): PartyIPPMRankingItem =>
  ({
    posicao: 1,
    partido_id: sigla,
    sigla,
    nome_completo: sigla,
    numero_eleitoral: null,
    espectro_politico: "CENTRO",
    bloco_politico: "INDEPENDENTE_CENTRO",
    cor_hex: "#123456",
    logo_url: null,
    total_cadeiras_ativas: 10,
    cadeiras_dia_equivalentes: 9.5,
    parlamentares_produtivos: 5,
    pontuacao_bruta_ialp: 100,
    ippm_score_medio: 10,
    projetos_apresentados: 20,
    projetos_aprovados: 2,
    pilares: { fidelidade_partidaria_pct: fidelidade, taxa_eficacia_pct: 10, total_relatorias: 0, volume_relatorias: 0 },
    quadrante_eficiencia: { codigo: "X", titulo: "X", descricao: "X" },
    ...over,
  }) as PartyIPPMRankingItem;

describe("evidências dos destaques", () => {
  it("média: lista do maior para o menor e mostra a conta", () => {
    const r = [partido("A", { ippm_score_medio: 4 }), partido("B", { ippm_score_medio: 8 })];
    const e = evidenciaMedia(r, 6);
    expect(e.linhas.map((l) => l.sigla)).toEqual(["B", "A"]);
    expect(e.rodape).toBe("Soma 12,00 ÷ 2 partidos = 6,00");
  });

  it("líder: partido com bancada pequena não disputa o título", () => {
    const r = [
      partido("MINI", { total_cadeiras_ativas: MIN_BANCADA_LIDERANCA - 1, ippm_score_medio: 99 }),
      partido("GRANDE", { ippm_score_medio: 20 }),
    ];
    const e = evidenciaLider(r, "GRANDE");
    expect(e.linhas.map((l) => l.sigla)).toEqual(["GRANDE"]);
    expect(e.linhas[0].vencedor).toBe(true);
    expect(e.rodape).toContain("1 partido(s) com menos de 3 parlamentares");
  });

  it("eficácia: ignora quem não teve projeto aprovado e desempata por aprovados", () => {
    const r = [
      partido("ZERO", { projetos_aprovados: 0 }),
      partido("A", { projetos_aprovados: 2, pilares: { fidelidade_partidaria_pct: 1, taxa_eficacia_pct: 10, total_relatorias: 0, volume_relatorias: 0 } }),
      partido("B", { projetos_aprovados: 5, pilares: { fidelidade_partidaria_pct: 1, taxa_eficacia_pct: 10, total_relatorias: 0, volume_relatorias: 0 } }),
    ];
    expect(evidenciaEficaz(r).linhas.map((l) => l.sigla)).toEqual(["B", "A"]);
  });

  it("coesão: sem votações a lista fica vazia e explica o motivo", () => {
    const e = evidenciaCoeso([partido("A", {}, null)]);
    expect(e.linhas).toEqual([]);
    expect(e.rodape).toContain("Sem votações nominais");
  });
});
