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

interface MacroeconomicChartProps {
  data: ResumoMacroeconomicoAnual[];
  selectedMandateId?: string | null;
}

const MANDATE_LOOKUP: Record<string, { start: number; end: number; label: string }> = {
  "itamar-franco-1992": { start: 1993, end: 1994, label: "Itamar Franco" },
  "fhc-1995": { start: 1995, end: 1998, label: "FHC 1" },
  "fhc-1999": { start: 1999, end: 2002, label: "FHC 2" },
  "lula-2003": { start: 2003, end: 2006, label: "Lula 1" },
  "lula-2007": { start: 2007, end: 2010, label: "Lula 2" },
  "dilma-2011": { start: 2011, end: 2014, label: "Dilma 1" },
  "dilma-2015": { start: 2015, end: 2016, label: "Dilma 2" },
  "temer-2016": { start: 2016, end: 2018, label: "Michel Temer" },
  "bolsonaro-2019": { start: 2019, end: 2022, label: "Jair Bolsonaro" },
  "lula-2023": { start: 2023, end: 2026, label: "Lula 3" },
};

// Delimitação dos períodos presidenciais para as ReferenceAreas
const MANDATE_ZONES = [
  { id: "itamar", label: "Itamar", start: 1993, end: 1994, color: "#10b981" },
  { id: "fhc1", label: "FHC 1", start: 1995, end: 1998, color: "#3b82f6" },
  { id: "fhc2", label: "FHC 2", start: 1999, end: 2002, color: "#2563eb" },
  { id: "lula1", label: "Lula 1", start: 2003, end: 2006, color: "#ef4444" },
  { id: "lula2", label: "Lula 2", start: 2007, end: 2010, color: "#dc2626" },
  { id: "dilma1", label: "Dilma 1", start: 2011, end: 2014, color: "#b91c1c" },
  { id: "dilma2", label: "Dilma 2", start: 2015, end: 2016, color: "#991b1b" },
  { id: "temer", label: "Temer", start: 2016, end: 2018, color: "#059669" },
  { id: "bolsonaro", label: "Bolsonaro", start: 2019, end: 2022, color: "#d97706" },
  { id: "lula3", label: "Lula 3", start: 2023, end: 2026, color: "#ef4444" },
];

interface CustomTooltipProps {
  active?: boolean;
  payload?: any[];
  label?: string | number;
  showIbovespa?: boolean;
}

