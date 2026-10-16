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
import { LineChart, Filter } from "lucide-react";
import { isNum } from "@/lib/format";
import type { MandateRange } from "@/lib/mandate";

interface MacroeconomicChartProps {
  data: ResumoMacroeconomicoAnual[];
  selectedMandateId?: string | null;
  /** Mandatos (derivados da API de presidentes) usados para delimitar os períodos e o zoom. */
  mandates?: MandateRange[];
}

const ZONE_COLORS = ["#10b981", "#3b82f6", "#ef4444", "#d97706", "#8b5cf6", "#06b6d4"];

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ payload: ResumoMacroeconomicoAnual }>;
  label?: string | number;
}

function MacroeconomicTooltip({ active, payload, label }: CustomTooltipProps) {
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
              R$ {item.cambio_dolar_medio.toFixed(2)}
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
  const [zoomMandate, setZoomMandate] = useState<boolean>(false);

  const activeMandateInfo = selectedMandateId
    ? mandates.find((m) => m.id === selectedMandateId) || null
    : null;

  const firstYear = data.length > 0 ? Math.min(...data.map((d) => d.ano)) : null;
  const lastYear = data.length > 0 ? Math.max(...data.map((d) => d.ano)) : null;

  // Zoom no mandato selecionado
  const chartData = React.useMemo(() => {
    if (activeMandateInfo && zoomMandate) {
      return data.filter((d) => d.ano >= activeMandateInfo.start && d.ano <= activeMandateInfo.end);
    }
    return data;
  }, [data, activeMandateInfo, zoomMandate]);

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
              Trajetória Macroeconômica: PIB vs. Inflação
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Eixo Esquerdo: Variação Real do PIB (%) • Eixo Direito: IPCA Anual (%) • Fundo: Períodos Presidenciais
          </p>
        </div>

        {/* Controles */}
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

        </div>
      </div>

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
              if (firstYear !== null && zone.end < firstYear) return null;
              if (lastYear !== null && zone.start > lastYear) return null;
              return (
                <ReferenceArea
                  key={zone.id}
                  x1={Math.max(zone.start, firstYear ?? zone.start)}
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
              domain={[0, (max: number) => Math.max(15, Math.ceil(max))]}
            />

            <Tooltip content={<MacroeconomicTooltip />} />
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

          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default React.memo(MacroeconomicChartBase);
