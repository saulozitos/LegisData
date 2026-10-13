"use client";

import React, { useState } from "react";
import {
  ResponsiveContainer,
  Tooltip,
  Cell,
  Pie,
  PieChart as RechartsPieChart,
} from "recharts";
import {
  Search,
  CheckCircle,
  AlertTriangle,
  Sparkles,
  ExternalLink,
  PieChart as LucidePieChart,
} from "lucide-react";
import type { PoliticoDossier } from "@/services/api";
import { safeExternalUrl } from "@/lib/safeUrl";

interface PropositionsTabProps {
  dossier: PoliticoDossier;
}

export default function PropositionsTab({ dossier }: PropositionsTabProps) {
  const [proposicaoFilter, setProposicaoFilter] = useState<"TODAS" | "IMPACTO" | "SIMBOLICO">("TODAS");
  const [proposicaoSearch, setProposicaoSearch] = useState<string>("");
  return (
            <div className="space-y-6">
              {/* Header do Detector de Leis Inúteis */}
              <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-purple-950/30 border border-purple-500/30 rounded-2xl p-5 sm:p-6 backdrop-blur-md shadow-lg space-y-4">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-3">
                    <div className="p-3 rounded-2xl bg-purple-500/10 border border-purple-500/20 text-purple-400 shadow-inner">
                      <LucidePieChart className="w-7 h-7" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-lg font-black text-slate-100">
                          Detector de Leis Inúteis & Relevância Legislativa
                        </h2>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30 font-bold">
                          Arsenal Antidesinformação
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">
                        Classificação automatizada por processamento de linguagem natural: Leis Estruturais vs Homenagens Simbólicas
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400">Diagnóstico:</span>
                    <span className={`text-xs font-mono font-bold px-3 py-1.5 rounded-xl border ${
                      (dossier?.relevancia_legislativa?.percentual_impacto || 0) >= 60
                        ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
                        : "bg-amber-500/15 text-amber-300 border-amber-500/40"
                    }`}>
                      {dossier?.relevancia_legislativa?.diagnostico || "Em análise"}
                    </span>
                  </div>
                </div>

                {/* Grid Analítico: Gráfico de Pizza + Estatísticas Detalhadas */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-center pt-2">
                  {/* Painel do Gráfico de Pizza */}
                  <div className="bg-slate-950/80 border border-slate-800 rounded-2xl p-4 flex flex-col items-center justify-center">
                    <span className="text-xs font-bold text-slate-200 mb-1">
                      Proporção de Relevância Legislativa
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono mb-2">
                      Gráfico de Pizza: Projetos de Impacto ({dossier?.relevancia_legislativa?.percentual_impacto || 0}%) vs Simbólicos ({dossier?.relevancia_legislativa?.percentual_simbolico || 0}%)
                    </span>

                    <div className="w-full h-52">
                      <ResponsiveContainer width="100%" height="100%">
                        <RechartsPieChart>
                          <Pie
                            data={[
                              {
                                name: "Projetos de Impacto / Substanciais",
                                value: dossier?.relevancia_legislativa?.projetos_impacto || 0,
                                pct: dossier?.relevancia_legislativa?.percentual_impacto || 0,
                              },
                              {
                                name: "Projetos Simbólicos / Homenagens",
                                value: dossier?.relevancia_legislativa?.projetos_simbolicos || 0,
                                pct: dossier?.relevancia_legislativa?.percentual_simbolico || 0,
                              },
                            ]}
                            dataKey="value"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            innerRadius={50}
                            outerRadius={80}
                            paddingAngle={4}
                          >
                            <Cell fill="#10b981" />
                            <Cell fill="#f59e0b" />
                          </Pie>
                          <Tooltip
                            content={({ active, payload }) => {
                              if (!active || !payload || !payload.length) return null;
                              const d = payload[0].payload;
                              return (
                                <div className="bg-slate-900 border border-slate-700 p-2.5 rounded-xl text-xs shadow-xl space-y-1">
                                  <span className="font-bold text-slate-200 block">{d.name}</span>
                                  <div className="flex items-center gap-2">
                                    <span className="font-mono text-cyan-400 font-bold">{d.value} matérias</span>
                                    <span className="text-slate-400 font-mono">({d.pct}%)</span>
                                  </div>
                                </div>
                              );
                            }}
                          />
                        </RechartsPieChart>
                      </ResponsiveContainer>
                    </div>

                    <div className="grid grid-cols-2 gap-2 w-full pt-2 text-[11px] font-mono">
                      <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-2 text-center">
                        <span className="text-emerald-400 font-bold block">
                          Impacto ({dossier?.relevancia_legislativa?.percentual_impacto || 0}%)
                        </span>
                        <span className="text-slate-400 text-[10px]">
                          {dossier?.relevancia_legislativa?.projetos_impacto || 0} projetos
                        </span>
                      </div>
                      <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-2 text-center">
                        <span className="text-amber-400 font-bold block">
                          Simbólico ({dossier?.relevancia_legislativa?.percentual_simbolico || 0}%)
                        </span>
                        <span className="text-slate-400 text-[10px]">
                          {dossier?.relevancia_legislativa?.projetos_simbolicos || 0} projetos
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Informações Metodológicas & Explicativas */}
                  <div className="lg:col-span-2 space-y-3">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                        <span className="text-[10px] text-slate-400 font-medium block mb-1">Total de Proposições</span>
                        <span className="text-xl font-black font-mono text-cyan-400 block">
                          {dossier?.relevancia_legislativa?.total_proposicoes || 0}
                        </span>
                        <span className="text-[10px] text-slate-400 mt-1 block">Projetos de autoria cadastrados</span>
                      </div>
                      <div className="bg-slate-950/70 border border-emerald-500/30 rounded-xl p-3.5">
                        <span className="text-[10px] text-emerald-400 font-medium block mb-1">Impacto / Estrutural</span>
                        <span className="text-xl font-black font-mono text-emerald-400 block">
                          {dossier?.relevancia_legislativa?.projetos_impacto || 0} ({dossier?.relevancia_legislativa?.percentual_impacto || 0}%)
                        </span>
                        <span className="text-[10px] text-slate-400 mt-1 block">Economia, Saúde, Código Penal</span>
                      </div>
                      <div className="bg-slate-950/70 border border-amber-500/30 rounded-xl p-3.5">
                        <span className="text-[10px] text-amber-400 font-medium block mb-1">Simbólico / Homenagem</span>
                        <span className="text-xl font-black font-mono text-amber-400 block">
                          {dossier?.relevancia_legislativa?.projetos_simbolicos || 0} ({dossier?.relevancia_legislativa?.percentual_simbolico || 0}%)
                        </span>
                        <span className="text-[10px] text-slate-400 mt-1 block">Títulos, Homenagens e Datas</span>
                      </div>
                    </div>

                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-2 text-xs">
                      <span className="font-bold text-slate-200 block">Como funciona o algoritmo de classificação?</span>
                      <p className="text-slate-400 leading-relaxed text-[11px]">
                        O detector analisa a ementa de cada proposição em busca de marcadores semânticos honoríficos (como <em>&quot;Dia Nacional&quot;</em>, <em>&quot;Homenagem&quot;</em>, <em>&quot;Denomina&quot;</em>, <em>&quot;Cidadão Honorário&quot;</em> e <em>&quot;Título&quot;</em>). Matérias com essas características são categorizadas como <strong>Simbólicas</strong>, enquanto as demais são classificadas como <strong>Impacto/Substancial</strong>.
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Filtros e Barra de Busca */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-900/60 border border-slate-800 p-3.5 rounded-2xl">
                <div className="flex items-center gap-1.5 w-full sm:w-auto overflow-x-auto">
                  <button
                    type="button"
                    onClick={() => setProposicaoFilter("TODAS")}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
                      proposicaoFilter === "TODAS"
                        ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Todas ({dossier?.materias_propostas?.length || 0})
                  </button>
                  <button
                    type="button"
                    onClick={() => setProposicaoFilter("IMPACTO")}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
                      proposicaoFilter === "IMPACTO"
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Impacto ({dossier?.relevancia_legislativa ? dossier.relevancia_legislativa.projetos_impacto : "—"})
                  </button>
                  <button
                    type="button"
                    onClick={() => setProposicaoFilter("SIMBOLICO")}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
                      proposicaoFilter === "SIMBOLICO"
                        ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Simbólicas ({dossier?.relevancia_legislativa ? dossier.relevancia_legislativa.projetos_simbolicos : "—"})
                  </button>
                </div>

                <div className="relative w-full sm:w-72">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" aria-hidden="true" />
                  <input
                    type="text"
                    value={proposicaoSearch}
                    onChange={(e) => setProposicaoSearch(e.target.value)}
                    placeholder="Buscar ementa, tipo ou número..."
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-400 focus:outline-none focus:border-purple-500/50"
                  />
                </div>
              </div>

              {/* Lista Detalhada de Proposições */}
              {(() => {
                const proposicoesExibidas = (dossier?.materias_propostas || []).filter((p) => {
                  const matchFilter =
                    proposicaoFilter === "TODAS"
                      ? true
                      : proposicaoFilter === "IMPACTO"
                      ? p.classificacao_relevancia === "IMPACTO"
                      : p.classificacao_relevancia === "SIMBOLICO";
                  const matchSearch =
                    !proposicaoSearch.trim() ||
                    p.titulo.toLowerCase().includes(proposicaoSearch.toLowerCase()) ||
                    p.ementa.toLowerCase().includes(proposicaoSearch.toLowerCase()) ||
                    `${p.tipo} ${p.numero}`.toLowerCase().includes(proposicaoSearch.toLowerCase());
                  return matchFilter && matchSearch;
                });

                if (proposicoesExibidas.length === 0) {
                  return (
                    <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-8 text-center text-xs text-slate-400">
                      Nenhuma proposição encontrada para os filtros selecionados.
                    </div>
                  );
                }

                return (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {proposicoesExibidas.map((p) => {
                      const isImpacto = p.classificacao_relevancia === "IMPACTO";
                      return (
                        <div
                          key={p.id}
                          className={`bg-slate-900/70 border rounded-2xl p-4.5 space-y-3 transition-all ${
                            isImpacto
                              ? "border-emerald-500/20 hover:border-emerald-500/40"
                              : "border-amber-500/20 hover:border-amber-500/40"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-slate-950 text-purple-300 border border-purple-500/20">
                              {p.tipo} {p.numero}/{p.ano}
                            </span>
                            <span
                              className={`text-[10px] font-mono font-bold px-2.5 py-1 rounded-lg border flex items-center gap-1 ${
                                isImpacto
                                  ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
                                  : "bg-amber-500/15 text-amber-300 border-amber-500/40"
                              }`}
                            >
                              {isImpacto ? (
                                <>
                                  <CheckCircle className="w-3 h-3 text-emerald-400" aria-hidden="true" />
                                  <span>Impacto / Estrutural</span>
                                </>
                              ) : (
                                <>
                                  <AlertTriangle className="w-3 h-3 text-amber-400" aria-hidden="true" />
                                  <span>Simbólico / Homenagem</span>
                                </>
                              )}
                            </span>
                          </div>

                          <div>
                            <div className="flex items-start justify-between gap-2">
                              <h4 className="text-xs font-bold text-slate-100 leading-snug">
                                {p.titulo}
                              </h4>
                              {p.url_oficial && (
                                <a
                                  href={safeExternalUrl(p.url_oficial)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 transition-colors shrink-0 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded-lg"
                                >
                                  <span>Íntegra</span>
                                  <ExternalLink className="w-3 h-3" aria-hidden="true" />
                                </a>
                              )}
                            </div>
                            <span className="text-[10px] text-slate-400 font-mono mt-1 block">
                              Apresentado em {p.data_apresentacao || "Data não registrada"}
                            </span>
                          </div>

                          <p className="text-xs text-slate-300 leading-relaxed bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
                            {p.ementa}
                          </p>

                          {p.justificativa_relevancia && (
                            <div className="flex items-center gap-1.5 text-[10px] text-slate-400 font-mono pt-1">
                              <Sparkles className="w-3 h-3 text-purple-400 shrink-0" aria-hidden="true" />
                              <span>{p.justificativa_relevancia}</span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                );
              })()}
            </div>
  );
}
