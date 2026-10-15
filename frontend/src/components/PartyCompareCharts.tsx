"use client";

import React, { useMemo, useState } from "react";
import type { PartyIPPMRankingItem } from "@/services/api";

type Indicador = "ippm" | "eficacia" | "coesao";

interface PartyCompareChartsProps {
  ranking: PartyIPPMRankingItem[];
  onSelectParty?: (sigla: string) => void;
}

const INDICADORES: Record<
  Indicador,
  { rotulo: string; pergunta: string; valor: (p: PartyIPPMRankingItem) => number | null; formato: (v: number) => string }
> = {
  ippm: {
    rotulo: "Produtividade (IPPM)",
    pergunta: "Quanto trabalho legislativo cada partido produziu para cada cadeira que ocupou?",
    valor: (p) => p.ippm_score_medio,
    formato: (v) => v.toFixed(2).replace(".", ","),
  },
  eficacia: {
    rotulo: "Aprovação",
    pergunta: "De cada 100 projetos apresentados pelo partido, quantos foram aprovados?",
    valor: (p) => p.pilares.taxa_eficacia_pct,
    formato: (v) => `${v.toFixed(1).replace(".", ",")}%`,
  },
  coesao: {
    rotulo: "Coesão nas votações",
    pergunta: "Quanto os parlamentares votaram do jeito que a bancada do partido orientou?",
    valor: (p) => p.pilares.fidelidade_partidaria_pct,
    formato: (v) => `${v.toFixed(1).replace(".", ",")}%`,
  },
};

const pct = (parte: number, total: number) => (total > 0 ? Math.max(1.5, (parte / total) * 100) : 0);

/** Duas visões simples: um indicador por vez em barras e "projetos apresentados × aprovados" por partido. */
export default function PartyCompareCharts({ ranking, onSelectParty }: PartyCompareChartsProps) {
  const [indicador, setIndicador] = useState<Indicador>("ippm");
  const config = INDICADORES[indicador];

  const barras = useMemo(() => {
    const linhas = ranking.map((p) => ({ p, v: config.valor(p) }));
    const comValor = linhas.filter((l) => l.v != null).sort((a, b) => (b.v as number) - (a.v as number));
    const semValor = linhas.filter((l) => l.v == null);
    return { comValor, semValor, maximo: Math.max(...comValor.map((l) => l.v as number), 0.0001) };
  }, [ranking, config]);

  const projetos = useMemo(() => {
    const ordenados = [...ranking].sort((a, b) => b.projetos_apresentados - a.projetos_apresentados);
    return { lista: ordenados, maximo: Math.max(...ordenados.map((p) => p.projetos_apresentados), 1) };
  }, [ranking]);

  if (ranking.length === 0) return null;

  return (
    <div className="space-y-6" id="compare-charts">
      <section className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-4" aria-labelledby="cmp-titulo-1">
        <div className="space-y-1">
          <h3 id="cmp-titulo-1" className="text-base font-bold text-white">
            Quem está na frente?
          </h3>
          <p className="text-xs text-slate-400">{config.pergunta}</p>
        </div>

        <div role="group" aria-label="Escolha o indicador" className="inline-flex flex-wrap gap-1 p-1 bg-slate-950/80 border border-slate-800 rounded-xl">
          {(Object.keys(INDICADORES) as Indicador[]).map((chave) => (
            <button
              key={chave}
              type="button"
              id={`indicador-${chave}`}
              aria-pressed={indicador === chave}
              onClick={() => setIndicador(chave)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                indicador === chave ? "bg-violet-600 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {INDICADORES[chave].rotulo}
            </button>
          ))}
        </div>

        <ol className="space-y-1.5" aria-label={`Partidos ordenados por ${config.rotulo}`}>
          {barras.comValor.map(({ p, v }) => (
            <li key={p.sigla} className="flex items-center gap-3 text-xs">
              <button
                type="button"
                onClick={() => onSelectParty?.(p.sigla)}
                className="w-24 shrink-0 text-right font-bold text-slate-200 hover:text-white truncate"
                title={`${p.nome_completo}: ver histórico da bancada`}
              >
                {p.sigla}
              </button>
              <div className="flex-1 h-5 bg-slate-950/70 rounded-md overflow-hidden">
                <div
                  className="h-full rounded-md transition-all"
                  style={{ width: `${pct(v as number, barras.maximo)}%`, backgroundColor: p.cor_hex || "#6366f1" }}
                />
              </div>
              <span className="w-16 shrink-0 font-mono font-bold text-slate-100 text-right">{config.formato(v as number)}</span>
            </li>
          ))}
        </ol>
        {barras.semValor.length > 0 && (
          <p className="text-[11px] text-slate-500">
            Sem dado neste período: {barras.semValor.map((l) => l.p.sigla).join(", ")}.
            {indicador === "coesao" && " Não houve votação nominal com orientação da bancada."}
          </p>
        )}
      </section>

      <section className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-4" aria-labelledby="cmp-titulo-2">
        <div className="space-y-1">
          <h3 id="cmp-titulo-2" className="text-base font-bold text-white">
            Projetos apresentados e aprovados
          </h3>
          <p className="text-xs text-slate-400">
            A barra clara é o total de projetos que o partido apresentou como autor principal; a parte colorida é a que foi aprovada.
            Requerimentos e indicações não entram.
          </p>
        </div>
        <ul className="space-y-1.5">
          {projetos.lista.map((p) => (
            <li key={p.sigla} className="flex items-center gap-3 text-xs">
              <span className="w-24 shrink-0 text-right font-bold text-slate-200 truncate">{p.sigla}</span>
              <div
                className="flex-1 h-5 bg-slate-950/70 rounded-md overflow-hidden"
                role="img"
                aria-label={`${p.sigla}: ${p.projetos_aprovados} de ${p.projetos_apresentados} projetos aprovados`}
              >
                <div
                  className="h-full rounded-md bg-slate-600/60 relative"
                  style={{ width: `${pct(p.projetos_apresentados, projetos.maximo)}%` }}
                >
                  <div
                    className="h-full rounded-md absolute left-0 top-0"
                    style={{
                      width: `${p.projetos_apresentados > 0 ? (p.projetos_aprovados / p.projetos_apresentados) * 100 : 0}%`,
                      backgroundColor: p.cor_hex || "#10b981",
                      minWidth: p.projetos_aprovados > 0 ? "3px" : 0,
                    }}
                  />
                </div>
              </div>
              <span className="w-40 shrink-0 font-mono text-slate-300">
                <strong className="text-slate-100">{p.projetos_aprovados}</strong> de {p.projetos_apresentados}
                <span className="text-slate-500"> ({p.pilares.taxa_eficacia_pct.toFixed(1).replace(".", ",")}%)</span>
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
