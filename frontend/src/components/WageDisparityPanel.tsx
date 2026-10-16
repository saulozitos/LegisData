"use client";

import React, { useState } from "react";
import {
  TrendingUp,
  Scale,
  Search,
  CheckCircle2,
  XCircle,
  HelpCircle,
} from "lucide-react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid
} from "recharts";
import { getWageDisparity } from "../services/api";
import { useApi } from "@/hooks/useApi";
import { safeExternalUrl } from "@/lib/safeUrl";
import { fmtNum, isNum } from "@/lib/format";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";

export default function WageDisparityPanel() {
  const { data, loading, error, retry } = useApi("wage-disparity", (signal) => getWageDisparity(signal));
  const [chartMode, setChartMode] = useState<"valores" | "indices">("valores");
  const [searchTerm, setSearchTerm] = useState("");
  const [voteFilter, setVoteFilter] = useState<string>("ALL");

  if (loading) return <LoadingState label="Carregando disparidade salarial..." />;
  if (error) return <ErrorState onRetry={retry} />;
  if (!data || !data.serie_historica?.length || !data.estatisticas_disparidade) {
    return <EmptyState title="Disparidade salarial indisponível" />;
  }

  const { serie_historica, votacao_salario_minimo, estatisticas_disparidade } = data;
  const votosAmostra = votacao_salario_minimo?.votos_amostra ?? [];
  const primeiroAno = serie_historica[0].ano;
  const ultimoAno = serie_historica[serie_historica.length - 1].ano;
  const picoPresidente = serie_historica.find((s) => s.ano === estatisticas_disparidade.pico_multiplo_ano)?.presidente_dominante;
  const fmtBrlValue = (v: number | null | undefined) =>
    isNum(v) ? `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}` : "Indisponível";
  const fmtGrowth = (v: number | null | undefined) =>
    isNum(v) ? `+${v.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}%` : "Variação indisponível";

  // Filtrar deputados na votação
  const filteredVotes = votosAmostra.filter((v) => {
    const matchesSearch =
      v.deputado_nome.toLowerCase().includes(searchTerm.toLowerCase()) ||
      v.partido_sigla.toLowerCase().includes(searchTerm.toLowerCase()) ||
      v.uf.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesVote = voteFilter === "ALL" || v.voto === voteFilter;
    return matchesSearch && matchesVote;
  });

  return (
    <div className="space-y-6">
      {/* Cabeçalho do Painel */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 backdrop-blur-md">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400">
                <Scale className="w-5 h-5" aria-hidden="true" />
              </span>
              <h2 className="text-xl font-extrabold text-slate-100 tracking-tight">
                Salário Mínimo do Trabalhador vs Salário Parlamentar ({primeiroAno} - {ultimoAno})
              </h2>
            </div>
            <p className="text-xs text-slate-400 max-w-3xl leading-relaxed">
              Análise comparativa da remuneração legal dos Deputados e Senadores (Decretos Legislativos) em relação ao Salário Mínimo nacional e à inflação acumulada do IPCA pós-Plano Real.
            </p>
          </div>

          {/* Toggle de Modo do Gráfico */}
          <div className="flex items-center bg-slate-950 p-1.5 rounded-2xl border border-slate-800 self-start md:self-auto">
            <button
              type="button"
              aria-pressed={chartMode === "valores"}
              onClick={() => setChartMode("valores")}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all ${
                chartMode === "valores"
                  ? "bg-amber-500 text-slate-950 shadow-md"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Valores Nominais (R$)
            </button>
            <button
              type="button"
              aria-pressed={chartMode === "indices"}
              onClick={() => setChartMode("indices")}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all ${
                chartMode === "indices"
                  ? "bg-amber-500 text-slate-950 shadow-md"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Índices Base 100 ({primeiroAno})
            </button>
          </div>
        </div>

        {/* Grade de 4 Cards de Métricas */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
          <div className="bg-slate-950/70 border border-slate-800/90 rounded-2xl p-4">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
              Subsídio Parlamentar Atual
            </span>
            <div className="text-2xl font-black text-amber-400 font-mono">
              {fmtBrlValue(estatisticas_disparidade.salario_parlamentar_atual)}
            </div>
            <span className="text-[11px] text-slate-400 mt-1 block">
              {fmtGrowth(estatisticas_disparidade.crescimento_acumulado_salario_parlamentar_pct)} desde {primeiroAno} ({fmtBrlValue(estatisticas_disparidade.salario_parlamentar_inicial)})
            </span>
          </div>

          <div className="bg-slate-950/70 border border-slate-800/90 rounded-2xl p-4">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
              Salário Mínimo Nacional
            </span>
            <div className="text-2xl font-black text-emerald-400 font-mono">
              {fmtBrlValue(estatisticas_disparidade.salario_minimo_atual)}
            </div>
            <span className="text-[11px] text-slate-400 mt-1 block">
              {fmtGrowth(estatisticas_disparidade.crescimento_acumulado_salario_minimo_pct)} desde {primeiroAno} ({fmtBrlValue(estatisticas_disparidade.salario_minimo_inicial)})
            </span>
          </div>

          <div className="bg-slate-950/70 border border-slate-800/90 rounded-2xl p-4">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
              Múltiplo de Disparidade Atual
            </span>
            <div className="text-2xl font-black text-slate-100 font-mono">
              {fmtNum(estatisticas_disparidade.multiplo_atual)}x
            </div>
            <span className="text-[11px] text-slate-400 mt-1 block">
              {isNum(estatisticas_disparidade.multiplo_atual)
                ? `1 salário parlamentar = ~${fmtNum(estatisticas_disparidade.multiplo_atual, 0)} salários mínimos`
                : "Múltiplo atual indisponível"}
            </span>
          </div>

          <div className="bg-slate-950/70 border border-slate-800/90 rounded-2xl p-4">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
              Pico Histórico de Disparidade
            </span>
            <div className="text-2xl font-black text-rose-400 font-mono">
              {fmtNum(estatisticas_disparidade.pico_multiplo_valor)}x
            </div>
            <span className="text-[11px] text-slate-400 mt-1 block">
              Atingido em {estatisticas_disparidade.pico_multiplo_ano}
              {picoPresidente ? ` (${picoPresidente})` : ""}
            </span>
          </div>
        </div>
      </div>

      {/* Gráfico Comparativo */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 backdrop-blur-md">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-amber-400" aria-hidden="true" />
            <h3 className="text-sm font-bold text-slate-200">
              {chartMode === "valores"
                ? "Evolução do Salário Parlamentar (Eixo Esq.) vs Salário Mínimo (Eixo Dir.)"
                : `Trajetória Indexada: Crescimento Relativo (${primeiroAno} = 100)`}
            </h3>
          </div>
          <span className="text-xs text-slate-400">
            Fonte: Decretos Legislativos & Séries BCB/IBGE
          </span>
        </div>

        <div
          role="img"
          aria-label="Gráfico comparativo entre o salário parlamentar e o salário mínimo ao longo dos anos"
          className="h-80 w-full"
        >
          <ResponsiveContainer width="100%" height="100%">
            {chartMode === "valores" ? (
              <ComposedChart data={serie_historica} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" opacity={0.6} />
                <XAxis dataKey="ano" stroke="#64748b" tick={{ fontSize: 11 }} />
                <YAxis
                  yAxisId="left"
                  stroke="#fbbf24"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => `R$ ${(v / 1000).toFixed(0)}k`}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke="#34d399"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => `R$ ${v}`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#090d16",
                    borderColor: "#334155",
                    borderRadius: "12px",
                    fontSize: "12px"
                  }}
                  formatter={(val, name) => {
                    const num = Number(val);
                    // null/undefined viram 0 em Number(): tratar antes para nunca exibir "R$ 0,00" como dado
                    if (val === null || val === undefined || !Number.isFinite(num)) return ["Indisponível", String(name)];
                    if (name === "Salário Parlamentar (BRL)" || name === "Salário Mínimo (BRL)") {
                      return [`R$ ${num.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`, String(name)];
                    }
                    if (name === "Múltiplo (x)") return [`${num.toFixed(1)}x salários mínimos`, String(name)];
                    return [String(val), String(name)];
                  }}
                />
                <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "10px" }} />
                <Bar yAxisId="left" dataKey="salario_parlamentar_brl" name="Salário Parlamentar (BRL)" fill="#f59e0b" radius={[4, 4, 0, 0]} opacity={0.8} />
                <Line yAxisId="right" type="monotone" dataKey="salario_minimo_brl" name="Salário Mínimo (BRL)" stroke="#10b981" strokeWidth={3} dot={{ r: 3 }} />
              </ComposedChart>
            ) : (
              <ComposedChart data={serie_historica} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" opacity={0.6} />
                <XAxis dataKey="ano" stroke="#64748b" tick={{ fontSize: 11 }} />
                <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}`} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#090d16",
                    borderColor: "#334155",
                    borderRadius: "12px",
                    fontSize: "12px"
                  }}
                />
                <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "10px" }} />
                <Line type="monotone" dataKey="indice_salario_minimo_base100" name="Índice Salário Mínimo" stroke="#10b981" strokeWidth={2.5} dot={false} />
                <Line type="monotone" dataKey="indice_salario_parlamentar_base100" name="Índice Salário Parlamentar" stroke="#f59e0b" strokeWidth={2.5} dot={false} />
                <Line type="monotone" dataKey="indice_ipca_base100" name="Inflação Acumulada (IPCA)" stroke="#ef4444" strokeWidth={2} strokeDasharray="4 4" dot={false} />
              </ComposedChart>
            )}
          </ResponsiveContainer>
        </div>
      </div>

      {/* Seção da Votação Nominal do Salário Mínimo */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 backdrop-blur-md space-y-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800/80 pb-5">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                Votação Nominal Auditável
              </span>
              <span className="text-xs text-slate-400 font-mono">
                {votacao_salario_minimo.data_votacao ?? "data indisponível"} • {votacao_salario_minimo.casa}
              </span>
            </div>
            <h3 className="text-lg font-bold text-slate-100">
              {votacao_salario_minimo.proposicao_titulo}
            </h3>
            <p className="text-xs text-slate-400 max-w-3xl mt-1 leading-relaxed">
              {votacao_salario_minimo.ementa}
            </p>
          </div>

          {/* Placar em Destaque */}
          <div className="flex items-center gap-3 bg-slate-950 p-3 rounded-2xl border border-slate-800">
            <div className="text-center px-2">
              <span className="text-[10px] uppercase font-bold text-emerald-400 block">SIM</span>
              <span className="text-xl font-black text-slate-100 font-mono">
                {votacao_salario_minimo.placar?.SIM ?? "—"}
              </span>
            </div>
            <div className="w-px h-8 bg-slate-800" />
            <div className="text-center px-2">
              <span className="text-[10px] uppercase font-bold text-rose-400 block">NÃO</span>
              <span className="text-xl font-black text-slate-100 font-mono">
                {votacao_salario_minimo.placar?.NAO ?? "—"}
              </span>
            </div>
            <div className="w-px h-8 bg-slate-800" />
            <div className="text-center px-2">
              <span className="text-[10px] uppercase font-bold text-amber-400 block">ABST.</span>
              <span className="text-xl font-black text-slate-100 font-mono">
                {votacao_salario_minimo.placar?.ABSTENCAO ?? "—"}
              </span>
            </div>
          </div>
        </div>

        {/* Filtros e Busca */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="relative w-full sm:w-80">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
            <input
              type="text"
              aria-label="Buscar deputado, partido ou UF"
              placeholder="Buscar deputado, partido ou UF..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3.5 py-2 text-xs font-medium text-slate-200 placeholder:text-slate-400 focus:outline-none focus:border-amber-500"
            />
          </div>

          <div className="flex items-center gap-2 self-start sm:self-auto">
            <button
              type="button"
              aria-pressed={voteFilter === "ALL"}
              onClick={() => setVoteFilter("ALL")}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
                voteFilter === "ALL" ? "bg-slate-800 text-slate-200 border border-slate-700" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Todos ({votosAmostra.length})
            </button>
            <button
              type="button"
              aria-pressed={voteFilter === "SIM"}
              onClick={() => setVoteFilter("SIM")}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
                voteFilter === "SIM" ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Votaram SIM
            </button>
            <button
              type="button"
              aria-pressed={voteFilter === "NAO"}
              onClick={() => setVoteFilter("NAO")}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
                voteFilter === "NAO" ? "bg-rose-500/20 text-rose-300 border border-rose-500/40" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Votaram NÃO
            </button>
          </div>
        </div>

        {/* Tabela de Votos dos Parlamentares */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-96 overflow-y-auto pr-1">
          {filteredVotes.map((v) => (
            <div
              key={`${v.deputado_nome}-${v.partido_sigla}-${v.uf}`}
              className="bg-slate-950/70 border border-slate-800/80 hover:border-slate-700 rounded-2xl p-3 flex items-center justify-between gap-3 transition-all"
            >
              <div className="flex items-center gap-3">
                {safeExternalUrl(v.foto_url) ? (
                  <img
                    src={safeExternalUrl(v.foto_url)}
                    alt=""
                    referrerPolicy="no-referrer"
                    className="w-10 h-10 rounded-xl object-cover border border-slate-700 flex-shrink-0"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = "none";
                    }}
                  />
                ) : (
                  <div className="w-10 h-10 rounded-xl bg-slate-800 flex items-center justify-center text-xs font-bold text-slate-300 flex-shrink-0">
                    {v.partido_sigla}
                  </div>
                )}
                <div>
                  <h4 className="text-xs font-bold text-slate-100">{v.deputado_nome}</h4>
                  <p className="text-[11px] text-slate-400">
                    <span className="font-semibold text-amber-400">{v.partido_sigla}</span> • {v.uf} • {v.cargo}
                  </p>
                </div>
              </div>

              <div>
                {v.voto === "SIM" && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-black bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                    <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
                    SIM
                  </span>
                )}
                {v.voto === "NAO" && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-black bg-rose-500/15 text-rose-400 border border-rose-500/30">
                    <XCircle className="w-3.5 h-3.5" aria-hidden="true" />
                    NÃO
                  </span>
                )}
                {v.voto !== "SIM" && v.voto !== "NAO" && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-black bg-amber-500/15 text-amber-400 border border-amber-500/30">
                    <HelpCircle className="w-3.5 h-3.5" aria-hidden="true" />
                    {v.voto}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
