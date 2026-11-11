"use client";

import ReportarErro from "@/components/ReportarErro";
import Compartilhar from "@/components/Compartilhar";
import { montarLink } from "@/lib/compartilhar";
import React from "react";
import {
  DollarSign,
  AlertTriangle,
  Award,
  ShieldAlert,
  ShieldCheck,
  MapPin,
  ArrowLeft,
} from "lucide-react";
import type { PoliticoDossier } from "@/services/api";
import { fmtNum } from "@/lib/format";
import { safeExternalUrl } from "@/lib/safeUrl";
import PartyLink from "@/components/PartyLink";
import BasometroCard from "./BasometroCard";
import FonteDoDado from "@/components/FonteDoDado";
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
                      <span>Ficha/Certidões: Possui processos vinculados</span>
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

            <BasometroCard dossier={dossier} onChangeTab={onChangeTab} />

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
                <FonteDoDado painel="gastos" />
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
                          <span>Processos vinculados</span>
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
                      {hasAttendance ? (assiduidade?.total_faltas ?? "n/d") : "—"}
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
                      {hasAttendance ? (assiduidade?.faltas_justificadas ?? "n/d") : "—"}
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
                <FonteDoDado painel="presenca" />
              </div>
            </div>

            <div className="mt-3.5 flex items-center justify-between gap-3 flex-wrap">
              <Compartilhar
                link={montarLink({ aba: "raiox", politico: perfil.id }, "/")}
                nomeDoArquivo={`legisdata-${perfil.nome_eleitoral.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}
                cartao={{
                  titulo: perfil.nome_eleitoral,
                  linhas: [
                    ["Cargo", perfil.cargo_atual],
                    ["Partido", perfil.partido_atual],
                    ["UF", perfil.uf],
                  ],
                  fonte: "Dados Abertos da Câmara dos Deputados e do Senado Federal; TSE",
                  data: new Date().toLocaleDateString("pt-BR"),
                  periodo: "Ficha atual, com a trajetória registrada na base",
                  etapa: "Ficha do político (cadastro, mandatos e partidos)",
                  link: montarLink({ aba: "raiox", politico: perfil.id }, "/"),
                }}
              />
              <ReportarErro alvoTipo="POLITICO" alvoId={perfil.id} alvoRotulo={perfil.nome_eleitoral} secao="Ficha do político" />
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
