"use client";

import React, { useState } from "react";
import {
  Search,
  FileText,
  Sparkles,
  ExternalLink,
} from "lucide-react";
import type { PoliticoDossier } from "@/services/api";
import { fmtNum } from "@/lib/format";
import { safeExternalUrl } from "@/lib/safeUrl";
import { voteLabel, voteTone } from "@/lib/votes";
import VotesSummaryBlock from "./VotesSummaryBlock";

interface VotesTabProps {
  dossier: PoliticoDossier;
}

export default function VotesTab({ dossier }: VotesTabProps) {
  const [voteSearchTerm, setVoteSearchTerm] = useState<string>("");
  return (
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 sm:p-6 space-y-5">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-purple-400" aria-hidden="true" />
                  <h3 className="text-sm sm:text-base font-bold text-slate-100">
                    Posicionamento nas Leis Estruturantes
                  </h3>
                </div>
                <span className="text-xs text-slate-400">
                  {dossier.votacoes_principais.length} deliberações nominais registradas
                </span>
              </div>

              <VotesSummaryBlock resumo={dossier.resumo_votos} />

              {/* Alinhamento Temático por Eixo de Impacto */}
              {dossier.alinhamento_tematico && dossier.alinhamento_tematico.length > 0 && (
                <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4.5 space-y-3.5">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />
                      <span>Alinhamento Temático por Categoria de Lei</span>
                    </h4>
                    <span className="text-[11px] text-slate-400">Classificação Técnica e Neutra</span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {dossier.alinhamento_tematico.map((al) => (
                      <div
                        key={al.eixo}
                        className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-3.5 space-y-2"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-slate-200 text-xs">{al.eixo}</span>
                          <span className={`text-xs font-mono font-extrabold ${
                            al.percentual_favoravel >= 60
                              ? "text-emerald-400"
                              : al.percentual_favoravel <= 40
                              ? "text-rose-400"
                              : "text-amber-400"
                          }`}>
                            {fmtNum(al.percentual_favoravel, 1)}% a favor
                          </span>
                        </div>

                        {/* Barra de Progresso do Alinhamento */}
                        <div className="w-full bg-slate-950 h-2 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ${
                              al.percentual_favoravel >= 60
                                ? "bg-emerald-500"
                                : al.percentual_favoravel <= 40
                                ? "bg-rose-500"
                                : "bg-amber-500"
                            }`}
                            style={{ width: `${al.percentual_favoravel}%` }}
                          />
                        </div>

                        <div className="flex justify-between text-[10px] text-slate-400">
                          <span>{al.votos_sim} a favor • {al.votos_nao} contra</span>
                          <span>{al.total_votacoes} votações</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Campo de Busca Simples na Capivara de Votos */}
              {(() => {
                const rawVotes =
                  dossier.historico_votos && dossier.historico_votos.length > 0
                    ? dossier.historico_votos
                    : dossier.votacoes_principais.map((v) => ({
                        proposicao_id: v.proposicao_id,
                        proposicao_titulo: v.proposicao_titulo,
                        proposicao_numero: `${v.proposicao_tipo} ${v.proposicao_numero}/${v.proposicao_ano}`,
                        proposicao_tipo: v.proposicao_tipo,
                        tema: "Geral",
                        setor: "Geral",
                        data: v.sessao_data ? v.sessao_data.slice(0, 10).split("-").reverse().join("/") : "-",
                        data_iso: v.sessao_data,
                        voto: voteLabel(v.decisao),
                        decisao: v.decisao,
                        sessao_titulo: v.sessao_titulo,
                        sessao_aprovada: v.sessao_aprovada,
                        casa_legislativa: v.casa_legislativa,
                        url_oficial: null as string | null,
                      }));

                const filteredVotes = rawVotes.filter((v) => {
                  if (!voteSearchTerm.trim()) return true;
                  const term = voteSearchTerm.toLowerCase();
                  return (
                    v.proposicao_titulo.toLowerCase().includes(term) ||
                    v.proposicao_numero.toLowerCase().includes(term) ||
                    (v.tema && v.tema.toLowerCase().includes(term)) ||
                    (v.setor && v.setor.toLowerCase().includes(term)) ||
                    (v.sessao_titulo && v.sessao_titulo.toLowerCase().includes(term)) ||
                    v.voto.toLowerCase().includes(term)
                  );
                });

                if (rawVotes.length === 0) {
                  return (
                    <div className="text-center py-10 text-slate-400 text-xs">
                      Nenhum voto nominal registrado para este parlamentar nas matérias cadastradas.
                    </div>
                  );
                }

                return (
                  <div className="space-y-4">
                    {/* Barra de Pesquisa de Votos */}
                    <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-slate-950/70 border border-slate-800 rounded-xl p-3">
                      <div className="relative flex-1">
                        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" aria-hidden="true" />
                        <input
                          type="text"
                          aria-label="Pesquisar votos por matéria, número, tema ou palavra-chave"
                          placeholder="Pesquisar por matéria, número, tema ou palavra-chave..."
                          value={voteSearchTerm}
                          onChange={(e) => setVoteSearchTerm(e.target.value)}
                          className="w-full bg-slate-900 border border-slate-800/80 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-100 placeholder-slate-400 focus:outline-none focus:border-cyan-400 transition-colors"
                        />
                      </div>
                      <div className="text-xs text-slate-400 px-1 whitespace-nowrap">
                        Exibindo <strong className="text-cyan-400 font-mono">{filteredVotes.length}</strong> de{" "}
                        <span className="font-mono">{rawVotes.length}</span> deliberações
                      </div>
                    </div>

                    {/* Tabela de Histórico de Votos */}
                    <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/50 shadow-inner">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[11px] font-bold border-b border-slate-800">
                          <tr>
                            <th className="py-3 px-4">Matéria / Proposição</th>
                            <th className="py-3 px-4 w-32 whitespace-nowrap">Data</th>
                            <th className="py-3 px-4 w-36 text-center whitespace-nowrap">Voto Registrado</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60">
                          {filteredVotes.length === 0 ? (
                            <tr>
                              <td colSpan={3} className="py-8 text-center text-slate-400 text-xs">
                                Nenhuma deliberação encontrada para &ldquo;{voteSearchTerm}&rdquo;.
                              </td>
                            </tr>
                          ) : (
                            filteredVotes.map((v, indice) => {
                              const decisaoVoto = v.decisao || v.voto;
                              const tone = voteTone(decisaoVoto);
                              const badgeColor =
                                tone === "yes"
                                  ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                                  : tone === "no"
                                  ? "bg-rose-500/15 text-rose-400 border-rose-500/30"
                                  : tone === "abstain"
                                  ? "bg-amber-500/15 text-amber-400 border-amber-500/30"
                                  : tone === "obstruction"
                                  ? "bg-purple-500/15 text-purple-300 border-purple-500/30"
                                  : "bg-slate-700/30 text-slate-300 border-slate-700/50";

                              const labelVoto = voteLabel(decisaoVoto);
                              const temaLabel = v.tema || v.setor || "Geral";

                              return (
                                <tr key={`${v.proposicao_id}-${v.data}-${v.casa_legislativa}-${indice}`} className="hover:bg-slate-900/60 transition-colors">
                                  {/* Coluna 1: Matéria/Proposição com Tema/Setor */}
                                  <td className="py-3 px-4">
                                    <div className="space-y-1">
                                      <div className="flex flex-wrap items-center gap-2">
                                        <span className="font-mono font-bold text-xs text-cyan-300 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded">
                                          {v.proposicao_numero}
                                        </span>
                                        <span className="text-[10px] font-semibold text-purple-300 bg-purple-500/10 border border-purple-500/20 px-2 py-0.5 rounded">
                                          {temaLabel}
                                        </span>
                                        <span className="text-[10px] text-slate-400">
                                          {v.casa_legislativa === "CAMARA_DOS_DEPUTADOS" ? "Câmara" : "Senado"}
                                        </span>
                                      </div>
                                      <div className="font-semibold text-slate-200 leading-snug flex items-start justify-between gap-2">
                                        <span>{v.proposicao_titulo}</span>
                                        {v.url_oficial && (
                                          <a
                                            href={safeExternalUrl(v.url_oficial)}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="inline-flex items-center gap-1 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 transition-colors shrink-0 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded-lg"
                                            title="Ler íntegra no site oficial"
                                          >
                                            <span>Íntegra</span>
                                            <ExternalLink className="w-3 h-3" aria-hidden="true" />
                                          </a>
                                        )}
                                      </div>
                                      {v.sessao_titulo && (
                                        <p className="text-[11px] text-slate-400 line-clamp-1">
                                          {v.sessao_titulo}
                                        </p>
                                      )}
                                    </div>
                                  </td>

                                  {/* Coluna 2: Data */}
                                  <td className="py-3 px-4 whitespace-nowrap text-slate-400 font-mono text-[11px]">
                                    {v.data}
                                  </td>

                                  {/* Coluna 3: Voto (Badge Colorido) */}
                                  <td className="py-3 px-4 text-center whitespace-nowrap">
                                    <span
                                      className={`inline-block font-mono font-black text-xs px-3 py-1 rounded-xl border ${badgeColor}`}
                                    >
                                      {labelVoto}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })()}
            </div>
  );
}
