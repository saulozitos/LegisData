"use client";

import React from "react";
import {
  Calendar,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  ExternalLink,
  Scale,
  Gavel,
} from "lucide-react";
import type { PoliticoDossier } from "@/services/api";
import { safeExternalUrl } from "@/lib/safeUrl";
import { getFichaStatus, orNd } from "./format";

interface JusticeTabProps {
  dossier: PoliticoDossier;
}

export default function JusticeTab({ dossier }: JusticeTabProps) {
  const fichaStatus = getFichaStatus(dossier);
  return (
            <div className="space-y-6">
              {/* Header do Painel Judicial */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 sm:p-6 backdrop-blur-md shadow-lg space-y-5">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-2.5">
                    <span className="p-2 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
                      <Scale className="w-5 h-5" aria-hidden="true" />
                    </span>
                    <div>
                      <h3 className="text-base sm:text-lg font-bold text-slate-100 flex items-center gap-2">
                        Raio-X Judicial &amp; Certidões de Ficha Limpa
                      </h3>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Conformidade com a Lei Complementar nº 135/2010 (Lei da Ficha Limpa) e certidões registradas na Justiça Eleitoral
                      </p>
                    </div>
                  </div>
                  <span className="text-[11px] font-mono text-purple-300 bg-purple-500/10 border border-purple-500/20 px-3 py-1 rounded-full font-bold">
                    TSE DivulgaCandContas &amp; Tribunais
                  </span>
                </div>

                {/* Banner Hero do Status da Ficha Limpa */}
                {fichaStatus === "declared" ? (
                  <div className="bg-gradient-to-r from-rose-950/60 via-slate-950 to-rose-950/30 border border-rose-500/40 rounded-2xl p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-xl">
                    <div className="flex items-start gap-3.5">
                      <div className="p-2.5 rounded-xl bg-rose-500/20 text-rose-400 border border-rose-500/30 shrink-0">
                        <ShieldAlert className="w-6 h-6" aria-hidden="true" />
                      </div>
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="text-base font-extrabold text-rose-300">
                            Possui processos vinculados na Justiça
                          </h4>
                          <span className="text-[11px] font-mono font-bold bg-rose-500/20 text-rose-200 border border-rose-500/30 px-2 py-0.5 rounded-lg">
                            Atenção do Eleitor
                          </span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed max-w-2xl">
                          Há processo ligado à pessoa por fonte oficial ou registro declarado no TSE. A base não informa o papel da pessoa no processo nem o desfecho: leia cada registro abaixo e consulte a fonte.
                        </p>
                        {dossier.ficha_limpa?.orgaos_declarados && dossier.ficha_limpa?.orgaos_declarados.length > 0 && (
                          <div className="flex items-center gap-2 pt-1 flex-wrap">
                            <span className="text-[11px] font-bold text-rose-400">Órgãos com declaração:</span>
                            {dossier.ficha_limpa?.orgaos_declarados.map((org) => (
                              <span key={org} className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-rose-900/50 text-rose-200 border border-rose-500/40">
                                {org}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    <a
                      href={safeExternalUrl(dossier.ficha_limpa?.link_tse_divulgacand || "https://divulgacandcontas.tse.jus.br/")}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 border border-rose-500/40 text-xs font-bold transition-all shrink-0 hover:scale-[1.02]"
                    >
                      <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
                      Consulta TSE DivulgaCand ↗
                    </a>
                  </div>
                ) : fichaStatus === "none" ? (
                  <div className="bg-gradient-to-r from-emerald-950/60 via-slate-950 to-emerald-950/30 border border-emerald-500/40 rounded-2xl p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-xl">
                    <div className="flex items-start gap-3.5">
                      <div className="p-2.5 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 shrink-0">
                        <ShieldCheck className="w-6 h-6" aria-hidden="true" />
                      </div>
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="text-base font-extrabold text-emerald-300">
                            Nenhum processo declarado na base consultada
                          </h4>
                          <span className="text-[11px] font-mono font-bold bg-emerald-500/20 text-emerald-200 border border-emerald-500/30 px-2 py-0.5 rounded-lg">
                            Sem registros na base
                          </span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed max-w-2xl">
                          A base de dados do LegisData não registra processos declarados para este parlamentar. Isso não substitui a certidão oficial: confirme a situação diretamente no TSE e nos tribunais antes de tirar conclusões.
                        </p>
                      </div>
                    </div>

                    <a
                      href={safeExternalUrl(dossier?.ficha_limpa?.link_tse_divulgacand || "https://divulgacandcontas.tse.jus.br/")}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-200 border border-emerald-500/40 text-xs font-bold transition-all shrink-0 hover:scale-[1.02]"
                    >
                      <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
                      Validar Registro no TSE ↗
                    </a>
                  </div>
                ) : (
                  <div role="status" className="bg-slate-950/70 border border-slate-700 rounded-2xl p-5 flex items-start gap-3.5">
                    <div className="p-2.5 rounded-xl bg-slate-800 text-slate-300 border border-slate-700 shrink-0">
                      <Scale className="w-6 h-6" aria-hidden="true" />
                    </div>
                    <div className="space-y-1">
                      <h4 className="text-base font-extrabold text-slate-200">Dado indisponível</h4>
                      <p className="text-xs text-slate-300 leading-relaxed max-w-2xl">
                        A API não retornou informações sobre a situação judicial deste parlamentar. A ausência do dado não significa &ldquo;nada consta&rdquo;: consulte o TSE e os tribunais.
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* SEÇÃO DE PROCESSOS COM COMPROVAÇÃO OFICIAL */}
              {dossier?.ficha_limpa?.possui_processos_declarados && dossier?.ficha_limpa?.processos_detalhados && dossier.ficha_limpa?.processos_detalhados.length > 0 && (
                <div className="bg-slate-900/80 border border-rose-500/30 rounded-2xl p-5 sm:p-6 space-y-4 shadow-xl">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <Scale className="w-5 h-5 text-rose-400" aria-hidden="true" />
                      <h4 className="text-base font-bold text-slate-100 flex items-center gap-2">
                        Processos e registros vinculados
                        <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/30">
                          {dossier.ficha_limpa?.processos_detalhados.length} {dossier.ficha_limpa?.processos_detalhados.length === 1 ? "registro" : "registros"}
                        </span>
                      </h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      Dados públicos do DataJud (CNJ) e do TSE, sem inferência de desfecho
                    </span>
                  </div>

                  <div className="grid grid-cols-1 gap-4">
                    {dossier.ficha_limpa?.processos_detalhados.map((proc, idx) => {
                      // Cor única e neutra: o texto do último movimento é do tribunal, e a tela não deduz desfecho dele.
                      const linkDoVinculo = safeExternalUrl(proc.link_comprovacao);
                      return (
                        <div
                          key={`${proc.numero_processo ?? "sem-numero"}-${idx}`}
                          className="bg-slate-950/90 border border-slate-800 hover:border-slate-700 rounded-xl p-4 sm:p-5 space-y-3.5 transition-all shadow-md"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-xs font-mono font-black px-2.5 py-1 rounded-lg bg-slate-900 border border-purple-500/30 text-purple-300">
                                {orNd(proc.tribunal)}
                              </span>
                              <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700 text-slate-200">
                                Nº {orNd(proc.numero_processo)}
                              </span>
                              <span className="text-[11px] font-mono text-slate-400 flex items-center gap-1 bg-slate-900/60 px-2 py-0.5 rounded border border-slate-800">
                                <Calendar className="w-3 h-3 text-slate-400" aria-hidden="true" />
                                {orNd(proc.data_processo)}
                              </span>
                            </div>
                            <span className="text-[11px] font-mono font-bold px-2.5 py-0.5 rounded-full border bg-slate-800 text-slate-200 border-slate-600">
                              {orNd(proc.status_resumo)}
                            </span>
                          </div>

                          <div className="space-y-1.5 text-xs">
                            <div className="font-semibold text-slate-200">
                              <span className="text-slate-400">Classe / Assunto:</span> {orNd(proc.classe_assunto)}
                            </div>
                            <p className="text-slate-300 leading-relaxed bg-slate-900/40 p-2.5 rounded-lg border border-slate-800/80">
                              {orNd(proc.descricao)}
                            </p>
                          </div>

                          <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
                            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">
                              Situação Jurídica &amp; Efeitos
                            </span>
                            <p className="text-xs font-medium leading-relaxed text-slate-200">
                              {orNd(proc.situacao_juridica)}
                            </p>
                          </div>

                          {linkDoVinculo && (
                            <div className="pt-1 flex items-center justify-between flex-wrap gap-2">
                              <span className="text-[11px] font-mono text-slate-400">
                                Fonte oficial que liga o processo à pessoa
                              </span>
                              <a
                                href={linkDoVinculo}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 text-purple-200 hover:text-white border border-purple-500/40 font-semibold text-xs transition-all shadow-sm"
                              >
                                <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
                                Consultar a fonte do vínculo ↗
                              </a>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Grid de Certidões por Tribunal */}
              <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <Gavel className="w-4 h-4 text-purple-400" aria-hidden="true" />
                    <h4 className="text-sm font-bold text-slate-100">
                      Certidões Oficiais Registradas no TSE
                    </h4>
                  </div>
                  <span className="text-xs text-slate-400">
                    Total: <strong className="text-purple-400">{dossier?.ficha_limpa?.certidoes?.length || 0}</strong> certidões
                  </span>
                </div>

                {(!dossier?.ficha_limpa?.certidoes || dossier.ficha_limpa?.certidoes.length === 0) ? (
                  <p className="text-xs text-slate-400 py-6 text-center">
                    Nenhuma certidão individual cadastrada na base para este parlamentar.
                  </p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                    {dossier.ficha_limpa?.certidoes.map((c) => {
                      const isPositiva = c.status_ficha.toLowerCase().includes("positiva") || c.status_ficha.toLowerCase().includes("declarada");
                      return (
                        <div
                          key={c.id}
                          className={`bg-slate-950/80 rounded-xl p-4 border space-y-3 transition-all ${
                            isPositiva
                              ? "border-rose-500/30 hover:border-rose-500/50"
                              : "border-slate-800 hover:border-emerald-500/30"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-mono font-black text-slate-100 px-2 py-0.5 rounded bg-slate-900 border border-slate-700">
                              {c.orgao}
                            </span>
                            <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
                              isPositiva
                                ? "bg-rose-500/15 text-rose-300 border-rose-500/30"
                                : "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                            }`}>
                              {c.status_ficha}
                            </span>
                          </div>

                          <div className="text-xs font-semibold text-slate-300">
                            Tipo: <span className="text-slate-100">{c.tipo_certidao}</span>
                          </div>

                          {c.detalhes && (
                            <p className="text-[11px] text-slate-400 leading-relaxed bg-slate-900/50 p-2.5 rounded-lg border border-slate-800/60">
                              {c.detalhes}
                            </p>
                          )}

                          {/* Metadados: Número do Processo / Protocolo e Data de Emissão */}
                          <div className="bg-slate-900/70 rounded-lg p-2.5 border border-slate-800/80 space-y-1 text-xs">
                            <div className="flex items-center justify-between text-[11px] text-slate-400">
                              <span>Nº Processo / Protocolo:</span>
                              <span className="font-mono font-bold text-slate-200">
                                {c.numero_processo ?? c.codigo_autenticidade ?? "Não informado"}
                              </span>
                            </div>
                            <div className="flex items-center justify-between text-[11px] text-slate-400">
                              <span>Data de Emissão:</span>
                              <span className="font-mono text-slate-300">
                                {c.data_emissao ?? "Não informada"}
                              </span>
                            </div>
                          </div>

                          {/* Link de Comprovação Oficial */}
                          {c.link_comprovacao && (
                            <div className="pt-0.5 flex justify-end">
                              <a
                                href={safeExternalUrl(c.link_comprovacao)}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-[11px] text-purple-400 hover:text-purple-300 font-semibold transition-colors hover:underline"
                              >
                                <ExternalLink className="w-3 h-3" aria-hidden="true" />
                                Conferir Comprovação no Órgão Oficial ↗
                              </a>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Box Informativo Legal Antidesinformação */}
              <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 text-xs text-slate-400 space-y-1.5">
                <span className="font-bold text-slate-200 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />
                  Marco Legal e Critério Técnico de Ficha Limpa
                </span>
                <p className="leading-relaxed">
                  A Lei Complementar nº 135/2010 estabelece a inelegibilidade de candidatos condenados por órgãos colegiados em crimes contra a administração pública, eleitorais e de lavagem de dinheiro. A mera existência de procedimentos investigatórios ou ações em andamento sem trânsito em julgado ou decisão colegiada respeita a presunção constitucional de inocência. As informações acima são transcritas fielmente das certidões do TSE e das consultas públicas oficiais do Poder Judiciário.
                </p>
              </div>
            </div>
  );
}
