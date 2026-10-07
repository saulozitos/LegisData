"use client";

import React, { useEffect, useState, useMemo } from "react";
import Header from "@/components/Header";
import {
  getMandatesPerformance,
  getCompareMandates,
  getPresidentes,
  MandatoPerformance,
  CompareMandatesResponse,
  PresidenteHistorico,
} from "@/services/api";
import { getPresidentPhotoUrl } from "@/components/PresidentTimeline";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from "recharts";
import {
  ArrowLeftRight,
  TrendingUp,
  TrendingDown,
  Sparkles,
  Scale,
  Calendar,
  DollarSign,
  Activity,
  Award,
  Info,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
} from "lucide-react";

export default function ComparadorPage() {
  const [mandates, setMandates] = useState<MandatoPerformance[]>([]);
  const [presidents, setPresidents] = useState<PresidenteHistorico[]>([]);
  const [mandate1Id, setMandate1Id] = useState<string>("fhc-1995");
  const [mandate2Id, setMandate2Id] = useState<string>("lula-2003");
  const [compareData, setCompareData] = useState<CompareMandatesResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isComparing, setIsComparing] = useState<boolean>(false);
  const [chartMetric, setChartMetric] = useState<"PIB" | "IPCA" | "USD">("PIB");

  // Presets para comparação instantânea
  const presets = [
    { label: "FHC 1 vs Lula 1", m1: "fhc-1995", m2: "lula-2003" },
    { label: "Lula 2 vs Dilma 1", m1: "lula-2007", m2: "dilma-2011" },
    { label: "Dilma 1 vs Bolsonaro", m1: "dilma-2011", m2: "bolsonaro-2019" },
    { label: "FHC 2 vs Lula 1", m1: "fhc-1999", m2: "lula-2003" },
    { label: "Bolsonaro vs Lula 3", m1: "bolsonaro-2019", m2: "lula-2023" },
  ];

  // Carregar lista de mandatos disponíveis
  useEffect(() => {
    async function init() {
      setIsLoading(true);
      try {
        const [mandatesList, presList] = await Promise.all([
          getMandatesPerformance(),
          getPresidentes(),
        ]);
        setMandates(mandatesList);
        setPresidents(presList);
      } catch (err) {
        console.error("Erro ao carregar lista de mandatos:", err);
      } finally {
        setIsLoading(false);
      }
    }
    init();
  }, []);

  // Buscar comparação quando mandate1Id ou mandate2Id mudarem
  useEffect(() => {
    if (!mandate1Id || !mandate2Id) return;

    async function fetchComparison() {
      setIsComparing(true);
      try {
        const res = await getCompareMandates(mandate1Id, mandate2Id);
        setCompareData(res);
      } catch (err) {
        console.error("Erro ao buscar dados de comparação:", err);
      } finally {
        setIsComparing(false);
      }
    }

    fetchComparison();
  }, [mandate1Id, mandate2Id]);

  // Mapa de fotos e detalhes presidenciais
  const presidentMap = useMemo(() => {
    const map: Record<string, PresidenteHistorico> = {};
    for (const p of presidents) {
      map[p.id_referencia] = p;
    }
    return map;
  }, [presidents]);

  const m1 = compareData?.mandate1;
  const m2 = compareData?.mandate2;
  const deltas = compareData?.deltas;
  const trajectory = compareData?.normalized_trajectory || [];

  const p1 = m1 ? presidentMap[m1.id_mandato] : null;
  const p2 = m2 ? presidentMap[m2.id_mandato] : null;

  const handleApplyPreset = (m1Id: string, m2Id: string) => {
    setMandate1Id(m1Id);
    setMandate2Id(m2Id);
  };

  const handleSwap = () => {
    const temp = mandate1Id;
    setMandate1Id(mandate2Id);
    setMandate2Id(temp);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-cyan-500/30 selection:text-cyan-200">
      <Header />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Título e Presets */}
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pb-2 border-b border-slate-900">
          <div>
            <div className="flex items-center gap-2">
              <span className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                <Scale className="w-5 h-5" />
              </span>
              <h2 className="text-xl sm:text-2xl font-black bg-gradient-to-r from-slate-100 via-slate-200 to-slate-400 bg-clip-text text-transparent">
                Comparador Lado a Lado de Mandatos
              </h2>
            </div>
            <p className="text-xs sm:text-sm text-slate-400 mt-1">
              Confronto analítico direto e curvas normalizadas por <strong>Ano 1 a Ano 4</strong> do ciclo presidencial
            </p>
          </div>

          {/* Atalhos Rápidos (Presets) */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] text-slate-400 font-semibold mr-1 flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-amber-400" /> Presets:
            </span>
            {presets.map((preset) => {
              const isCurrent =
                (mandate1Id === preset.m1 && mandate2Id === preset.m2) ||
                (mandate1Id === preset.m2 && mandate2Id === preset.m1);
              return (
                <button
                  key={preset.label}
                  onClick={() => handleApplyPreset(preset.m1, preset.m2)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-all ${
                    isCurrent
                      ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/40 shadow-sm shadow-cyan-500/10"
                      : "bg-slate-900/80 text-slate-400 border-slate-800 hover:text-slate-200 hover:border-slate-700"
                  }`}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Dual Selector Interativo */}
        <div className="grid grid-cols-1 md:grid-cols-11 gap-4 items-center">
          {/* Mandato A (Card) */}
          <div className="md:col-span-5 bg-slate-900/70 border border-cyan-500/30 rounded-2xl p-5 backdrop-blur-md relative overflow-hidden shadow-lg shadow-cyan-950/20">
            <div className="absolute top-0 right-0 w-32 h-32 bg-cyan-500/5 rounded-full blur-2xl pointer-events-none" />

            <div className="flex items-center justify-between mb-3">
              <span className="text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-cyan-500/15 text-cyan-400 border border-cyan-500/30">
                Mandato A (Referência)
              </span>
              <span className="text-xs text-slate-400">{m1?.anos_cobertos}</span>
            </div>

            <div className="space-y-3">
              <label className="block text-xs font-semibold text-slate-300">
                Selecione o Primeiro Mandato:
              </label>
              <select
                value={mandate1Id}
                onChange={(e) => setMandate1Id(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm font-semibold text-slate-100 focus:outline-none focus:border-cyan-500 transition-colors cursor-pointer"
              >
                {mandates.map((m) => (
                  <option key={m.id_mandato} value={m.id_mandato}>
                    {m.presidente} ({m.anos_cobertos})
                  </option>
                ))}
              </select>

              {/* Detalhes Rápidos do Mandato A */}
              {m1 && (
                <div className="flex items-center gap-3 pt-2">
                  <div className="relative w-12 h-12 rounded-xl overflow-hidden bg-slate-800 border border-cyan-500/40 shadow-sm flex items-center justify-center flex-shrink-0">
                    <img
                      src={getPresidentPhotoUrl(m1.id_mandato, p1?.foto_url)}
                      alt={m1.presidente}
                      referrerPolicy="no-referrer"
                      className="w-full h-full object-cover object-top"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                    <div className="absolute inset-0 bg-slate-800 -z-10 flex items-center justify-center font-bold text-cyan-400 text-xs">
                      {m1.partido}
                    </div>
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-100">{m1.presidente}</h3>
                    <p className="text-xs text-slate-400">
                      Partido: <strong className="text-cyan-400">{m1.partido}</strong> • {m1.status_mandato}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Botão Swap (Meio) */}
          <div className="md:col-span-1 flex justify-center py-2 md:py-0">
            <button
              onClick={handleSwap}
              title="Inverter Mandatos"
              className="p-3 rounded-full bg-slate-900 border border-slate-700 hover:border-cyan-400 text-slate-300 hover:text-cyan-300 hover:scale-110 active:scale-95 transition-all shadow-md group"
            >
              <ArrowLeftRight className="w-5 h-5 group-hover:rotate-180 transition-transform duration-300" />
            </button>
          </div>

          {/* Mandato B (Card) */}
          <div className="md:col-span-5 bg-slate-900/70 border border-amber-500/30 rounded-2xl p-5 backdrop-blur-md relative overflow-hidden shadow-lg shadow-amber-950/20">
            <div className="absolute top-0 right-0 w-32 h-32 bg-amber-500/5 rounded-full blur-2xl pointer-events-none" />

            <div className="flex items-center justify-between mb-3">
              <span className="text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30">
                Mandato B (Comparado)
              </span>
              <span className="text-xs text-slate-400">{m2?.anos_cobertos}</span>
            </div>

            <div className="space-y-3">
              <label className="block text-xs font-semibold text-slate-300">
                Selecione o Segundo Mandato:
              </label>
              <select
                value={mandate2Id}
                onChange={(e) => setMandate2Id(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm font-semibold text-slate-100 focus:outline-none focus:border-amber-500 transition-colors cursor-pointer"
              >
                {mandates.map((m) => (
                  <option key={m.id_mandato} value={m.id_mandato}>
                    {m.presidente} ({m.anos_cobertos})
                  </option>
                ))}
              </select>

              {/* Detalhes Rápidos do Mandato B */}
              {m2 && (
                <div className="flex items-center gap-3 pt-2">
                  <div className="relative w-12 h-12 rounded-xl overflow-hidden bg-slate-800 border border-amber-500/40 shadow-sm flex items-center justify-center flex-shrink-0">
                    <img
                      src={getPresidentPhotoUrl(m2.id_mandato, p2?.foto_url)}
                      alt={m2.presidente}
                      referrerPolicy="no-referrer"
                      className="w-full h-full object-cover object-top"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                    <div className="absolute inset-0 bg-slate-800 -z-10 flex items-center justify-center font-bold text-amber-400 text-xs">
                      {m2.partido}
                    </div>
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-100">{m2.presidente}</h3>
                    <p className="text-xs text-slate-400">
                      Partido: <strong className="text-amber-400">{m2.partido}</strong> • {m2.status_mandato}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Tabela de Contraste de KPIs Lado a Lado */}
        {m1 && m2 && deltas && (
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-md space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <Activity className="w-5 h-5 text-emerald-400" />
                <h3 className="text-base font-bold text-slate-100">
                  Tabela de Contraste Macroeconômico e Deltas
                </h3>
              </div>
              <span className="text-xs text-slate-400">
                Delta calculado como: <strong className="text-slate-200">Mandato B − Mandato A</strong>
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-xs text-slate-400 uppercase tracking-wider">
                    <th className="py-3 px-4 font-semibold">Indicador Econômico</th>
                    <th className="py-3 px-4 font-semibold text-cyan-400">
                      Mandato A: {m1.presidente}
                    </th>
                    <th className="py-3 px-4 font-semibold text-amber-400">
                      Mandato B: {m2.presidente}
                    </th>
                    <th className="py-3 px-4 font-semibold text-right">Diferença (Delta B − A)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-200">
                  {/* PIB Médio Anual */}
                  <tr className="hover:bg-slate-800/20 transition-colors">
                    <td className="py-3.5 px-4 font-medium flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-emerald-400" />
                      <span>Crescimento Médio Anual do PIB</span>
                    </td>
                    <td className="py-3.5 px-4 font-mono font-bold text-cyan-300">
                      {m1.pib_medio_anual_pct > 0 ? `+${m1.pib_medio_anual_pct}%` : `${m1.pib_medio_anual_pct}%`} a.a.
                    </td>
                    <td className="py-3.5 px-4 font-mono font-bold text-amber-300">
                      {m2.pib_medio_anual_pct > 0 ? `+${m2.pib_medio_anual_pct}%` : `${m2.pib_medio_anual_pct}%`} a.a.
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <span
                        className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2.5 py-1 rounded-full ${
                          deltas.pib_medio_diff_pp > 0
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                            : deltas.pib_medio_diff_pp < 0
                            ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                            : "bg-slate-800 text-slate-300"
                        }`}
                      >
                        {deltas.pib_medio_diff_pp > 0 ? `+${deltas.pib_medio_diff_pp} p.p.` : `${deltas.pib_medio_diff_pp} p.p.`}
                      </span>
                    </td>
                  </tr>

                  {/* PIB Crescimento Acumulado */}
                  <tr className="hover:bg-slate-800/20 transition-colors">
                    <td className="py-3.5 px-4 font-medium">Crescimento Acumulado do PIB no Mandato</td>
                    <td className="py-3.5 px-4 font-mono font-semibold text-slate-300">
                      +{m1.pib_crescimento_acumulado_pct}%
                    </td>
                    <td className="py-3.5 px-4 font-mono font-semibold text-slate-300">
                      +{m2.pib_crescimento_acumulado_pct}%
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <span
                        className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2.5 py-1 rounded-full ${
                          deltas.pib_acumulado_diff_pp > 0
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                            : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                        }`}
                      >
                        {deltas.pib_acumulado_diff_pp > 0 ? `+${deltas.pib_acumulado_diff_pp} p.p.` : `${deltas.pib_acumulado_diff_pp} p.p.`}
                      </span>
                    </td>
                  </tr>

                  {/* Inflação Acumulada IPCA */}
                  <tr className="hover:bg-slate-800/20 transition-colors">
                    <td className="py-3.5 px-4 font-medium flex items-center gap-2">
                      <TrendingDown className="w-4 h-4 text-rose-400" />
                      <span>Inflação Acumulada (IPCA)</span>
                    </td>
                    <td className="py-3.5 px-4 font-mono font-bold text-cyan-300">
                      {m1.ipca_pos_real_pct ? `${m1.ipca_pos_real_pct}% (pós-Real)` : `${m1.ipca_acumulado_pct.toLocaleString("pt-BR")}%`}
                    </td>
                    <td className="py-3.5 px-4 font-mono font-bold text-amber-300">
                      {m2.ipca_pos_real_pct ? `${m2.ipca_pos_real_pct}% (pós-Real)` : `${m2.ipca_acumulado_pct.toLocaleString("pt-BR")}%`}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      {/* Para inflação, delta negativo é favorável (menor inflação) */}
                      <span
                        className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2.5 py-1 rounded-full ${
                          deltas.ipca_acumulado_diff_pp < 0
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                            : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                        }`}
                      >
                        {deltas.ipca_acumulado_diff_pp > 0 ? `+${deltas.ipca_acumulado_diff_pp} p.p.` : `${deltas.ipca_acumulado_diff_pp} p.p.`}
                        {deltas.ipca_acumulado_relative_pct ? ` (${deltas.ipca_acumulado_relative_pct}%)` : ""}
                      </span>
                    </td>
                  </tr>

                  {/* Variação Cambial */}
                  <tr className="hover:bg-slate-800/20 transition-colors">
                    <td className="py-3.5 px-4 font-medium flex items-center gap-2">
                      <DollarSign className="w-4 h-4 text-cyan-400" />
                      <span>Variação Cambial USD/BRL</span>
                    </td>
                    <td className="py-3.5 px-4 font-mono font-semibold text-slate-300">
                      {m1.cambio_variacao_pct !== null ? `${m1.cambio_variacao_pct > 0 ? "+" : ""}${m1.cambio_variacao_pct}%` : "N/D"}
                      <span className="text-xs text-slate-500 block">
                        (R$ {m1.cambio_inicial_usd_brl} → R$ {m1.cambio_final_usd_brl})
                      </span>
                    </td>
                    <td className="py-3.5 px-4 font-mono font-semibold text-slate-300">
                      {m2.cambio_variacao_pct !== null ? `${m2.cambio_variacao_pct > 0 ? "+" : ""}${m2.cambio_variacao_pct}%` : "N/D"}
                      <span className="text-xs text-slate-500 block">
                        (R$ {m2.cambio_inicial_usd_brl} → R$ {m2.cambio_final_usd_brl})
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      {deltas.cambio_variacao_diff_pp !== null ? (
                        <span className="inline-flex items-center font-mono font-bold text-xs px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                          {deltas.cambio_variacao_diff_pp > 0 ? `+${deltas.cambio_variacao_diff_pp} p.p.` : `${deltas.cambio_variacao_diff_pp} p.p.`}
                        </span>
                      ) : (
                        <span className="text-slate-500 text-xs">N/D</span>
                      )}
                    </td>
                  </tr>

                  {/* Salário Mínimo Final em Reais e Dólar */}
                  <tr className="hover:bg-slate-800/20 transition-colors">
                    <td className="py-3.5 px-4 font-medium">Salário Mínimo Final (Moeda Nacional & USD)</td>
                    <td className="py-3.5 px-4 font-mono font-bold text-cyan-300">
                      {m1.salario_minimo_final_brl ? (
                        <div>
                          <span>R$ {m1.salario_minimo_final_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                          {m1.salario_minimo_final_usd && (
                            <span className="text-[11px] text-slate-400 font-normal block">(US$ {m1.salario_minimo_final_usd.toFixed(2)})</span>
                          )}
                        </div>
                      ) : "N/D"}
                    </td>
                    <td className="py-3.5 px-4 font-mono font-bold text-amber-300">
                      {m2.salario_minimo_final_brl ? (
                        <div>
                          <span>R$ {m2.salario_minimo_final_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                          {m2.salario_minimo_final_usd && (
                            <span className="text-[11px] text-slate-400 font-normal block">(US$ {m2.salario_minimo_final_usd.toFixed(2)})</span>
                          )}
                        </div>
                      ) : "N/D"}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      {deltas.salario_minimo_usd_diff !== null ? (
                        <div className="flex flex-col items-end gap-0.5">
                          {m1.salario_minimo_final_brl && m2.salario_minimo_final_brl && (
                            <span
                              className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2.5 py-0.5 rounded-full ${
                                m2.salario_minimo_final_brl > m1.salario_minimo_final_brl
                                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                  : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                              }`}
                            >
                              {m2.salario_minimo_final_brl > m1.salario_minimo_final_brl ? "+" : ""}
                              R$ {(m2.salario_minimo_final_brl - m1.salario_minimo_final_brl).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </span>
                          )}
                          <span className="text-[10px] text-slate-400 font-mono">
                            {deltas.salario_minimo_usd_diff > 0 ? `+US$ ${deltas.salario_minimo_usd_diff}` : `US$ ${deltas.salario_minimo_usd_diff}`}
                          </span>
                        </div>
                      ) : (
                        <span className="text-slate-500 text-xs">N/D</span>
                      )}
                    </td>
                  </tr>

                  {/* Ministros da Fazenda Chave */}
                  <tr className="hover:bg-slate-800/20 transition-colors">
                    <td className="py-3.5 px-4 font-medium text-slate-400">Ministros da Fazenda / Economia</td>
                    <td className="py-3.5 px-4 text-xs text-slate-300">
                      {m1.ministros_fazenda_principais?.join(", ") || "Nenhum mapeado"}
                    </td>
                    <td className="py-3.5 px-4 text-xs text-slate-300">
                      {m2.ministros_fazenda_principais?.join(", ") || "Nenhum mapeado"}
                    </td>
                    <td className="py-3.5 px-4 text-right text-xs text-slate-500 italic">
                      Equipe Econômica
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Gráfico de Trajetória Normalizada (Recharts) */}
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-md space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
            <div>
              <div className="flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-cyan-400" />
                <h3 className="text-base font-bold text-slate-100">
                  Gráfico de Trajetória Normalizada (Ano a Ano)
                </h3>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                O eixo horizontal alinha o <strong>Ano 1, Ano 2, Ano 3 e Ano 4</strong> de cada mandato para permitir comparação direta de ciclos
              </p>
            </div>

            {/* Seletor de Métrica do Gráfico */}
            <div className="flex items-center bg-slate-950 border border-slate-800 p-1 rounded-xl">
              <button
                onClick={() => setChartMetric("PIB")}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  chartMetric === "PIB"
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm shadow-emerald-500/10"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Crescimento do PIB (%)
              </button>
              <button
                onClick={() => setChartMetric("IPCA")}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  chartMetric === "IPCA"
                    ? "bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm shadow-rose-500/10"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Inflação IPCA (%)
              </button>
              <button
                onClick={() => setChartMetric("USD")}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  chartMetric === "USD"
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm shadow-cyan-500/10"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Câmbio Médio (R$/US$)
              </button>
            </div>
          </div>

          {/* Gráfico Recharts */}
          <div className="h-80 w-full pt-4">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trajectory} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  dataKey="label"
                  stroke="#64748b"
                  tick={{ fill: "#94a3b8", fontSize: 12 }}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fill: "#94a3b8", fontSize: 12 }}
                  unit={chartMetric === "USD" ? " R$" : "%"}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload || !payload.length) return null;
                    const dataPoint = payload[0]?.payload;
                    return (
                      <div className="bg-slate-950/95 border border-slate-700/80 rounded-xl p-3.5 shadow-2xl text-xs space-y-2 backdrop-blur-lg">
                        <div className="font-bold text-slate-200 border-b border-slate-800 pb-1 flex items-center justify-between gap-4">
                          <span>{label} do Mandato</span>
                          <span className="text-[10px] text-slate-400">Normalizado</span>
                        </div>
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between gap-4 text-cyan-400">
                            <span>
                              {m1?.presidente} ({dataPoint?.m1_calendar_year || "N/D"}):
                            </span>
                            <span className="font-mono font-bold">
                              {chartMetric === "PIB"
                                ? `${dataPoint?.m1_pib ?? "N/D"}%`
                                : chartMetric === "IPCA"
                                ? `${dataPoint?.m1_ipca ?? "N/D"}%`
                                : `R$ ${dataPoint?.m1_usd ?? "N/D"}`}
                            </span>
                          </div>
                          <div className="flex items-center justify-between gap-4 text-amber-400">
                            <span>
                              {m2?.presidente} ({dataPoint?.m2_calendar_year || "N/D"}):
                            </span>
                            <span className="font-mono font-bold">
                              {chartMetric === "PIB"
                                ? `${dataPoint?.m2_pib ?? "N/D"}%`
                                : chartMetric === "IPCA"
                                ? `${dataPoint?.m2_ipca ?? "N/D"}%`
                                : `R$ ${dataPoint?.m2_usd ?? "N/D"}`}
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  }}
                />
                <Legend
                  wrapperStyle={{ paddingTop: "12px", fontSize: "12px" }}
                />
                {chartMetric === "PIB" && (
                  <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                )}

                {/* Linha do Mandato A */}
                <Line
                  type="monotone"
                  dataKey={
                    chartMetric === "PIB"
                      ? "m1_pib"
                      : chartMetric === "IPCA"
                      ? "m1_ipca"
                      : "m1_usd"
                  }
                  name={`${m1?.presidente || "Mandato A"}`}
                  stroke="#06b6d4"
                  strokeWidth={3}
                  dot={{ r: 5, fill: "#06b6d4" }}
                  activeDot={{ r: 7 }}
                />

                {/* Linha do Mandato B */}
                <Line
                  type="monotone"
                  dataKey={
                    chartMetric === "PIB"
                      ? "m2_pib"
                      : chartMetric === "IPCA"
                      ? "m2_ipca"
                      : "m2_usd"
                  }
                  name={`${m2?.presidente || "Mandato B"}`}
                  stroke="#f59e0b"
                  strokeWidth={3}
                  dot={{ r: 5, fill: "#f59e0b" }}
                  activeDot={{ r: 7 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Resumo Analítico Cruzado */}
        {m1 && m2 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 text-xs text-slate-400 space-y-2">
              <div className="flex items-center gap-2 text-cyan-400 font-bold text-sm">
                <Award className="w-4 h-4" />
                <span>Marcos Históricos: {m1.presidente}</span>
              </div>
              <ul className="list-disc list-inside space-y-1">
                {m1.marcos_economicos_principais?.map((marco, i) => (
                  <li key={i} className="text-slate-300 leading-relaxed">
                    {marco}
                  </li>
                )) || <li>Dados históricos não informados</li>}
              </ul>
            </div>

            <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 text-xs text-slate-400 space-y-2">
              <div className="flex items-center gap-2 text-amber-400 font-bold text-sm">
                <Award className="w-4 h-4" />
                <span>Marcos Históricos: {m2.presidente}</span>
              </div>
              <ul className="list-disc list-inside space-y-1">
                {m2.marcos_economicos_principais?.map((marco, i) => (
                  <li key={i} className="text-slate-300 leading-relaxed">
                    {marco}
                  </li>
                )) || <li>Dados históricos não informados</li>}
              </ul>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
