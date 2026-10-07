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
  BarChart,
  Bar,
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
  DollarSign,
  Activity,
  Award,
  HeartHandshake,
  GraduationCap,
  Building2,
  ShieldAlert,
  Users,
  Trees,
  Search,
  Filter,
  BarChart3,
  Landmark,
  Coins,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";

type ChartMetricType =
  | "PIB"
  | "IPCA"
  | "USD"
  | "SALARIO"
  | "POBREZA"
  | "ANALFABETISMO"
  | "FOME"
  | "GINI"
  | "HOMICIDIOS"
  | "DESMATAMENTO";

export default function ComparadorPage() {
  const [mandates, setMandates] = useState<MandatoPerformance[]>([]);
  const [presidents, setPresidents] = useState<PresidenteHistorico[]>([]);
  const [mandate1Id, setMandate1Id] = useState<string>("bolsonaro-2019");
  const [mandate2Id, setMandate2Id] = useState<string>("lula-2023");
  const [compareData, setCompareData] = useState<CompareMandatesResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isComparing, setIsComparing] = useState<boolean>(false);
  const [chartMetric, setChartMetric] = useState<ChartMetricType>("PIB");

  // Filtros da seção de Repasses Federais por Estado
  const [repasseRegionFilter, setRepasseRegionFilter] = useState<string>("TODAS");
  const [repasseAreaFilter, setRepasseAreaFilter] = useState<string>("TODAS");
  const [repasseSearchTerm, setRepasseSearchTerm] = useState<string>("");

  // Presets para comparação instantânea
  const presets = [
    { label: "Bolsonaro vs Lula 3", m1: "bolsonaro-2019", m2: "lula-2023" },
    { label: "FHC 1 vs Lula 1", m1: "fhc-1995", m2: "lula-2003" },
    { label: "Lula 2 vs Dilma 1", m1: "lula-2007", m2: "dilma-2011" },
    { label: "Dilma 1 vs Bolsonaro", m1: "dilma-2011", m2: "bolsonaro-2019" },
    { label: "FHC 2 vs Lula 1", m1: "fhc-1999", m2: "lula-2003" },
    { label: "Temer vs Bolsonaro", m1: "temer-2016", m2: "bolsonaro-2019" },
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
  const repassesComp = compareData?.repasses_comparison;

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

  // Formatadores de valores
  const formatBRL = (val: number | null | undefined) => {
    if (val === null || val === undefined) return "N/D";
    if (Math.abs(val) >= 1_000_000_000) {
      return `R$ ${(val / 1_000_000_000).toLocaleString("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })} bi`;
    }
    if (Math.abs(val) >= 1_000_000) {
      return `R$ ${(val / 1_000_000).toLocaleString("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })} mi`;
    }
    return `R$ ${val.toLocaleString("pt-BR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  };

  const formatNumber = (val: number | null | undefined, decimals = 1, unit = "") => {
    if (val === null || val === undefined) return "N/D";
    return `${val.toLocaleString("pt-BR", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })}${unit}`;
  };

  // Filtragem dos estados na tabela de repasses
  const filteredUFs = useMemo(() => {
    if (!repassesComp?.by_uf) return [];
    return repassesComp.by_uf.filter((item) => {
      const matchRegion =
        repasseRegionFilter === "TODAS" ||
        item.regiao.toUpperCase() === repasseRegionFilter.toUpperCase();
      const matchSearch =
        repasseSearchTerm === "" ||
        item.estado_nome.toLowerCase().includes(repasseSearchTerm.toLowerCase()) ||
        item.uf.toLowerCase().includes(repasseSearchTerm.toLowerCase());
      return matchRegion && matchSearch;
    });
  }, [repassesComp, repasseRegionFilter, repasseSearchTerm]);

  // Top 6 estados por volume de repasses para gráfico comparativo
  const topStatesChartData = useMemo(() => {
    if (!repassesComp?.by_uf) return [];
    return [...repassesComp.by_uf]
      .sort((a, b) => b.m2_total + b.m1_total - (a.m2_total + a.m1_total))
      .slice(0, 6)
      .map((item) => ({
        uf: item.uf,
        nome: item.estado_nome,
        m1_bi: Number((item.m1_total / 1_000_000_000).toFixed(2)),
        m2_bi: Number((item.m2_total / 1_000_000_000).toFixed(2)),
      }));
  }, [repassesComp]);

  // Configuração da métrica do gráfico de trajetória
  const getMetricConfig = (metric: ChartMetricType) => {
    switch (metric) {
      case "PIB":
        return {
          title: "Crescimento do PIB (%)",
          unit: "%",
          m1Key: "m1_pib",
          m2Key: "m2_pib",
          zeroLine: true,
        };
      case "IPCA":
        return {
          title: "Inflação Anual IPCA (%)",
          unit: "%",
          m1Key: "m1_ipca",
          m2Key: "m2_ipca",
          zeroLine: false,
        };
      case "USD":
        return {
          title: "Cotação Média do Dólar (R$/US$)",
          unit: " R$",
          m1Key: "m1_usd",
          m2Key: "m2_usd",
          zeroLine: false,
        };
      case "SALARIO":
        return {
          title: "Salário Mínimo Nominal (R$)",
          unit: " R$",
          m1Key: "m1_salario_minimo",
          m2Key: "m2_salario_minimo",
          zeroLine: false,
        };
      case "POBREZA":
        return {
          title: "Extrema Pobreza Nacional (% pop.)",
          unit: "%",
          m1Key: "m1_extrema_pobreza",
          m2Key: "m2_extrema_pobreza",
          zeroLine: false,
        };
      case "ANALFABETISMO":
        return {
          title: "Taxa de Analfabetismo (% 15+ anos)",
          unit: "%",
          m1Key: "m1_analfabetismo",
          m2Key: "m2_analfabetismo",
          zeroLine: false,
        };
      case "FOME":
        return {
          title: "Insegurança Alimentar Grave / Fome (%)",
          unit: "%",
          m1Key: "m1_inseguranca_alimentar",
          m2Key: "m2_inseguranca_alimentar",
          zeroLine: false,
        };
      case "GINI":
        return {
          title: "Índice de Gini (Desigualdade 0 a 1)",
          unit: "",
          m1Key: "m1_gini",
          m2Key: "m2_gini",
          zeroLine: false,
        };
      case "HOMICIDIOS":
        return {
          title: "Taxa de Homicídios (por 100k hab)",
          unit: " /100k",
          m1Key: "m1_homicidios",
          m2Key: "m2_homicidios",
          zeroLine: false,
        };
      case "DESMATAMENTO":
        return {
          title: "Desmatamento Amazônia (km²/ano)",
          unit: " km²",
          m1Key: "m1_desmatamento",
          m2Key: "m2_desmatamento",
          zeroLine: false,
        };
    }
  };

  const metricConfig = getMetricConfig(chartMetric);

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
              <h1 className="text-xl sm:text-2xl font-black bg-gradient-to-r from-slate-100 via-slate-200 to-slate-400 bg-clip-text text-transparent">
                Comparador Lado a Lado de Mandatos Presidenciais
              </h1>
            </div>
            <p className="text-xs sm:text-sm text-slate-400 mt-1">
              Confronto analítico direto: <strong>Economia, Questão Social, Segurança, Amazônia e Repasses Federais aos Estados</strong>
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
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
                    isCurrent
                      ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/40 shadow-sm shadow-cyan-500/10 font-bold"
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
              className="p-3 rounded-full bg-slate-900 border border-slate-700 hover:border-cyan-400 text-slate-300 hover:text-cyan-300 hover:scale-110 active:scale-95 transition-all shadow-md group cursor-pointer"
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

        {/* 1. TABELA PRINCIPAL DE CONTRASTE MULTIDIMENSIONAL */}
        {m1 && m2 && deltas && (
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-md space-y-6">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <Activity className="w-5 h-5 text-emerald-400" />
                <h2 className="text-base font-bold text-slate-100">
                  Tabela Comparativa Multidimensional & Deltas
                </h2>
              </div>
              <span className="text-xs text-slate-400">
                Delta calculado como: <strong className="text-slate-200">Mandato B − Mandato A</strong>
              </span>
            </div>

            {/* SEÇÃO 1: MACROECONOMIA & INFLAÇÃO */}
            <div className="space-y-2">
              <div className="flex items-center gap-2 px-1 text-xs font-extrabold uppercase tracking-wider text-cyan-400">
                <TrendingUp className="w-4 h-4" />
                <span>Dimensão 1: Economia, Inflação & Salário Mínimo</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-xs text-slate-400 uppercase tracking-wider">
                      <th className="py-2.5 px-4 font-semibold">Indicador Econômico</th>
                      <th className="py-2.5 px-4 font-semibold text-cyan-400">
                        {m1.presidente}
                      </th>
                      <th className="py-2.5 px-4 font-semibold text-amber-400">
                        {m2.presidente}
                      </th>
                      <th className="py-2.5 px-4 font-semibold text-right">Diferença (Delta B − A)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-200">
                    {/* PIB Médio Anual */}
                    <tr className="hover:bg-slate-800/20 transition-colors">
                      <td className="py-3 px-4 font-medium flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-emerald-400" />
                        <span>Crescimento do PIB (Médio Anual)</span>
                      </td>
                      <td className="py-3 px-4 font-mono font-bold text-cyan-300">
                        {m1.pib_medio_anual_pct > 0 ? `+${m1.pib_medio_anual_pct}%` : `${m1.pib_medio_anual_pct}%`} a.a.
                      </td>
                      <td className="py-3 px-4 font-mono font-bold text-amber-300">
                        {m2.pib_medio_anual_pct > 0 ? `+${m2.pib_medio_anual_pct}%` : `${m2.pib_medio_anual_pct}%`} a.a.
                      </td>
                      <td className="py-3 px-4 text-right">
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
                      <td className="py-3 px-4 font-medium">Crescimento Acumulado do PIB no Mandato</td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        +{m1.pib_crescimento_acumulado_pct}%
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        +{m2.pib_crescimento_acumulado_pct}%
                      </td>
                      <td className="py-3 px-4 text-right">
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
                      <td className="py-3 px-4 font-medium flex items-center gap-2">
                        <TrendingDown className="w-4 h-4 text-rose-400" />
                        <span>Inflação Acumulada (IPCA)</span>
                      </td>
                      <td className="py-3 px-4 font-mono font-bold text-cyan-300">
                        {m1.ipca_pos_real_pct
                          ? `${m1.ipca_pos_real_pct}% (pós-Real)`
                          : `${m1.ipca_acumulado_pct.toLocaleString("pt-BR")}%`}
                      </td>
                      <td className="py-3 px-4 font-mono font-bold text-amber-300">
                        {m2.ipca_pos_real_pct
                          ? `${m2.ipca_pos_real_pct}% (pós-Real)`
                          : `${m2.ipca_acumulado_pct.toLocaleString("pt-BR")}%`}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <span
                          className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2.5 py-1 rounded-full ${
                            deltas.ipca_acumulado_diff_pp < 0
                              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                              : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                          }`}
                        >
                          {deltas.ipca_acumulado_diff_pp > 0
                            ? `+${deltas.ipca_acumulado_diff_pp} p.p.`
                            : `${deltas.ipca_acumulado_diff_pp} p.p.`}
                        </span>
                      </td>
                    </tr>

                    {/* Cotação do Dólar PTAX */}
                    <tr className="hover:bg-slate-800/20 transition-colors">
                      <td className="py-3 px-4 font-medium flex items-center gap-2">
                        <DollarSign className="w-4 h-4 text-cyan-400" />
                        <span>Cotação do Dólar (PTAX Inicial → Final)</span>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        {m1.cambio_variacao_pct !== null ? `${m1.cambio_variacao_pct > 0 ? "+" : ""}${m1.cambio_variacao_pct}%` : "N/D"}
                        <span className="text-xs text-slate-500 block">
                          (R$ {m1.cambio_inicial_usd_brl} → R$ {m1.cambio_final_usd_brl})
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        {m2.cambio_variacao_pct !== null ? `${m2.cambio_variacao_pct > 0 ? "+" : ""}${m2.cambio_variacao_pct}%` : "N/D"}
                        <span className="text-xs text-slate-500 block">
                          (R$ {m2.cambio_inicial_usd_brl} → R$ {m2.cambio_final_usd_brl})
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        {deltas.cambio_variacao_diff_pp !== null ? (
                          <span className="inline-flex items-center font-mono font-bold text-xs px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                            {deltas.cambio_variacao_diff_pp > 0
                              ? `+${deltas.cambio_variacao_diff_pp} p.p.`
                              : `${deltas.cambio_variacao_diff_pp} p.p.`}
                          </span>
                        ) : (
                          <span className="text-slate-500 text-xs">N/D</span>
                        )}
                      </td>
                    </tr>

                    {/* Salário Mínimo */}
                    <tr className="hover:bg-slate-800/20 transition-colors">
                      <td className="py-3 px-4 font-medium flex items-center gap-2">
                        <Coins className="w-4 h-4 text-amber-400" />
                        <span>Salário Mínimo Final (em R$ e US$)</span>
                      </td>
                      <td className="py-3 px-4 font-mono font-bold text-cyan-300">
                        {m1.salario_minimo_final_brl ? (
                          <div>
                            <span>R$ {m1.salario_minimo_final_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                            {m1.salario_minimo_final_usd && (
                              <span className="text-[11px] text-slate-400 font-normal block">
                                (US$ {m1.salario_minimo_final_usd.toFixed(2)})
                              </span>
                            )}
                          </div>
                        ) : "N/D"}
                      </td>
                      <td className="py-3 px-4 font-mono font-bold text-amber-300">
                        {m2.salario_minimo_final_brl ? (
                          <div>
                            <span>R$ {m2.salario_minimo_final_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                            {m2.salario_minimo_final_usd && (
                              <span className="text-[11px] text-slate-400 font-normal block">
                                (US$ {m2.salario_minimo_final_usd.toFixed(2)})
                              </span>
                            )}
                          </div>
                        ) : "N/D"}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {deltas.salario_minimo_brl_diff !== null && deltas.salario_minimo_brl_diff !== undefined ? (
                          <span
                            className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2.5 py-1 rounded-full ${
                              deltas.salario_minimo_brl_diff > 0
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                            }`}
                          >
                            {deltas.salario_minimo_brl_diff > 0 ? "+" : ""}
                            R$ {deltas.salario_minimo_brl_diff.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </span>
                        ) : (
                          <span className="text-slate-500 text-xs">N/D</span>
                        )}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* SEÇÃO 2: SOCIAIS & DESIGUALDADE */}
            <div className="space-y-2 pt-2">
              <div className="flex items-center gap-2 px-1 text-xs font-extrabold uppercase tracking-wider text-rose-400">
                <HeartHandshake className="w-4 h-4" />
                <span>Dimensão 2: Sociais, Pobreza & Desigualdade</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-xs text-slate-400 uppercase tracking-wider">
                      <th className="py-2.5 px-4 font-semibold">Indicador Social</th>
                      <th className="py-2.5 px-4 font-semibold text-cyan-400">
                        {m1.presidente}
                      </th>
                      <th className="py-2.5 px-4 font-semibold text-amber-400">
                        {m2.presidente}
                      </th>
                      <th className="py-2.5 px-4 font-semibold text-right">Diferença (Delta B − A)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-200">
                    {/* Extrema Pobreza Nacional */}
                    <tr className="hover:bg-slate-800/20 transition-colors">
                      <td className="py-3 px-4 font-medium flex items-center gap-2">
                        <Users className="w-4 h-4 text-rose-400" />
                        <div>
                          <span>Extrema Pobreza Nacional (% população)</span>
                          <span className="text-[11px] text-slate-500 block">Linha de Pobreza Extrema Banco Mundial / IBGE</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        {m1.sociais?.extrema_pobreza_final_pct !== undefined ? (
                          <div>
                            <span className="font-bold text-cyan-300">{m1.sociais?.extrema_pobreza_final_pct}%</span>
                            <span className="text-[11px] text-slate-500 block">
                              (Inicial: {m1.sociais?.extrema_pobreza_inicial_pct}%)
                            </span>
                          </div>
                        ) : "N/D"}
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        {m2.sociais?.extrema_pobreza_final_pct !== undefined ? (
                          <div>
                            <span className="font-bold text-amber-300">{m2.sociais?.extrema_pobreza_final_pct}%</span>
                            <span className="text-[11px] text-slate-500 block">
                              (Inicial: {m2.sociais?.extrema_pobreza_inicial_pct}%)
                            </span>
                          </div>
                        ) : "N/D"}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {deltas.extrema_pobreza_diff_pp !== null && deltas.extrema_pobreza_diff_pp !== undefined ? (
                          <span
                            className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2.5 py-1 rounded-full ${
                              deltas.extrema_pobreza_diff_pp < 0
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                            }`}
                          >
                            {deltas.extrema_pobreza_diff_pp > 0 ? `+${deltas.extrema_pobreza_diff_pp} p.p.` : `${deltas.extrema_pobreza_diff_pp} p.p.`}
                          </span>
                        ) : (
                          <span className="text-slate-500 text-xs">N/D</span>
                        )}
                      </td>
                    </tr>

                    {/* Taxa de Analfabetismo */}
                    <tr className="hover:bg-slate-800/20 transition-colors">
                      <td className="py-3 px-4 font-medium flex items-center gap-2">
                        <GraduationCap className="w-4 h-4 text-indigo-400" />
                        <div>
                          <span>Taxa de Analfabetismo (% 15+ anos)</span>
                          <span className="text-[11px] text-slate-500 block">População sem domínio de leitura e escrita (PNAD/IBGE)</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        {m1.sociais?.analfabetismo_final_pct !== undefined ? (
                          <div>
                            <span className="font-bold text-cyan-300">{m1.sociais?.analfabetismo_final_pct}%</span>
                            <span className="text-[11px] text-slate-500 block">
                              (Inicial: {m1.sociais?.analfabetismo_inicial_pct}%)
                            </span>
                          </div>
                        ) : "N/D"}
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        {m2.sociais?.analfabetismo_final_pct !== undefined ? (
                          <div>
                            <span className="font-bold text-amber-300">{m2.sociais?.analfabetismo_final_pct}%</span>
                            <span className="text-[11px] text-slate-500 block">
                              (Inicial: {m2.sociais?.analfabetismo_inicial_pct}%)
                            </span>
                          </div>
                        ) : "N/D"}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {deltas.analfabetismo_diff_pp !== null && deltas.analfabetismo_diff_pp !== undefined ? (
                          <span
                            className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2.5 py-1 rounded-full ${
                              deltas.analfabetismo_diff_pp < 0
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                            }`}
                          >
                            {deltas.analfabetismo_diff_pp > 0 ? `+${deltas.analfabetismo_diff_pp} p.p.` : `${deltas.analfabetismo_diff_pp} p.p.`}
                          </span>
                        ) : (
                          <span className="text-slate-500 text-xs">N/D</span>
                        )}
                      </td>
                    </tr>

                    {/* Insegurança Alimentar Grave */}
                    <tr className="hover:bg-slate-800/20 transition-colors">
                      <td className="py-3 px-4 font-medium flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4 text-amber-400" />
                        <div>
                          <span>Insegurança Alimentar Grave (Fome Crônica)</span>
                          <span className="text-[11px] text-slate-500 block">Escala Brasileira de Insegurança Alimentar (EBIA / Rede PENSSAN)</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        {m1.fome_final_pct !== undefined && m1.fome_final_pct !== null ? (
                          <div>
                            <span className="font-bold text-cyan-300">{m1.fome_final_pct}%</span>
                            <span className="text-[11px] text-slate-500 block">
                              (Inicial: {m1.fome_inicial_pct}%)
                            </span>
                          </div>
                        ) : "N/D"}
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        {m2.fome_final_pct !== undefined && m2.fome_final_pct !== null ? (
                          <div>
                            <span className="font-bold text-amber-300">{m2.fome_final_pct}%</span>
                            <span className="text-[11px] text-slate-500 block">
                              (Inicial: {m2.fome_inicial_pct}%)
                            </span>
                          </div>
                        ) : "N/D"}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {deltas.inseguranca_alimentar_diff_pp !== null && deltas.inseguranca_alimentar_diff_pp !== undefined ? (
                          <span
                            className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2.5 py-1 rounded-full ${
                              deltas.inseguranca_alimentar_diff_pp < 0
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                            }`}
                          >
                            {deltas.inseguranca_alimentar_diff_pp > 0 ? `+${deltas.inseguranca_alimentar_diff_pp} p.p.` : `${deltas.inseguranca_alimentar_diff_pp} p.p.`}
                          </span>
                        ) : (
                          <span className="text-slate-500 text-xs">N/D</span>
                        )}
                      </td>
                    </tr>

                    {/* Índice de Gini */}
                    <tr className="hover:bg-slate-800/20 transition-colors">
                      <td className="py-3 px-4 font-medium flex items-center gap-2">
                        <Scale className="w-4 h-4 text-cyan-400" />
                        <div>
                          <span>Índice de Gini (Desigualdade de Renda)</span>
                          <span className="text-[11px] text-slate-500 block">Escala de 0 a 1 (quanto menor, menor a desigualdade social)</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        {m1.sociais?.gini_final !== undefined ? (
                          <div>
                            <span className="font-bold text-cyan-300">{m1.sociais?.gini_final}</span>
                            <span className="text-[11px] text-slate-500 block">
                              (Inicial: {m1.sociais?.gini_inicial})
                            </span>
                          </div>
                        ) : "N/D"}
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        {m2.sociais?.gini_final !== undefined ? (
                          <div>
                            <span className="font-bold text-amber-300">{m2.sociais?.gini_final}</span>
                            <span className="text-[11px] text-slate-500 block">
                              (Inicial: {m2.sociais?.gini_inicial})
                            </span>
                          </div>
                        ) : "N/D"}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {deltas.gini_diff !== null && deltas.gini_diff !== undefined ? (
                          <span
                            className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2.5 py-1 rounded-full ${
                              deltas.gini_diff < 0
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                            }`}
                          >
                            {deltas.gini_diff > 0 ? `+${deltas.gini_diff}` : `${deltas.gini_diff}`}
                          </span>
                        ) : (
                          <span className="text-slate-500 text-xs">N/D</span>
                        )}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* SEÇÃO 3: SEGURANÇA PÚBLICA & MEIO AMBIENTE */}
            <div className="space-y-2 pt-2">
              <div className="flex items-center gap-2 px-1 text-xs font-extrabold uppercase tracking-wider text-emerald-400">
                <ShieldAlert className="w-4 h-4" />
                <span>Dimensão 3: Segurança Pública & Desmatamento Amazônia</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-xs text-slate-400 uppercase tracking-wider">
                      <th className="py-2.5 px-4 font-semibold">Indicador</th>
                      <th className="py-2.5 px-4 font-semibold text-cyan-400">
                        {m1.presidente}
                      </th>
                      <th className="py-2.5 px-4 font-semibold text-amber-400">
                        {m2.presidente}
                      </th>
                      <th className="py-2.5 px-4 font-semibold text-right">Diferença (Delta B − A)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-200">
                    {/* Taxa de Homicídios */}
                    <tr className="hover:bg-slate-800/20 transition-colors">
                      <td className="py-3 px-4 font-medium flex items-center gap-2">
                        <ShieldAlert className="w-4 h-4 text-rose-400" />
                        <div>
                          <span>Taxa de Homicídios (por 100 mil habitantes)</span>
                          <span className="text-[11px] text-slate-500 block">Atlas da Violência / IPEA / FBSP</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        <span className="font-bold text-cyan-300">{formatNumber(m1.homicidios_medio, 1)}</span>
                        <span className="text-[11px] text-slate-500 block">
                          (Início: {formatNumber(m1.homicidios_inicial, 1)} → Fim: {formatNumber(m1.homicidios_final, 1)})
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        <span className="font-bold text-amber-300">{formatNumber(m2.homicidios_medio, 1)}</span>
                        <span className="text-[11px] text-slate-500 block">
                          (Início: {formatNumber(m2.homicidios_inicial, 1)} → Fim: {formatNumber(m2.homicidios_final, 1)})
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        {deltas.homicidios_medio_diff !== null && deltas.homicidios_medio_diff !== undefined ? (
                          <span
                            className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2.5 py-1 rounded-full ${
                              deltas.homicidios_medio_diff < 0
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                            }`}
                          >
                            {deltas.homicidios_medio_diff > 0 ? `+${deltas.homicidios_medio_diff}` : `${deltas.homicidios_medio_diff}`} /100k
                          </span>
                        ) : (
                          <span className="text-slate-500 text-xs">N/D</span>
                        )}
                      </td>
                    </tr>

                    {/* Taxa de Feminicídios */}
                    <tr className="hover:bg-slate-800/20 transition-colors">
                      <td className="py-3 px-4 font-medium flex items-center gap-2">
                        <Users className="w-4 h-4 text-fuchsia-400" />
                        <div>
                          <span>Taxa de Feminicídios (por 100 mil mulheres)</span>
                          <span className="text-[11px] text-slate-500 block">Assassinatos de mulheres em razão do gênero</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        <span className="font-bold text-cyan-300">{formatNumber(m1.feminicidios_medio, 2)}</span>
                        <span className="text-[11px] text-slate-500 block">
                          (Início: {formatNumber(m1.feminicidios_inicial, 2)} → Fim: {formatNumber(m1.feminicidios_final, 2)})
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        <span className="font-bold text-amber-300">{formatNumber(m2.feminicidios_medio, 2)}</span>
                        <span className="text-[11px] text-slate-500 block">
                          (Início: {formatNumber(m2.feminicidios_inicial, 2)} → Fim: {formatNumber(m2.feminicidios_final, 2)})
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        {deltas.feminicidios_medio_diff !== null && deltas.feminicidios_medio_diff !== undefined ? (
                          <span
                            className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2.5 py-1 rounded-full ${
                              deltas.feminicidios_medio_diff < 0
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                            }`}
                          >
                            {deltas.feminicidios_medio_diff > 0 ? `+${deltas.feminicidios_medio_diff}` : `${deltas.feminicidios_medio_diff}`}
                          </span>
                        ) : (
                          <span className="text-slate-500 text-xs">N/D</span>
                        )}
                      </td>
                    </tr>

                    {/* Desmatamento Amazônia */}
                    <tr className="hover:bg-slate-800/20 transition-colors">
                      <td className="py-3 px-4 font-medium flex items-center gap-2">
                        <Trees className="w-4 h-4 text-emerald-400" />
                        <div>
                          <span>Desmatamento Amazônia (km² anual / PRODES/INPE)</span>
                          <span className="text-[11px] text-slate-500 block">Taxa oficial de supressão vegetal na Amazônia Legal</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        <span className="font-bold text-cyan-300">
                          {m1.desmatamento_medio_anual_km2 ? `${m1.desmatamento_medio_anual_km2.toLocaleString("pt-BR")} km²/ano` : "N/D"}
                        </span>
                        {m1.desmatamento_acumulado_km2 && (
                          <span className="text-[11px] text-slate-500 block">
                            (Total no mandato: {m1.desmatamento_acumulado_km2.toLocaleString("pt-BR")} km²)
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-300">
                        <span className="font-bold text-amber-300">
                          {m2.desmatamento_medio_anual_km2 ? `${m2.desmatamento_medio_anual_km2.toLocaleString("pt-BR")} km²/ano` : "N/D"}
                        </span>
                        {m2.desmatamento_acumulado_km2 && (
                          <span className="text-[11px] text-slate-500 block">
                            (Total no mandato: {m2.desmatamento_acumulado_km2.toLocaleString("pt-BR")} km²)
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {deltas.desmatamento_medio_diff !== null && deltas.desmatamento_medio_diff !== undefined ? (
                          <span
                            className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2.5 py-1 rounded-full ${
                              deltas.desmatamento_medio_diff < 0
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                            }`}
                          >
                            {deltas.desmatamento_medio_diff > 0 ? `+${deltas.desmatamento_medio_diff.toLocaleString("pt-BR")}` : `${deltas.desmatamento_medio_diff.toLocaleString("pt-BR")}`} km²
                          </span>
                        ) : (
                          <span className="text-slate-500 text-xs">N/D</span>
                        )}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* 2. GRÁFICO DE TRAJETÓRIA NORMALIZADA (ANO 1 A ANO N) */}
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-md space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
            <div>
              <div className="flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-cyan-400" />
                <h3 className="text-base font-bold text-slate-100">
                  Gráfico de Trajetória Normalizada: {metricConfig.title}
                </h3>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Alinha o <strong>Ano 1, Ano 2, Ano 3 e Ano 4</strong> de cada mandato para permitir comparação direta de ciclos
              </p>
            </div>

            {/* Seletor de Métrica do Gráfico */}
            <div className="flex items-center bg-slate-950 border border-slate-800 p-1 rounded-xl overflow-x-auto max-w-full">
              <button
                onClick={() => setChartMetric("PIB")}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  chartMetric === "PIB"
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                PIB (%)
              </button>
              <button
                onClick={() => setChartMetric("IPCA")}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  chartMetric === "IPCA"
                    ? "bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                IPCA (%)
              </button>
              <button
                onClick={() => setChartMetric("USD")}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  chartMetric === "USD"
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Dólar (R$)
              </button>
              <button
                onClick={() => setChartMetric("SALARIO")}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  chartMetric === "SALARIO"
                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Salário Mínimo
              </button>
              <button
                onClick={() => setChartMetric("POBREZA")}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  chartMetric === "POBREZA"
                    ? "bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Extr. Pobreza
              </button>
              <button
                onClick={() => setChartMetric("ANALFABETISMO")}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  chartMetric === "ANALFABETISMO"
                    ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Analfabetismo
              </button>
              <button
                onClick={() => setChartMetric("FOME")}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  chartMetric === "FOME"
                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Fome
              </button>
              <button
                onClick={() => setChartMetric("GINI")}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  chartMetric === "GINI"
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Gini
              </button>
              <button
                onClick={() => setChartMetric("HOMICIDIOS")}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  chartMetric === "HOMICIDIOS"
                    ? "bg-red-500/20 text-red-300 border border-red-500/40 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Homicídios
              </button>
              <button
                onClick={() => setChartMetric("DESMATAMENTO")}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  chartMetric === "DESMATAMENTO"
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Desmatamento
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
                  unit={metricConfig.unit}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload || !payload.length) return null;
                    const dataPoint = payload[0]?.payload;
                    return (
                      <div className="bg-slate-950/95 border border-slate-700/80 rounded-xl p-3.5 shadow-2xl text-xs space-y-2 backdrop-blur-lg">
                        <div className="font-bold text-slate-200 border-b border-slate-800 pb-1 flex items-center justify-between gap-4">
                          <span>{label} do Mandato</span>
                          <span className="text-[10px] text-slate-400">{metricConfig.title}</span>
                        </div>
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between gap-4 text-cyan-400">
                            <span>
                              {m1?.presidente} ({dataPoint?.m1_calendar_year || "N/D"}):
                            </span>
                            <span className="font-mono font-bold">
                              {dataPoint?.[metricConfig.m1Key] !== null && dataPoint?.[metricConfig.m1Key] !== undefined
                                ? `${dataPoint[metricConfig.m1Key]}${metricConfig.unit}`
                                : "N/D"}
                            </span>
                          </div>
                          <div className="flex items-center justify-between gap-4 text-amber-400">
                            <span>
                              {m2?.presidente} ({dataPoint?.m2_calendar_year || "N/D"}):
                            </span>
                            <span className="font-mono font-bold">
                              {dataPoint?.[metricConfig.m2Key] !== null && dataPoint?.[metricConfig.m2Key] !== undefined
                                ? `${dataPoint[metricConfig.m2Key]}${metricConfig.unit}`
                                : "N/D"}
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  }}
                />
                <Legend wrapperStyle={{ paddingTop: "12px", fontSize: "12px" }} />
                {metricConfig.zeroLine && (
                  <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                )}

                {/* Linha do Mandato A */}
                <Line
                  type="monotone"
                  dataKey={metricConfig.m1Key}
                  name={`${m1?.presidente || "Mandato A"}`}
                  stroke="#06b6d4"
                  strokeWidth={3}
                  dot={{ r: 5, fill: "#06b6d4" }}
                  activeDot={{ r: 7 }}
                />

                {/* Linha do Mandato B */}
                <Line
                  type="monotone"
                  dataKey={metricConfig.m2Key}
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

        {/* 3. DISTRIBUIÇÃO DE VERBAS E REPASSES FEDERAIS POR ESTADOS */}
        {repassesComp && (
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-md space-y-6">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <Building2 className="w-5 h-5 text-emerald-400" />
                <div>
                  <h2 className="text-base font-bold text-slate-100">
                    Distribuição de Verbas e Repasses Federais por Estados
                  </h2>
                  <p className="text-xs text-slate-400">
                    Confronto direto dos recursos transferidos aos 27 estados da federação em 4 áreas estruturantes
                  </p>
                </div>
              </div>
              <div className="text-right">
                <span className="text-[11px] text-slate-400 block">Total Geral Repassado (4 anos):</span>
                <span className="text-xs font-mono font-bold text-cyan-400">
                  {formatBRL(repassesComp.summary?.m1_total_geral)} (A)
                </span>
                <span className="text-xs text-slate-500 mx-1.5">vs</span>
                <span className="text-xs font-mono font-bold text-amber-400">
                  {formatBRL(repassesComp.summary?.m2_total_geral)} (B)
                </span>
              </div>
            </div>

            {/* CARDS DAS 4 ÁREAS TEMÁTICAS */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* 1. Saúde (SUS & FNS) */}
              {repassesComp.by_area?.["Saúde"] && (
                <div className="bg-slate-950/80 border border-rose-500/20 rounded-xl p-4 space-y-2.5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 text-xs font-bold text-rose-400">
                      <HeartHandshake className="w-4 h-4" />
                      Saúde (SUS & FNS)
                    </span>
                    <span
                      className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full ${
                        repassesComp.by_area["Saúde"].growth_pct >= 0
                          ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                          : "bg-rose-500/15 text-rose-300 border border-rose-500/30"
                      }`}
                    >
                      {repassesComp.by_area["Saúde"].growth_pct >= 0 ? "+" : ""}
                      {repassesComp.by_area["Saúde"].growth_pct}%
                    </span>
                  </div>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between items-center text-slate-400">
                      <span>{m1?.presidente.split(" ")[0]}:</span>
                      <strong className="text-cyan-300 font-mono">
                        {formatBRL(repassesComp.by_area["Saúde"].m1_total)}
                      </strong>
                    </div>
                    <div className="flex justify-between items-center text-slate-400">
                      <span>{m2?.presidente.split(" ")[0]}:</span>
                      <strong className="text-amber-300 font-mono">
                        {formatBRL(repassesComp.by_area["Saúde"].m2_total)}
                      </strong>
                    </div>
                  </div>
                  <div className="text-[11px] text-slate-500 border-t border-slate-900 pt-2 flex justify-between">
                    <span>Diferença:</span>
                    <strong className="text-slate-300 font-mono">
                      {formatBRL(repassesComp.by_area["Saúde"].diff_brl)}
                    </strong>
                  </div>
                </div>
              )}

              {/* 2. Educação (FUNDEB & FNDE) */}
              {repassesComp.by_area?.["Educação"] && (
                <div className="bg-slate-950/80 border border-indigo-500/20 rounded-xl p-4 space-y-2.5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 text-xs font-bold text-indigo-400">
                      <GraduationCap className="w-4 h-4" />
                      Educação (FUNDEB & FNDE)
                    </span>
                    <span
                      className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full ${
                        repassesComp.by_area["Educação"].growth_pct >= 0
                          ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                          : "bg-rose-500/15 text-rose-300 border border-rose-500/30"
                      }`}
                    >
                      {repassesComp.by_area["Educação"].growth_pct >= 0 ? "+" : ""}
                      {repassesComp.by_area["Educação"].growth_pct}%
                    </span>
                  </div>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between items-center text-slate-400">
                      <span>{m1?.presidente.split(" ")[0]}:</span>
                      <strong className="text-cyan-300 font-mono">
                        {formatBRL(repassesComp.by_area["Educação"].m1_total)}
                      </strong>
                    </div>
                    <div className="flex justify-between items-center text-slate-400">
                      <span>{m2?.presidente.split(" ")[0]}:</span>
                      <strong className="text-amber-300 font-mono">
                        {formatBRL(repassesComp.by_area["Educação"].m2_total)}
                      </strong>
                    </div>
                  </div>
                  <div className="text-[11px] text-slate-500 border-t border-slate-900 pt-2 flex justify-between">
                    <span>Diferença:</span>
                    <strong className="text-slate-300 font-mono">
                      {formatBRL(repassesComp.by_area["Educação"].diff_brl)}
                    </strong>
                  </div>
                </div>
              )}

              {/* 3. Infraestrutura & Cidades */}
              {repassesComp.by_area?.["Infraestrutura"] && (
                <div className="bg-slate-950/80 border border-amber-500/20 rounded-xl p-4 space-y-2.5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 text-xs font-bold text-amber-400">
                      <Building2 className="w-4 h-4" />
                      Infraestrutura & Cidades
                    </span>
                    <span
                      className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full ${
                        repassesComp.by_area["Infraestrutura"].growth_pct >= 0
                          ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                          : "bg-rose-500/15 text-rose-300 border border-rose-500/30"
                      }`}
                    >
                      {repassesComp.by_area["Infraestrutura"].growth_pct >= 0 ? "+" : ""}
                      {repassesComp.by_area["Infraestrutura"].growth_pct}%
                    </span>
                  </div>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between items-center text-slate-400">
                      <span>{m1?.presidente.split(" ")[0]}:</span>
                      <strong className="text-cyan-300 font-mono">
                        {formatBRL(repassesComp.by_area["Infraestrutura"].m1_total)}
                      </strong>
                    </div>
                    <div className="flex justify-between items-center text-slate-400">
                      <span>{m2?.presidente.split(" ")[0]}:</span>
                      <strong className="text-amber-300 font-mono">
                        {formatBRL(repassesComp.by_area["Infraestrutura"].m2_total)}
                      </strong>
                    </div>
                  </div>
                  <div className="text-[11px] text-slate-500 border-t border-slate-900 pt-2 flex justify-between">
                    <span>Diferença:</span>
                    <strong className="text-slate-300 font-mono">
                      {formatBRL(repassesComp.by_area["Infraestrutura"].diff_brl)}
                    </strong>
                  </div>
                </div>
              )}

              {/* 4. Segurança Pública */}
              {repassesComp.by_area?.["Segurança Pública"] && (
                <div className="bg-slate-950/80 border border-cyan-500/20 rounded-xl p-4 space-y-2.5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 text-xs font-bold text-cyan-400">
                      <ShieldAlert className="w-4 h-4" />
                      Segurança Pública
                    </span>
                    <span
                      className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full ${
                        repassesComp.by_area["Segurança Pública"].growth_pct >= 0
                          ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                          : "bg-rose-500/15 text-rose-300 border border-rose-500/30"
                      }`}
                    >
                      {repassesComp.by_area["Segurança Pública"].growth_pct >= 0 ? "+" : ""}
                      {repassesComp.by_area["Segurança Pública"].growth_pct}%
                    </span>
                  </div>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between items-center text-slate-400">
                      <span>{m1?.presidente.split(" ")[0]}:</span>
                      <strong className="text-cyan-300 font-mono">
                        {formatBRL(repassesComp.by_area["Segurança Pública"].m1_total)}
                      </strong>
                    </div>
                    <div className="flex justify-between items-center text-slate-400">
                      <span>{m2?.presidente.split(" ")[0]}:</span>
                      <strong className="text-amber-300 font-mono">
                        {formatBRL(repassesComp.by_area["Segurança Pública"].m2_total)}
                      </strong>
                    </div>
                  </div>
                  <div className="text-[11px] text-slate-500 border-t border-slate-900 pt-2 flex justify-between">
                    <span>Diferença:</span>
                    <strong className="text-slate-300 font-mono">
                      {formatBRL(repassesComp.by_area["Segurança Pública"].diff_brl)}
                    </strong>
                  </div>
                </div>
              )}
            </div>

            {/* GRÁFICO COMPARATIVO TOP ESTADOS */}
            {topStatesChartData.length > 0 && (
              <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                    <BarChart3 className="w-4 h-4 text-emerald-400" />
                    Top Estados com Maior Volume de Repasses Federais (em R$ Bilhões)
                  </span>
                  <span className="text-[11px] text-slate-400">Soma acumulada de todas as áreas</span>
                </div>
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={topStatesChartData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis dataKey="uf" stroke="#64748b" tick={{ fill: "#94a3b8", fontSize: 12 }} />
                      <YAxis stroke="#64748b" tick={{ fill: "#94a3b8", fontSize: 12 }} unit=" bi" />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload || !payload.length) return null;
                          const d = payload[0]?.payload;
                          return (
                            <div className="bg-slate-950/95 border border-slate-700 p-2.5 rounded-lg text-xs space-y-1">
                              <p className="font-bold text-slate-200">
                                {d.nome} ({d.uf})
                              </p>
                              <p className="text-cyan-400">
                                {m1?.presidente}: R$ {d.m1_bi} bilhões
                              </p>
                              <p className="text-amber-400">
                                {m2?.presidente}: R$ {d.m2_bi} bilhões
                              </p>
                            </div>
                          );
                        }}
                      />
                      <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "8px" }} />
                      <Bar dataKey="m1_bi" name={`${m1?.presidente || "Mandato A"}`} fill="#06b6d4" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="m2_bi" name={`${m2?.presidente || "Mandato B"}`} fill="#f59e0b" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* BARRA DE FILTROS DA TABELA DE REPASSES */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-2">
              <div className="flex items-center gap-2 flex-wrap">
                {/* Filtro por Região */}
                <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5">
                  {["TODAS", "Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"].map((reg) => (
                    <button
                      key={reg}
                      onClick={() => setRepasseRegionFilter(reg)}
                      className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-all cursor-pointer ${
                        repasseRegionFilter === reg
                          ? "bg-slate-800 text-emerald-400 shadow-sm"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      {reg}
                    </button>
                  ))}
                </div>
              </div>

              {/* Busca por Estado */}
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Filtrar estado ou UF..."
                  value={repasseSearchTerm}
                  onChange={(e) => setRepasseSearchTerm(e.target.value)}
                  className="bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500 w-full sm:w-48"
                />
              </div>
            </div>

            {/* TABELA DETALHADA POR ESTADO (27 UFs) */}
            <div className="overflow-x-auto max-h-96 custom-scrollbar border border-slate-800 rounded-xl">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-slate-950/90 sticky top-0 z-10 backdrop-blur-md">
                  <tr className="border-b border-slate-800 text-slate-400 uppercase tracking-wider">
                    <th className="py-2.5 px-3.5 font-bold">UF / Estado</th>
                    <th className="py-2.5 px-3 font-semibold">Região</th>
                    <th className="py-2.5 px-3 font-semibold text-cyan-400">
                      Total {m1?.presidente.split(" ")[0]}
                    </th>
                    <th className="py-2.5 px-3 font-semibold text-amber-400">
                      Total {m2?.presidente.split(" ")[0]}
                    </th>
                    <th className="py-2.5 px-3 font-semibold">Diferença (B − A)</th>
                    <th className="py-2.5 px-3 font-semibold">Variação %</th>
                    <th className="py-2.5 px-3.5 font-semibold text-right">Per Capita (A vs B)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-200">
                  {filteredUFs.map((item) => (
                    <tr key={item.uf} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-2.5 px-3.5 font-bold flex items-center gap-1.5">
                        <span className="px-1.5 py-0.5 rounded bg-slate-800 text-emerald-400 font-mono text-[10px]">
                          {item.uf}
                        </span>
                        <span>{item.estado_nome}</span>
                      </td>
                      <td className="py-2.5 px-3 text-slate-400">{item.regiao}</td>
                      <td className="py-2.5 px-3 font-mono font-bold text-cyan-300">
                        {formatBRL(item.m1_total)}
                      </td>
                      <td className="py-2.5 px-3 font-mono font-bold text-amber-300">
                        {formatBRL(item.m2_total)}
                      </td>
                      <td className="py-2.5 px-3 font-mono">
                        <span
                          className={`font-semibold ${
                            item.diff_brl >= 0 ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {item.diff_brl >= 0 ? "+" : ""}
                          {formatBRL(item.diff_brl)}
                        </span>
                      </td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`inline-flex items-center font-mono font-bold text-[10px] px-2 py-0.5 rounded-full ${
                            item.growth_pct >= 0
                              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                              : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                          }`}
                        >
                          {item.growth_pct >= 0 ? `+${item.growth_pct}%` : `${item.growth_pct}%`}
                        </span>
                      </td>
                      <td className="py-2.5 px-3.5 text-right font-mono text-slate-400">
                        <span className="text-cyan-400">R$ {item.m1_per_capita.toFixed(0)}</span>
                        <span className="mx-1 text-slate-600">/</span>
                        <span className="text-amber-400 font-bold">R$ {item.m2_per_capita.toFixed(0)}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 4. RESUMO HISTÓRICO & EQUIPE ECONÔMICA */}
        {m1 && m2 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 text-xs text-slate-400 space-y-3">
              <div className="flex items-center gap-2 text-cyan-400 font-bold text-sm">
                <Award className="w-4 h-4" />
                <span>Marcos Históricos & Equipe: {m1.presidente}</span>
              </div>
              <div className="space-y-1">
                <span className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider block">
                  Ministros da Fazenda / Economia:
                </span>
                <p className="text-slate-200">
                  {m1.ministros_fazenda_principais?.join(", ") || "Nenhum mapeado"}
                </p>
              </div>
              <div className="space-y-1">
                <span className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider block">
                  Principais Reformas e Acontecimentos:
                </span>
                <ul className="list-disc list-inside space-y-1">
                  {m1.marcos_economicos_principais?.map((marco, i) => (
                    <li key={i} className="text-slate-300 leading-relaxed">
                      {marco}
                    </li>
                  )) || <li>Dados históricos não informados</li>}
                </ul>
              </div>
            </div>

            <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 text-xs text-slate-400 space-y-3">
              <div className="flex items-center gap-2 text-amber-400 font-bold text-sm">
                <Award className="w-4 h-4" />
                <span>Marcos Históricos & Equipe: {m2.presidente}</span>
              </div>
              <div className="space-y-1">
                <span className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider block">
                  Ministros da Fazenda / Economia:
                </span>
                <p className="text-slate-200">
                  {m2.ministros_fazenda_principais?.join(", ") || "Nenhum mapeado"}
                </p>
              </div>
              <div className="space-y-1">
                <span className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider block">
                  Principais Reformas e Acontecimentos:
                </span>
                <ul className="list-disc list-inside space-y-1">
                  {m2.marcos_economicos_principais?.map((marco, i) => (
                    <li key={i} className="text-slate-300 leading-relaxed">
                      {marco}
                    </li>
                  )) || <li>Dados históricos não informados</li>}
                </ul>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
