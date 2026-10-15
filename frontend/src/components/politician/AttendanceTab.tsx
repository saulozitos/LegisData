"use client";

import React from "react";
import {
  CheckCircle,
} from "lucide-react";
import type { PoliticoDossier } from "@/services/api";
import { fmtNum } from "@/lib/format";

interface AttendanceTabProps {
  dossier: PoliticoDossier;
}

export default function AttendanceTab({ dossier }: AttendanceTabProps) {
  const assiduidade = dossier.assiduidade;
  const hasAttendance = Boolean(assiduidade) && (assiduidade?.total_sessoes ?? 0) > 0;
  return (
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 sm:p-6 space-y-6">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
                <div>
                  <h3 className="text-sm sm:text-base font-bold text-slate-100 flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-emerald-400" aria-hidden="true" />
                    Balanço Oficial de Assiduidade em Plenário
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {assiduidade?.unidade
                      ? `Unidade: ${assiduidade.unidade}${
                          assiduidade.periodo_inicio && assiduidade.periodo_fim
                            ? ` · ${assiduidade.periodo_inicio} a ${assiduidade.periodo_fim}`
                            : ""
                        }`
                      : "Contabilização de sessões deliberativas ordinárias e extraordinárias na Legislatura"}
                  </p>
                  {assiduidade?.fonte ? (
                    <p className="text-[11px] text-slate-500 mt-0.5">Fonte: {assiduidade.fonte}</p>
                  ) : null}
                </div>

                <div className="px-3.5 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300 font-mono font-bold">
                  Taxa de Presença: {hasAttendance ? `${fmtNum(assiduidade?.taxa_presenca_pct)}%` : "Dado indisponível"}
                </div>
              </div>

              {assiduidade?.observacao && (
                <div className="p-3 rounded-xl bg-sky-500/5 border border-sky-500/20 text-[11px] text-sky-200">
                  {assiduidade.observacao}
                </div>
              )}

              {/* Indicadores de Presença */}
              <div
                className={`grid grid-cols-1 gap-4 ${(assiduidade?.faltas_inferidas ?? 0) > 0 ? "sm:grid-cols-4" : "sm:grid-cols-3"}`}
              >
                <div className="bg-slate-950/70 border border-emerald-500/20 rounded-xl p-4 space-y-1">
                  <span className="text-xs text-slate-400">Presenças Confirmadas</span>
                  <div className="text-2xl font-black text-emerald-400 font-mono">
                    {hasAttendance ? assiduidade?.total_presencas : "—"}
                  </div>
                  <span className="text-[11px] text-slate-400">
                    Sessões deliberativas registradas
                  </span>
                </div>

                <div className="bg-slate-950/70 border border-amber-500/20 rounded-xl p-4 space-y-1">
                  <span className="text-xs text-slate-400">Faltas Justificadas</span>
                  <div className="text-2xl font-black text-amber-400 font-mono">
                    {hasAttendance ? assiduidade?.faltas_justificadas : "—"}
                  </div>
                  <span className="text-[11px] text-slate-400">
                    Ausências com justificativa formal
                  </span>
                </div>

                <div className="bg-slate-950/70 border border-rose-500/20 rounded-xl p-4 space-y-1">
                  <span className="text-xs text-slate-400">Faltas Não Justificadas</span>
                  <div className="text-2xl font-black text-rose-400 font-mono">
                    {hasAttendance ? (assiduidade?.faltas_nao_justificadas ?? "n/d") : "—"}
                  </div>
                  <span className="text-[11px] text-slate-400">
                    {hasAttendance && assiduidade?.faltas_nao_justificadas == null
                      ? "Não informado pela fonte"
                      : "Ausências sem protocolo prévio"}
                  </span>
                </div>

                {(assiduidade?.faltas_inferidas ?? 0) > 0 && (
                  <div className="bg-slate-950/70 border border-sky-500/20 rounded-xl p-4 space-y-1">
                    <span className="text-xs text-slate-400">Faltas Inferidas</span>
                    <div className="text-2xl font-black text-sky-400 font-mono">{assiduidade?.faltas_inferidas}</div>
                    <span className="text-[11px] text-slate-400">Deduzidas: em exercício e sem presença registrada</span>
                  </div>
                )}
              </div>

              {/* Tabela de Justificativas / Ocorrências de Ausência */}
              <div className="space-y-3 pt-2">
                <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                  Histórico Detalhado de Ausências e Justificativas Regimentais
                </h4>

                {assiduidade?.amostra_faltas?.length === 0 ? (
                  <div className="p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20 text-xs text-emerald-300 text-center">
                    Nenhuma ausência na amostra retornada pela API. A amostra não equivale ao total: consulte a taxa de presença acima.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {assiduidade?.amostra_faltas?.map((f) => (
                      <div
                        key={`${f.data}-${f.casa}-${f.tipo}`}
                        className="bg-slate-950/80 border border-slate-800 rounded-xl p-3 flex items-start justify-between gap-3 text-xs"
                      >
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-slate-300 font-bold">
                              {f.data}
                            </span>
                            <span
                              className={`text-[10px] font-bold px-2 py-0.2 rounded ${
                                f.tipo.includes("JUSTIFICADA") || f.tipo.includes("LICENCA") || f.tipo.includes("MISSAO")
                                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                  : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                              }`}
                            >
                              {f.tipo.replace(/_/g, " ")}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400">
                            {f.justificativa || "Sem justificativa formal protocolada"}
                          </p>
                        </div>

                        <span className="text-[10px] text-slate-400 font-semibold flex-shrink-0">
                          {f.casa === "CAMARA_DOS_DEPUTADOS" ? "Câmara" : "Senado"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
  );
}
