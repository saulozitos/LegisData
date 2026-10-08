"use client";

import React, { useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ReferenceArea,
  ReferenceLine,
} from "recharts";
import { ResumoMacroeconomicoAnual } from "@/services/api";
import { LineChart, Filter, Info, TrendingUp } from "lucide-react";
import { isNum } from "@/lib/format";
import type { MandateRange } from "@/lib/mandate";

interface MacroeconomicChartProps {
  data: ResumoMacroeconomicoAnual[];
  selectedMandateId?: string | null;
  /** Mandatos (derivados da API de presidentes) usados para delimitar os períodos e o zoom. */
  mandates?: MandateRange[];
}

const ZONE_COLORS = ["#10b981", "#3b82f6", "#ef4444", "#d97706", "#8b5cf6", "#06b6d4"];

// Planos econômicos anteriores ao Real: valores monetários não são comparáveis em R$.
const LAST_PRE_REAL_YEAR = 1994;

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ payload: ResumoMacroeconomicoAnual }>;
  label?: string | number;
  showIbovespa?: boolean;
}

function MacroeconomicTooltip({ active, payload, label, showIbovespa }: CustomTooltipProps) {
  if (active && payload && payload.length) {
    const item = payload[0].payload;
    const pib = item.pib_crescimento_real_pct;
    const ipca = item.ipca_acumulado_ano_pct;
    return (
      <div className="bg-slate-950/95 border border-slate-700/80 p-3.5 rounded-xl shadow-2xl backdrop-blur-md text-xs space-y-1.5 min-w-[220px]">
        <div className="flex items-center justify-between border-b border-slate-800 pb-1.5 mb-2">
          <span className="font-bold text-slate-100 text-sm">Ano {label}</span>
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-300">
            {item.presidente_dominante}
          </span>
        </div>
        <div className="flex items-center justify-between text-emerald-400">
          <span>Crescimento PIB Real:</span>
          <span className="font-bold">
            {isNum(pib) ? `${pib > 0 ? "+" : ""}${pib.toFixed(2)}%` : "N/D"}
          </span>
        </div>
        <div className="flex items-center justify-between text-rose-400">
          <span>Inflação Anual (IPCA):</span>
          <span className="font-bold">{isNum(ipca) ? `${ipca.toFixed(2)}%` : "N/D"}</span>
        </div>
        {isNum(item.cambio_dolar_medio) && (
          <div className="flex items-center justify-between text-slate-400 border-t border-slate-800/80 pt-1 mt-1">
            <span>Câmbio Médio:</span>
            <span className="font-medium text-slate-200">
              {item.ano <= LAST_PRE_REAL_YEAR
                ? "moeda pré-Real (não comparável)"
                : `R$ ${item.cambio_dolar_medio.toFixed(2)}`}
            </span>
          </div>
        )}
        {showIbovespa && isNum(item.ibovespa_fechamento) && (
          <div className="flex items-center justify-between text-purple-400 border-t border-slate-800/80 pt-1 mt-1">
            <span>Ibovespa (Fechamento):</span>
            <span className="font-bold">
              {Math.round(item.ibovespa_fechamento).toLocaleString("pt-BR")} pts
            </span>
          </div>
        )}
      </div>
    );
  }
  return null;
}

