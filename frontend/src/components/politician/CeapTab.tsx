"use client";

import React from "react";
import {
  Building2,
  TrendingUp,
  ExternalLink,
  Receipt,
  FileCheck,
} from "lucide-react";
import type { PoliticoDossier } from "@/services/api";
import { safeExternalUrl } from "@/lib/safeUrl";
import { EmptyState } from "@/components/StateViews";
import { formatMoney } from "./format";

interface CeapTabProps {
  dossier: PoliticoDossier;
}

export default function CeapTab({ dossier }: CeapTabProps) {
  const remuneracao = dossier.remuneracao;
  // Sem dados de CEAP não se exibe "R$ 0,00": ausência de dado não é gasto zero.
  if (!dossier.custos_ceap?.possui_dados) {
    return (
      <EmptyState
        title="Custos da cota parlamentar indisponíveis"
        message="A base não possui despesas da CEAP registradas para este parlamentar."
      />
    );
  }
  return (
            <div className="space-y-6">
              {/* Header do Painel CEAP */}
              <div className="bg-slate-900/80 border border-amber-500/30 rounded-2xl p-5 sm:p-6 backdrop-blur-md shadow-lg space-y-5">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-2.5">
                    <span className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400">
                      <Receipt className="w-5 h-5" aria-hidden="true" />
                    </span>
                    <div>
                      <h3 className="text-base sm:text-lg font-bold text-slate-100 flex items-center gap-2">
                        Custos do Mandato &amp; Cota Parlamentar (CEAP)
                      </h3>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Cota para o Exercício da Atividade Parlamentar (gastos públicos de gabinete auditados)
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono text-amber-300 bg-amber-500/10 border border-amber-500/20 px-3 py-1 rounded-full font-bold">
                      Legislatura 2023–2026
                    </span>
                    <span className="text-[11px] font-mono text-slate-400 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800">
                      {dossier?.custos_ceap?.total_notas || 0} comprovantes fiscais
                    </span>
                  </div>
                </div>

                {/* 4 Cards de Resumo Executivo */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Gasto Total Auditado
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-amber-400 block leading-tight">
                      R$ {(dossier?.custos_ceap?.gasto_total_recente || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      Reembolsos oficiais na legislatura
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Média de Gasto Mensal
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-cyan-400 block leading-tight">
                      {formatMoney(remuneracao?.resumo?.media_ceap_mensal)}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      Média calculada por mês ativo
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Maior Categoria de Custo
                    </span>
                    <span className="text-xs sm:text-sm font-bold text-slate-200 block truncate leading-tight" title={dossier?.custos_ceap?.gastos_por_tipo?.[0]?.tipo_despesa || "Nenhum gasto"}>
                      {dossier?.custos_ceap?.gastos_por_tipo?.[0]?.tipo_despesa || "Sem lançamentos"}
                    </span>
                    <span className="text-[10px] font-mono text-amber-400/90 mt-1 block">
                      R$ {(dossier?.custos_ceap?.gastos_por_tipo?.[0]?.total_gasto || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Maior Fornecedor Único
                    </span>
                    <span className="text-xs sm:text-sm font-bold text-slate-200 block truncate leading-tight" title={dossier?.custos_ceap?.maiores_fornecedores?.[0]?.nome_fornecedor || "Nenhum"}>
                      {dossier?.custos_ceap?.maiores_fornecedores?.[0]?.nome_fornecedor || "Nenhum"}
                    </span>
                    <span className="text-[10px] font-mono text-emerald-400 mt-1 block">
                      R$ {(dossier?.custos_ceap?.maiores_fornecedores?.[0]?.total_recebido || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                </div>
              </div>

              {/* Grid 2 colunas: Gráfico/Barras por Tipo de Despesa + Mini-tabela Maiores Fornecedores */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Gastos por Tipo de Despesa (Barras de Distribuição) */}
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-amber-400" aria-hidden="true" />
                      <h4 className="text-sm font-bold text-slate-100">
                        Gastos por Tipo de Despesa
                      </h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      {dossier?.custos_ceap?.gastos_por_tipo?.length || 0} categorias
                    </span>
                  </div>

                  {(!dossier?.custos_ceap?.gastos_por_tipo || dossier.custos_ceap.gastos_por_tipo.length === 0) ? (
                    <p className="text-xs text-slate-400 py-6 text-center">
                      Nenhum registro de cota parlamentar detalhado encontrado para este período.
                    </p>
                  ) : (
                    <div className="space-y-3 pt-1">
                      {dossier.custos_ceap.gastos_por_tipo.map((g) => (
                        <div key={g.tipo_despesa} className="space-y-1">
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-slate-300 font-medium truncate max-w-[240px] sm:max-w-[320px]" title={g.tipo_despesa}>
                              {g.tipo_despesa}
                            </span>
                            <div className="flex items-center gap-2 shrink-0 font-mono">
                              <span className="text-amber-400 font-bold">
                                R$ {g.total_gasto.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                              </span>
                              <span className="text-slate-400 text-[11px] w-12 text-right">
                                {g.percentual}%
                              </span>
                            </div>
                          </div>
                          <div className="h-2 w-full bg-slate-950 rounded-full overflow-hidden border border-slate-800">
                            <div
                              className="h-full bg-gradient-to-r from-amber-500 to-amber-300 rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(100, Math.max(2, g.percentual))}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Mini-Tabela: Maiores Fornecedores */}
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <Building2 className="w-4 h-4 text-cyan-400" aria-hidden="true" />
                      <h4 className="text-sm font-bold text-slate-100">
                        Maiores Fornecedores &amp; Prestadores
                      </h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      Top 10 beneficiários
                    </span>
                  </div>

                  {(!dossier?.custos_ceap?.maiores_fornecedores || dossier.custos_ceap.maiores_fornecedores.length === 0) ? (
                    <p className="text-xs text-slate-400 py-6 text-center">
                      Nenhum fornecedor registrado.
                    </p>
                  ) : (
                    <div className="overflow-x-auto rounded-xl border border-slate-800/80 bg-slate-950/60 shadow-inner">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] font-bold border-b border-slate-800">
                          <tr>
                            <th className="py-2.5 px-3">Empresa / Fornecedor</th>
                            <th className="py-2.5 px-2 text-center whitespace-nowrap">Notas</th>
                            <th className="py-2.5 px-3 text-right whitespace-nowrap">Total Pago</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/50">
                          {dossier.custos_ceap.maiores_fornecedores.map((f) => (
                            <tr key={`${f.nome_fornecedor}-${f.cnpj_cpf}`} className="hover:bg-slate-900/80 transition-colors">
                              <td className="py-2.5 px-3">
                                <p className="font-semibold text-slate-200 line-clamp-1 max-w-[220px]" title={f.nome_fornecedor}>
                                  {f.nome_fornecedor}
                                </p>
                                {f.cnpj_cpf && (
                                  <p className="font-mono text-[10px] text-slate-400">
                                    CNPJ/CPF: {f.cnpj_cpf}
                                  </p>
                                )}
                              </td>
                              <td className="py-2.5 px-2 text-center font-mono text-slate-400">
                                <span className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px]">
                                  {f.num_notas}
                                </span>
                              </td>
                              <td className="py-2.5 px-3 text-right font-mono font-bold text-amber-400 whitespace-nowrap">
                                R$ {f.total_recebido.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>

              {/* Feed de Despesas e Notas Fiscais Recentes com Link Oficial */}
              {dossier?.custos_ceap?.despesas_recentes && dossier.custos_ceap.despesas_recentes.length > 0 && (
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <FileCheck className="w-4 h-4 text-emerald-400" aria-hidden="true" />
                      <h4 className="text-sm font-bold text-slate-100">
                        Últimos Comprovantes Fiscais Auditados
                      </h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      Exibindo últimas {dossier.custos_ceap.despesas_recentes.length} notas emitidas
                    </span>
                  </div>

                  <div className="overflow-x-auto rounded-xl border border-slate-800/80 bg-slate-950/60">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] font-bold border-b border-slate-800">
                        <tr>
                          <th className="py-2.5 px-3 whitespace-nowrap">Mês/Ano</th>
                          <th className="py-2.5 px-3">Rubrica / Tipo de Despesa</th>
                          <th className="py-2.5 px-3">Prestador / Fornecedor</th>
                          <th className="py-2.5 px-3 text-right whitespace-nowrap">Valor da Nota</th>
                          <th className="py-2.5 px-3 text-center whitespace-nowrap">Documento</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/50">
                        {dossier.custos_ceap.despesas_recentes.map((d) => (
                          <tr key={`${d.data_emissao}-${d.nome_fornecedor}-${d.valor_liquido}`} className="hover:bg-slate-900/80 transition-colors">
                            <td className="py-2.5 px-3 font-mono text-slate-300 whitespace-nowrap">
                              {d.mes ? String(d.mes).padStart(2, "0") : "--"}/{d.ano}
                            </td>
                            <td className="py-2.5 px-3 text-slate-300 font-medium">
                              {d.tipo_despesa}
                            </td>
                            <td className="py-2.5 px-3 text-slate-400">
                              <span className="line-clamp-1" title={d.nome_fornecedor}>
                                {d.nome_fornecedor}
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono font-bold text-cyan-400 whitespace-nowrap">
                              R$ {d.valor_liquido.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                            </td>
                            <td className="py-2.5 px-3 text-center whitespace-nowrap">
                              {d.documento_url ? (
                                <a
                                  href={safeExternalUrl(d.documento_url)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded-lg"
                                  title="Ver nota original no portal oficial"
                                >
                                  <span>NF-e</span>
                                  <ExternalLink className="w-3 h-3" aria-hidden="true" />
                                </a>
                              ) : (
                                <span className="text-[10px] text-slate-400">Registrado</span>
                              )}
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
