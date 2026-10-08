"use client";

import React, { useState } from "react";
import {
  Vote,
  BarChart3,
  BookOpen,
  UtensilsCrossed,
  Search,
  CheckCircle2,
  Calendar,
} from "lucide-react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from "recharts";
import { getSocialElectionsCorrelation, getSocialIndicators } from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { EmptyState, ErrorState } from "@/components/StateViews";
import { fmtNum, isNum } from "@/lib/format";
import type { MandateRange } from "@/lib/mandate";

interface DeepBrazilPanelProps {
  /** Mandato selecionado (derivado da API de presidentes). Use `key={mandate.id}` para reiniciar o ano. */
  mandate?: MandateRange | null;
}

const REGIONS = ["TODAS", "NORDESTE", "NORTE", "SUDESTE", "SUL", "CENTRO-OESTE"];

type SortKey = "pobreza" | "analfabetismo" | "votos_vencedor";

export default function DeepBrazilPanel({ mandate = null }: DeepBrazilPanelProps) {
  const mandateYears = mandate
    ? Array.from({ length: mandate.end - mandate.start + 1 }, (_, i) => mandate.start + i)
    : null;

  // Ano eleitoral escolhido pelo usuário; sem escolha, usa a eleição do mandato (ou o padrão da API).
  const [pickedYear, setPickedYear] = useState<number | null>(null);
  const requestedYear = pickedYear ?? mandate?.electionYear ?? null;

  const elections = useApi(`social-elections:${requestedYear ?? "default"}`, (signal) =>
    getSocialElectionsCorrelation(requestedYear ?? undefined, signal)
  );
  const social = useApi("social-indicators", (signal) => getSocialIndicators(signal));

  const data = elections.data ?? null;
  const socialAnnual = social.data ?? [];
  const selectedYear = data?.ano_eleicao ?? requestedYear;
  const loading = elections.loading;

  const [regionFilter, setRegionFilter] = useState<string>("TODAS");
  const [sortBy, setSortBy] = useState<SortKey>("pobreza");
  const [searchTerm, setSearchTerm] = useState<string>("");

  // Filtragem e ordenação dos estados
  const filteredStates = (data?.estados || [])
    .filter((e) => {
      const matchesRegion = regionFilter === "TODAS" || e.regiao.toUpperCase() === regionFilter;
      const matchesSearch =
        e.estado_nome.toLowerCase().includes(searchTerm.toLowerCase()) ||
        e.uf.toLowerCase().includes(searchTerm.toLowerCase()) ||
        e.vencedor_nome.toLowerCase().includes(searchTerm.toLowerCase());
      return matchesRegion && matchesSearch;
    })
    .sort((a, b) => {
      // Valores ausentes vão para o fim da lista (não são tratados como zero).
      const key = (e: typeof a) =>
        sortBy === "pobreza" ? e.extrema_pobreza_pct : sortBy === "analfabetismo" ? e.taxa_analfabetismo_pct : e.vencedor_votos_pct;
      const va = key(a);
      const vb = key(b);
      if (!isNum(va) && !isNum(vb)) return 0;
      if (!isNum(va)) return 1;
      if (!isNum(vb)) return -1;
      return vb - va;
    });

  // Ano atual de referência para indicadores sociais
  const currentSocialYear = socialAnnual.find((s) => s.ano === selectedYear) ?? socialAnnual[socialAnnual.length - 1];
  const chartSeries = mandateYears ? socialAnnual.filter((s) => mandateYears.includes(s.ano)) : socialAnnual;
  const firstSeriesYear = socialAnnual.length > 0 ? socialAnnual[0].ano : null;
  const lastSeriesYear = socialAnnual.length > 0 ? socialAnnual[socialAnnual.length - 1].ano : null;

  const getPartyColor = (party: string) => {
    switch (party.toUpperCase()) {
      case "PT":
        return "text-red-400 bg-red-500/10 border-red-500/30";
      case "PSDB":
        return "text-blue-400 bg-blue-500/10 border-blue-500/30";
      case "PSL":
      case "PL":
        return "text-amber-400 bg-amber-500/10 border-amber-500/30";
      default:
        return "text-emerald-400 bg-emerald-500/10 border-emerald-500/30";
    }
  };

  if (elections.error && !data) return <ErrorState onRetry={elections.retry} />;
  if (!loading && !data) return <EmptyState title="Dados eleitorais e sociais indisponíveis" />;

  return (
    <div className="space-y-6">
      {/* Banner Principal com Seletor de Ano Eleitoral */}
      <div className="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-md shadow-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-5">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400">
              <Vote className="w-6 h-6" aria-hidden="true" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-100">
                Painel Brasil Profundo: Sociedade, Pobreza e Eleições
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Cruzamento analítico entre vulnerabilidade socioeconômica (IBGE/IPEA) e comportamento eleitoral (TSE) por Estado
              </p>
            </div>
          </div>
        </div>

        {/* Seletor de Anos Eleitorais */}
        <div className="flex items-center gap-1.5 bg-slate-950 p-1.5 rounded-xl border border-slate-800 overflow-x-auto max-w-full">
          {(data?.anos_disponiveis ?? []).map((year) => (
            <button
              type="button"
              key={year}
              aria-pressed={selectedYear === year}
              onClick={() => setPickedYear(year)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1 ${
                selectedYear === year
                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/30 shadow-md"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Calendar className="w-3 h-3" aria-hidden="true" />
              <span>{year}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Cartões Rápidos de Contexto Nacional do Ano */}
      {currentSocialYear && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-slate-900/60 border border-slate-800/80 p-4 rounded-xl">
            <span className="text-[11px] text-slate-400 font-medium">Extrema Pobreza Nacional ({selectedYear})</span>
            <div className="text-xl font-extrabold text-rose-400 mt-1">
              {isNum(currentSocialYear.extrema_pobreza_pct) ? `${fmtNum(currentSocialYear.extrema_pobreza_pct)}%` : "N/D"}
            </div>
            <span className="text-[10px] text-slate-400 mt-0.5 block">
              {isNum(currentSocialYear.extrema_pobreza_milhoes) ? `~${fmtNum(currentSocialYear.extrema_pobreza_milhoes)}M pessoas abaixo da linha` : "IBGE / IPEA"}
            </span>
          </div>

          <div className="bg-slate-900/60 border border-slate-800/80 p-4 rounded-xl">
            <span className="text-[11px] text-slate-400 font-medium">Taxa de Analfabetismo (15+ anos)</span>
            <div className="text-xl font-extrabold text-amber-400 mt-1">
              {isNum(currentSocialYear.analfabetismo_pct) ? `${fmtNum(currentSocialYear.analfabetismo_pct)}%` : "N/D"}
            </div>
            <span className="text-[10px] text-slate-400 mt-0.5 block">
              Censo Demográfico e PNAD Contínua
            </span>
          </div>

          <div className="bg-slate-900/60 border border-slate-800/80 p-4 rounded-xl">
            <span className="text-[11px] text-slate-400 font-medium">Insegurança Alimentar Grave (Fome)</span>
            <div className="text-xl font-extrabold text-purple-400 mt-1">
              {isNum(currentSocialYear.inseguranca_alimentar_pct) ? `${fmtNum(currentSocialYear.inseguranca_alimentar_pct)}%` : "N/D"}
            </div>
            <span className="text-[10px] text-slate-400 mt-0.5 block">
              {isNum(currentSocialYear.inseguranca_alimentar_milhoes) ? `~${fmtNum(currentSocialYear.inseguranca_alimentar_milhoes)}M pessoas (Mapa da Fome)` : "FAO / Penssan"}
            </span>
          </div>

          <div className="bg-slate-900/60 border border-slate-800/80 p-4 rounded-xl">
            <span className="text-[11px] text-slate-400 font-medium">Índice de Gini (Desigualdade)</span>
            <div className="text-xl font-extrabold text-sky-400 mt-1">
              {isNum(currentSocialYear.gini) ? fmtNum(currentSocialYear.gini, 3) : "N/D"}
            </div>
            <span className="text-[10px] text-slate-400 mt-0.5 block">
              0 = Perfeita igualdade | 1 = Máxima concentração
            </span>
          </div>
        </div>
      )}

      {/* Gráfico de Evolução da Fome e Desigualdade com Zoom Automático por Mandato */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-md space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-purple-500/10 border border-purple-500/20 rounded-xl text-purple-400">
              <UtensilsCrossed className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <span>Trajetória da Fome e Desigualdade de Renda</span>
                {mandate ? (
                  <span className="text-[10px] px-2.5 py-0.5 rounded-full font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                    Zoom: {mandate.label} ({mandate.start} - {mandate.end})
                  </span>
                ) : (
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-slate-800 text-slate-300 border border-slate-700">
                    Série Histórica Completa{firstSeriesYear !== null && lastSeriesYear !== null ? ` (${firstSeriesYear} - ${lastSeriesYear})` : ""}
                  </span>
                )}
              </h3>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Eixo Esquerdo: Insegurança Alimentar Grave (%) e Extrema Pobreza (%) • Eixo Direito: Índice de Gini (0 a 1)
              </p>
            </div>
          </div>
        </div>

        {/* Gráfico Recharts de Fome e Desigualdade */}
        {social.error ? (
          <ErrorState message="Não foi possível carregar a série de indicadores sociais." onRetry={social.retry} />
        ) : chartSeries.length === 0 && !social.loading ? (
          <EmptyState message="Não há indicadores sociais para o período selecionado." />
        ) : (
        <div
          role="img"
          aria-label="Gráfico de linhas: insegurança alimentar, extrema pobreza e índice de Gini por ano"
          className="w-full h-72 sm:h-80"
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={chartSeries}
              margin={{ top: 10, right: 20, bottom: 10, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" opacity={0.6} />
              <XAxis dataKey="ano" stroke="#64748b" tick={{ fontSize: 11 }} />
              <YAxis
                yAxisId="left"
                stroke="#a855f7"
                tick={{ fontSize: 11 }}
                domain={[0, 'auto']}
                tickFormatter={(val) => `${val}%`}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                stroke="#38bdf8"
                tick={{ fontSize: 11 }}
                domain={[(min: number) => Math.floor(min * 20) / 20, (max: number) => Math.ceil(max * 20) / 20]}
                tickFormatter={(val) => Number(val).toFixed(2)}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#020617",
                  borderColor: "#334155",
                  borderRadius: "0.75rem",
                  fontSize: "12px",
                }}
              />
              <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }} />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="inseguranca_alimentar_pct"
                name="Fome / Insegurança Alimentar (%)"
                stroke="#a855f7"
                strokeWidth={2.5}
                dot={{ r: 4, fill: "#a855f7" }}
                activeDot={{ r: 6 }}
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="extrema_pobreza_pct"
                name="Extrema Pobreza (%)"
                stroke="#f43f5e"
                strokeWidth={2}
                dot={{ r: 3, fill: "#f43f5e" }}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="gini"
                name="Índice de Gini (Desigualdade)"
                stroke="#38bdf8"
                strokeWidth={2}
                dot={{ r: 3, fill: "#38bdf8" }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        )}
      </div>

      {/* Resumo Regional do Ano */}
      {data?.regioes_resumo && (
        <div className="bg-slate-900/50 border border-slate-800/80 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-emerald-400" aria-hidden="true" />
              <span>Médias Regionais de Vulnerabilidade e Preferência Eleitoral ({selectedYear})</span>
            </h3>
            <span className="text-[11px] text-slate-400">Total: {data.total_estados} Unidades da Federação</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            {data.regioes_resumo.map((reg) => (
              <button
                type="button"
                key={reg.regiao}
                aria-pressed={regionFilter === reg.regiao.toUpperCase()}
                onClick={() => setRegionFilter(regionFilter === reg.regiao.toUpperCase() ? "TODAS" : reg.regiao.toUpperCase())}
                className={`p-3.5 rounded-xl border transition-all cursor-pointer text-left ${
                  regionFilter === reg.regiao.toUpperCase()
                    ? "bg-slate-800/90 border-slate-600 shadow-lg"
                    : "bg-slate-950/60 border-slate-800/80 hover:bg-slate-800/40"
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-bold text-slate-200 text-xs">{reg.regiao}</span>
                  <span className="text-[10px] text-slate-400">{reg.total_estados} UFs</span>
                </div>
                <div className="space-y-1 text-[11px]">
                  <div className="flex justify-between text-rose-300">
                    <span>Extrema Pobreza:</span>
                    <span className="font-bold">{fmtNum(reg.media_extrema_pobreza_pct)}%</span>
                  </div>
                  <div className="flex justify-between text-amber-300">
                    <span>Analfabetismo:</span>
                    <span className="font-bold">{fmtNum(reg.media_analfabetismo_pct)}%</span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Controles de Busca e Ordenação */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-slate-900/60 border border-slate-800/80 p-3 rounded-xl text-xs">
        {/* Barra de Pesquisa */}
        <div className="relative flex-1 max-w-xs">
          <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" aria-hidden="true" />
          <input
            type="text"
            aria-label="Buscar estado, UF ou vencedor"
            placeholder="Buscar Estado, UF ou Vencedor..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-slate-200 placeholder-slate-400 focus:outline-none focus:border-rose-500 text-xs"
          />
        </div>

        {/* Filtros e Ordenação */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Filtro por Região */}
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
            {REGIONS.map((reg) => (
              <button
                type="button"
                key={reg}
                aria-pressed={regionFilter === reg}
                onClick={() => setRegionFilter(reg)}
                className={`px-2 py-1 rounded text-[10px] font-semibold transition-all ${
                  regionFilter === reg
                    ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {reg}
              </button>
            ))}
          </div>

          {/* Ordenador */}
          <div className="flex items-center gap-1.5">
            <label htmlFor="deep-brazil-sort" className="text-slate-400 text-[11px]">Ordenar por:</label>
            <select
              id="deep-brazil-sort"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortKey)}
              className="bg-slate-950 border border-slate-800 rounded-lg px-2 py-1 text-slate-200 text-xs focus:outline-none focus:border-rose-500"
            >
              <option value="pobreza">Extrema Pobreza (Decrescente)</option>
              <option value="analfabetismo">Taxa de Analfabetismo (Decrescente)</option>
              <option value="votos_vencedor">Maior % Voto Vencedor</option>
            </select>
          </div>
        </div>
      </div>

      {/* Lista de Estados Cruzada */}
      {loading ? (
        <div role="status" aria-live="polite" className="p-12 text-center text-slate-400 bg-slate-900/40 border border-slate-800 rounded-2xl">
          <div className="animate-spin w-6 h-6 border-2 border-rose-500 border-t-transparent rounded-full mx-auto mb-2" aria-hidden="true" />
          <span>Carregando dados eleitorais e sociais do Brasil...</span>
        </div>
      ) : filteredStates.length === 0 ? (
        <div role="status" className="p-12 text-center text-slate-400 bg-slate-900/40 border border-slate-800 rounded-2xl">
          Nenhum estado encontrado com os filtros aplicados.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filteredStates.map((st) => (
            <div
              key={st.uf}
              className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-4.5 backdrop-blur-md hover:border-slate-700/80 transition-all flex flex-col justify-between space-y-3.5"
            >
              {/* Topo do Card: UF, Região e Indicadores */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="w-8 h-8 rounded-xl bg-slate-800 text-slate-100 font-extrabold text-xs flex items-center justify-center">
                      {st.uf}
                    </span>
                    <div>
                      <h4 className="text-sm font-bold text-slate-100 leading-tight">
                        {st.estado_nome}
                      </h4>
                      <span className="text-[10px] text-slate-400">{st.regiao}</span>
                    </div>
                  </div>

                  {/* Badges de Indicadores Sociais */}
                  <div className="text-right space-y-0.5">
                    <div className="text-[11px] text-rose-300 font-bold">
                      {isNum(st.extrema_pobreza_pct) ? `${fmtNum(st.extrema_pobreza_pct)}%` : "N/D"}{" "}
                      <span className="text-[10px] text-slate-400 font-normal">pobreza</span>
                    </div>
                    <div className="text-[10px] text-amber-300 font-semibold">
                      {isNum(st.taxa_analfabetismo_pct) ? `${fmtNum(st.taxa_analfabetismo_pct)}%` : "N/D"}{" "}
                      <span className="text-[9px] text-slate-400 font-normal">analf.</span>
                    </div>
                  </div>
                </div>

                {/* Barra de Intensidade da Pobreza */}
                <div className="w-full bg-slate-950 h-1.5 rounded-full overflow-hidden mb-3">
                  <div
                    className="h-full bg-rose-500/80 rounded-full"
                    style={{ width: `${Math.min((st.extrema_pobreza_pct ?? 0) * 8, 100)}%` }}
                  />
                </div>
              </div>

              {/* Resultado da Eleição Presidencial no Estado */}
              <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800/80 space-y-2 text-xs">
                {/* Vencedor no Estado */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" aria-hidden="true" />
                    <span className="font-bold text-slate-100 truncate max-w-[150px]">
                      {st.vencedor_nome}
                    </span>
                    <span className={`text-[10px] px-1.5 py-0.2 rounded font-bold border ${getPartyColor(st.vencedor_partido)}`}>
                      {st.vencedor_partido}
                    </span>
                  </div>
                  <span className="font-extrabold text-emerald-400 text-sm">
                    {fmtNum(st.vencedor_votos_pct)}%
                  </span>
                </div>

                {/* Segundo Colocado no Estado */}
                <div className="flex items-center justify-between text-slate-400 text-[11px] pt-1 border-t border-slate-800/60">
                  <div className="flex items-center gap-1.5">
                    <span className="w-3.5 text-center text-slate-400" aria-hidden="true">•</span>
                    <span className="truncate max-w-[150px]">{st.segundo_nome}</span>
                    <span className={`text-[9px] px-1 py-0.2 rounded font-semibold border ${getPartyColor(st.segundo_partido)}`}>
                      {st.segundo_partido}
                    </span>
                  </div>
                  <span className="font-medium text-slate-300">
                    {fmtNum(st.segundo_votos_pct)}%
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Nota Metodológica e Educativa */}
      <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 text-xs text-slate-400 space-y-1.5">
        <h5 className="font-bold text-slate-200 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4 text-rose-400" aria-hidden="true" />
          <span>Interpretação Sociopolítica e Eleitoral</span>
        </h5>
        <p className="leading-relaxed">
          Os indicadores sociais (IBGE/IPEA) e os resultados do 1º turno das eleições presidenciais (TSE) são apresentados lado a lado por Unidade da Federação. A correlação entre vulnerabilidade social e preferência eleitoral não implica causalidade; use os dados como ponto de partida para análise.
        </p>
      </div>
    </div>
  );
}
