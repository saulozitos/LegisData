"use client";

import React from "react";
import { ArrowRight, Gauge } from "lucide-react";
import type { PoliticoDossier } from "@/services/api";
import { isNum } from "@/lib/format";
import FonteDoDado from "@/components/FonteDoDado";
import type { DossierTab } from "./types";

interface BasometroCardProps {
  dossier: PoliticoDossier;
  onChangeTab: (tab: DossierTab) => void;
}

function dataBr(iso?: string | null): string | null {
  if (!iso) return null;
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return ano && mes && dia ? `${dia}/${mes}/${ano}` : null;
}

/**
 * Alinhamento à orientação do Governo. Sem amostra suficiente o índice não aparece, mas o cartão nunca fica vazio:
 * diz por que não há índice e mostra o que se sabe de como o parlamentar votou.
 */
export default function BasometroCard({ dossier, onChangeTab }: BasometroCardProps) {
  const baso = dossier.basometro;
  const taxaGov = baso?.taxa_governismo_pct;
  const temIndice = isNum(taxaGov);
  const registrados = baso?.votos_registrados ?? 0;
  const resumo = dossier.resumo_votos;
  const sim = resumo?.sim.total ?? 0;
  const nao = resumo?.nao.total ?? 0;
  const ausente = resumo?.ausente.total ?? 0;
  const primeiro = dataBr(baso?.primeiro_voto);
  const ultimo = dataBr(baso?.ultimo_voto);
  const baseDesde = dataBr(baso?.base_desde);

  return (
    <div
      data-testid="basometro-card"
      className="mt-6 bg-gradient-to-r from-slate-900/95 via-slate-950/95 to-slate-900/95 border border-cyan-500/30 hover:border-cyan-500/50 rounded-2xl p-4.5 shadow-xl transition-all relative overflow-hidden backdrop-blur-sm"
    >
      <div className="absolute top-0 right-0 w-80 h-80 bg-cyan-500/5 rounded-full blur-3xl -z-10 pointer-events-none" />

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
        <div className="flex items-center gap-2.5">
          <span className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 shadow-inner">
            <Gauge className="w-5 h-5" aria-hidden="true" />
          </span>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider">
                O Basômetro (Alinhamento Governista)
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-bold">
                Radar de Votações
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Cruzamento das deliberações com a orientação do governo federal no Congresso Nacional
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Classificação:</span>
          <span
            className={`text-xs font-extrabold px-2.5 py-1 rounded-xl border font-mono ${
              !temIndice
                ? "bg-slate-800/80 border-slate-600 text-slate-200"
                : taxaGov >= 70
                ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-300 ring-1 ring-emerald-500/20"
                : taxaGov <= 35
                ? "bg-rose-500/15 border-rose-500/40 text-rose-300 ring-1 ring-rose-500/20"
                : "bg-amber-500/15 border-amber-500/40 text-amber-300 ring-1 ring-amber-500/20"
            }`}
          >
            {baso?.classificacao ?? "Índice não calculado"}
          </span>
        </div>
      </div>

      {temIndice ? (
        <div className="pt-3.5 space-y-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs sm:text-sm font-bold text-slate-200">Taxa de Governismo:</span>
              <span className="text-lg sm:text-2xl font-black font-mono text-cyan-400">{taxaGov}%</span>
              <span className="text-xs text-slate-400">de alinhamento nas votações</span>
            </div>
            <span className="text-xs text-slate-400 font-mono">
              {baso?.votos_alinhados ?? "—"} favoráveis / {baso?.votos_divergentes ?? "—"} contrários
            </span>
          </div>

          <div className="w-full bg-slate-950 rounded-full h-3.5 relative overflow-hidden border border-slate-800 p-0.5">
            <div
              className={`h-full rounded-full transition-all duration-700 ease-out ${
                taxaGov >= 70
                  ? "bg-gradient-to-r from-teal-500 via-cyan-400 to-emerald-400 shadow-lg shadow-emerald-500/20"
                  : taxaGov <= 35
                  ? "bg-gradient-to-r from-rose-600 via-rose-500 to-orange-400 shadow-lg shadow-rose-500/20"
                  : "bg-gradient-to-r from-amber-500 via-yellow-400 to-cyan-400 shadow-lg shadow-cyan-500/20"
              }`}
              style={{ width: `${Math.min(100, Math.max(0, taxaGov))}%` }}
            />
          </div>

          <div className="flex justify-between items-center text-[10px] text-slate-400 font-mono pt-0.5">
            <span className="text-rose-400 font-semibold">0% Oposição</span>
            <span className="text-slate-400">50% Independente</span>
            <span className="text-emerald-400 font-semibold">100% Base Aliada</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-2">
            <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-2.5 flex items-center justify-between text-xs">
              <span className="text-slate-400">Votos com o Governo:</span>
              <span className="font-mono font-bold text-emerald-400">{baso?.votos_alinhados ?? "—"}</span>
            </div>
            <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-2.5 flex items-center justify-between text-xs">
              <span className="text-slate-400">Votos Divergentes:</span>
              <span className="font-mono font-bold text-rose-400">{baso?.votos_divergentes ?? "—"}</span>
            </div>
            <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-2.5 flex items-center justify-between text-xs">
              <span className="text-slate-400">Total Analisado:</span>
              <button
                type="button"
                onClick={() => onChangeTab("votacoes")}
                className="font-mono font-bold text-cyan-400 hover:underline flex items-center gap-1"
                title="Ver histórico nominal de votos"
              >
                {baso?.total_votacoes_analisadas ?? "—"} votos
                <ArrowRight className="w-3 h-3" aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="pt-3.5 space-y-3" data-testid="basometro-sem-indice">
          <p className="text-sm font-semibold text-slate-200">
            O índice de alinhamento ainda não pode ser calculado para este parlamentar.
          </p>
          <p className="text-xs text-slate-300 leading-relaxed">
            {baso?.explicacao_indisponivel ??
              "Não há votos nominais suficientes comparáveis com a orientação do Governo."}
          </p>

          {registrados > 0 && (
            <div className="space-y-2">
              <p className="text-xs text-slate-400">
                O que há registrado sobre como ele vota
                {primeiro && ultimo ? ` (de ${primeiro} a ${ultimo})` : ""}:
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-2.5 text-xs">
                  <span className="block text-slate-400">Votos registrados</span>
                  <span className="font-mono font-bold text-cyan-300">{registrados}</span>
                </div>
                <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-2.5 text-xs">
                  <span className="block text-slate-400">Votou SIM</span>
                  <span className="font-mono font-bold text-emerald-400">{sim}</span>
                </div>
                <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-2.5 text-xs">
                  <span className="block text-slate-400">Votou NÃO</span>
                  <span className="font-mono font-bold text-rose-400">{nao}</span>
                </div>
                <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-2.5 text-xs">
                  <span className="block text-slate-400">Ausente</span>
                  <span className="font-mono font-bold text-slate-200">{ausente}</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => onChangeTab("votacoes")}
                className="inline-flex items-center gap-1 text-xs font-semibold text-cyan-400 hover:underline"
              >
                Ver cada votação
                <ArrowRight className="w-3 h-3" aria-hidden="true" />
              </button>
            </div>
          )}

          {baseDesde && (
            <p className="text-[11px] text-slate-500">
              Cobertura: votações nominais em plenário desde {baseDesde}. Antes dessa data não há votos carregados.
            </p>
          )}
        </div>
      )}
      <div className="pt-2.5">
        <FonteDoDado painel="votacoes" />
      </div>
    </div>
  );
}
