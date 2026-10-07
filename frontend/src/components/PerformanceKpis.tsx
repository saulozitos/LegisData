"use client";

import React, { useState, useMemo } from "react";
import {
  MandatoPerformance,
  PresidenteHistorico,
  ResumoMacroeconomicoAnual,
} from "@/services/api";
import {
  TrendingUp,
  Percent,
  DollarSign,
  Coins,
  Briefcase,
  ShieldAlert,
  HeartHandshake,
  Trees,
  Sparkles,
  Award,
  Layers,
  X,
  BarChart2,
  ArrowRight,
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
} from "recharts";

interface PerformanceKpisProps {
  performance: MandatoPerformance | null;
  presidentMeta: PresidenteHistorico | null;
  annualData?: ResumoMacroeconomicoAnual[];
}

type KpiType =
  | "pib"
  | "ipca"
  | "dolar"
  | "salario_minimo"
  | "desemprego"
  | "homicidios"
  | "feminicidios"
  | "desmatamento";

interface KpiConfig {
  id: KpiType;
  title: string;
  category: string;
  icon: React.ReactNode;
  colorHex: string;
  borderColor: string;
  bgColor: string;
  textColor: string;
  badgeText: string;
  unit: string;
  chartType: "bar" | "line";
  dataKey: string;
}

