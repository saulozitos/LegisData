"use client";

import React, { useState } from "react";
import {
  Search,
  FileText,
  Award,
  Coins,
} from "lucide-react";
import type { PoliticoDossier } from "@/services/api";
import { formatCpfCnpj } from "./format";
import { EmptyState } from "@/components/StateViews";
import { fmtReais } from "@/lib/format";

interface FinancingTabProps {
  dossier: PoliticoDossier;
}

export default function FinancingTab({ dossier }: FinancingTabProps) {
  const [doacaoSearch, setDoacaoSearch] = useState<string>("");
  // Sem prestação de contas na base não se exibe "R$ 0,00 arrecadados": ausência de dado não é receita zero.
  if (!dossier.financiamento_campanha?.possui_dados) {
    return (
      <EmptyState
        title="Financiamento de campanha indisponível"
        message="A base não possui a prestação de contas de campanha deste parlamentar."
      />
    );
  }
  // Média por doador só existe com a quantidade de doadores conhecida; sem ela fica "n/d" em vez de um palpite.
  const campanha = dossier.financiamento_campanha;
  // o resumo é de uma eleição só (eleições diferentes nunca se misturam no total): as demais ficam avisadas
  const outrasEleicoes = (campanha.eleicoes_disponiveis ?? []).filter((ano) => ano !== campanha.ano_eleicao);
  const ticketMedio =
    campanha.total_doadores && campanha.total_arrecadado !== null ? campanha.total_arrecadado / campanha.total_doadores : null;
  return (
            <div className="space-y-6">
              {/* Header de Financiamento */}
              <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-emerald-950/30 border border-emerald-500/30 rounded-2xl p-5 sm:p-6 backdrop-blur-md shadow-lg space-y-4">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-3">
                    <div className="p-3 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 shadow-inner">
                      <Coins className="w-7 h-7" aria-hidden="true" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-lg font-black text-slate-100">
                          Quem Paga a Conta? (Financiamento Eleitoral)
                        </h2>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-bold">
                          TSE DivulgaCand
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">
                        Prestação de contas oficial da campanha de {dossier.financiamento_campanha?.ano_eleicao ?? "ano não informado"} declarada à Justiça Eleitoral
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400">Total Arrecadado:</span>
                    <span className="text-base font-black font-mono text-emerald-400 px-3 py-1 rounded-xl bg-emerald-500/10 border border-emerald-500/30">
                      {fmtReais(dossier?.financiamento_campanha?.total_arrecadado)}
                    </span>
                  </div>
                </div>

                {/* Resumo de KPIs do Financiamento */}
                <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 pt-2">
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[10px] text-slate-400 font-medium block mb-1">Receita Total de Campanha</span>
                    <span className="text-lg font-black font-mono text-emerald-400 block">
                      {fmtReais(dossier?.financiamento_campanha?.total_arrecadado)}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block">Ano Eleitoral: {dossier.financiamento_campanha?.ano_eleicao ?? "ano não informado"}</span>
                    {outrasEleicoes.length > 0 ? (
                      <span className="text-[10px] text-slate-400 mt-1 block" data-testid="outras-eleicoes">
                        Resumo da eleição mais recente; também há doações registradas de {outrasEleicoes.join(", ")}.
                      </span>
                    ) : null}
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[10px] text-slate-400 font-medium block mb-1">Total de Doadores</span>
                    <span className="text-lg font-black font-mono text-cyan-400 block">
                      {dossier?.financiamento_campanha?.total_doadores ?? "n/d"}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block">Pessoas e empresas distintas na prestação de contas</span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[10px] text-slate-400 font-medium block mb-1">Maior Doador Individual</span>
                    <span className="text-lg font-black font-mono text-amber-400 block">
                      {dossier?.financiamento_campanha?.top_doadores?.[0]?.percentual || 0}%
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block truncate">
                      {dossier?.financiamento_campanha?.top_doadores?.[0]?.nome_doador || "Sem registros"}
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[10px] text-slate-400 font-medium block mb-1">Ticket Médio por Doador</span>
                    <span className="text-lg font-black font-mono text-purple-400 block">
                      {ticketMedio === null ? "n/d" : `R$ ${ticketMedio.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block">Valor médio por doador</span>
                  </div>
                </div>
              </div>

              {/* Seção dos Top 5 Doadores */}
              <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <Award className="w-4 h-4 text-emerald-400" aria-hidden="true" />
                    <h3 className="text-sm font-bold text-slate-100">
                      Top 5 Maiores Financiadores da Campanha
                    </h3>
                  </div>
                  <span className="text-xs text-slate-400 font-mono">
                    Concentração de recursos
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                  {(dossier?.financiamento_campanha?.top_doadores || []).slice(0, 5).map((d, idx) => (
                    <div
                      key={`${d.nome_doador}-${d.cpf_cnpj_doador}`}
                      className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-2 hover:border-slate-700 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="w-6 h-6 rounded-lg bg-emerald-500/15 text-emerald-400 font-mono font-bold text-xs flex items-center justify-center shrink-0 border border-emerald-500/30">
                            #{idx + 1}
                          </span>
                          <div>
                            <h4 className="text-xs font-bold text-slate-200 leading-snug">
                              {d.nome_doador}
                            </h4>
                            <span className="text-[10px] text-slate-400 font-mono">
                              Doc: {formatCpfCnpj(d.cpf_cnpj_doador)}
                            </span>
                          </div>
                        </div>

                        <div className="text-right shrink-0">
                          <span className="text-xs font-mono font-black text-emerald-400 block">
                            R$ {d.valor_doado.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                          </span>
                          <span className="text-[10px] font-mono text-slate-400">
                            {d.percentual}% da campanha
                          </span>
                        </div>
                      </div>

                      <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden">
                        <div
                          className="bg-gradient-to-r from-emerald-500 to-teal-400 h-full rounded-full transition-all duration-500"
                          style={{ width: `${Math.min(100, Math.max(3, d.percentual))}%` }}
                        />
                      </div>

                      {d.tipo_receita && (
                        <div className="text-[10px] font-mono text-slate-400 flex items-center gap-1.5 pt-0.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          <span>Tipo de Receita: {d.tipo_receita}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {campanha.demais_doadores && (
                  <p className="text-xs text-slate-400" data-testid="demais-doadores">
                    {campanha.demais_doadores.quantidade === null
                      ? "Os demais doadores"
                      : `Outros ${campanha.demais_doadores.quantidade} doadores`}{" "}
                    somam R$ {campanha.demais_doadores.valor.toLocaleString("pt-BR", { minimumFractionDigits: 2 })} e a fonte
                    não os lista um a um.
                  </p>
                )}
              </div>

              {/* Tabela de Todas as Doações Declaradas */}
              <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-3">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-cyan-400" aria-hidden="true" />
                    <h3 className="text-sm font-bold text-slate-100">
                      Relação de Doações Declaradas
                    </h3>
                  </div>

                  <div className="relative w-full sm:w-72">
                    <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" aria-hidden="true" />
                    <input
                      type="text"
                      value={doacaoSearch}
                      onChange={(e) => setDoacaoSearch(e.target.value)}
                      placeholder="Filtrar por nome ou CPF/CNPJ..."
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-400 focus:outline-none focus:border-emerald-500/50"
                    />
                  </div>
                </div>

                {(() => {
                  const doacoesExibidas = (dossier?.financiamento_campanha?.todas_doacoes || []).filter((d) => {
                    if (!doacaoSearch.trim()) return true;
                    const term = doacaoSearch.toLowerCase();
                    return (
                      d.nome_doador.toLowerCase().includes(term) ||
                      (d.cpf_cnpj_doador && d.cpf_cnpj_doador.includes(term)) ||
                      (d.tipo_receita && d.tipo_receita.toLowerCase().includes(term))
                    );
                  });

                  if (doacoesExibidas.length === 0) {
                    return (
                      <p className="text-xs text-slate-400 py-6 text-center">
                        Nenhuma doação encontrada para o termo pesquisado.
                      </p>
                    );
                  }

                  return (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="border-b border-slate-800 text-slate-400 text-[11px] font-mono uppercase">
                            <th className="py-2.5 px-3">Nome do Doador</th>
                            <th className="py-2.5 px-3">CPF / CNPJ</th>
                            <th className="py-2.5 px-3">Tipo de Receita</th>
                            <th className="py-2.5 px-3 text-right">Valor Doado</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 font-mono">
                          {doacoesExibidas.map((d, idx) => (
                            <tr key={d.id || idx} className="hover:bg-slate-900/60 transition-colors">
                              <td className="py-2.5 px-3 text-slate-200 font-sans font-medium">
                                {d.nome_doador}
                                {d.agregado && (
                                  <span className="block text-[10px] font-normal text-slate-400" data-testid="linha-agregada">
                                    {d.quantidade_doadores === null
                                      ? "Soma de vários doadores; a fonte não informa quantos"
                                      : `Soma de ${d.quantidade_doadores} doadores que a fonte não lista um a um`}
                                  </span>
                                )}
                              </td>
                              <td className="py-2.5 px-3 text-slate-400 text-[11px]">
                                {d.agregado ? "—" : formatCpfCnpj(d.cpf_cnpj_doador)}
                              </td>
                              <td className="py-2.5 px-3 text-slate-400 text-[11px]">
                                {d.tipo_receita || "Recurso Financeiro"}
                              </td>
                              <td className="py-2.5 px-3 text-right font-black text-emerald-400">
                                R$ {d.valor_doado.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  );
                })()}
              </div>
            </div>
  );
}