function MacroeconomicChartBase({
  data,
  selectedMandateId,
  mandates = [],
}: MacroeconomicChartProps) {
  const [filterMode, setFilterMode] = useState<"pos_real" | "completo">("pos_real");
  const [showIbovespa, setShowIbovespa] = useState<boolean>(false);
  const [zoomMandate, setZoomMandate] = useState<boolean>(false);

  const activeMandateInfo = selectedMandateId
    ? mandates.find((m) => m.id === selectedMandateId) || null
    : null;

  const firstYear = data.length > 0 ? Math.min(...data.map((d) => d.ano)) : null;
  const lastYear = data.length > 0 ? Math.max(...data.map((d) => d.ano)) : null;
  const firstPosRealYear = 1995;

  // Filtragem conforme toggle e zoom no mandato com useMemo
  const chartData = React.useMemo(() => {
    let filtered = filterMode === "pos_real"
      ? data.filter((d) => d.ano >= firstPosRealYear)
      : data;

    if (activeMandateInfo && zoomMandate) {
      filtered = data.filter((d) => d.ano >= activeMandateInfo.start && d.ano <= activeMandateInfo.end);
    }
    return filtered;
  }, [data, filterMode, activeMandateInfo, zoomMandate]);

  const zones = React.useMemo(
    () => mandates.map((m, i) => ({ ...m, color: ZONE_COLORS[i % ZONE_COLORS.length] })),
    [mandates]
  );

  if (data.length === 0) {
    return (
      <div role="status" className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-8 text-center text-sm text-slate-300">
        Dado indisponível: a série macroeconômica anual não foi retornada pela API.
      </div>
    );
  }

  return (
    <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-md">
      {/* Cabeçalho do Gráfico com Título e Seletor de Escala */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
        <div>
          <div className="flex items-center gap-2">
            <LineChart className="w-5 h-5 text-emerald-400" aria-hidden="true" />
            <h2 className="text-base font-bold text-slate-100">
              Trajetória Macroeconômica: PIB vs. Inflação {showIbovespa ? "vs. Ibovespa" : ""}
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Eixo Esquerdo: Variação Real do PIB (%) • Eixo Direito: IPCA Anual (%){showIbovespa ? " • Eixo Roxo: Ibovespa (Pontos)" : ""} • Fundo: Períodos Presidenciais
          </p>
        </div>

        {/* Controles: Ibovespa e Recorte Temporal */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Botão de Zoom no Mandato Selecionado */}
          {activeMandateInfo && (
            <button
              type="button"
              aria-pressed={zoomMandate}
              onClick={() => setZoomMandate(!zoomMandate)}
              className={`px-3 py-1.5 rounded-xl font-medium transition-all text-xs flex items-center gap-1.5 border cursor-pointer ${
                zoomMandate
                  ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-lg shadow-emerald-500/10"
                  : "bg-slate-950 text-slate-300 border-slate-800 hover:text-slate-100"
              }`}
              title={`Filtrar apenas os anos do governo ${activeMandateInfo.label}`}
            >
              <Filter className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />
              <span>Zoom: {activeMandateInfo.label} ({activeMandateInfo.start}-{activeMandateInfo.end})</span>
            </button>
          )}

          {/* Botão de Ativação do Ibovespa */}
          <button
            type="button"
            aria-pressed={showIbovespa}
            onClick={() => setShowIbovespa(!showIbovespa)}
            className={`px-3 py-1.5 rounded-xl font-medium transition-all text-xs flex items-center gap-1.5 border cursor-pointer ${
              showIbovespa
                ? "bg-purple-500/20 text-purple-300 border-purple-500/40 shadow-lg shadow-purple-500/10"
                : "bg-slate-950 text-slate-300 border-slate-800 hover:text-slate-100"
            }`}
            title="Alternar exibição da linha do Ibovespa com escala própria em pontos"
          >
            <TrendingUp className="w-3.5 h-3.5 text-purple-400" aria-hidden="true" />
            <span>Ibovespa (Pontos B3)</span>
          </button>

          {/* Toggle de Recorte Histórico */}
          <div className="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
            <button
              type="button"
              aria-pressed={filterMode === "pos_real"}
              onClick={() => setFilterMode("pos_real")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
                filterMode === "pos_real"
                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Pós-Plano Real ({firstPosRealYear}-{lastYear})
            </button>
            <button
              type="button"
              aria-pressed={filterMode === "completo"}
              onClick={() => setFilterMode("completo")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
                filterMode === "completo"
                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Histórico Completo ({firstYear}-{lastYear})
            </button>
          </div>
        </div>
      </div>

      {filterMode === "completo" && (
        <div className="mb-4 flex items-center gap-2 p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs">
          <Info className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
          <span>
            Atenção: a inflação do período pré-Real (anterior a 1995) foi muito superior à atual, o que comprime visualmente as séries posteriores, e valores em moeda anterior ao Real não são comparáveis. Use &quot;Pós-Plano Real&quot; para análise de alta precisão.
          </span>
        </div>
      )}

      {/* Área do Gráfico */}
      <div
        role="img"
        aria-label="Gráfico de barras e linhas: crescimento real do PIB e inflação anual (IPCA) por ano, com períodos presidenciais ao fundo"
        className="w-full h-80 sm:h-96"
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 15, right: 25, bottom: 20, left: 10 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" opacity={0.6} />

            {/* Delimitação dos Períodos Presidenciais (ReferenceArea) */}
            {zones.map((zone) => {
              if (filterMode === "pos_real" && zone.end < firstPosRealYear) return null;
              if (lastYear !== null && zone.start > lastYear) return null;
              return (
                <ReferenceArea
                  key={zone.id}
                  x1={Math.max(zone.start, filterMode === "pos_real" ? firstPosRealYear : (firstYear ?? zone.start))}
                  x2={Math.min(zone.end, lastYear ?? zone.end)}
                  yAxisId="left"
                  fill={zone.color}
                  fillOpacity={0.07}
                  stroke={zone.color}
                  strokeOpacity={0.2}
                  strokeDasharray="2 2"
                />
              );
            })}

            {/* Linha Zero do PIB */}
            <ReferenceLine y={0} yAxisId="left" stroke="#475569" strokeDasharray="2 2" />

            {/* Eixo X: Anos */}
            <XAxis
              dataKey="ano"
              stroke="#64748b"
              fontSize={11}
              tickLine={false}
              dy={10}
            />

            {/* Eixo Y Esquerdo: PIB Real */}
            <YAxis
              yAxisId="left"
              stroke="#10b981"
              fontSize={11}
              tickLine={false}
              tickFormatter={(v) => `${v}%`}
              domain={[(min: number) => Math.min(-2, Math.floor(min)), (max: number) => Math.max(5, Math.ceil(max))]}
            />

            {/* Eixo Y Direito: IPCA */}
            <YAxis
              yAxisId="right"
              orientation="right"
              stroke="#f43f5e"
              fontSize={11}
              tickLine={false}
              tickFormatter={(v) => `${v}%`}
              domain={filterMode === "pos_real" ? [0, (max: number) => Math.max(15, Math.ceil(max))] : [0, "auto"]}
            />

            {/* Eixo Y Terciário: Ibovespa Pontos (quando ativado) */}
            {showIbovespa && (
              <YAxis
                yAxisId="ibov"
                orientation="right"
                stroke="#a855f7"
                fontSize={10}
                tickLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                domain={[0, "auto"]}
              />
            )}

            <Tooltip content={<MacroeconomicTooltip showIbovespa={showIbovespa} />} />
            <Legend
              verticalAlign="top"
              height={36}
              iconType="circle"
              wrapperStyle={{ fontSize: 12, paddingBottom: 10 }}
            />

            {/* Barra/Linha de Crescimento do PIB (Verde Esmeralda) */}
            <Bar
              yAxisId="left"
              dataKey="pib_crescimento_real_pct"
              name="Crescimento PIB Real (%)"
              fill="#10b981"
              opacity={0.7}
              radius={[4, 4, 0, 0]}
            />

            {/* Linha de Inflação IPCA (Rosa Choque / Carmim) */}
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="ipca_acumulado_ano_pct"
              name="Inflação Anual IPCA (%)"
              stroke="#f43f5e"
              strokeWidth={2.5}
              dot={{ r: 3, fill: "#f43f5e", strokeWidth: 0 }}
              activeDot={{ r: 6, stroke: "#ffffff", strokeWidth: 2 }}
            />

            {/* Linha do Ibovespa (Roxo B3) com escala própria em pontos */}
            {showIbovespa && (
              <Line
                yAxisId="ibov"
                type="monotone"
                dataKey="ibovespa_fechamento"
                name="Ibovespa (Pontos B3)"
                stroke="#a855f7"
                strokeWidth={2.5}
                dot={{ r: 3, fill: "#a855f7", strokeWidth: 0 }}
                activeDot={{ r: 6, stroke: "#ffffff", strokeWidth: 2 }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default React.memo(MacroeconomicChartBase);
