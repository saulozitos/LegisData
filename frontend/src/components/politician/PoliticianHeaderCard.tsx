"use client";

import React from "react";
import {
  DollarSign,
  AlertTriangle,
  Award,
  ShieldAlert,
  ShieldCheck,
  MapPin,
  ArrowRight,
  ArrowLeft,
  Gauge,
} from "lucide-react";
import type { PoliticoDossier } from "@/services/api";
import { fmtNum, isNum } from "@/lib/format";
import { safeExternalUrl } from "@/lib/safeUrl";
import PartyLink from "@/components/PartyLink";
import { formatMoney, getFichaStatus } from "./format";
import type { DossierTab } from "./types";

interface PoliticianHeaderCardProps {
  dossier: PoliticoDossier;
  onBack: () => void;
  onChangeTab: (tab: DossierTab) => void;
  onSelectParty?: (sigla: string) => void;
}

export default function PoliticianHeaderCard({ dossier, onBack, onChangeTab, onSelectParty }: PoliticianHeaderCardProps) {
  const perfil = dossier.perfil;
  const assiduidade = dossier.assiduidade;
  const remuneracao = dossier.remuneracao;
  const fichaStatus = getFichaStatus(dossier);
  const taxaGov = dossier.basometro?.taxa_governismo_pct;
  const hasAttendance = Boolean(assiduidade) && (assiduidade?.total_sessoes ?? 0) > 0;

  return (
    <>
          {/* Barra Superior de Retorno à Home do Raio-X */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-slate-900/60 border border-slate-800 rounded-2xl">
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-950 hover:bg-slate-800 text-slate-300 hover:text-cyan-300 border border-slate-700/80 transition-all text-xs font-semibold shadow-md group max-w-fit"
            >
              <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform text-cyan-400" aria-hidden="true" />
              <span>← Voltar ao Catálogo Geral (Home do Raio-X)</span>
            </button>

            <div className="text-xs text-slate-400">
              Visualizando dossiê de <strong className="text-white">{perfil?.nome_eleitoral}</strong>{" "}
              <span className="font-mono text-cyan-400 font-bold">
                (
                <PartyLink sigla={perfil?.partido_atual} onSelectParty={onSelectParty} />
                /{perfil?.uf})
              </span>
            </div>
          </div>

          {/* Card Principal do Perfil */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 backdrop-blur-md relative overflow-hidden shadow-xl">
            <div className="absolute top-0 right-0 w-80 h-80 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none" />

            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 pb-6 border-b border-slate-800">
              <div className="flex items-center gap-4.5">
                {/* Foto Oficial */}
                <div className="relative w-20 h-20 sm:w-24 sm:h-24 rounded-2xl overflow-hidden bg-slate-800 border-2 border-cyan-500/40 shadow-lg flex-shrink-0 flex items-center justify-center">
                  {safeExternalUrl(perfil?.foto_url) ? (
                    <img
                      src={safeExternalUrl(perfil?.foto_url)}
                      alt=""
                      referrerPolicy="no-referrer"
                      className="w-full h-full object-cover object-top"
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                      }}
                    />
                  ) : null}
                  <div className="absolute inset-0 bg-slate-800 -z-10 flex items-center justify-center font-bold text-cyan-400 text-lg">
                    {perfil?.partido_atual?.slice(0, 2) ?? ""}
                  </div>
                </div>

                {/* Identificação */}
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <PartyLink
                      sigla={perfil?.partido_atual}
                      onSelectParty={onSelectParty}
                      className="text-xs font-mono font-bold px-2.5 py-0.5 rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:border-cyan-400"
                    />
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-slate-800 text-slate-300">
                      {perfil?.cargo_atual === "PRESIDENTE" ? "Presidente da República" : perfil?.cargo_atual === "SENADOR" ? "Senador Federal" : "Deputado Federal"}
                    </span>
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-slate-800 text-slate-400">
                      {perfil?.uf}
                    </span>
                  </div>

                  <h2 className="text-xl sm:text-2xl font-black text-slate-100">
                    {perfil?.nome_eleitoral}
                  </h2>
                  <p className="text-xs text-slate-400">
                    Nome Civil: <strong className="text-slate-300">{perfil?.nome_civil}</strong>
                  </p>
                  <p className="text-xs text-slate-400 flex items-center gap-1.5 pt-0.5">
                    <MapPin className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
                    Naturalidade: {perfil?.naturalidade ?? "Dado indisponível"}
                    {perfil?.data_nascimento && ` • Nascido em ${perfil.data_nascimento}`}
                  </p>
                </div>
              </div>

              {/* Badges de Atividade Parlamentar e Ficha Limpa */}
              <div className="flex flex-col sm:flex-row md:flex-col items-start md:items-end gap-2 text-xs">
                {/* Badge Ficha/Certidões Judicial */}
                <button
                  type="button"
                  onClick={() => onChangeTab("justica")}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-bold transition-all shadow-sm ${
                    fichaStatus === "declared"
                      ? "bg-rose-500/15 border-rose-500/40 text-rose-300 hover:bg-rose-500/25 ring-1 ring-rose-500/20"
                      : fichaStatus === "none"
                      ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/25 ring-1 ring-emerald-500/20"
                      : "bg-slate-800/80 border-slate-600 text-slate-200 hover:bg-slate-700"
                  }`}
                  title="Clique para inspecionar as certidões judiciais no Raio-X"
                >
                  {fichaStatus === "declared" ? (
                    <>
                      <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" aria-hidden="true" />
                      <span>Ficha/Certidões: Possui Processos Declarados</span>
                      {dossier.ficha_limpa?.orgaos_declarados && dossier.ficha_limpa?.orgaos_declarados.length > 0 && (
                        <span className="font-mono text-[10px] bg-rose-950/90 px-1.5 py-0.5 rounded text-rose-200 border border-rose-500/40">
                          {dossier.ficha_limpa?.orgaos_declarados.join(", ")}
                        </span>
                      )}
                    </>
                  ) : fichaStatus === "none" ? (
                    <>
                      <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" aria-hidden="true" />
                      <span>Ficha/Certidões: nenhum processo declarado na base</span>
                    </>
                  ) : (
                    <>
                      <ShieldAlert className="w-4 h-4 text-slate-300 shrink-0" aria-hidden="true" />
                      <span>Ficha/Certidões: dado indisponível</span>
                    </>
                  )}
                </button>

                <div className="flex items-center gap-2">
                  {perfil?.camara_id && (
                    <span className="px-3 py-1 rounded-xl bg-slate-950 border border-slate-800 text-slate-400">
                      Câmara ID: <strong className="text-cyan-400 font-mono">{perfil.camara_id}</strong>
                    </span>
                  )}
                  {perfil?.senado_id && (
                    <span className="px-3 py-1 rounded-xl bg-slate-950 border border-slate-800 text-slate-400">
                      Senado ID: <strong className="text-cyan-400 font-mono">{perfil.senado_id}</strong>
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* O BASÔMETRO: TAXA DE ALINHAMENTO COM O GOVERNO */}
            <div className="mt-6 bg-gradient-to-r from-slate-900/95 via-slate-950/95 to-slate-900/95 border border-cyan-500/30 hover:border-cyan-500/50 rounded-2xl p-4.5 shadow-xl transition-all relative overflow-hidden backdrop-blur-sm">
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
                      !isNum(taxaGov)
                        ? "bg-slate-800/80 border-slate-600 text-slate-200"
                        : taxaGov >= 70
                        ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-300 ring-1 ring-emerald-500/20"
                        : taxaGov <= 35
                        ? "bg-rose-500/15 border-rose-500/40 text-rose-300 ring-1 ring-rose-500/20"
                        : "bg-amber-500/15 border-amber-500/40 text-amber-300 ring-1 ring-amber-500/20"
                    }`}
                  >
                    {dossier.basometro?.classificacao ?? "Dado indisponível"}
                  </span>
                </div>
              </div>

              {/* Barra de Progresso Horizontal: Taxa de Governismo */}
              <div className="pt-3.5 space-y-2">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs sm:text-sm font-bold text-slate-200">
                      Taxa de Governismo:
                    </span>
                    <span className="text-lg sm:text-2xl font-black font-mono text-cyan-400">
                      {isNum(taxaGov) ? `${taxaGov}%` : "Indisponível"}
                    </span>
                    <span className="text-xs text-slate-400">de alinhamento nas votações</span>
                  </div>
                  <span className="text-xs text-slate-400 font-mono">
                    {dossier.basometro ? `${dossier.basometro.votos_alinhados ?? "—"} favoráveis / ${dossier.basometro.votos_divergentes ?? "—"} contrários` : "Sem dados de votação"}
                  </span>
                </div>

                {/* Barra Estilizada com Gradiente e Marcador */}
                <div className="w-full bg-slate-950 rounded-full h-3.5 relative overflow-hidden border border-slate-800 p-0.5">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ease-out ${
                      !isNum(taxaGov)
                        ? "bg-slate-700"
                        : taxaGov >= 70
                        ? "bg-gradient-to-r from-teal-500 via-cyan-400 to-emerald-400 shadow-lg shadow-emerald-500/20"
                        : taxaGov <= 35
                        ? "bg-gradient-to-r from-rose-600 via-rose-500 to-orange-400 shadow-lg shadow-rose-500/20"
                        : "bg-gradient-to-r from-amber-500 via-yellow-400 to-cyan-400 shadow-lg shadow-cyan-500/20"
                    }`}
                    style={{ width: `${isNum(taxaGov) ? Math.min(100, Math.max(0, taxaGov)) : 0}%` }}
                  />
                </div>

                {/* Régua de Orientação Política */}
                <div className="flex justify-between items-center text-[10px] text-slate-400 font-mono pt-0.5">
                  <span className="text-rose-400 font-semibold">0% Oposição</span>
                  <span className="text-slate-400">50% Independente</span>
                  <span className="text-emerald-400 font-semibold">100% Base Aliada</span>
                </div>

                {/* Sub-indicadores rápidos */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-2">
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-2.5 flex items-center justify-between text-xs">
                    <span className="text-slate-400">Votos com o Governo:</span>
                    <span className="font-mono font-bold text-emerald-400">
                      {dossier.basometro?.votos_alinhados ?? "—"}
                    </span>
                  </div>
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-2.5 flex items-center justify-between text-xs">
                    <span className="text-slate-400">Votos Divergentes:</span>
                    <span className="font-mono font-bold text-rose-400">
                      {dossier.basometro?.votos_divergentes ?? "—"}
                    </span>
                  </div>
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-2.5 flex items-center justify-between text-xs">
                    <span className="text-slate-400">Total Analisado:</span>
                    <button
                      type="button"
                      onClick={() => onChangeTab("votacoes")}
                      className="font-mono font-bold text-cyan-400 hover:underline flex items-center gap-1"
                      title="Ver histórico nominal de votos"
                    >
                      {dossier.basometro?.total_votacoes_analisadas ?? "—"} votos
                      <ArrowRight className="w-3 h-3" aria-hidden="true" />
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* PAINÉIS DE DESTAQUE NO TOPO: SALÁRIO & REMUNERAÇÃO E ASSIDUIDADE & FALTAS */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 pt-4">
              {/* PAINEL 1: SALÁRIO E REMUNERAÇÃO OFICIAL */}
              <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-emerald-950/20 border border-emerald-500/30 hover:border-emerald-500/50 rounded-2xl p-4.5 space-y-3 shadow-lg transition-all">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
                  <span className="flex items-center gap-2 text-xs font-bold text-emerald-400 uppercase tracking-wider">
                    <span className="p-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                      <DollarSign className="w-4 h-4" aria-hidden="true" />
                    </span>
                    Remuneração & Subsídio Oficial
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-bold">
                    Transparência Pública
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3">
                    <span className="text-[10px] font-medium text-slate-400 block mb-1">
                      Salário Bruto
                    </span>
                    <span className="text-base sm:text-lg font-black font-mono text-cyan-400 block leading-tight">
                      {formatMoney(remuneracao?.resumo?.salario_bruto_atual)}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      Subsídio mensal
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3">
                    <span className="text-[10px] font-medium text-slate-400 block mb-1">
                      Salário Líquido
                    </span>
                    <span className="text-base sm:text-lg font-black font-mono text-emerald-400 block leading-tight">
                      {formatMoney(remuneracao?.resumo?.salario_liquido_atual)}
                    </span>
                    <span className="text-[10px] text-emerald-500/90 mt-1 block font-medium">
                      Após deduções oficiais
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3 col-span-2 sm:col-span-1">
                    <span className="text-[10px] font-medium text-slate-400 block mb-1">
                      Cota CEAP (Média)
                    </span>
                    <span className="text-base sm:text-lg font-black font-mono text-amber-400 block leading-tight">
                      {formatMoney(remuneracao?.resumo?.media_ceap_mensal)}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      Gasto atividade / mês
                    </span>
                  </div>
                </div>
              </div>

              {/* PAINEL 2: ASSIDUIDADE E CONTROLE DE FALTAS */}
              <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-rose-950/20 border border-rose-500/30 hover:border-rose-500/50 rounded-2xl p-4.5 space-y-3 shadow-lg transition-all">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
                  <span className="flex items-center gap-2 text-xs font-bold text-rose-400 uppercase tracking-wider">
                    <span className="p-1.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400">
                      <AlertTriangle className="w-4 h-4" aria-hidden="true" />
                    </span>
                    Assiduidade & Faltas no Plenário
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => onChangeTab("justica")}
                      className={`text-[10px] font-mono px-2 py-0.5 rounded border font-bold flex items-center gap-1 transition-all ${
                        fichaStatus === "declared"
                          ? "bg-rose-500/15 text-rose-300 border-rose-500/30 hover:bg-rose-500/25"
                          : fichaStatus === "none"
                          ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/25"
                          : "bg-slate-800 text-slate-200 border-slate-600 hover:bg-slate-700"
                      }`}
                      title="Ver certidões judiciais do parlamentar"
                    >
                      {fichaStatus === "declared" ? (
                        <>
                          <ShieldAlert className="w-3 h-3 text-rose-400 shrink-0" aria-hidden="true" />
                          <span>Processos Declarados</span>
                        </>
                      ) : fichaStatus === "none" ? (
                        <>
                          <ShieldCheck className="w-3 h-3 text-emerald-400 shrink-0" aria-hidden="true" />
                          <span>Sem processos na base</span>
                        </>
                      ) : (
                        <>
                          <ShieldAlert className="w-3 h-3 text-slate-300 shrink-0" aria-hidden="true" />
                          <span>Situação indisponível</span>
                        </>
                      )}
                    </button>
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded border font-bold ${
                      (assiduidade?.taxa_presenca_pct ?? 0) >= 90
                        ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
                        : "bg-amber-500/10 text-amber-300 border-amber-500/20"
                    }`}>
                      {hasAttendance ? `${fmtNum(assiduidade?.taxa_presenca_pct)}% de Presença` : "Presença indisponível"}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2.5">
                  {/* Total de Faltas */}
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3">
                    <span className="text-[10px] font-medium text-slate-400 block mb-1">
                      Total de Faltas
                    </span>
                    <span className="text-base sm:text-lg font-black font-mono text-slate-100 block leading-tight">
                      {hasAttendance
                        ? assiduidade?.faltas_nao_justificadas == null
                          ? "n/d"
                          : (assiduidade?.faltas_justificadas ?? 0) + assiduidade.faltas_nao_justificadas
                        : "—"}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      Em {assiduidade?.total_sessoes ?? "—"} sessões
                    </span>
                  </div>

                  {/* Faltas Justificadas */}
                  <div className="bg-slate-950/70 border border-amber-500/20 rounded-xl p-3">
                    <span className="text-[10px] font-medium text-amber-400/90 block mb-1">
                      Justificadas
                    </span>
                    <span className="text-base sm:text-lg font-black font-mono text-amber-400 block leading-tight">
                      {hasAttendance ? assiduidade?.faltas_justificadas : "—"}
                    </span>
                    <span className="text-[10px] text-amber-500/80 mt-1 block">
                      Motivo formal
                    </span>
                  </div>

                  {/* Faltas Não Justificadas */}
                  <div className="bg-slate-950/70 border border-rose-500/30 rounded-xl p-3">
                    <span className="text-[10px] font-medium text-rose-400/90 block mb-1">
                      Não Justificadas
                    </span>
                    <span className="text-base sm:text-lg font-black font-mono text-rose-400 block leading-tight">
                      {hasAttendance ? (assiduidade?.faltas_nao_justificadas ?? "n/d") : "—"}
                    </span>
                    <span className="text-[10px] text-rose-500/80 mt-1 block font-medium">
                      Sem justificativa
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Mini-resumo de Mandatos & Legendas */}
            <div className="mt-3.5 bg-slate-950/50 border border-slate-800/80 rounded-xl p-3 flex flex-wrap items-center justify-between text-xs text-slate-400 gap-3">
              <div className="flex items-center gap-2">
                <Award className="w-4 h-4 text-purple-400" aria-hidden="true" />
                <span>Atuação Parlamentar: <strong>{dossier.trajetoria_mandatos?.length ?? "—"}</strong> mandato(s) registrado(s)</span>
              </div>
              <div className="flex items-center gap-4">
                <span><strong>{dossier?.filiacoes_partidarias?.length}</strong> partido(s) no histórico</span>
                <span>•</span>
                <span><strong>{dossier?.materias_propostas?.length}</strong> proposição(ões) de autoria</span>
                <span>•</span>
                <span><strong>{assiduidade?.total_presencas}</strong> presenças registradas</span>
              </div>
            </div>
          </div>
    </>
  );
}
