"use client";

import React from "react";
import {
  Users,
  CheckCircle,
  AlertTriangle,
  Landmark,
  TrendingUp,
  Sparkles,
  Receipt,
  Scale,
  Gauge,
} from "lucide-react";
import type { PoliticoDossier } from "@/services/api";
import { fmtNum, isNum } from "@/lib/format";
import { formatMoney, formatCpfCnpj, gradeBadgeClass, riskBadgeClass, compatBadgeClass, orUnavailable } from "./format";
import { EmptyState } from "@/components/StateViews";

interface IntelligenceTabProps {
  dossier: PoliticoDossier;
}

export default function IntelligenceTab({ dossier }: IntelligenceTabProps) {
  const indices = dossier.indices_inteligencia;
  if (!indices) return <EmptyState title="Inteligência cívica indisponível" />;
  return (
            <div className="space-y-6">
              {/* Header do Painel de Inteligência */}
              <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-cyan-950/30 border border-cyan-500/30 rounded-2xl p-5 sm:p-6 backdrop-blur-md shadow-xl space-y-4">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-3">
                    <span className="p-3 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 shadow-inner">
                      <Sparkles className="w-6 h-6" aria-hidden="true" />
                    </span>
                    <div>
                      <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                        Auditoria de Inteligência Cívica & Algoritmos de Transparência
                        <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                          Auditoria Automática
                        </span>
                      </h3>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Modelos matemáticos aplicados a dados públicos oficiais: CEAP, TSE, Siga Brasil e Diários Oficiais
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[11px] font-mono px-3 py-1 rounded-lg bg-slate-950 border border-slate-800 text-slate-400">
                      Câmara & Senado • TSE • Siga Brasil
                    </span>
                  </div>
                </div>

                <div className="text-xs text-slate-300 leading-relaxed bg-slate-950/60 border border-slate-800/80 rounded-xl p-3.5">
                  <p>
                    Esta auditoria aplica <strong>5 algoritmos independentes</strong> para mensurar a entrega legislativa em relação ao custo do gabinete, detectar concentrações anômalas de fornecedores de cota parlamentar (HHI), confrontar a evolução patrimonial declarada com a remuneração oficial acumulada e avaliar a coerência partidária e eficiência orçamentária do mandato.
                  </p>
                </div>
              </div>

              {/* CARD 1: RETORNO SOBRE O INVESTIMENTO PÚBLICO (ROI DO CIDADÃO) */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 backdrop-blur-md shadow-lg space-y-5">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-3">
                    <span className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                      <Gauge className="w-5 h-5" aria-hidden="true" />
                    </span>
                    <div>
                      <h4 className="text-base font-bold text-slate-100 flex items-center gap-2">
                        1. ROI do Cidadão (Retorno sobre Investimento Público)
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                          Custo-Benefício
                        </span>
                      </h4>
                      <p className="text-xs text-slate-400">
                        Relação entre os custos operacionais do mandato e a produção de leis de impacto estrutural
                      </p>
                    </div>
                  </div>

                  {/* Badge de Nota */}
                  <div className="flex items-center gap-3 bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2">
                    <div className="text-right">
                      <div className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Score Cívico</div>
                      <div className="text-xs text-slate-400">
                        {isNum(indices.roi_cidadao.nota) ? `${indices.roi_cidadao.nota}/100 pontos` : "Nota indisponível"}
                      </div>
                    </div>
                    <span className={`text-2xl font-black font-mono px-3 py-1 rounded-xl ${gradeBadgeClass(indices.roi_cidadao.score)}`}>
                      {indices.roi_cidadao.score ?? "—"}
                    </span>
                  </div>
                </div>

                {/* Grid dos Números do ROI */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                    <span className="text-[11px] font-semibold text-slate-400 block">
                      Custo Operacional Total
                    </span>
                    <span className="text-lg font-black font-mono text-slate-200 block">
                      {formatMoney(indices.roi_cidadao.custo_total_operacional)}
                    </span>
                    <span className="text-[10px] text-slate-400 block">
                      Soma de salários brutos + cota parlamentar (CEAP)
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                    <span className="text-[11px] font-semibold text-slate-400 block">
                      Matérias Estruturantes
                    </span>
                    <span className="text-lg font-black font-mono text-cyan-400 block">
                      {indices.roi_cidadao.projetos_estruturantes} proposições
                    </span>
                    <span className="text-[10px] text-slate-400 block">
                      PECs, PLs, PLPs e MPs de impacto nacional
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                    <span className="text-[11px] font-semibold text-slate-400 block">
                      Custo Médio por Matéria Relevante
                    </span>
                    <span className="text-lg font-black font-mono text-emerald-400 block">
                      {formatMoney(indices.roi_cidadao.custo_por_projeto_impacto)}
                    </span>
                    <span className="text-[10px] text-slate-400 block">
                      Custo total dividido pelas leis estruturantes
                    </span>
                  </div>
                </div>

                {/* Diagnóstico do Algoritmo */}
                <div className="bg-slate-950/80 border border-cyan-500/20 rounded-xl p-4 space-y-1.5">
                  <span className="text-xs font-bold text-cyan-400 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
                    Diagnóstico do Modelo:
                  </span>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {indices.roi_cidadao.diagnostico}
                  </p>
                </div>
              </div>

              {/* CARD 2: CONCENTRAÇÃO DE FORNECEDORES DA CEAP (ÍNDICE HHI) */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 backdrop-blur-md shadow-lg space-y-5">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-3">
                    <span className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400">
                      <Receipt className="w-5 h-5" aria-hidden="true" />
                    </span>
                    <div>
                      <h4 className="text-base font-bold text-slate-100 flex items-center gap-2">
                        2. Concentração de Fornecedores da Cota (Índice HHI)
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${riskBadgeClass(indices.concentracao_ceap.nivel_risco)}`}>
                          {indices.concentracao_ceap.nivel_risco ? `Risco ${indices.concentracao_ceap.nivel_risco}` : "Risco indisponível"}
                        </span>
                      </h4>
                      <p className="text-xs text-slate-400">
                        Índice Herfindahl-Hirschman (HHI) para detectar monopólios ou dependência excessiva de empresas
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 bg-slate-950/80 border border-slate-800 rounded-xl px-3.5 py-2">
                    <span className="text-xs text-slate-400">HHI Medido:</span>
                    <span className="text-sm font-black font-mono text-amber-400">
                      {fmtNum(indices.concentracao_ceap.indice_hhi, 0)}
                    </span>
                    <span className="text-[10px] text-slate-400">/ 10.000</span>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* Maior Fornecedor */}
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-2">
                    <span className="text-[11px] font-semibold text-slate-400 block">
                      Fornecedor com Maior Faturamento na Cota
                    </span>
                    <div className="text-sm font-bold text-slate-100">
                      {indices.concentracao_ceap.maior_fornecedor || "Diversificado entre múltiplos estabelecimentos"}
                    </div>
                    {indices.concentracao_ceap.cnpj_maior_fornecedor && (
                      <span className="text-xs font-mono text-slate-400 block">
                        CNPJ: {formatCpfCnpj(indices.concentracao_ceap.cnpj_maior_fornecedor)}
                      </span>
                    )}
                  </div>

                  {/* Concentração % */}
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-2">
                    <span className="text-[11px] font-semibold text-slate-400 block">
                      Fatia da Cota Consumida pelo Top 1
                    </span>
                    <div className="text-2xl font-black font-mono text-amber-400">
                      {fmtNum(indices.concentracao_ceap.percentual_maior_fornecedor, 1)}%
                    </div>
                    <span className="text-[10px] text-slate-400 block">
                      Escala antitruste: Acima de 45% ou HHI {'>'} 2.500 aciona alerta de concentração
                    </span>
                  </div>
                </div>

                {/* Diagnóstico */}
                <div className="bg-slate-950/80 border border-amber-500/20 rounded-xl p-4 space-y-1.5">
                  <span className="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5" aria-hidden="true" />
                    Auditoria de Conformidade da Cota:
                  </span>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {indices.concentracao_ceap.diagnostico}
                  </p>
                </div>
              </div>

              {/* CARD 3: PATRIMÔNIO DECLARADO VS RENDA OFICIAL */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 backdrop-blur-md shadow-lg space-y-5">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-3">
                    <span className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                      <TrendingUp className="w-5 h-5" aria-hidden="true" />
                    </span>
                    <div>
                      <h4 className="text-base font-bold text-slate-100 flex items-center gap-2">
                        3. Evolução Patrimonial Declarada vs. Renda Oficial
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${compatBadgeClass(indices.enriquecimento_patrimonial.compatibilidade)}`}>
                          {orUnavailable(indices.enriquecimento_patrimonial.compatibilidade)}
                        </span>
                      </h4>
                      <p className="text-xs text-slate-400">
                        Cruzamento da variação patrimonial informada ao TSE com os subsídios pagos pela Câmara/Senado
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 bg-slate-950/80 border border-slate-800 rounded-xl px-3.5 py-2">
                    <span className="text-xs text-slate-400">Razão Patrimônio/Renda:</span>
                    <span className="text-sm font-black font-mono text-emerald-400">
                      {fmtNum(indices.enriquecimento_patrimonial.razao_patrimonio_renda, 1)}x
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                    <span className="text-[11px] font-semibold text-slate-400 block">
                      Variação Patrimonial (TSE)
                    </span>
                    <span className="text-lg font-black font-mono text-slate-200 block">
                      {isNum(indices.enriquecimento_patrimonial.delta_patrimonio) && indices.enriquecimento_patrimonial.delta_patrimonio >= 0 ? "+" : ""}
                      {formatMoney(indices.enriquecimento_patrimonial.delta_patrimonio)}
                    </span>
                    <span className="text-[10px] text-slate-400 block">
                      Diferença entre primeira e última declaração
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                    <span className="text-[11px] font-semibold text-slate-400 block">
                      Renda Parlamentar Acumulada
                    </span>
                    <span className="text-lg font-black font-mono text-cyan-400 block">
                      {formatMoney(indices.enriquecimento_patrimonial.salario_acumulado_estimado)}
                    </span>
                    <span className="text-[10px] text-slate-400 block">
                      Soma estimada de subsídios oficiais recebidos
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                    <span className="text-[11px] font-semibold text-slate-400 block">
                      Enquadramento
                    </span>
                    <span className={`text-base font-black block ${
                      indices.enriquecimento_patrimonial.compatibilidade === "COMPATÍVEL"
                        ? "text-emerald-400"
                        : indices.enriquecimento_patrimonial.compatibilidade === "MODERADO"
                        ? "text-amber-400"
                        : indices.enriquecimento_patrimonial.compatibilidade === "ATÍPICO"
                        ? "text-rose-400"
                        : "text-slate-300"
                    }`}>
                      {orUnavailable(indices.enriquecimento_patrimonial.compatibilidade)}
                    </span>
                    <span className="text-[10px] text-slate-400 block">
                      Compatibilidade matemática com ganhos do cargo
                    </span>
                  </div>
                </div>

                <div className="bg-slate-950/80 border border-emerald-500/20 rounded-xl p-4 space-y-1.5">
                  <span className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                    <CheckCircle className="w-3.5 h-3.5" aria-hidden="true" />
                    Diagnóstico Patrimonial:
                  </span>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {indices.enriquecimento_patrimonial.diagnostico}
                  </p>
                </div>
              </div>

              {/* CARD 4: ESTABILIDADE PARTIDÁRIA & GOVERNISMO */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 backdrop-blur-md shadow-lg space-y-5">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-3">
                    <span className="p-2.5 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
                      <Users className="w-5 h-5" aria-hidden="true" />
                    </span>
                    <div>
                      <h4 className="text-base font-bold text-slate-100 flex items-center gap-2">
                        4. Estabilidade Partidária & Coerência de Plenário
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">
                          {orUnavailable(indices.estabilidade_partidaria.classificacao)}
                        </span>
                      </h4>
                      <p className="text-xs text-slate-400">
                        Histórico de trocas de legenda e taxa de alinhamento com orientações do governo
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 bg-slate-950/80 border border-slate-800 rounded-xl px-3.5 py-2">
                    <span className="text-xs text-slate-400">Taxa de Governismo:</span>
                    <span className="text-sm font-black font-mono text-purple-400">
                      {fmtNum(indices.estabilidade_partidaria.taxa_governismo_pct, 0)}%
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                    <span className="text-[11px] font-semibold text-slate-400 block">
                      Trocas de Partido
                    </span>
                    <span className="text-lg font-black font-mono text-slate-200 block">
                      {indices.estabilidade_partidaria.total_trocas} mudanças
                    </span>
                    <span className="text-[10px] text-slate-400 block">
                      Filiado a {dossier?.filiacoes_partidarias?.length || 1} legendas ao longo da carreira
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                    <span className="text-[11px] font-semibold text-slate-400 block">
                      Tempo Médio por Partido
                    </span>
                    <span className="text-lg font-black font-mono text-purple-400 block">
                      {fmtNum(indices.estabilidade_partidaria.anos_medio_por_partido, 1)} anos
                    </span>
                    <span className="text-[10px] text-slate-400 block">
                      Permanência média em cada sigla
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                    <span className="text-[11px] font-semibold text-slate-400 block">
                      Perfil de Atuação
                    </span>
                    <span className="text-sm font-bold text-slate-200 block">
                      {orUnavailable(indices.estabilidade_partidaria.classificacao)}
                    </span>
                    <span className="text-[10px] text-slate-400 block">
                      Consistência de posicionamento legislativo
                    </span>
                  </div>
                </div>

                <div className="bg-slate-950/80 border border-purple-500/20 rounded-xl p-4 space-y-1.5">
                  <span className="text-xs font-bold text-purple-400 flex items-center gap-1.5">
                    <Scale className="w-3.5 h-3.5" aria-hidden="true" />
                    Diagnóstico de Trajetória:
                  </span>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {indices.estabilidade_partidaria.diagnostico}
                  </p>
                </div>
              </div>

              {/* CARD 5: EFICIÊNCIA DE EMENDAS & QUOTA PIX */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 backdrop-blur-md shadow-lg space-y-5">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-3">
                    <span className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                      <Landmark className="w-5 h-5" aria-hidden="true" />
                    </span>
                    <div>
                      <h4 className="text-base font-bold text-slate-100 flex items-center gap-2">
                        5. Eficiência e Destino de Emendas Orçamentárias
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          {orUnavailable(indices.eficiencia_emendas.classificacao)}
                        </span>
                      </h4>
                      <p className="text-xs text-slate-400">
                        Taxa de conversão do empenhado em repasses pagos e transparência das emendas especiais (PIX)
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 bg-slate-950/80 border border-slate-800 rounded-xl px-3.5 py-2">
                    <span className="text-xs text-slate-400">Taxa de Conversão:</span>
                    <span className="text-sm font-black font-mono text-emerald-400">
                      {fmtNum(indices.eficiencia_emendas.taxa_conversao_pct, 1)}%
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                    <span className="text-[11px] font-semibold text-slate-400 block">
                      Total Pago / Liquidado
                    </span>
                    <span className="text-lg font-black font-mono text-emerald-400 block">
                      {formatMoney(indices.eficiencia_emendas.total_pago)}
                    </span>
                    <span className="text-[10px] text-slate-400 block">
                      De {formatMoney(indices.eficiencia_emendas.total_empenhado)} empenhados
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                    <span className="text-[11px] font-semibold text-slate-400 block">
                      Quota de Emendas PIX
                    </span>
                    <span className={`text-lg font-black font-mono block ${
                      indices.eficiencia_emendas.percentual_pix > 30 ? "text-amber-400" : "text-slate-200"
                    }`}>
                      {fmtNum(indices.eficiencia_emendas.percentual_pix, 1)}%
                    </span>
                    <span className="text-[10px] text-slate-400 block">
                      Transferências especiais sem convênio vinculado
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                    <span className="text-[11px] font-semibold text-slate-400 block">
                      Município Predileto
                    </span>
                    <span className="text-sm font-bold text-slate-200 block truncate" title={indices.eficiencia_emendas.municipio_predileto || "Distribuído"}>
                      {indices.eficiencia_emendas.municipio_predileto || "Distribuição equilibrada"}
                    </span>
                    <span className="text-[10px] text-slate-400 block">
                      Concentra {fmtNum(indices.eficiencia_emendas.concentracao_municipio_predileto_pct, 1)}% dos recursos
                    </span>
                  </div>
                </div>

                <div className="bg-slate-950/80 border border-emerald-500/20 rounded-xl p-4 space-y-1.5">
                  <span className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                    <CheckCircle className="w-3.5 h-3.5" aria-hidden="true" />
                    Diagnóstico de Entrega Orçamentária:
                  </span>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {indices.eficiencia_emendas.diagnostico}
                  </p>
                </div>
              </div>
            </div>
  );
}
