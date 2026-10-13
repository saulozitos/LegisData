"use client";

import React from "react";
import {
  DollarSign,
  FileText,
  CheckCircle,
  Landmark,
  Sparkles,
  Layers,
  Receipt,
  Scale,
  Coins,
  PieChart as LucidePieChart,
} from "lucide-react";
import type { PoliticoDossier } from "@/services/api";
import { fmtNum, isNum } from "@/lib/format";
import { getFichaStatus, gradeBadgeClass } from "./format";
import type { DossierTab } from "./types";

interface PoliticianTabNavProps {
  dossier: PoliticoDossier;
  activeTab: DossierTab;
  onChange: (tab: DossierTab) => void;
}

export default function PoliticianTabNav({ dossier, activeTab, onChange }: PoliticianTabNavProps) {
  const assiduidade = dossier.assiduidade;
  const indices = dossier.indices_inteligencia;
  const fichaStatus = getFichaStatus(dossier);

  return (
          <div role="tablist" aria-label="Seções do dossiê" className="flex items-center gap-2 border-b border-slate-800 pb-2 overflow-x-auto">
            <button
              type="button"
              role="tab"
              id="dossier-tab-visao_geral"
              aria-selected={activeTab === "visao_geral"}
              aria-controls="dossier-tabpanel"
              onClick={() => onChange("visao_geral")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "visao_geral"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Layers className="w-3.5 h-3.5" aria-hidden="true" /> Visão Geral & Trajetória
            </button>

            <button
              type="button"
              role="tab"
              id="dossier-tab-inteligencia"
              aria-selected={activeTab === "inteligencia"}
              aria-controls="dossier-tabpanel"
              onClick={() => onChange("inteligencia")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "inteligencia"
                  ? "bg-gradient-to-r from-cyan-500/20 to-blue-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Sparkles className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" /> Inteligência Cívica
              {indices?.roi_cidadao?.score && (
                <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded ${gradeBadgeClass(indices.roi_cidadao.score)}`}>
                  Nota {indices.roi_cidadao.score}
                </span>
              )}
            </button>

            <button
              type="button"
              role="tab"
              id="dossier-tab-proposicoes"
              aria-selected={activeTab === "proposicoes"}
              aria-controls="dossier-tabpanel"
              onClick={() => onChange("proposicoes")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "proposicoes"
                  ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <LucidePieChart className="w-3.5 h-3.5" /> Proposições & Relevância ({dossier?.materias_propostas?.length || 0})
              {dossier?.relevancia_legislativa ? (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300">
                  {dossier.relevancia_legislativa.percentual_impacto}% Impacto
                </span>
              ) : null}
            </button>

            <button
              type="button"
              role="tab"
              id="dossier-tab-financiamento"
              aria-selected={activeTab === "financiamento"}
              aria-controls="dossier-tabpanel"
              onClick={() => onChange("financiamento")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "financiamento"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Coins className="w-3.5 h-3.5" aria-hidden="true" /> Quem Paga a Conta?
              {dossier?.financiamento_campanha?.total_arrecadado ? (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300">
                  R$ {fmtNum(dossier.financiamento_campanha.total_arrecadado / 1000000)}M
                </span>
              ) : null}
            </button>

            <button
              type="button"
              role="tab"
              id="dossier-tab-ceap"
              aria-selected={activeTab === "ceap"}
              aria-controls="dossier-tabpanel"
              onClick={() => onChange("ceap")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "ceap"
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Receipt className="w-3.5 h-3.5" aria-hidden="true" /> Custos do Mandato (CEAP)
              {dossier?.custos_ceap?.gasto_total_recente ? (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300">
                  R$ {fmtNum(dossier.custos_ceap.gasto_total_recente / 1000, 0)}k
                </span>
              ) : null}
            </button>

            <button
              type="button"
              role="tab"
              id="dossier-tab-emendas"
              aria-selected={activeTab === "emendas"}
              aria-controls="dossier-tabpanel"
              onClick={() => onChange("emendas")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "emendas"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Landmark className="w-3.5 h-3.5" aria-hidden="true" /> Destino das Emendas
              {dossier?.emendas_parlamentares?.total_pago ? (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300">
                  R$ {fmtNum(dossier.emendas_parlamentares.total_pago / 1000000)}M
                </span>
              ) : null}
            </button>

            <button
              type="button"
              role="tab"
              id="dossier-tab-justica"
              aria-selected={activeTab === "justica"}
              aria-controls="dossier-tabpanel"
              onClick={() => onChange("justica")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "justica"
                  ? (fichaStatus === "declared"
                      ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                      : fichaStatus === "none"
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                      : "bg-slate-700/60 text-slate-200 border border-slate-500")
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Scale className="w-3.5 h-3.5" aria-hidden="true" /> Justiça & Ficha Limpa
              <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded ${
                fichaStatus === "declared"
                  ? "bg-rose-500/20 text-rose-300"
                  : fichaStatus === "none"
                  ? "bg-emerald-500/20 text-emerald-300"
                  : "bg-slate-700/60 text-slate-200"
              }`}>
                {fichaStatus === "declared" ? "Alerta" : fichaStatus === "none" ? "Sem registros" : "Indisponível"}
              </span>
            </button>

            <button
              type="button"
              role="tab"
              id="dossier-tab-assiduidade"
              aria-selected={activeTab === "assiduidade"}
              aria-controls="dossier-tabpanel"
              onClick={() => onChange("assiduidade")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "assiduidade"
                  ? "bg-blue-500/20 text-blue-300 border border-blue-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <CheckCircle className="w-3.5 h-3.5" aria-hidden="true" /> Presenças ({isNum(assiduidade?.taxa_presenca_pct) ? `${fmtNum(assiduidade?.taxa_presenca_pct)}%` : "n/d"})
            </button>

            <button
              type="button"
              role="tab"
              id="dossier-tab-remuneracao"
              aria-selected={activeTab === "remuneracao"}
              aria-controls="dossier-tabpanel"
              onClick={() => onChange("remuneracao")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "remuneracao"
                  ? "bg-teal-500/20 text-teal-300 border border-teal-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <DollarSign className="w-3.5 h-3.5" aria-hidden="true" /> Remuneração
            </button>

            <button
              type="button"
              role="tab"
              id="dossier-tab-votacoes"
              aria-selected={activeTab === "votacoes"}
              aria-controls="dossier-tabpanel"
              onClick={() => onChange("votacoes")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "votacoes"
                  ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <FileText className="w-3.5 h-3.5" aria-hidden="true" /> Votações Nominais ({dossier.votacoes_principais?.length ?? 0})
            </button>
          </div>
  );
}
