"use client";

import React, { useState, useMemo } from "react";
import {
  PartyFidelityResponse,
  PartyBalanceItem,
  TopNomad,
} from "@/services/api";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Cell,
} from "recharts";
import {
  Users,
  TrendingUp,
  TrendingDown,
  ArrowRight,
  Search,
  Sparkles,
  Award,
  Layers,
  ChevronDown,
  ChevronUp,
  Landmark,
  ShieldAlert,
} from "lucide-react";

interface PartyFidelityPanelProps {
  fidelityData: PartyFidelityResponse | null;
  onSelectParty?: (sigla: string) => void;
}

export default function PartyFidelityPanel({
  fidelityData,
  onSelectParty,
}: PartyFidelityPanelProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedNomadId, setExpandedNomadId] = useState<string | null>(null);
  const [chartFilter, setChartFilter] = useState<"TOP_MOVERS" | "ALL">("TOP_MOVERS");

  if (!fidelityData) {
    return null;
  }

  const { party_balance, top_nomads, summary } = fidelityData;

  // Filtrar partidos para o gráfico (remover siglas zeradas e limitar aos que tiveram movimentação)
  const chartData = useMemo(() => {
    const withMovement = party_balance.filter(
      (p) => p.saldo_liquido !== 0 || p.ganhos > 0 || p.perdas > 0
    );

    if (chartFilter === "TOP_MOVERS") {
      // Top 7 maiores ganhadores e Top 7 maiores perdedores
      const gainers = withMovement.filter((p) => p.saldo_liquido > 0).slice(0, 6);
      const losers = withMovement.filter((p) => p.saldo_liquido < 0).slice(-6);
      return [...gainers, ...losers].sort((a, b) => b.saldo_liquido - a.saldo_liquido);
    }

    return withMovement.slice(0, 20);
  }, [party_balance, chartFilter]);

  // Filtrar nômades pela busca
  const filteredNomads = useMemo(() => {
    if (!searchTerm.trim()) return top_nomads.slice(0, 15);
    const term = searchTerm.toLowerCase();
    return top_nomads.filter(
      (n) =>
        n.nome_eleitoral.toLowerCase().includes(term) ||
        n.partido_atual.toLowerCase().includes(term) ||
        n.siglas_sequencia.some((s) => s.toLowerCase().includes(term)) ||
        n.uf.toLowerCase().includes(term)
    );
  }, [top_nomads, searchTerm]);

  const toggleExpand = (id: string) => {
    setExpandedNomadId(expandedNomadId === id ? null : id);
  };

  return (
    <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-md space-y-6">
      {/* Cabeçalho do Painel */}
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <ShieldAlert className="w-5 h-5" />
            </span>
            <h2 className="text-base sm:text-lg font-bold text-slate-100">
              TSE Analytics: Dinâmica Partidária & Infidelidade Parlamentar
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Mapeamento de trocas de legenda, fusões partidárias (PSL + DEM, PTB + PATRIOTA) e migrações no Congresso Nacional
          </p>
        </div>

        {/* Badges de Resumo */}
        <div className="flex items-center gap-2 flex-wrap">
          <div className="px-3 py-1.5 rounded-xl bg-slate-950/80 border border-slate-800 text-xs">
            <span className="text-slate-400">Taxa de Migração: </span>
            <strong className="text-amber-400 font-mono">
              {summary.taxa_migracao_pct}%
            </strong>{" "}
            <span className="text-[11px] text-slate-400">
              ({summary.total_nomades}/{summary.total_parlamentares})
            </span>
          </div>

          <div className="px-3 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300">
            <span>Maior Ganho: </span>
            <strong
              onClick={() => onSelectParty && summary.partido_maior_ganho && onSelectParty(summary.partido_maior_ganho)}
              className={`font-bold ${onSelectParty ? "cursor-pointer hover:underline" : ""}`}
              title={onSelectParty ? `Ver bancada do ${summary.partido_maior_ganho}` : undefined}
            >
              {summary.partido_maior_ganho}
            </strong>{" "}
            <span className="font-mono font-bold">+{summary.saldo_maior_ganho}</span>
          </div>

          <div className="px-3 py-1.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-xs text-rose-300">
            <span>Maior Perda: </span>
            <strong
              onClick={() => onSelectParty && summary.partido_maior_perda && onSelectParty(summary.partido_maior_perda)}
              className={`font-bold ${onSelectParty ? "cursor-pointer hover:underline" : ""}`}
              title={onSelectParty ? `Ver bancada do ${summary.partido_maior_perda}` : undefined}
            >
              {summary.partido_maior_perda}
            </strong>{" "}
            <span className="font-mono font-bold">{summary.saldo_maior_perda}</span>
          </div>
        </div>
      </div>

      {/* Grid: Gráfico de Saldo Partidário + Tabela de Nômades */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Gráfico de Saldo Partidário Divergente (7 colunas em telas grandes) */}
        <div className="lg:col-span-5 bg-slate-950/70 border border-slate-800/90 rounded-xl p-4.5 flex flex-col justify-between space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-slate-900">
            <div>
              <div className="flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 text-emerald-400" />
                <h3 className="text-xs sm:text-sm font-bold text-slate-200">
                  Saldo Líquido de Cadeiras por Legenda
                </h3>
              </div>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Verde = Ganho líquido • Vermelho = Perda líquida
              </p>
            </div>

            {/* Alternador de visualização */}
            <div className="flex items-center bg-slate-900 border border-slate-800 p-0.5 rounded-lg text-[10px]">
              <button
                onClick={() => setChartFilter("TOP_MOVERS")}
                className={`px-2 py-1 rounded font-semibold transition-all ${
                  chartFilter === "TOP_MOVERS"
                    ? "bg-cyan-500/20 text-cyan-300"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Destaques
              </button>
              <button
                onClick={() => setChartFilter("ALL")}
                className={`px-2 py-1 rounded font-semibold transition-all ${
                  chartFilter === "ALL"
                    ? "bg-cyan-500/20 text-cyan-300"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Top 20
              </button>
            </div>
          </div>

          {/* Gráfico Horizontal Divergente */}
          <div className="h-96 w-full pt-1">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                layout="vertical"
                data={chartData}
                margin={{ top: 5, right: 25, left: 20, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  type="number"
                  stroke="#64748b"
                  tick={{ fill: "#94a3b8", fontSize: 11 }}
                />
                <YAxis
                  type="category"
                  dataKey="partido"
                  stroke="#64748b"
                  tick={{ fill: "#e2e8f0", fontSize: 11, fontWeight: 600 }}
                  width={75}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload || !payload.length) return null;
                    const item = payload[0].payload as PartyBalanceItem;
                    return (
                      <div className="bg-slate-950 border border-slate-700 rounded-xl p-3 shadow-xl text-xs space-y-1">
                        <div className="font-bold text-slate-100 flex items-center justify-between gap-3 border-b border-slate-800 pb-1">
                          <span>{item.partido}</span>
                          <span
                            className={`font-mono font-bold ${
                              item.saldo_liquido > 0
                                ? "text-emerald-400"
                                : item.saldo_liquido < 0
                                ? "text-rose-400"
                                : "text-slate-400"
                            }`}
                          >
                            {item.saldo_liquido > 0 ? `+${item.saldo_liquido}` : item.saldo_liquido} cadeiras
                          </span>
                        </div>
                        <div className="space-y-0.5 text-slate-300 pt-0.5">
                          <div className="flex justify-between gap-4 text-emerald-400">
                            <span>Migrações de entrada:</span>
                            <span className="font-mono">+{item.ganhos}</span>
                          </div>
                          <div className="flex justify-between gap-4 text-rose-400">
                            <span>Migrações de saída:</span>
                            <span className="font-mono">-{item.perdas}</span>
                          </div>
                          <div className="flex justify-between gap-4 text-slate-400 pt-1 border-t border-slate-900">
                            <span>Bancada Atual:</span>
                            <span className="font-mono text-slate-200 font-bold">
                              {item.bancada_atual}
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  }}
                />
                <ReferenceLine x={0} stroke="#475569" strokeWidth={1.5} />
                <Bar dataKey="saldo_liquido" radius={[4, 4, 4, 4]}>
                  {chartData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.saldo_liquido >= 0 ? "#10b981" : "#f43f5e"}
                      fillOpacity={0.85}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <p className="text-[10px] text-slate-400 italic text-center">
            Nota: Perdas acentuadas em PSL e DEM refletem a fusão que originou o União Brasil.
          </p>
        </div>

        {/* Tabela de Nômades Partidários (7 colunas em telas grandes) */}
        <div className="lg:col-span-7 bg-slate-950/70 border border-slate-800/90 rounded-xl p-4.5 flex flex-col justify-between space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2.5 pb-2 border-b border-slate-900">
            <div className="flex items-center gap-1.5">
              <Award className="w-4 h-4 text-amber-400" />
              <div>
                <h3 className="text-xs sm:text-sm font-bold text-slate-200">
                  Ranking dos "Nômades Partidários"
                </h3>
                <p className="text-[11px] text-slate-400">
                  Parlamentares da 57ª Legislatura com mais trocas de legenda na carreira
                </p>
              </div>
            </div>

            {/* Busca Rápida */}
            <div className="relative w-full sm:w-56">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Buscar por nome ou partido..."
                className="w-full bg-slate-900/90 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors"
              />
            </div>
          </div>

          {/* Lista Compacta de Parlamentares */}
          <div className="space-y-2.5 max-h-[380px] overflow-y-auto pr-1">
            {filteredNomads.length === 0 ? (
              <div className="text-center py-8 text-slate-500 text-xs">
                Nenhum parlamentar encontrado para o termo pesquisado.
              </div>
            ) : (
              filteredNomads.map((nomad) => {
                const isExpanded = expandedNomadId === nomad.id;
                return (
                  <div
                    key={nomad.id}
                    className="bg-slate-900/80 border border-slate-800 hover:border-slate-700/80 rounded-xl p-3 transition-all space-y-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        {nomad.foto_url ? (
                          <img
                            src={nomad.foto_url}
                            alt={nomad.nome_eleitoral}
                            referrerPolicy="no-referrer"
                            className="w-8 h-8 rounded-full object-cover border border-slate-700 flex-shrink-0"
                            onError={(e) => {
                              (e.target as HTMLImageElement).style.display = "none";
                            }}
                          />
                        ) : (
                          <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-bold text-slate-300 flex-shrink-0">
                            {nomad.partido_atual.slice(0, 2)}
                          </div>
                        )}

                        <div>
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="text-xs font-bold text-slate-100">
                              {nomad.nome_eleitoral}
                            </span>
                            <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded bg-slate-800 text-slate-300">
                              {nomad.cargo === "SENADOR" ? "Senador" : "Deputado"} • {nomad.uf}
                            </span>
                          </div>
                          <span className="text-[11px] text-slate-400">
                            Atual:{" "}
                            <strong
                              onClick={() => onSelectParty && nomad.partido_atual && onSelectParty(nomad.partido_atual)}
                              className={`text-cyan-400 ${onSelectParty ? "cursor-pointer hover:underline" : ""}`}
                              title={onSelectParty ? `Ver bancada do ${nomad.partido_atual}` : undefined}
                            >
                              {nomad.partido_atual}
                            </strong>
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/20">
                          {nomad.total_trocas} trocas
                        </span>

                        <button
                          onClick={() => toggleExpand(nomad.id)}
                          className="p-1 text-slate-400 hover:text-slate-200 transition-colors"
                          title="Ver detalhes de cada filiação"
                        >
                          {isExpanded ? (
                            <ChevronUp className="w-4 h-4" />
                          ) : (
                            <ChevronDown className="w-4 h-4" />
                          )}
                        </button>
                      </div>
                    </div>

                    {/* Linha do Tempo das Siglas (Trajetória Visual) */}
                    <div className="flex items-center gap-1 flex-wrap pt-1 text-[10px]">
                      {nomad.siglas_sequencia.map((sigla, idx) => {
                        const isLast = idx === nomad.siglas_sequencia.length - 1;
                        return (
                          <React.Fragment key={`${nomad.id}-${sigla}-${idx}`}>
                            <span
                              onClick={() => onSelectParty && sigla && onSelectParty(sigla)}
                              className={`px-1.5 py-0.5 rounded font-mono font-semibold ${
                                isLast
                                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                                  : "bg-slate-800/80 text-slate-400"
                              } ${onSelectParty ? "cursor-pointer hover:underline hover:text-cyan-200" : ""}`}
                              title={onSelectParty ? `Ver bancada do ${sigla}` : undefined}
                            >
                              {sigla}
                            </span>
                            {!isLast && (
                              <ArrowRight className="w-2.5 h-2.5 text-slate-600 flex-shrink-0" />
                            )}
                          </React.Fragment>
                        );
                      })}
                    </div>

                    {/* Detalhamento de Datas quando Expandido */}
                    {isExpanded && (
                      <div className="pt-2 border-t border-slate-800/80 space-y-1.5 text-[11px]">
                        <span className="text-slate-400 font-semibold block text-[10px] uppercase tracking-wider">
                          Histórico Cronológico Registrado no TSE:
                        </span>
                        <div className="space-y-1 bg-slate-950/60 p-2 rounded-lg border border-slate-900">
                          {nomad.historico.map((h, i) => (
                            <div
                              key={i}
                              className="flex items-center justify-between text-slate-300 text-[10px]"
                            >
                              <div className="flex items-center gap-2">
                                <span
                                  onClick={() => onSelectParty && h.partido && onSelectParty(h.partido)}
                                  className={`font-mono font-bold text-cyan-300 w-14 ${
                                    onSelectParty ? "cursor-pointer hover:underline" : ""
                                  }`}
                                  title={onSelectParty ? `Ver bancada do ${h.partido}` : undefined}
                                >
                                  {h.partido}
                                </span>
                                <span className="text-slate-400">
                                  {h.data_filiacao} → {h.data_desfiliacao || "Ativo (Atual)"}
                                </span>
                              </div>
                              {h.motivo && (
                                <span className="text-[9px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 font-medium">
                                  {h.motivo.replace(/_/g, " ")}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