export default function PerformanceKpis({
  performance,
  presidentMeta,
  annualData = [],
}: PerformanceKpisProps) {
  const [selectedKpi, setSelectedKpi] = useState<KpiType | null>(null);

  const isItamar = performance?.id_mandato.includes("itamar");

  // Dados filtrados para o mandato selecionado
  const chartData = useMemo(() => {
    if (performance?.valores_anuais && performance.valores_anuais.length > 0) {
      return performance.valores_anuais;
    }
    if (!performance || annualData.length === 0) return [];
    const anos = performance.anos_cobertos.split("-").map((s) => parseInt(s.trim(), 10));
    if (anos.length >= 2 && !isNaN(anos[0]) && !isNaN(anos[1])) {
      return annualData.filter((d) => d.ano >= anos[0] && d.ano <= anos[1]);
    }
    return [];
  }, [performance, annualData]);

  // Formatação de valores dos KPIs
  const ipcaFormatado = performance
    ? isItamar
      ? `${performance.ipca_pos_real_pct.toFixed(1)}% (pós-Real)`
      : `${performance.ipca_acumulado_pct.toFixed(1)}%`
    : "6.2% a.a.";

  const pibMedio = performance?.pib_medio_anual_pct ?? 2.3;
  const isPibPositivo = pibMedio >= 0;

  const cambioIni = performance?.cambio_inicial_usd_brl
    ? `R$ ${performance.cambio_inicial_usd_brl.toFixed(2)}`
    : "R$ 0.85";
  const cambioFim = performance?.cambio_final_usd_brl
    ? `R$ ${performance.cambio_final_usd_brl.toFixed(2)}`
    : "R$ 5.14";

  const salMinIni = performance?.salario_minimo_inicial_brl
    ? `R$ ${performance.salario_minimo_inicial_brl.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
    : "R$ 100";
  const salMinFim = performance?.salario_minimo_final_brl
    ? `R$ ${performance.salario_minimo_final_brl.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
    : "R$ 1.621";

  const desempIni = performance?.desemprego_inicial_pct
    ? `${performance.desemprego_inicial_pct.toFixed(1)}%`
    : "N/D";
  const desempFim = performance?.desemprego_final_pct
    ? `${performance.desemprego_final_pct.toFixed(1)}%`
    : "N/D";

  const desmatMedio = performance?.desmatamento_medio_anual_km2
    ? `${Math.round(performance.desmatamento_medio_anual_km2).toLocaleString("pt-BR")} km²/ano`
    : "12.850 km²/ano";
  const desmatAcumulado = performance?.desmatamento_acumulado_km2
    ? `${Math.round(performance.desmatamento_acumulado_km2).toLocaleString("pt-BR")} km²`
    : "385.500 km²";

  const homicIni = performance?.homicidios_inicial
    ? `${performance.homicidios_inicial.toFixed(1)}`
    : "20.9";
  const homicFim = performance?.homicidios_final
    ? `${performance.homicidios_final.toFixed(1)}`
    : "18.2";
  const homicMed = performance?.homicidios_medio
    ? `${performance.homicidios_medio.toFixed(1)}`
    : "19.3";

  const femIni = performance?.feminicidios_inicial
    ? `${performance.feminicidios_inicial.toFixed(2)}`
    : "1.42";
  const femFim = performance?.feminicidios_final
    ? `${performance.feminicidios_final.toFixed(2)}`
    : "1.30";
  const femMed = performance?.feminicidios_medio
    ? `${performance.feminicidios_medio.toFixed(2)}`
    : "1.36";

  // Configurações visuais e analíticas de cada KPI
  const KPI_CONFIGS: Record<KpiType, KpiConfig> = {
    pib: {
      id: "pib",
      title: "Crescimento do PIB",
      category: "Atividade Econômica",
      icon: <TrendingUp className="w-4 h-4" />,
      colorHex: isPibPositivo ? "#10b981" : "#f43f5e",
      borderColor: isPibPositivo ? "border-emerald-500/30" : "border-rose-500/30",
      bgColor: isPibPositivo ? "bg-emerald-500/10" : "bg-rose-500/10",
      textColor: isPibPositivo ? "text-emerald-400" : "text-rose-400",
      badgeText: isPibPositivo ? "Expansão" : "Retração",
      unit: "% ao ano",
      chartType: "bar",
      dataKey: "pib_crescimento_real_pct",
    },
    ipca: {
      id: "ipca",
      title: "Inflação Acumulada (IPCA)",
      category: "Poder de Compra",
      icon: <Percent className="w-4 h-4" />,
      colorHex: "#f43f5e",
      borderColor: "border-rose-500/30",
      bgColor: "bg-rose-500/10",
      textColor: "text-rose-400",
      badgeText: "IBGE",
      unit: "% no ano",
      chartType: "line",
      dataKey: "ipca_acumulado_ano_pct",
    },
    dolar: {
      id: "dolar",
      title: "Cotação do Dólar (PTAX)",
      category: "Câmbio & Moeda",
      icon: <DollarSign className="w-4 h-4" />,
      colorHex: "#38bdf8",
      borderColor: "border-sky-500/30",
      bgColor: "bg-sky-500/10",
      textColor: "text-sky-400",
      badgeText: "Banco Central",
      unit: "R$",
      chartType: "line",
      dataKey: "cotacao_dolar_fechamento",
    },
    salario_minimo: {
      id: "salario_minimo",
      title: "Salário Mínimo Nominal",
      category: "Renda do Trabalhador",
      icon: <Coins className="w-4 h-4" />,
      colorHex: "#10b981",
      borderColor: "border-emerald-500/30",
      bgColor: "bg-emerald-500/10",
      textColor: "text-emerald-400",
      badgeText: "Lei Federal",
      unit: "R$",
      chartType: "bar",
      dataKey: "salario_minimo",
    },
    desemprego: {
      id: "desemprego",
      title: "Taxa de Desemprego",
      category: "Mercado de Trabalho",
      icon: <Briefcase className="w-4 h-4" />,
      colorHex: "#f59e0b",
      borderColor: "border-amber-500/30",
      bgColor: "bg-amber-500/10",
      textColor: "text-amber-400",
      badgeText: "PNAD / IBGE",
      unit: "%",
      chartType: "line",
      dataKey: "taxa_desemprego_anual",
    },
    homicidios: {
      id: "homicidios",
      title: "Taxa de Homicídios",
      category: "Segurança Pública",
      icon: <ShieldAlert className="w-4 h-4" />,
      colorHex: "#a855f7",
      borderColor: "border-purple-500/30",
      bgColor: "bg-purple-500/10",
      textColor: "text-purple-400",
      badgeText: "IPEA / FBSP",
      unit: "por 100k hab.",
      chartType: "line",
      dataKey: "taxa_homicidios",
    },
    feminicidios: {
      id: "feminicidios",
      title: "Taxa de Feminicídios",
      category: "Proteção à Mulher",
      icon: <HeartHandshake className="w-4 h-4" />,
      colorHex: "#ec4899",
      borderColor: "border-pink-500/30",
      bgColor: "bg-pink-500/10",
      textColor: "text-pink-400",
      badgeText: "FBSP",
      unit: "por 100k hab.",
      chartType: "line",
      dataKey: "taxa_feminicidios",
    },
    desmatamento: {
      id: "desmatamento",
      title: "Desmatamento Amazônia",
      category: "Meio Ambiente",
      icon: <Trees className="w-4 h-4" />,
      colorHex: "#84cc16",
      borderColor: "border-lime-500/30",
      bgColor: "bg-lime-500/10",
      textColor: "text-lime-400",
      badgeText: "INPE / PRODES",
      unit: "km²/ano",
      chartType: "bar",
      dataKey: "taxa_desmatamento_amazonia",
    },
  };

  // Cálculo da variação do KPI selecionado para o modal
  const selectedKpiSummary = useMemo(() => {
    if (!selectedKpi || chartData.length === 0) return null;
    const config = KPI_CONFIGS[selectedKpi];
    const key = config.dataKey;

    const validItems = chartData.filter((d) => (d as any)[key] !== null && (d as any)[key] !== undefined);
    if (validItems.length === 0) return null;

    const first = validItems[0];
    const last = validItems[validItems.length - 1];
    const valFirst = (first as any)[key] as number;
    const valLast = (last as any)[key] as number;

    const delta = valLast - valFirst;
    const pctChange = valFirst !== 0 ? ((valLast - valFirst) / Math.abs(valFirst)) * 100 : 0;

    let variationText = "";
    if (selectedKpi === "salario_minimo") {
      variationText = `Passou de R$ ${valFirst.toLocaleString("pt-BR")} em ${first.ano} para R$ ${valLast.toLocaleString("pt-BR")} em ${last.ano} (${pctChange >= 0 ? "+" : ""}${pctChange.toFixed(1)}%)`;
    } else if (selectedKpi === "dolar") {
      variationText = `Passou de R$ ${valFirst.toFixed(2)} em ${first.ano} para R$ ${valLast.toFixed(2)} em ${last.ano} (${pctChange >= 0 ? "+" : ""}${pctChange.toFixed(1)}%)`;
    } else if (selectedKpi === "pib") {
      variationText = `Variou de ${valFirst > 0 ? "+" : ""}${valFirst.toFixed(2)}% em ${first.ano} para ${valLast > 0 ? "+" : ""}${valLast.toFixed(2)}% em ${last.ano}`;
    } else if (selectedKpi === "ipca") {
      variationText = `Inflação anual foi de ${valFirst.toFixed(1)}% em ${first.ano} e fechou em ${valLast.toFixed(1)}% em ${last.ano}`;
    } else if (selectedKpi === "desemprego") {
      variationText = `Desocupação variou de ${valFirst.toFixed(1)}% em ${first.ano} para ${valLast.toFixed(1)}% em ${last.ano} (${delta > 0 ? "+" : ""}${delta.toFixed(1)} p.p.)`;
    } else if (selectedKpi === "homicidios") {
      variationText = `Taxa de homicídios foi de ${valFirst.toFixed(1)} em ${first.ano} para ${valLast.toFixed(1)} em ${last.ano} (${pctChange >= 0 ? "+" : ""}${pctChange.toFixed(1)}%)`;
    } else if (selectedKpi === "feminicidios") {
      variationText = `Taxa de feminicídios foi de ${valFirst.toFixed(2)} em ${first.ano} para ${valLast.toFixed(2)} em ${last.ano}`;
    } else if (selectedKpi === "desmatamento") {
      variationText = `Desmatamento anual foi de ${Math.round(valFirst).toLocaleString("pt-BR")} km² em ${first.ano} para ${Math.round(valLast).toLocaleString("pt-BR")} km² em ${last.ano}`;
    }

    return {
      firstYear: first.ano,
      lastYear: last.ano,
      valFirst,
      valLast,
      delta,
      pctChange,
      variationText,
    };
  }, [selectedKpi, chartData]);

  return (
    <div className="space-y-4">
      {/* 1. Header do Resumo do Mandato Selecionado */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-emerald-400" />
          <h3 className="text-xs font-bold tracking-wider uppercase text-slate-300">
            {performance
              ? `Painel de KPIs do Mandato: ${performance.presidente} (${performance.anos_cobertos})`
              : "Resumo Histórico Geral da Nova República (1995 - 2026)"}
          </h3>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-slate-400">
          <span className="hidden sm:inline">Role para o lado para mais indicadores</span>
          <span className="px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-300 font-semibold">
            Clique no card para ver o gráfico detalhado
          </span>
        </div>
      </div>

      {/* 2. Lista de Cards com Rolagem Horizontal Fluida */}
      <div className="flex flex-nowrap overflow-x-auto gap-4 pb-4 pt-1 custom-scrollbar snap-x scroll-smooth">
        {/* Card 1: Crescimento Médio do PIB */}
        <div
          onClick={() => setSelectedKpi("pib")}
          className="min-w-[280px] shrink-0 snap-start bg-slate-900/80 border border-emerald-500/30 hover:border-emerald-400/80 rounded-2xl p-4.5 backdrop-blur-md relative overflow-hidden group cursor-pointer hover:ring-2 hover:ring-emerald-400/60 transition-all shadow-lg hover:shadow-emerald-950/20 flex flex-col justify-between"
        >
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-300">
                Crescimento do PIB
              </span>
              <div
                className={`w-8 h-8 rounded-lg border flex items-center justify-center ${
                  isPibPositivo
                    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                    : "bg-rose-500/10 border-rose-500/30 text-rose-400"
                }`}
              >
                <TrendingUp className="w-4 h-4" />
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <span
                className={`text-2xl font-extrabold tracking-tight ${
                  isPibPositivo ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {pibMedio > 0 ? `+${pibMedio.toFixed(2)}%` : `${pibMedio.toFixed(2)}%`}
              </span>
              <span className="text-xs text-slate-400 font-medium">ao ano</span>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">
              {performance?.pib_crescimento_acumulado_pct !== undefined
                ? `Acumulado no período: ${performance.pib_crescimento_acumulado_pct > 0 ? "+" : ""}${performance.pib_crescimento_acumulado_pct.toFixed(1)}%`
                : "Taxa de variação real anual (IBGE)"}
            </p>
          </div>
          <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-emerald-400/90 font-bold group-hover:text-emerald-300">
            <span>Ver evolução ano a ano</span>
            <BarChart2 className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </div>

        {/* Card 2: Inflação Acumulada (IPCA) */}
        <div
          onClick={() => setSelectedKpi("ipca")}
          className="min-w-[280px] shrink-0 snap-start bg-slate-900/80 border border-rose-500/30 hover:border-rose-400/80 rounded-2xl p-4.5 backdrop-blur-md relative overflow-hidden group cursor-pointer hover:ring-2 hover:ring-rose-400/60 transition-all shadow-lg hover:shadow-rose-950/20 flex flex-col justify-between"
        >
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-300">
                Inflação Acumulada (IPCA)
              </span>
              <div className="w-8 h-8 rounded-lg bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400">
                <Percent className="w-4 h-4" />
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-extrabold text-slate-100 tracking-tight">
                {ipcaFormatado}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">
              {isItamar
                ? "*Pós-Real (julho a dezembro de 1994)"
                : performance
                ? `Composição oficial do IPCA/IBGE (${performance.anos_cobertos})`
                : "Índice Nacional de Preços ao Consumidor Amplo"}
            </p>
          </div>
          <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-rose-400/90 font-bold group-hover:text-rose-300">
            <span>Ver inflação anual</span>
            <BarChart2 className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </div>

        {/* Card 3: Cotação do Dólar (PTAX Fechamento) */}
        <div
          onClick={() => setSelectedKpi("dolar")}
          className="min-w-[280px] shrink-0 snap-start bg-slate-900/80 border border-sky-500/30 hover:border-sky-400/80 rounded-2xl p-4.5 backdrop-blur-md relative overflow-hidden group cursor-pointer hover:ring-2 hover:ring-sky-400/60 transition-all shadow-lg hover:shadow-sky-950/20 flex flex-col justify-between"
        >
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-300">
                Cotação Dólar (PTAX)
              </span>
              <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400">
                <DollarSign className="w-4 h-4" />
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-xl sm:text-2xl font-extrabold text-sky-300 tracking-tight">
                {cambioIni} ➔ {cambioFim}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">
              {performance?.cambio_variacao_pct !== null && performance?.cambio_variacao_pct !== undefined
                ? `Variação cambial: ${performance.cambio_variacao_pct > 0 ? "+" : ""}${performance.cambio_variacao_pct.toFixed(1)}% no mandato`
                : "Fechamento anual (Banco Central do Brasil)"}
            </p>
          </div>
          <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-sky-400/90 font-bold group-hover:text-sky-300">
            <span>Ver histórico do Dólar</span>
            <BarChart2 className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </div>

        {/* Card 4: Salário Mínimo Nominal */}
        <div
          onClick={() => setSelectedKpi("salario_minimo")}
          className="min-w-[280px] shrink-0 snap-start bg-slate-900/80 border border-emerald-500/30 hover:border-emerald-400/80 rounded-2xl p-4.5 backdrop-blur-md relative overflow-hidden group cursor-pointer hover:ring-2 hover:ring-emerald-400/60 transition-all shadow-lg hover:shadow-emerald-950/20 flex flex-col justify-between"
        >
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-300">
                Salário Mínimo Nominal
              </span>
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                <Coins className="w-4 h-4" />
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-xl sm:text-2xl font-extrabold text-slate-100 tracking-tight">
                {salMinIni} ➔ {salMinFim}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">
              {performance?.salario_minimo_inicial_usd && performance?.salario_minimo_final_usd
                ? `Em dólar: US$ ${performance.salario_minimo_inicial_usd.toFixed(0)} ➔ US$ ${performance.salario_minimo_final_usd.toFixed(0)}`
                : "Valor nominal aprovado por legislação federal"}
            </p>
          </div>
          <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-emerald-400/90 font-bold group-hover:text-emerald-300">
            <span>Ver evolução do salário</span>
            <BarChart2 className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </div>

        {/* Card 5: Taxa de Desemprego */}
        <div
          onClick={() => setSelectedKpi("desemprego")}
          className="min-w-[280px] shrink-0 snap-start bg-slate-900/80 border border-amber-500/30 hover:border-amber-400/80 rounded-2xl p-4.5 backdrop-blur-md relative overflow-hidden group cursor-pointer hover:ring-2 hover:ring-amber-400/60 transition-all shadow-lg hover:shadow-amber-950/20 flex flex-col justify-between"
        >
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-300">
                Taxa de Desemprego
              </span>
              <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
                <Briefcase className="w-4 h-4" />
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-xl sm:text-2xl font-extrabold text-amber-400 tracking-tight">
                {desempIni} ➔ {desempFim}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">
              {performance?.desemprego_medio_pct
                ? `Média de desocupação do mandato: ${performance.desemprego_medio_pct.toFixed(1)}%`
                : "Taxa apurada pela PME e PNAD Contínua (IBGE)"}
            </p>
          </div>
          <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-amber-400/90 font-bold group-hover:text-amber-300">
            <span>Ver curva de desemprego</span>
            <BarChart2 className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </div>

        {/* Card 6: Segurança Pública - Homicídios */}
        <div
          onClick={() => setSelectedKpi("homicidios")}
          className="min-w-[280px] shrink-0 snap-start bg-slate-900/80 border border-purple-500/30 hover:border-purple-400/80 rounded-2xl p-4.5 backdrop-blur-md relative overflow-hidden group cursor-pointer hover:ring-2 hover:ring-purple-400/60 transition-all shadow-lg hover:shadow-purple-950/20 flex flex-col justify-between"
        >
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-300">
                Segurança: Homicídios
              </span>
              <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400">
                <ShieldAlert className="w-4 h-4" />
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-xl sm:text-2xl font-extrabold text-purple-300 tracking-tight">
                {homicIni} ➔ {homicFim}
              </span>
              <span className="text-[11px] text-slate-400">/ 100k hab.</span>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">
              Média do mandato: <strong>{homicMed}</strong> por 100 mil habitantes (IPEA / FBSP)
            </p>
          </div>
          <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-purple-400/90 font-bold group-hover:text-purple-300">
            <span>Ver curva de homicídios</span>
            <BarChart2 className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </div>

        {/* Card 7: Proteção à Mulher - Feminicídios */}
        <div
          onClick={() => setSelectedKpi("feminicidios")}
          className="min-w-[280px] shrink-0 snap-start bg-slate-900/80 border border-pink-500/30 hover:border-pink-400/80 rounded-2xl p-4.5 backdrop-blur-md relative overflow-hidden group cursor-pointer hover:ring-2 hover:ring-pink-400/60 transition-all shadow-lg hover:shadow-pink-950/20 flex flex-col justify-between"
        >
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-300">
                Proteção: Feminicídios
              </span>
              <div className="w-8 h-8 rounded-lg bg-pink-500/10 border border-pink-500/30 flex items-center justify-center text-pink-400">
                <HeartHandshake className="w-4 h-4" />
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-xl sm:text-2xl font-extrabold text-pink-300 tracking-tight">
                {femIni} ➔ {femFim}
              </span>
              <span className="text-[11px] text-slate-400">/ 100k hab.</span>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">
              Média: <strong>{femMed}</strong> / 100 mil (Fórum Brasileiro de Segurança Pública)
            </p>
          </div>
          <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-pink-400/90 font-bold group-hover:text-pink-300">
            <span>Ver taxa de feminicídios</span>
            <BarChart2 className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </div>

        {/* Card 8: Desmatamento da Amazônia */}
        <div
          onClick={() => setSelectedKpi("desmatamento")}
          className="min-w-[280px] shrink-0 snap-start bg-slate-900/80 border border-lime-500/30 hover:border-lime-400/80 rounded-2xl p-4.5 backdrop-blur-md relative overflow-hidden group cursor-pointer hover:ring-2 hover:ring-lime-400/60 transition-all shadow-lg hover:shadow-lime-950/20 flex flex-col justify-between"
        >
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-300">
                Desmatamento Amazônia
              </span>
              <div className="w-8 h-8 rounded-lg bg-lime-500/10 border border-lime-500/30 flex items-center justify-center text-lime-400">
                <Trees className="w-4 h-4" />
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-xl sm:text-2xl font-extrabold text-slate-100 tracking-tight">
                {desmatMedio}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">
              {desmatAcumulado} acumulados (INPE / PRODES)
            </p>
          </div>
          <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-lime-400/90 font-bold group-hover:text-lime-300">
            <span>Ver corte anual em km²</span>
            <BarChart2 className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </div>
      </div>

      {/* 3. Modal Drill-Down de Evolução Anual do Indicador Selecionado */}
      {selectedKpi && (
        <div
          className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4 animate-in fade-in duration-200"
          onClick={() => setSelectedKpi(null)}
        >
          <div
            className="bg-slate-900 border border-slate-700/80 rounded-3xl p-6 sm:p-8 max-w-3xl w-full shadow-2xl relative animate-in zoom-in-95 duration-200 space-y-6"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Cabeçalho do Modal */}
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <div
                  className={`w-12 h-12 rounded-2xl flex items-center justify-center border shadow-md ${KPI_CONFIGS[selectedKpi].bgColor} ${KPI_CONFIGS[selectedKpi].borderColor} ${KPI_CONFIGS[selectedKpi].textColor}`}
                >
                  {KPI_CONFIGS[selectedKpi].icon}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-xl font-extrabold text-white">
                      {KPI_CONFIGS[selectedKpi].title}
                    </h3>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300 uppercase tracking-wider">
                      {KPI_CONFIGS[selectedKpi].category}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {performance
                      ? `Mandato de ${performance.presidente} (${performance.anos_cobertos})`
                      : "Série histórica anual"}
                  </p>
                </div>
              </div>

              <button
                onClick={() => setSelectedKpi(null)}
                className="w-9 h-9 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Destaque da Variação no Mandato */}
            {selectedKpiSummary && (
              <div className="bg-slate-950/60 border border-slate-800 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-1">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    Variação no Mandato Presidencial
                  </span>
                  <p className="text-sm font-semibold text-slate-200">
                    {selectedKpiSummary.variationText}
                  </p>
                </div>
                <div className="flex items-center gap-2 self-start sm:self-center">
                  <span
                    className={`text-xs font-bold px-3 py-1.5 rounded-xl border ${
                      selectedKpiSummary.pctChange >= 0
                        ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                        : "bg-rose-500/10 border-rose-500/30 text-rose-400"
                    }`}
                  >
                    {selectedKpiSummary.pctChange >= 0 ? "+" : ""}
                    {selectedKpiSummary.pctChange.toFixed(1)}% no período
                  </span>
                </div>
              </div>
            )}

            {/* Gráfico Recharts de Evolução Ano a Ano */}
            <div className="bg-slate-950/40 border border-slate-800/80 rounded-2xl p-4 sm:p-5">
              <div className="h-64 sm:h-72 w-full">
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    {KPI_CONFIGS[selectedKpi].chartType === "bar" ? (
                      <BarChart data={chartData} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
                        <XAxis
                          dataKey="ano"
                          stroke="#94a3b8"
                          fontSize={12}
                          tickLine={false}
                        />
                        <YAxis
                          stroke="#94a3b8"
                          fontSize={12}
                          tickLine={false}
                          domain={["auto", "auto"]}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "#0f172a",
                            border: "1px solid #334155",
                            borderRadius: "12px",
                            fontSize: "12px",
                          }}
                          formatter={(val: any) => [
                            typeof val === "number" ? `${val.toLocaleString("pt-BR")} ${KPI_CONFIGS[selectedKpi].unit}` : val,
                            KPI_CONFIGS[selectedKpi].title,
                          ]}
                          labelFormatter={(label) => `Ano de ${label}`}
                        />
                        <Bar
                          dataKey={KPI_CONFIGS[selectedKpi].dataKey}
                          fill={KPI_CONFIGS[selectedKpi].colorHex}
                          radius={[6, 6, 0, 0]}
                        >
                          {chartData.map((entry, index) => {
                            const val = (entry as any)[KPI_CONFIGS[selectedKpi].dataKey];
                            let barColor = KPI_CONFIGS[selectedKpi].colorHex;
                            if (selectedKpi === "pib") {
                              barColor = val >= 0 ? "#10b981" : "#f43f5e";
                            }
                            return <Cell key={`cell-${index}`} fill={barColor} />;
                          })}
                        </Bar>
                      </BarChart>
                    ) : (
                      <LineChart data={chartData} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
                        <XAxis
                          dataKey="ano"
                          stroke="#94a3b8"
                          fontSize={12}
                          tickLine={false}
                        />
                        <YAxis
                          stroke="#94a3b8"
                          fontSize={12}
                          tickLine={false}
                          domain={["auto", "auto"]}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "#0f172a",
                            border: "1px solid #334155",
                            borderRadius: "12px",
                            fontSize: "12px",
                          }}
                          formatter={(val: any) => [
                            typeof val === "number" ? `${val.toLocaleString("pt-BR")} ${KPI_CONFIGS[selectedKpi].unit}` : val,
                            KPI_CONFIGS[selectedKpi].title,
                          ]}
                          labelFormatter={(label) => `Ano de ${label}`}
                        />
                        <Line
                          type="monotone"
                          dataKey={KPI_CONFIGS[selectedKpi].dataKey}
                          stroke={KPI_CONFIGS[selectedKpi].colorHex}
                          strokeWidth={3}
                          dot={{ r: 5, fill: KPI_CONFIGS[selectedKpi].colorHex }}
                          activeDot={{ r: 7 }}
                        />
                      </LineChart>
                    )}
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-slate-500 text-xs">
                    Dados anuais não disponíveis para o período deste mandato.
                  </div>
                )}
              </div>
            </div>

            {/* Pílulas de valores ano a ano */}
            <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
              {chartData.map((d) => {
                const val = (d as any)[KPI_CONFIGS[selectedKpi].dataKey];
                return (
                  <div
                    key={d.ano}
                    className="flex-shrink-0 px-3 py-2 rounded-xl bg-slate-950/70 border border-slate-800/80 text-center space-y-0.5"
                  >
                    <span className="text-[10px] text-slate-400 block font-semibold">
                      {d.ano}
                    </span>
                    <span className="text-xs font-bold text-slate-100 block">
                      {val !== null && val !== undefined
                        ? typeof val === "number"
                          ? val.toLocaleString("pt-BR")
                          : val
                        : "-"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* 4. Caixa de Contexto Político-Econômico (Ministros da Fazenda + Grandes Marcos) */}
      <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-md">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Ministros da Fazenda / Economia */}
          <div>
            <div className="flex items-center gap-2 mb-2.5">
              <Award className="w-4 h-4 text-emerald-400" />
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Ministros da Fazenda / Economia no Período
              </h3>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {presidentMeta?.ministros_fazenda_chave &&
              presidentMeta.ministros_fazenda_chave.length > 0 ? (
                presidentMeta.ministros_fazenda_chave.map((min, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-800/80 border border-slate-700/60 text-xs font-medium text-slate-200"
                  >
                    <span>{min.nome}</span>
                    {min.papel && (
                      <span className="text-[10px] text-emerald-400 font-bold">
                        ({min.papel})
                      </span>
                    )}
                  </span>
                ))
              ) : (
                <span className="text-xs text-slate-500">
                  {performance?.ministros_fazenda_principais?.join(", ") || "Informação não disponível"}
                </span>
              )}
            </div>
          </div>

          {/* Grandes Marcos e Políticas Estruturantes */}
          <div>
            <div className="flex items-center gap-2 mb-2.5">
              <Layers className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Marcos e Políticas Econômicas
              </h3>
            </div>
            <ul className="space-y-1.5">
              {presidentMeta?.marcos_economicos &&
              presidentMeta.marcos_economicos.length > 0 ? (
                presidentMeta.marcos_economicos.slice(0, 3).map((marco, idx) => (
                  <li
                    key={idx}
                    className="text-xs text-slate-300 flex items-start gap-2"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 mt-1.5 flex-shrink-0" />
                    <span>{marco}</span>
                  </li>
                ))
              ) : (
                <li className="text-xs text-slate-500">
                  Consulte os relatórios detalhados na esteira de dados.
                </li>
              )}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