function MacroeconomicTooltip({ active, payload, label, showIbovespa }: CustomTooltipProps) {
  if (active && payload && payload.length) {
    const item = payload[0].payload as ResumoMacroeconomicoAnual;
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
            {item.pib_crescimento_real_pct !== null
              ? `${item.pib_crescimento_real_pct > 0 ? "+" : ""}${item.pib_crescimento_real_pct.toFixed(2)}%`
              : "N/D"}
          </span>
        </div>
        <div className="flex items-center justify-between text-rose-400">
          <span>Inflação Anual (IPCA):</span>
          <span className="font-bold">
            {item.ipca_acumulado_ano_pct !== null
              ? `${item.ipca_acumulado_ano_pct.toFixed(2)}%`
              : "N/D"}
          </span>
        </div>
        {item.cambio_dolar_medio && (
          <div className="flex items-center justify-between text-slate-400 border-t border-slate-800/80 pt-1 mt-1">
            <span>Câmbio Médio:</span>
            <span className="font-medium text-slate-200">
              R$ {item.cambio_dolar_medio.toFixed(2)}
            </span>
          </div>
        )}
        {showIbovespa && item.ibovespa_fechamento && (
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
}: MacroeconomicChartProps) {
  const [filterMode, setFilterMode] = useState<"pos_real" | "completo">("pos_real");
  const [showIbovespa, setShowIbovespa] = useState<boolean>(false);
  const [zoomMandate, setZoomMandate] = useState<boolean>(false);

  const activeMandateInfo = selectedMandateId ? MANDATE_LOOKUP[selectedMandateId] || null : null;

  // Filtragem conforme toggle e zoom no mandato com useMemo
  const chartData = React.useMemo(() => {
    let filtered = filterMode === "pos_real"
      ? data.filter((d) => d.ano >= 1995)
      : data;

    if (activeMandateInfo && zoomMandate) {
      filtered = data.filter((d) => d.ano >= activeMandateInfo.start && d.ano <= activeMandateInfo.end);
    }
    return filtered;
  }, [data, filterMode, activeMandateInfo, zoomMandate]);

  return (
    <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-md">
      {/* Cabeçalho do Gráfico com Título e Seletor de Escala */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
        <div>
          <div className="flex items-center gap-2">
            <LineChart className="w-5 h-5 text-emerald-400" />
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
              onClick={() => setZoomMandate(!zoomMandate)}
              className={`px-3 py-1.5 rounded-xl font-medium transition-all text-xs flex items-center gap-1.5 border cursor-pointer ${
                zoomMandate
                  ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-lg shadow-emerald-500/10"
                  : "bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200"
              }`}
              title={`Filtrar apenas os anos do governo ${activeMandateInfo.label}`}
            >
              <Filter className="w-3.5 h-3.5 text-emerald-400" />
              <span>Zoom: {activeMandateInfo.label} ({activeMandateInfo.start}-{activeMandateInfo.end})</span>
            </button>
          )}

          {/* Botão de Ativação do Ibovespa */}
          <button
            onClick={() => setShowIbovespa(!showIbovespa)}
            className={`px-3 py-1.5 rounded-xl font-medium transition-all text-xs flex items-center gap-1.5 border cursor-pointer ${
              showIbovespa
                ? "bg-purple-500/20 text-purple-300 border-purple-500/40 shadow-lg shadow-purple-500/10"
                : "bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200"
            }`}
            title="Alternar exibição da linha do Ibovespa com escala própria em pontos"
          >
            <TrendingUp className="w-3.5 h-3.5 text-purple-400" />
            <span>Ibovespa (Pontos B3)</span>
          </button>

          {/* Toggle de Recorte Histórico */}
          <div className="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
            <button
              onClick={() => setFilterMode("pos_real")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
                filterMode === "pos_real"
                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Pós-Plano Real (1995-2026)
            </button>
            <button
              onClick={() => setFilterMode("completo")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
                filterMode === "completo"
                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Histórico Completo (1993-2026)
            </button>
          </div>
        </div>
      </div>

      {filterMode === "completo" && (
        <div className="mb-4 flex items-center gap-2 p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs">
          <Info className="w-4 h-4 flex-shrink-0" />
          <span>
            Atenção: A inflação de 1993 atingiu 2.477% a.a. no período pré-Real de Itamar Franco, provocando compressão visual das séries posteriores. Use &quot;Pós-Plano Real&quot; para análise de alta precisão.
          </span>
        </div>
      )}

      {/* Área do Gráfico */}
      <div className="w-full h-80 sm:h-96">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 15, right: 25, bottom: 20, left: 10 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" opacity={0.6} />

            {/* Delimitação dos Períodos Presidenciais (ReferenceArea) */}
            {MANDATE_ZONES.map((zone) => {
              if (filterMode === "pos_real" && zone.end < 1995) return null;
              return (
                <ReferenceArea
                  key={zone.id}
                  x1={Math.max(zone.start, filterMode === "pos_real" ? 1995 : 1993)}
                  x2={zone.end}
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
              domain={[-6, 10]}
            />

            {/* Eixo Y Direito: IPCA */}
            <YAxis
              yAxisId="right"
              orientation="right"
              stroke="#f43f5e"
              fontSize={11}
              tickLine={false}
              tickFormatter={(v) => `${v}%`}
              domain={filterMode === "pos_real" ? [0, 25] : [0, "auto"]}
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
                domain={[0, 150000]}
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
