"use client";

import React, { useState } from "react";
import {
  Building2,
  HeartPulse,
  GraduationCap,
  HardHat,
  Shield,
  Layers,
  Search
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell
} from "recharts";
import { getFederalTransfers } from "../services/api";
import { useApi } from "@/hooks/useApi";
import { fmtNum } from "@/lib/format";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";

interface FederalTransfersPanelProps {
  mandateId: string;
}

const REGIAO_COLORS: Record<string, string> = {
  "Sudeste": "#3b82f6",
  "Nordeste": "#10b981",
  "Sul": "#f59e0b",
  "Norte": "#06b6d4",
  "Centro-Oeste": "#8b5cf6"
};

// Aparência por área temática; áreas desconhecidas usam o padrão (as áreas vêm da API).
const AREA_STYLE: Record<string, { icon: LucideIcon; active: string }> = {
  "Saúde": { icon: HeartPulse, active: "bg-rose-500" },
  "Educação": { icon: GraduationCap, active: "bg-blue-500" },
  "Infraestrutura": { icon: HardHat, active: "bg-amber-500" },
  "Segurança Pública": { icon: Shield, active: "bg-purple-500" },
};
const DEFAULT_AREA_STYLE = { icon: Layers, active: "bg-emerald-500" };

export default function FederalTransfersPanel({ mandateId }: FederalTransfersPanelProps) {
  const [selectedArea, setSelectedArea] = useState<string>("TODAS");
  const [sortBy, setSortBy] = useState<"total" | "per_capita">("total");
  const [searchTerm, setSearchTerm] = useState("");

  // A consulta sem filtro alimenta a lista de áreas (os botões nunca desaparecem ao filtrar).
  const base = useApi(`federal-transfers:${mandateId}:ALL`, (signal) => getFederalTransfers(mandateId, undefined, signal));
  const filtered = useApi(
    `federal-transfers:${mandateId}:${selectedArea}`,
    (signal) => getFederalTransfers(mandateId, selectedArea, signal),
    selectedArea !== "TODAS"
  );
  const active = selectedArea === "TODAS" ? base : filtered;
  const data = active.data ?? null;
  const areas = Object.keys(base.data?.areas_resumo ?? {});

  if (base.loading) return <LoadingState label="Carregando repasses federais..." />;
  if (base.error) return <ErrorState onRetry={base.retry} />;
  if (!base.data) return <EmptyState title="Repasses federais indisponíveis" />;

  // Filtrar e agrupar por UF (caso TODAS as áreas estejam selecionadas, somamos por UF)
  const ufMap = new Map<string, {
    uf: string;
    nome: string;
    regiao: string;
    populacao: number;
    total_brl: number;
    per_capita: number;
  }>();

  (data?.por_uf ?? []).forEach((item) => {
    if (!ufMap.has(item.uf)) {
      ufMap.set(item.uf, {
        uf: item.uf,
        nome: item.estado_nome,
        regiao: item.regiao,
        populacao: item.populacao_estimada,
        total_brl: item.valor_pago_brl,
        per_capita: item.valor_per_capita_brl
      });
    } else {
      const existing = ufMap.get(item.uf)!;
      existing.total_brl += item.valor_pago_brl;
      existing.per_capita = existing.populacao > 0 ? existing.total_brl / existing.populacao : 0;
    }
  });

  let ufsList = Array.from(ufMap.values());

  // Busca textual
  if (searchTerm.trim()) {
    ufsList = ufsList.filter(
      (u) =>
        u.nome.toLowerCase().includes(searchTerm.toLowerCase()) ||
        u.uf.toLowerCase().includes(searchTerm.toLowerCase()) ||
        u.regiao.toLowerCase().includes(searchTerm.toLowerCase())
    );
  }

  // Ordenação
  ufsList.sort((a, b) => {
    if (sortBy === "total") return b.total_brl - a.total_brl;
    return b.per_capita - a.per_capita;
  });

  const top10ChartData = ufsList.slice(0, 10);
  const totalBrlBi = data ? fmtNum(data.total_repassado_brl / 1_000_000_000) : null;

  return (
    <div className="space-y-6">
      {/* Cabeçalho do Painel */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 backdrop-blur-md">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                <Building2 className="w-5 h-5" aria-hidden="true" />
              </span>
              <h2 className="text-xl font-extrabold text-slate-100 tracking-tight">
                Distribuição de Verbas e Repasses Federais por Estado (UF)
              </h2>
            </div>
            <p className="text-xs text-slate-400">
              Execução orçamentária da União transferida aos Estados e ao Distrito Federal nas áreas prioritárias de desenvolvimento.
            </p>
          </div>

          <div className="bg-slate-950 p-3 rounded-2xl border border-slate-800 text-right self-start md:self-auto">
            <span className="text-[10px] uppercase font-bold text-slate-400 block">Total Repassado no Mandato ({selectedArea})</span>
            <span className="text-xl font-black text-emerald-400 font-mono">
              {totalBrlBi ? `R$ ${totalBrlBi} Bilhões` : "Indisponível"}
            </span>
          </div>
        </div>

        {/* Filtros por Área Temática (áreas vindas da API) */}
        <div className="flex flex-wrap items-center gap-2 mt-6 pt-4 border-t border-slate-800/80">
          {["TODAS", ...areas].map((area) => {
            const style = AREA_STYLE[area] ?? DEFAULT_AREA_STYLE;
            const Icon = area === "TODAS" ? Layers : style.icon;
            const isActive = selectedArea === area;
            return (
              <button
                type="button"
                key={area}
                aria-pressed={isActive}
                onClick={() => setSelectedArea(area)}
                className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all ${
                  isActive
                    ? `${area === "TODAS" ? "bg-emerald-500" : style.active} text-slate-950 shadow-md`
                    : "bg-slate-950 border border-slate-800 text-slate-300 hover:text-slate-100"
                }`}
              >
                <Icon className="w-3.5 h-3.5" aria-hidden="true" />
                {area === "TODAS" ? "Todas as Áreas" : area}
              </button>
            );
          })}
        </div>
      </div>

      {active.loading && <LoadingState label="Atualizando repasses..." />}
      {active.error && <ErrorState onRetry={active.retry} />}
      {!active.loading && !active.error && !data && (
        <EmptyState message="Nenhum repasse encontrado para a área selecionada." />
      )}

      {data && (
        <>
      {/* Gráfico Top 10 Estados */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 backdrop-blur-md">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-slate-200">
            Top 10 Estados com Maior Destinação de Recursos Federais ({selectedArea})
          </h3>
          <span className="text-xs text-slate-400 font-medium">Valores em Bilhões de R$</span>
        </div>

        <div
          role="img"
          aria-label={`Gráfico de barras com os 10 estados que mais receberam repasses federais (${selectedArea})`}
          className="h-72 w-full"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={top10ChartData} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
              <XAxis dataKey="uf" stroke="#64748b" tick={{ fontSize: 11 }} />
              <YAxis
                stroke="#64748b"
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => `R$ ${(v / 1_000_000_000).toFixed(0)}B`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#090d16",
                  borderColor: "#334155",
                  borderRadius: "12px",
                  fontSize: "12px"
                }}
                formatter={(val) => [
                  `R$ ${fmtNum(Number(val) / 1_000_000_000, 2)} Bilhões`,
                  "Repasse Total"
                ]}
              />
              <Bar dataKey="total_brl" radius={[6, 6, 0, 0]}>
                {top10ChartData.map((entry) => (
                  <Cell
                    key={`cell-${entry.uf}`}
                    fill={REGIAO_COLORS[entry.regiao] || "#10b981"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Tabela Interativa de Repasses por UF */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 backdrop-blur-md space-y-4">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="relative w-full sm:w-80">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
            <input
              type="text"
              aria-label="Buscar estado, UF ou região"
              placeholder="Buscar Estado, UF ou Região..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3.5 py-2 text-xs font-medium text-slate-200 placeholder:text-slate-400 focus:outline-none focus:border-emerald-500"
            />
          </div>

          {/* Toggle de Ordenação */}
          <div className="flex items-center gap-2 self-start sm:self-auto">
            <span className="text-xs text-slate-400 font-semibold">Ordenar por:</span>
            <button
              type="button"
              aria-pressed={sortBy === "total"}
              onClick={() => setSortBy("total")}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
                sortBy === "total"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                  : "bg-slate-950 text-slate-300 border border-slate-800 hover:text-slate-100"
              }`}
            >
              Volume Total (R$)
            </button>
            <button
              type="button"
              aria-pressed={sortBy === "per_capita"}
              onClick={() => setSortBy("per_capita")}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
                sortBy === "per_capita"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                  : "bg-slate-950 text-slate-300 border border-slate-800 hover:text-slate-100"
              }`}
            >
              Per Capita (R$/hab)
            </button>
          </div>
        </div>

        {/* Tabela com Scroll */}
        <div className="overflow-x-auto rounded-2xl border border-slate-800/80 max-h-96 overflow-y-auto">
          <table className="w-full text-left border-collapse text-xs">
            <caption className="sr-only">Repasses federais por Unidade da Federação ({selectedArea})</caption>
            <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider sticky top-0 z-10">
              <tr>
                <th scope="col" className="py-3 px-4">UF</th>
                <th scope="col" className="py-3 px-4">Estado</th>
                <th scope="col" className="py-3 px-4">Região</th>
                <th scope="col" className="py-3 px-4 text-right">População (IBGE)</th>
                <th scope="col" className="py-3 px-4 text-right">Repasse Total ({selectedArea})</th>
                <th scope="col" className="py-3 px-4 text-right">Per Capita (R$/hab)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-medium">
              {ufsList.map((u) => (
                <tr key={u.uf} className="hover:bg-slate-800/30 transition-colors">
                  <td className="py-2.5 px-4 font-bold text-slate-100 font-mono">
                    {u.uf}
                  </td>
                  <td className="py-2.5 px-4 text-slate-200 font-semibold">{u.nome}</td>
                  <td className="py-2.5 px-4">
                    <span
                      style={{ color: REGIAO_COLORS[u.regiao] || "#94a3b8" }}
                      className="font-bold text-[11px]"
                    >
                      {u.regiao}
                    </span>
                  </td>
                  <td className="py-2.5 px-4 text-right text-slate-400 font-mono">
                    {u.populacao.toLocaleString("pt-BR")}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono font-bold text-emerald-400">
                    R$ {u.total_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono text-cyan-300 font-bold">
                    R$ {u.per_capita.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
        </>
      )}
    </div>
  );
}
