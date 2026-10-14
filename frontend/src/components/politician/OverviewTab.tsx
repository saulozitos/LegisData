"use client";

import React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
  Pie,
  PieChart as RechartsPieChart,
} from "recharts";
import {
  Building,
  Building2,
  FileText,
  Award,
  TrendingUp,
  MapPin,
  Sparkles,
  ArrowRight,
  ExternalLink,
  Mail,
  Phone,
  Coins,
  PieChart as LucidePieChart,
} from "lucide-react";
import type { PoliticoDossier } from "@/services/api";
import { fmtNum } from "@/lib/format";
import PartyLink from "@/components/PartyLink";
import { safeExternalUrl } from "@/lib/safeUrl";
import { formatCpfCnpj, gradeBadgeClass, riskBadgeClass, compatBadgeClass, orUnavailable } from "./format";
import type { DossierTab } from "./types";

interface OverviewTabProps {
  dossier: PoliticoDossier;
  onChangeTab: (tab: DossierTab) => void;
  onSelectParty?: (sigla: string) => void;
}

export default function OverviewTab({ dossier, onChangeTab, onSelectParty }: OverviewTabProps) {
  const perfil = dossier.perfil;
  const indices = dossier.indices_inteligencia;
  return (
            <div className="space-y-6">
              {/* CARD RESUMO DE INTELIGÊNCIA CÍVICA */}
              {indices && (
                <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-cyan-950/20 border border-cyan-500/30 rounded-2xl p-5 backdrop-blur-md shadow-xl space-y-4">
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 pb-3 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <span className="p-1.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                        <Sparkles className="w-4 h-4" aria-hidden="true" />
                      </span>
                      <div>
                        <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                          Painel de Inteligência Cívica & Algoritmos de Transparência
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                            5 Métricas Auditadas
                          </span>
                        </h3>
                        <p className="text-xs text-slate-400">
                          Cruzamento automatizado de dados: custos operacionais, concentração de fornecedores, patrimônio e eficiência
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => onChangeTab("inteligencia")}
                      className="inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 px-3 py-1.5 rounded-xl transition-all cursor-pointer"
                    >
                      <span>Auditoria Completa</span>
                      <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
                    </button>
                  </div>

                  {/* Grid das 5 Métricas */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                    {/* 1. ROI do Cidadão */}
                    <button
                      type="button"
                      onClick={() => onChangeTab("inteligencia")}
                      className="bg-slate-950/70 border border-slate-800 hover:border-cyan-500/40 rounded-xl p-3 space-y-2 cursor-pointer transition-all group text-left w-full"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-semibold text-slate-400">ROI do Cidadão</span>
                        <span className={`text-[11px] font-black font-mono px-2 py-0.5 rounded ${gradeBadgeClass(indices.roi_cidadao.score)}`}>
                          {indices.roi_cidadao.score ? `Nota ${indices.roi_cidadao.score}` : "Nota indisponível"}
                        </span>
                      </div>
                      <div className="text-xs font-mono font-bold text-slate-200">
                        {indices.roi_cidadao.projetos_estruturantes} projetos de impacto
                      </div>
                      <p className="text-[10px] text-slate-400 line-clamp-2">
                        {indices.roi_cidadao.diagnostico}
                      </p>
                    </button>

                    {/* 2. Concentração CEAP */}
                    <button
                      type="button"
                      onClick={() => onChangeTab("inteligencia")}
                      className="bg-slate-950/70 border border-slate-800 hover:border-cyan-500/40 rounded-xl p-3 space-y-2 cursor-pointer transition-all group text-left w-full"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-semibold text-slate-400">Cota CEAP (HHI)</span>
                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${riskBadgeClass(indices.concentracao_ceap.nivel_risco)}`}>
                          {orUnavailable(indices.concentracao_ceap.nivel_risco)}
                        </span>
                      </div>
                      <div className="text-xs font-mono font-bold text-slate-200">
                        HHI: {fmtNum(indices.concentracao_ceap.indice_hhi, 0)} ({fmtNum(indices.concentracao_ceap.percentual_maior_fornecedor, 1)}% top)
                      </div>
                      <p className="text-[10px] text-slate-400 line-clamp-2">
                        {indices.concentracao_ceap.diagnostico}
                      </p>
                    </button>

                    {/* 3. Patrimônio vs Renda */}
                    <button
                      type="button"
                      onClick={() => onChangeTab("inteligencia")}
                      className="bg-slate-950/70 border border-slate-800 hover:border-cyan-500/40 rounded-xl p-3 space-y-2 cursor-pointer transition-all group text-left w-full"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-semibold text-slate-400">Patrimônio x Renda</span>
                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${compatBadgeClass(indices.enriquecimento_patrimonial.compatibilidade)}`}>
                          {orUnavailable(indices.enriquecimento_patrimonial.compatibilidade)}
                        </span>
                      </div>
                      <div className="text-xs font-mono font-bold text-slate-200">
                        Razão: {fmtNum(indices.enriquecimento_patrimonial.razao_patrimonio_renda, 1)}x renda
                      </div>
                      <p className="text-[10px] text-slate-400 line-clamp-2">
                        {indices.enriquecimento_patrimonial.diagnostico}
                      </p>
                    </button>

                    {/* 4. Fidelidade Partidária */}
                    <button
                      type="button"
                      onClick={() => onChangeTab("inteligencia")}
                      className="bg-slate-950/70 border border-slate-800 hover:border-cyan-500/40 rounded-xl p-3 space-y-2 cursor-pointer transition-all group text-left w-full"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-semibold text-slate-400">Fidelidade</span>
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-400 border border-purple-500/30">
                          {orUnavailable(indices.estabilidade_partidaria.classificacao)}
                        </span>
                      </div>
                      <div className="text-xs font-mono font-bold text-slate-200">
                        {indices.estabilidade_partidaria.total_trocas} trocas • {fmtNum(indices.estabilidade_partidaria.anos_medio_por_partido, 1)}a/sigla
                      </div>
                      <p className="text-[10px] text-slate-400 line-clamp-2">
                        Governismo: {fmtNum(indices.estabilidade_partidaria.taxa_governismo_pct, 0)}%
                      </p>
                    </button>

                    {/* 5. Eficiência de Emendas */}
                    <button
                      type="button"
                      onClick={() => onChangeTab("inteligencia")}
                      className="bg-slate-950/70 border border-slate-800 hover:border-cyan-500/40 rounded-xl p-3 space-y-2 cursor-pointer transition-all group text-left w-full"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-semibold text-slate-400">Emendas</span>
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                          {fmtNum(indices.eficiencia_emendas.taxa_conversao_pct, 0)}% pagas
                        </span>
                      </div>
                      <div className="text-xs font-mono font-bold text-slate-200">
                        Quota PIX: {fmtNum(indices.eficiencia_emendas.percentual_pix, 0)}%
                      </div>
                      <p className="text-[10px] text-slate-400 line-clamp-2">
                        Foco: {indices.eficiencia_emendas.municipio_predileto || "Distribuído"}
                      </p>
                    </button>
                  </div>
                </div>
              )}

              {/* CARD DE CONTATO E GABINETE PARLAMENTAR */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 backdrop-blur-md shadow-lg">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <span className="p-1.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                      <Building2 className="w-4 h-4" aria-hidden="true" />
                    </span>
                    <h3 className="text-sm font-bold text-slate-100">
                      Contato Oficial & Gabinete Parlamentar
                    </h3>
                  </div>
                  <span className="text-[11px] font-mono text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-2.5 py-1 rounded-full">
                    {perfil?.cargo_atual === "SENADOR" ? "Senado Federal" : "Câmara dos Deputados"} • Brasília/DF
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 pt-4">
                  {/* E-mail Oficial */}
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3.5 flex flex-col justify-between space-y-2">
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      <Mail className="w-4 h-4 text-cyan-400" aria-hidden="true" />
                      <span className="font-semibold text-slate-300">E-mail Institucional</span>
                    </div>
                    <div className="text-xs font-mono text-cyan-300 break-all select-all font-semibold">
                      {perfil?.email ?? "Dado indisponível"}
                    </div>
                    {perfil?.email && (
                      <a
                        href={`mailto:${perfil.email}`}
                        className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 transition-colors pt-1"
                      >
                        <span>Enviar mensagem</span>
                        <ExternalLink className="w-3 h-3" aria-hidden="true" />
                      </a>
                    )}
                  </div>

                  {/* Sala do Gabinete */}
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3.5 flex flex-col justify-between space-y-2">
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      <MapPin className="w-4 h-4 text-emerald-400" aria-hidden="true" />
                      <span className="font-semibold text-slate-300">Gabinete / Localização</span>
                    </div>
                    <div className="text-xs font-semibold text-slate-100">
                      {perfil?.gabinete_sala ?? "Dado indisponível"}
                    </div>
                    <span className="text-[11px] text-slate-400">
                      Atendimento e protocolo presencial
                    </span>
                  </div>

                  {/* Telefone do Gabinete */}
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3.5 flex flex-col justify-between space-y-2">
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      <Phone className="w-4 h-4 text-amber-400" aria-hidden="true" />
                      <span className="font-semibold text-slate-300">Telefone Oficial</span>
                    </div>
                    <div className="text-xs font-mono font-bold text-amber-300">
                      {perfil?.gabinete_telefone ?? "Dado indisponível"}
                    </div>
                    {perfil?.gabinete_telefone && (
                      <a
                        href={`tel:${perfil.gabinete_telefone.replace(/\D/g, "")}`}
                        className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-amber-400 hover:text-amber-300 transition-colors pt-1"
                      >
                        <span>Ligar para o gabinete</span>
                        <ExternalLink className="w-3 h-3" aria-hidden="true" />
                      </a>
                    )}
                  </div>
                </div>
              </div>

              {/* CARD DE EVOLUÇÃO PATRIMONIAL DECLARADA (TSE DIVULGACAND) */}
              {dossier.evolucao_patrimonial?.resumo?.possui_dados && (
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 backdrop-blur-md shadow-lg space-y-5">
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                    <div className="flex items-center gap-2.5">
                      <span className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                        <TrendingUp className="w-5 h-5" aria-hidden="true" />
                      </span>
                      <div>
                        <h3 className="text-sm sm:text-base font-bold text-slate-100 flex items-center gap-2">
                          Evolução Patrimonial Declarada
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                            TSE DivulgaCand
                          </span>
                        </h3>
                        <p className="text-xs text-slate-400">
                          Histórico oficial de bens declarados à Justiça Eleitoral em eleições disputadas
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-400">
                        Crescimento Total:
                      </span>
                      <span className={`text-xs font-mono font-bold px-2.5 py-1 rounded-full border ${
                        dossier.evolucao_patrimonial.resumo.crescimento_pct >= 0
                          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                          : "bg-rose-500/10 text-rose-400 border-rose-500/30"
                      }`}>
                        {dossier.evolucao_patrimonial.resumo.crescimento_pct >= 0 ? "+" : ""}
                        {fmtNum(dossier.evolucao_patrimonial.resumo.crescimento_pct, 1)}%
                      </span>
                    </div>
                  </div>

                  {/* Métricas Resumidas em Destaque */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-1">
                      <div className="text-[11px] font-semibold text-slate-400">
                        Primeira Declaração ({dossier.evolucao_patrimonial.resumo.primeiro_ano})
                      </div>
                      <div className="text-base font-black font-mono text-slate-200">
                        {dossier.evolucao_patrimonial.resumo.primeiro_valor_formatado}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        Registro eleitoral inicial documentado
                      </div>
                    </div>

                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-1">
                      <div className="text-[11px] font-semibold text-slate-400">
                        Última Declaração ({dossier.evolucao_patrimonial.resumo.ultimo_ano})
                      </div>
                      <div className="text-base font-black font-mono text-emerald-400">
                        {dossier.evolucao_patrimonial.resumo.ultimo_valor_formatado}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        Valor atualizado informado ao TSE
                      </div>
                    </div>

                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-1">
                      <div className="text-[11px] font-semibold text-slate-400">
                        Variação Absoluta
                      </div>
                      <div className={`text-base font-black font-mono ${
                        dossier.evolucao_patrimonial.resumo.crescimento_absoluto >= 0 ? "text-cyan-400" : "text-rose-400"
                      }`}>
                        {dossier.evolucao_patrimonial.resumo.crescimento_absoluto >= 0 ? "+" : ""}
                        {new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(
                          dossier.evolucao_patrimonial.resumo.crescimento_absoluto
                        )}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        {dossier.evolucao_patrimonial.resumo.total_declaracoes} ciclos eleitorais analisados
                      </div>
                    </div>
                  </div>

                  {/* Gráfico Recharts de Barras */}
                  <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-4 space-y-2">
                    <div className="flex items-center justify-between text-xs text-slate-400 px-1 pb-2">
                      <span className="font-semibold text-slate-300">Gráfico de Patrimônio Declarado por Ano Eleitoral</span>
                      <span className="text-[11px] font-mono text-slate-400">Valores em R$ nominais</span>
                    </div>
                    <div className="h-56 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={dossier.evolucao_patrimonial.historico}
                          margin={{ top: 10, right: 10, left: 10, bottom: 5 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                          <XAxis
                            dataKey="ano"
                            stroke="#64748b"
                            fontSize={11}
                            tickLine={false}
                            axisLine={{ stroke: "#334155" }}
                          />
                          <YAxis
                            stroke="#64748b"
                            fontSize={10}
                            tickLine={false}
                            axisLine={{ stroke: "#334155" }}
                            tickFormatter={(val) => {
                              if (val >= 1000000) return `R$ ${fmtNum(val / 1000000, 1)}M`;
                              if (val >= 1000) return `R$ ${fmtNum(val / 1000, 0)}k`;
                              return `R$ ${val}`;
                            }}
                          />
                          <Tooltip
                            content={({ active, payload }) => {
                              if (active && payload && payload.length) {
                                const data = payload[0].payload as PoliticoDossier["evolucao_patrimonial"] extends infer E ? (E extends { historico: Array<infer H> } ? H : never) : never;
                                return (
                                  <div className="bg-slate-900 border border-slate-700 p-3 rounded-xl shadow-2xl text-xs space-y-1 max-w-xs">
                                    <div className="font-bold text-cyan-300">Eleição {data.ano}</div>
                                    <div className="text-emerald-400 font-mono font-bold text-sm">
                                      {data.valor_formatado}
                                    </div>
                                    <div className="text-slate-400 text-[11px] pt-1 border-t border-slate-800 leading-snug">
                                      {data.detalhes}
                                    </div>
                                  </div>
                                );
                              }
                              return null;
                            }}
                          />
                          <Bar dataKey="valor" radius={[6, 6, 0, 0]}>
                            {dossier.evolucao_patrimonial.historico.map((entry, index) => (
                              <Cell
                                key={`cell-${entry.ano}`}
                                fill={index === dossier.evolucao_patrimonial!.historico.length - 1 ? "#10b981" : "#06b6d4"}
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  {/* Histórico Discriminado das Eleições */}
                  <div className="space-y-2">
                    <div className="text-xs font-bold text-slate-300 flex items-center gap-1.5 px-1">
                      <FileText className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" />
                      Detalhamento dos Bens Informados ao TSE
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                      {dossier.evolucao_patrimonial.historico.map((item) => (
                        <div
                          key={item.ano}
                          className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3 flex flex-col justify-between space-y-1.5"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                              Eleição {item.ano}
                            </span>
                            <span className="text-xs font-mono font-extrabold text-emerald-400">
                              {item.valor_formatado}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400 leading-snug">
                            {item.detalhes}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Linha do Tempo dos Mandatos */}
              <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div className="flex items-center gap-2 pb-2 border-b border-slate-800">
                  <Award className="w-4 h-4 text-cyan-400" aria-hidden="true" />
                  <h3 className="text-sm font-bold text-slate-100">
                    Trajetória de Mandatos Eletivos
                  </h3>
                </div>

                <div className="space-y-3">
                  {dossier.trajetoria_mandatos.map((m) => (
                    <div
                      key={m.id}
                      className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 flex items-start justify-between gap-3"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-slate-100">
                            {m.cargo.replace(/_/g, " ")}
                          </span>
                          <PartyLink sigla={m.partido_sigla} onSelectParty={onSelectParty} className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 hover:border-cyan-400" />
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                            {m.uf}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400">
                          Eleição {m.ano_eleicao} • Mandato nº {m.numero_mandato} ({m.esfera})
                        </p>
                        {m.coligacao && (
                          <p className="text-[11px] text-slate-400">
                            Coligação: {m.coligacao}
                          </p>
                        )}
                      </div>

                      <span className="text-[10px] font-bold px-2 py-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        {m.status.replace(/_/g, " ")}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Histórico Completo de Partidos (TSE) */}
              <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <Building className="w-4 h-4 text-amber-400" aria-hidden="true" />
                    <h3 className="text-sm font-bold text-slate-100">
                      Histórico Partidário (TSE)
                    </h3>
                  </div>
                  <span className="text-xs text-slate-400">
                    Total: <strong className="text-amber-400">{dossier.filiacoes_partidarias.length}</strong> legendas
                  </span>
                </div>

                <div className="space-y-2.5">
                  {dossier.filiacoes_partidarias.map((f) => (
                    <div
                      key={f.id}
                      className="bg-slate-950/70 border border-slate-800 rounded-xl p-3 flex items-center justify-between gap-3"
                    >
                      <div className="flex items-center gap-3">
                        <PartyLink sigla={f.partido_sigla} onSelectParty={onSelectParty} className="text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-slate-900 text-cyan-400 border border-slate-800 hover:border-cyan-400" />
                        <div>
                          <h4 className="text-xs font-bold text-slate-200">
                            {f.partido_nome}
                          </h4>
                          <span className="text-[11px] text-slate-400">
                            Filiado em {f.data_filiacao || "Data não registrada"}
                            {f.data_desfiliacao && ` até ${f.data_desfiliacao}`}
                          </span>
                        </div>
                      </div>

                      {f.is_atual ? (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          Atual
                        </span>
                      ) : (
                        <span className="text-[10px] text-slate-400">
                          {f.motivo_desfiliacao?.replace(/_/g, " ") || "Desfiliação"}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* CARD: QUEM PAGA A CONTA? (FINANCIAMENTO DE CAMPANHA) */}
              <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-emerald-950/20 border border-emerald-500/30 rounded-2xl p-5 space-y-4 lg:col-span-2 shadow-lg">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
                  <div className="flex items-center gap-2.5">
                    <span className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                      <Coins className="w-5 h-5" aria-hidden="true" />
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wide">
                          Quem Paga a Conta? (Financiadores de Campanha)
                        </h3>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-bold">
                          TSE DivulgaCand
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">
                        Top doadores e recursos arrecadados na última campanha eleitoral ({dossier.financiamento_campanha?.ano_eleicao ?? "ano não informado"})
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => onChangeTab("financiamento")}
                    className="inline-flex items-center gap-1.5 text-xs font-bold text-emerald-400 hover:text-emerald-300 transition-colors bg-emerald-500/10 border border-emerald-500/25 px-3 py-1.5 rounded-xl hover:bg-emerald-500/20 self-start sm:self-auto"
                  >
                    <span>Ver Todas as Doações</span>
                    <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
                  </button>
                </div>

                {/* Métricas do Financiamento */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[10px] font-medium text-slate-400 block mb-1">
                      Total Arrecadado na Campanha
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-emerald-400 block leading-tight">
                      R$ {(dossier?.financiamento_campanha?.total_arrecadado || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      Receita total declarada à Justiça Eleitoral
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[10px] font-medium text-slate-400 block mb-1">
                      Total de Doadores Registrados
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-cyan-400 block leading-tight">
                      {dossier?.financiamento_campanha?.total_doadores || 0} doações
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      Partidos, pessoas físicas e recursos próprios
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[10px] font-medium text-slate-400 block mb-1">
                      Maior Doador Individual
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-amber-400 block leading-tight">
                      {dossier?.financiamento_campanha?.top_doadores?.[0]?.percentual || 0}%
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block truncate">
                      {dossier?.financiamento_campanha?.top_doadores?.[0]?.nome_doador || "Sem registros"}
                    </span>
                  </div>
                </div>

                {/* Lista / Gráfico dos Top 5 Maiores Doadores */}
                <div className="space-y-2.5 pt-1">
                  <div className="text-xs font-bold text-slate-300 flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <Award className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />
                      Top 5 Maiores Doadores da Eleição
                    </span>
                    <span className="text-[11px] text-slate-400 font-mono">
                      Concentração de receita eleitoral
                    </span>
                  </div>

                  {(!dossier?.financiamento_campanha?.top_doadores || dossier.financiamento_campanha.top_doadores.length === 0) ? (
                    <p className="text-xs text-slate-400 py-3 text-center">
                      Nenhum registro de doação eleitoral localizado nesta base de dados do TSE.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {dossier.financiamento_campanha.top_doadores.slice(0, 5).map((doador, idx) => (
                        <div
                          key={`${doador.nome_doador}-${doador.cpf_cnpj_doador}`}
                          className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3 hover:border-slate-700 transition-colors space-y-1.5"
                        >
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                            <div className="flex items-center gap-2">
                              <span className="w-5 h-5 rounded-full bg-emerald-500/15 text-emerald-400 font-mono font-bold text-xs flex items-center justify-center shrink-0 border border-emerald-500/30">
                                #{idx + 1}
                              </span>
                              <div>
                                <span className="text-xs font-bold text-slate-200 block">
                                  {doador.nome_doador}
                                </span>
                                <div className="flex items-center gap-2 text-[10px] text-slate-400 font-mono">
                                  <span>Doc: {formatCpfCnpj(doador.cpf_cnpj_doador)}</span>
                                  {doador.tipo_receita && (
                                    <>
                                      <span>•</span>
                                      <span className="text-emerald-400/90">{doador.tipo_receita}</span>
                                    </>
                                  )}
                                </div>
                              </div>
                            </div>

                            <div className="text-left sm:text-right shrink-0">
                              <span className="text-xs font-mono font-black text-emerald-400 block">
                                R$ {doador.valor_doado.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                              </span>
                              <span className="text-[10px] font-mono text-slate-400">
                                {doador.percentual}% do total
                              </span>
                            </div>
                          </div>

                          {/* Barra de Proporção Visual */}
                          <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-gradient-to-r from-emerald-500 to-teal-400 h-full rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(100, Math.max(2, doador.percentual))}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* PAINEL: DETECTOR DE LEIS INÚTEIS (TAXA DE RELEVÂNCIA LEGISLATIVA) */}
              <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-purple-950/20 border border-purple-500/30 rounded-2xl p-5 space-y-4 lg:col-span-2 shadow-lg">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
                  <div className="flex items-center gap-2.5">
                    <span className="p-2 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
                      <LucidePieChart className="w-5 h-5" />
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wide">
                          Detector de Leis Inúteis (Taxa de Relevância)
                        </h3>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20 font-bold">
                          Arsenal Antidesinformação
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">
                        Classificação semântica de ementas: Projetos Estruturais vs Homenagens Simbólicas
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => onChangeTab("proposicoes")}
                    className="inline-flex items-center gap-1.5 text-xs font-bold text-purple-400 hover:text-purple-300 transition-colors bg-purple-500/10 border border-purple-500/25 px-3 py-1.5 rounded-xl hover:bg-purple-500/20 self-start sm:self-auto"
                  >
                    <span>Painel Completo de Leis</span>
                    <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
                  </button>
                </div>

                {/* Gráfico de Pizza + Métricas de Relevância */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
                  {/* Gráfico de Pizza (Recharts PieChart) */}
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3 flex flex-col items-center justify-center">
                    <span className="text-[11px] font-bold text-slate-300 mb-1">
                      Projetos de Impacto vs Simbólicos
                    </span>
                    <div className="w-full h-44">
                      <ResponsiveContainer width="100%" height="100%">
                        <RechartsPieChart>
                          <Pie
                            data={[
                              {
                                name: "Projetos de Impacto",
                                value: dossier?.relevancia_legislativa?.projetos_impacto || 0,
                                color: "#10b981",
                                pct: dossier?.relevancia_legislativa?.percentual_impacto || 0,
                              },
                              {
                                name: "Projetos Simbólicos",
                                value: dossier?.relevancia_legislativa?.projetos_simbolicos || 0,
                                color: "#f59e0b",
                                pct: dossier?.relevancia_legislativa?.percentual_simbolico || 0,
                              },
                            ]}
                            dataKey="value"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            innerRadius={42}
                            outerRadius={68}
                            paddingAngle={3}
                          >
                            <Cell fill="#10b981" />
                            <Cell fill="#f59e0b" />
                          </Pie>
                          <Tooltip
                            content={({ active, payload }) => {
                              if (!active || !payload || !payload.length) return null;
                              const d = payload[0].payload;
                              return (
                                <div className="bg-slate-900 border border-slate-700 p-2 rounded-lg text-xs shadow-xl">
                                  <span className="font-bold text-slate-200 block">{d.name}</span>
                                  <span className="font-mono text-cyan-400 font-bold">{d.value} matérias ({d.pct}%)</span>
                                </div>
                              );
                            }}
                          />
                        </RechartsPieChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="flex items-center gap-3 text-[11px] font-mono pt-1">
                      <span className="flex items-center gap-1 text-emerald-400">
                        <span className="w-2 h-2 rounded-full bg-emerald-400" />
                        Impacto ({dossier?.relevancia_legislativa?.percentual_impacto || 0}%)
                      </span>
                      <span className="flex items-center gap-1 text-amber-400">
                        <span className="w-2 h-2 rounded-full bg-amber-400" />
                        Simbólico ({dossier?.relevancia_legislativa?.percentual_simbolico || 0}%)
                      </span>
                    </div>
                  </div>

                  {/* Diagnóstico e Estatísticas */}
                  <div className="md:col-span-2 space-y-3">
                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-medium text-slate-400">Diagnóstico de Produtividade</span>
                        <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
                          (dossier?.relevancia_legislativa?.percentual_impacto || 0) >= 60
                            ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                            : "bg-amber-500/10 text-amber-300 border-amber-500/30"
                        }`}>
                          {dossier?.relevancia_legislativa?.diagnostico || "Em análise"}
                        </span>
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed">
                        De um total de <strong className="text-cyan-400">{dossier?.relevancia_legislativa?.total_proposicoes || 0} proposições</strong> analisadas,{" "}
                        <strong className="text-emerald-400">{dossier?.relevancia_legislativa?.projetos_impacto || 0} ({dossier?.relevancia_legislativa?.percentual_impacto || 0}%)</strong> versam sobre matérias substanciais (Economia, Saúde, Código Penal, Educação) e{" "}
                        <strong className="text-amber-400">{dossier?.relevancia_legislativa?.projetos_simbolicos || 0} ({dossier?.relevancia_legislativa?.percentual_simbolico || 0}%)</strong> são projetos simbólicos (Dias Nacionais, Homenagens e Denominações).
                      </p>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                      <div className="bg-slate-950/70 border border-amber-500/20 rounded-xl p-2.5">
                        <span className="text-[10px] text-amber-300 font-medium block">Liderança (Autor)</span>
                        <span className="text-base font-black font-mono text-white block">
                          {dossier?.relevancia_legislativa?.lideranca_legislativa_count ?? dossier?.relevancia_legislativa?.total_proposicoes ?? 0}
                        </span>
                        <span className="text-[10px] text-slate-400 block">Autor principal (1.0 pt)</span>
                      </div>
                      <div className="bg-slate-950/70 border border-indigo-500/20 rounded-xl p-2.5">
                        <span className="text-[10px] text-indigo-300 font-medium block">Apoio Político</span>
                        <span className="text-base font-black font-mono text-white block">
                          {dossier?.relevancia_legislativa?.apoio_politico_count ?? 0}
                        </span>
                        <span className="text-[10px] text-slate-400 block">Coautor / quórum (0.2 pt)</span>
                      </div>
                      <div className="bg-slate-950/70 border border-emerald-500/20 rounded-xl p-2.5">
                        <span className="text-[10px] text-emerald-400 font-medium block">Matérias Impacto</span>
                        <span className="text-base font-black font-mono text-emerald-400 block">
                          {dossier?.relevancia_legislativa?.projetos_impacto || 0}
                        </span>
                        <span className="text-[10px] text-slate-400 block">Economia, Saúde, Leis</span>
                      </div>
                      <div className="bg-slate-950/70 border border-amber-500/20 rounded-xl p-2.5">
                        <span className="text-[10px] text-amber-400 font-medium block">Simbólicos</span>
                        <span className="text-base font-black font-mono text-amber-400 block">
                          {dossier?.relevancia_legislativa?.projetos_simbolicos || 0}
                        </span>
                        <span className="text-[10px] text-slate-400 block">Homenagens e datas</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Amostra recente de matérias com badges */}
                <div className="space-y-2 pt-2">
                  <div className="text-xs font-bold text-slate-300 flex items-center justify-between">
                    <span>Amostra Recente de Proposições</span>
                    <button
                      type="button"
                      onClick={() => onChangeTab("proposicoes")}
                      className="text-[11px] font-mono text-purple-400 hover:underline flex items-center gap-1"
                    >
                      Ver todas as {dossier?.materias_propostas?.length || 0} matérias
                      <ArrowRight className="w-3 h-3" aria-hidden="true" />
                    </button>
                  </div>

                  {(!dossier?.materias_propostas || dossier.materias_propostas.length === 0) ? (
                    <p className="text-xs text-slate-400 py-3 text-center">
                      Nenhuma matéria de autoria individual registrada nesta base legislativa estrutural.
                    </p>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {dossier.materias_propostas.slice(0, 4).map((p) => {
                        const isImpacto = p.classificacao_relevancia === "IMPACTO";
                        return (
                          <div
                            key={p.id}
                            className="bg-slate-950/70 border border-slate-800 rounded-xl p-3 space-y-2"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20">
                                {p.tipo} {p.numero}/{p.ano}
                              </span>
                              <span
                                className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
                                  isImpacto
                                    ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                                    : "bg-amber-500/15 text-amber-300 border-amber-500/30"
                                }`}
                              >
                                {isImpacto ? "Impacto / Substancial" : "Simbólico / Homenagem"}
                              </span>
                            </div>

                            <div className="flex items-start justify-between gap-2">
                              <h4 className="text-xs font-bold text-slate-100 leading-snug line-clamp-1">
                                {p.titulo}
                              </h4>
                              {p.url_oficial && (
                                <a
                                  href={safeExternalUrl(p.url_oficial)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-[10px] font-semibold text-cyan-400 hover:text-cyan-300 transition-colors shrink-0 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded"
                                >
                                  <span>Íntegra</span>
                                  <ExternalLink className="w-2.5 h-2.5" aria-hidden="true" />
                                </a>
                              )}
                            </div>
                            <p className="text-xs text-slate-400 line-clamp-2">
                              {p.ementa}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>
            </div>
  );
}
