"use client";

import React from "react";
import {
  FileText,
  Landmark,
  MapPin,
  Briefcase,
} from "lucide-react";
import type { PoliticoDossier } from "@/services/api";
import { EmptyState } from "@/components/StateViews";

interface AmendmentsTabProps {
  dossier: PoliticoDossier;
}

export default function AmendmentsTab({ dossier }: AmendmentsTabProps) {
  // Sem emendas na base não se exibe "R$ 0,00 pagos": ausência de dado não é execução zero.
  if (!dossier.emendas_parlamentares?.possui_dados) {
    return (
      <EmptyState
        title="Emendas parlamentares indisponíveis"
        message="A base não possui emendas registradas para este parlamentar."
      />
    );
  }
  return (
            <div className="space-y-6">
              {/* Header do Painel Emendas */}
              <div className="bg-slate-900/80 border border-emerald-500/30 rounded-2xl p-5 sm:p-6 backdrop-blur-md shadow-lg space-y-5">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-2.5">
                    <span className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                      <Landmark className="w-5 h-5" aria-hidden="true" />
                    </span>
                    <div>
                      <h3 className="text-base sm:text-lg font-bold text-slate-100 flex items-center gap-2">
                        A Trilha do Dinheiro &amp; Emendas Parlamentares
                      </h3>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Rastreamento de verbas públicas direcionadas por este parlamentar aos municípios e estados
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono text-emerald-300 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1 rounded-full font-bold">
                      Orçamento Geral da União
                    </span>
                    <span className="text-[11px] font-mono text-slate-400 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800">
                      {dossier?.emendas_parlamentares?.lista_emendas?.length || 0} emendas cadastradas
                    </span>
                  </div>
                </div>

                {/* 4 Cards de Resumo Executivo */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Total Efetivamente Pago
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-emerald-400 block leading-tight">
                      R$ {(dossier?.emendas_parlamentares?.total_pago || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      Recursos depositados nos destinos
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Total Empenhado no OGU
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-cyan-400 block leading-tight">
                      R$ {(dossier?.emendas_parlamentares?.total_empenhado || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      Compromisso orçamentário aprovado
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Taxa de Execução
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-purple-400 block leading-tight">
                      {dossier?.emendas_parlamentares?.percentual_execucao || 0}%
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      Razão entre pago e empenhado
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Principal Destino
                    </span>
                    <span className="text-xs sm:text-sm font-bold text-slate-200 block truncate leading-tight" title={dossier?.emendas_parlamentares?.destinos_principais?.[0]?.localidade || "Nenhum"}>
                      {dossier?.emendas_parlamentares?.destinos_principais?.[0]?.localidade || "Sem dados"}
                    </span>
                    <span className="text-[10px] font-mono text-emerald-400 mt-1 block">
                      R$ {(dossier?.emendas_parlamentares?.destinos_principais?.[0]?.valor_pago || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                </div>
              </div>

              {/* Grid 2 colunas: Ranking de Cidades/Estados Destino + Tipos & Áreas Temáticas */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Ranking de Cidades/Estados */}
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <MapPin className="w-4 h-4 text-emerald-400" aria-hidden="true" />
                      <h4 className="text-sm font-bold text-slate-100">
                        Localidades &amp; Municípios Mais Beneficiados
                      </h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      {dossier?.emendas_parlamentares?.destinos_principais?.length || 0} localidades
                    </span>
                  </div>

                  {(!dossier?.emendas_parlamentares?.destinos_principais || dossier.emendas_parlamentares.destinos_principais.length === 0) ? (
                    <p className="text-xs text-slate-400 py-6 text-center">
                      Nenhum repasse de emenda registrado.
                    </p>
                  ) : (
                    <div className="space-y-3 pt-1">
                      {dossier.emendas_parlamentares.destinos_principais.map((dest) => (
                        <div key={dest.localidade} className="space-y-1">
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-slate-300 font-medium truncate max-w-[240px] sm:max-w-[320px]">
                              {dest.localidade}
                            </span>
                            <div className="flex items-center gap-2 shrink-0 font-mono">
                              <span className="text-emerald-400 font-bold">
                                R$ {dest.valor_pago.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                              </span>
                              <span className="text-slate-400 text-[11px] w-12 text-right">
                                {dest.percentual}%
                              </span>
                            </div>
                          </div>
                          <div className="h-2 w-full bg-slate-950 rounded-full overflow-hidden border border-slate-800">
                            <div
                              className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(100, Math.max(2, dest.percentual))}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Distribuição por Tipo de Emenda e Função */}
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-5">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <Briefcase className="w-4 h-4 text-purple-400" aria-hidden="true" />
                      <h4 className="text-sm font-bold text-slate-100">
                        Modalidades &amp; Funções Orçamentárias
                      </h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      Critérios de Alocação
                    </span>
                  </div>

                  {/* Por Tipo de Emenda */}
                  <div className="space-y-2.5">
                    <span className="text-xs font-bold text-slate-300 uppercase tracking-wider block">
                      Por Modalidade de Emenda
                    </span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {dossier?.emendas_parlamentares?.distribuicao_por_tipo?.map((t) => (
                        <div key={t.tipo ?? t.area} className="bg-slate-950/70 border border-slate-800 rounded-xl p-3">
                          <span className="text-[11px] text-slate-400 block font-medium truncate">
                            {t.tipo || "Modalidade"}
                          </span>
                          <span className="text-sm font-bold font-mono text-purple-400 block mt-0.5">
                            R$ {t.valor_pago.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                          </span>
                          <span className="text-[10px] text-slate-400 font-mono">
                            {t.percentual}% do total
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Por Área Temática */}
                  <div className="space-y-2.5 pt-2 border-t border-slate-800/80">
                    <span className="text-xs font-bold text-slate-300 uppercase tracking-wider block">
                      Por Área de Aplicação dos Recursos
                    </span>
                    <div className="space-y-2">
                      {dossier?.emendas_parlamentares?.distribuicao_por_area?.map((a) => (
                        <div key={a.area ?? a.tipo} className="flex items-center justify-between text-xs bg-slate-950/50 p-2 rounded-lg border border-slate-800/60">
                          <span className="text-slate-300 font-medium">
                            {a.area || "Geral"}
                          </span>
                          <div className="flex items-center gap-2 font-mono">
                            <span className="text-cyan-400 font-bold">
                              R$ {a.valor_pago.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                            </span>
                            <span className="text-slate-400 text-[10px]">
                              ({a.percentual}%)
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Tabela das Emendas Parlamentares Registradas */}
              {dossier?.emendas_parlamentares?.lista_emendas && dossier.emendas_parlamentares.lista_emendas.length > 0 && (
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-emerald-400" aria-hidden="true" />
                      <h4 className="text-sm font-bold text-slate-100">
                        Detalhamento das Emendas no OGU
                      </h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      Rastreabilidade completa de cada repasse
                    </span>
                  </div>

                  <div className="overflow-x-auto rounded-xl border border-slate-800/80 bg-slate-950/60">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] font-bold border-b border-slate-800">
                        <tr>
                          <th className="py-2.5 px-3">Código / Ano</th>
                          <th className="py-2.5 px-3">Modalidade</th>
                          <th className="py-2.5 px-3">Localidade Destino</th>
                          <th className="py-2.5 px-3">Função / Área</th>
                          <th className="py-2.5 px-3 text-right">Empenhado</th>
                          <th className="py-2.5 px-3 text-right">Efetivamente Pago</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/50">
                        {dossier.emendas_parlamentares.lista_emendas.map((e) => (
                          <tr key={e.id} className="hover:bg-slate-900/80 transition-colors">
                            <td className="py-2.5 px-3 font-mono font-bold text-cyan-300 whitespace-nowrap">
                              {e.codigo_emenda || "--"} ({e.ano})
                            </td>
                            <td className="py-2.5 px-3 text-slate-300">
                              <span className="px-2 py-0.5 rounded bg-slate-800 text-[10px] font-medium">
                                {e.tipo_emenda}
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-slate-200 font-semibold">
                              {e.localidade_destino}
                            </td>
                            <td className="py-2.5 px-3 text-slate-400">
                              {e.funcao || "Geral"}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono text-slate-300 whitespace-nowrap">
                              R$ {e.valor_empenhado.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono font-bold text-emerald-400 whitespace-nowrap">
                              R$ {e.valor_pago.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
  );
}
