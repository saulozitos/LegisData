"use client";

import React, { useMemo } from "react";
import {
  MandatoPerformance,
  PresidenteHistorico,
  ResumoMacroeconomicoAnual,
} from "@/services/api";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
} from "recharts";
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Users,
  BarChart2,
  Leaf,
  ShieldAlert,
  Wallet,
  AlertCircle,
  Info,
  Minus,
  Briefcase,
} from "lucide-react";
import { getPresidentPhotoUrl } from "@/components/PresidentTimeline";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt(v: number | null | undefined, d = 1, prefix = "", suffix = ""): string {
  if (v == null || isNaN(v)) return "—";
  return `${prefix}${v.toFixed(d)}${suffix}`;
}

function fmtBRL(v: number | null | undefined): string {
  if (v == null) return "—";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(v);
}

function deltaColor(delta: number | null | undefined, invertGood = false): string {
  if (delta == null) return "text-slate-400";
  const isGood = invertGood ? delta < 0 : delta > 0;
  const isBad = invertGood ? delta > 0 : delta < 0;
  if (isGood) return "text-emerald-400";
  if (isBad) return "text-rose-400";
  return "text-slate-400";
}

function DeltaIcon({ delta, invertGood = false }: { delta: number | null | undefined; invertGood?: boolean }) {
  if (delta == null) return <Minus className="w-3.5 h-3.5 text-slate-500" />;
  const isGood = invertGood ? delta < 0 : delta > 0;
  if (Math.abs(delta) < 0.5) return <Minus className="w-3.5 h-3.5 text-slate-500" />;
  return isGood
    ? <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
    : <TrendingDown className="w-3.5 h-3.5 text-rose-400" />;
}

const TOOLTIP_STYLE = {
  contentStyle: { backgroundColor: "#0f172a", borderColor: "#1e293b", borderRadius: "0.75rem", fontSize: "12px" },
  itemStyle: { color: "#f1f5f9" },
  labelStyle: { color: "#64748b", marginBottom: "6px", fontWeight: "bold" },
};

// ─── Sub-componentes ──────────────────────────────────────────────────────────

interface KPICardProps {
  label: string;
  value: string;
  sublabel?: string;
  delta?: number | null;
  invertGood?: boolean;
  icon: React.ReactNode;
  accentBg: string;
  tooltip?: string;
}

function KPICard({ label, value, sublabel, delta, invertGood = false, icon, accentBg, tooltip }: KPICardProps) {
  return (
    <div className={`relative bg-slate-900/70 border border-slate-800 rounded-2xl p-4 flex flex-col gap-2.5 hover:border-slate-700 transition-all group`}>
      <div className="flex items-start justify-between">
        <div className={`p-2 rounded-xl ${accentBg}`}>{icon}</div>
        {tooltip && (
          <div className="relative">
            <Info className="w-3.5 h-3.5 text-slate-700 group-hover:text-slate-500 transition-colors cursor-help" />
            <div className="absolute right-0 top-5 z-20 w-52 bg-slate-800 border border-slate-700 rounded-lg p-2.5 text-[11px] text-slate-300 hidden group-hover:block shadow-xl leading-relaxed">
              {tooltip}
            </div>
          </div>
        )}
      </div>
      <div>
        <p className="text-slate-500 text-[10px] font-semibold uppercase tracking-wider mb-0.5">{label}</p>
        <span className="text-2xl font-bold text-slate-100 tabular-nums leading-tight">{value}</span>
        {sublabel && <p className="text-[11px] text-slate-500 mt-0.5">{sublabel}</p>}
      </div>
      {delta != null && (
        <div className={`flex items-center gap-1 text-xs font-semibold ${deltaColor(delta, invertGood)}`}>
          <DeltaIcon delta={delta} invertGood={invertGood} />
          <span>{delta > 0 ? "+" : ""}{fmt(delta)} pp (início→fim)</span>
        </div>
      )}
    </div>
  );
}

function SectionHeader({ icon, title, desc }: { icon: React.ReactNode; title: string; desc: string }) {
  return (
    <div className="flex items-start gap-3 pb-3 border-b border-slate-800">
      <div className="mt-0.5 flex-shrink-0">{icon}</div>
      <div>
        <h3 className="text-base font-bold text-slate-100 leading-tight">{title}</h3>
        <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
      </div>
    </div>
  );
}

function NoDataCard({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-40 gap-3 text-slate-600">
      <AlertCircle className="w-8 h-8 opacity-40" />
      <p className="text-sm">{message}</p>
    </div>
  );
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface ExecutivoPanelProps {
  performance: MandatoPerformance | null;
  presidentMeta: PresidenteHistorico | null;
  annualData: ResumoMacroeconomicoAnual[];
  mandateId: string | null;
  allPerformances: MandatoPerformance[];
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function ExecutivoPanel({
  performance,
  presidentMeta,
  annualData,
  mandateId,
  allPerformances,
}: ExecutivoPanelProps) {

  // Filtra série anual para o mandato selecionado
  const mandateYears = useMemo(() => {
    if (!mandateId || !performance) return annualData;
    const start = parseInt(performance.data_inicio?.slice(0, 4) ?? "0");
    const end = parseInt(performance.data_fim?.slice(0, 4) ?? String(new Date().getFullYear()));
    return annualData.filter((d) => d.ano >= start && d.ano <= end);
  }, [annualData, mandateId, performance]);

  // Dados para o gráfico de PIB anual (todos os mandatos para contexto histórico)
  const allYearsChartData = useMemo(() => {
    return annualData
      .filter((d) => d.pib_crescimento_real_pct != null)
      .map((d) => ({
        ano: d.ano,
        pib: d.pib_crescimento_real_pct,
        inflacao: d.ipca_acumulado_ano_pct != null && d.ipca_acumulado_ano_pct < 50
          ? d.ipca_acumulado_ano_pct
          : null, // Exclui hiperinflação para não distorcer escala
        desemprego: d.taxa_desemprego_anual,
        desmatamento: d.taxa_desmatamento_amazonia,
        presidente: d.presidente_dominante,
      }));
  }, [annualData]);

  // Dados específicos do mandato para os gráficos de detalhe
  const mandateChartData = useMemo(() => {
    return mandateYears
      .map((d) => ({
        ano: d.ano,
        pib: d.pib_crescimento_real_pct,
        inflacao: d.ipca_acumulado_ano_pct,
        desemprego: d.taxa_desemprego_anual,
        desmatamento: d.taxa_desmatamento_amazonia,
        salario: d.salario_minimo_nominal_brl,
      }))
      .filter((d) => d.ano != null);
  }, [mandateYears]);

  // Comparativo de todos mandatos (para ranking)
  const rankingData = useMemo(() => {
    return allPerformances
      .filter((p) => p.pib_medio_anual_pct != null)
      .map((p) => ({
        label: p.presidente.split(" ").slice(-1)[0] + (p.anos_cobertos ? ` (${p.anos_cobertos.slice(0, 4)})` : ""),
        fullName: p.presidente,
        pib: p.pib_medio_anual_pct,
        ipca: p.ipca_pos_real_pct,
        id: p.id_mandato,
      }))
      .sort((a, b) => (b.pib ?? 0) - (a.pib ?? 0));
  }, [allPerformances]);

  // ── Render sem seleção ──
  if (!mandateId || !performance) {
    return (
      <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-8 text-center space-y-3">
        <Briefcase className="w-10 h-10 mx-auto text-slate-700" />
        <p className="text-slate-400 font-semibold">Selecione um presidente na Linha do Tempo</p>
        <p className="text-sm text-slate-600">O Raio-X do Executivo exibirá KPIs econômicos e sociais detalhados do mandato selecionado.</p>
      </div>
    );
  }

  const p = performance;
  const meta = presidentMeta;

  // Deltas calculados
  const deltaCambio = (p.cambio_final_usd_brl != null && p.cambio_inicial_usd_brl != null)
    ? p.cambio_final_usd_brl - p.cambio_inicial_usd_brl : null;
  const deltaDivida = p.divida_liquida_delta_pct ?? null;
  const deltaSalario = (p.salario_minimo_final_brl != null && p.salario_minimo_inicial_brl != null)
    ? p.salario_minimo_final_brl - p.salario_minimo_inicial_brl : null;
  const deltaDesemprego = (p.desemprego_final_pct != null && p.desemprego_inicial_pct != null)
    ? p.desemprego_final_pct - p.desemprego_inicial_pct : null;

  return (
    <div className="space-y-6">

      {/* ── Título da Seção: Raio-X do Executivo Integrado ── */}
      <div className="flex items-center gap-3">
        <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
          <Briefcase className="w-5 h-5" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-base sm:text-lg font-bold text-slate-100">Raio-X do Mandato Executivo</h3>
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              Indicadores Consolidados
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Balanço fiscal, indicadores sociais e ranking comparativo com todos os mandatos da Nova República (1992 - 2026)
          </p>
        </div>
      </div>

      {/* ── Cabeçalho do Mandato ── */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-5 bg-gradient-to-r from-slate-900/90 to-slate-950/60 border border-slate-800 rounded-2xl p-5">
        <div className="relative flex-shrink-0">
          <img
            src={getPresidentPhotoUrl(meta?.id_referencia ?? p.id_mandato, meta?.foto_url)}
            alt={p.presidente}
            className="w-20 h-20 rounded-2xl object-cover object-top ring-2 ring-slate-700 shadow-xl"
            onError={(e) => {
              (e.target as HTMLImageElement).src = getPresidentPhotoUrl(p.id_mandato);
            }}
          />
          {p.status_mandato !== "CONCLUIDO" && (
            <span className="absolute -top-1 -right-1 flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500" />
            </span>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h2 className="text-xl font-extrabold text-slate-100 truncate">{p.presidente}</h2>
            <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-slate-800 text-slate-300 border border-slate-700">
              {p.partido}
            </span>
            {p.status_mandato !== "CONCLUIDO" && (
              <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                Em exercício
              </span>
            )}
          </div>
          <p className="text-slate-400 text-sm">{p.anos_cobertos}</p>
          {meta?.marcos_economicos && meta.marcos_economicos.length > 0 && (
            <p className="text-xs text-slate-500 mt-1.5 truncate">
              📌 {meta.marcos_economicos[0]}
            </p>
          )}
        </div>
        <div className="hidden sm:flex flex-col items-end gap-1 text-xs text-slate-600">
          <span>Fontes: IBGE, BCB</span>
          <span>INPE, Atlas da Violência</span>
          <span>Portal Transparência</span>
        </div>
      </div>

      {/* ── KPI Cards: Econômico ── */}
      <div>
        <p className="text-[10px] text-slate-500 uppercase tracking-widest font-semibold mb-3 flex items-center gap-1.5">
          <BarChart2 className="w-3.5 h-3.5 text-emerald-400" />
          Indicadores Econômicos
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <KPICard
            label="PIB (médio a.a.)"
            value={fmt(p.pib_medio_anual_pct, 1, "", "%")}
            sublabel={`Acum.: ${fmt(p.pib_crescimento_acumulado_pct, 1)}%`}
            icon={<TrendingUp className="w-4 h-4 text-emerald-400" />}
            accentBg="bg-emerald-400/10"
            tooltip="Crescimento médio anual do PIB real durante o mandato. Fonte: IBGE/BCB"
          />
          <KPICard
            label="Inflação IPCA"
            value={fmt(p.ipca_pos_real_pct, 1, "", "%/a")}
            sublabel={`Acum.: ${p.ipca_acumulado_pct != null && p.ipca_acumulado_pct < 1000 ? fmt(p.ipca_acumulado_pct, 1) + "%" : "hiperinfl."}`}
            icon={<BarChart2 className="w-4 h-4 text-rose-400" />}
            accentBg="bg-rose-400/10"
            tooltip="IPCA pós-real: inflação média anual calculada sobre o período. Acumulado é o total do mandato. Fonte: IBGE"
          />
          <KPICard
            label="Câmbio USD/BRL"
            value={`R$${fmt(p.cambio_final_usd_brl, 2)}`}
            sublabel={`Início: R$${fmt(p.cambio_inicial_usd_brl, 2)}`}
            delta={deltaCambio}
            invertGood
            icon={<DollarSign className="w-4 h-4 text-sky-400" />}
            accentBg="bg-sky-400/10"
            tooltip="Cotação USD/BRL no início e fim do mandato. Desvalorização = dólar mais caro. Fonte: BCB"
          />
          <KPICard
            label="Dívida Líquida"
            value={`${fmt(p.divida_liquida_final_pct_pib, 1)}% PIB`}
            sublabel={`Início: ${fmt(p.divida_liquida_inicial_pct_pib, 1)}% PIB`}
            delta={deltaDivida}
            invertGood
            icon={<Wallet className="w-4 h-4 text-amber-400" />}
            accentBg="bg-amber-400/10"
            tooltip="Dívida Líquida do Setor Público como % do PIB. Aumento = mais endividamento. Fonte: BCB/STN"
          />
          <KPICard
            label="Salário Mínimo"
            value={fmtBRL(p.salario_minimo_final_brl)}
            sublabel={`Início: ${fmtBRL(p.salario_minimo_inicial_brl)}`}
            delta={deltaSalario}
            icon={<Users className="w-4 h-4 text-violet-400" />}
            accentBg="bg-violet-400/10"
            tooltip="Salário mínimo nominal (BRL) no início e fim do mandato. Fonte: MTE"
          />
          <KPICard
            label="Desemprego"
            value={`${fmt(p.desemprego_medio_pct, 1)}%`}
            sublabel={`Fim: ${fmt(p.desemprego_final_pct, 1)}%`}
            delta={deltaDesemprego}
            invertGood
            icon={<Users className="w-4 h-4 text-orange-400" />}
            accentBg="bg-orange-400/10"
            tooltip="Taxa de desemprego média do período (PNAD Contínua). Fonte: IBGE"
          />
        </div>
      </div>

      {/* ── KPI Cards: Social & Ambiental ── */}
      {(p.desmatamento_acumulado_km2 != null || p.fome_final_pct != null || p.homicidios_medio != null) && (
        <div>
          <p className="text-[10px] text-slate-500 uppercase tracking-widest font-semibold mb-3 flex items-center gap-1.5">
            <Leaf className="w-3.5 h-3.5 text-teal-400" />
            Indicadores Sociais & Ambientais
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {p.desmatamento_acumulado_km2 != null && (
              <KPICard
                label="Desmatamento Amazônia"
                value={`${(p.desmatamento_acumulado_km2 / 1000).toFixed(0)}k km²`}
                sublabel={`Média: ${fmt(p.desmatamento_medio_anual_km2 ?? 0, 0)} km²/ano`}
                icon={<Leaf className="w-4 h-4 text-teal-400" />}
                accentBg="bg-teal-400/10"
                tooltip="Desmatamento acumulado na Amazônia Legal (PRODES/INPE) durante o mandato"
              />
            )}
            {p.fome_final_pct != null && (
              <KPICard
                label="Insegurança Alimentar"
                value={`${fmt(p.fome_final_pct, 1)}%`}
                sublabel={`Início: ${fmt(p.fome_inicial_pct, 1)}%`}
                delta={(p.fome_final_pct ?? 0) - (p.fome_inicial_pct ?? 0)}
                invertGood
                icon={<AlertCircle className="w-4 h-4 text-yellow-400" />}
                accentBg="bg-yellow-400/10"
                tooltip="% da população em situação de insegurança alimentar. Fonte: IBGE/FAO"
              />
            )}
            {p.homicidios_medio != null && (
              <KPICard
                label="Homicídios"
                value={`${fmt(p.homicidios_medio, 1)}/100k`}
                sublabel="taxa média por 100 mil hab."
                icon={<ShieldAlert className="w-4 h-4 text-red-400" />}
                accentBg="bg-red-400/10"
                tooltip="Taxa de homicídios por 100 mil habitantes (média do mandato). Fonte: Atlas da Violência/FBSP"
              />
            )}
            {p.feminicidios_medio != null && (
              <KPICard
                label="Feminicídios"
                value={`${fmt(p.feminicidios_medio, 1)}/100k`}
                sublabel="taxa média por 100 mil mulh."
                icon={<ShieldAlert className="w-4 h-4 text-pink-400" />}
                accentBg="bg-pink-400/10"
                tooltip="Taxa de feminicídios por 100 mil mulheres (média do mandato). Fonte: Atlas da Violência/FBSP"
              />
            )}
          </div>
        </div>
      )}

      {/* ── Gráficos do mandato ── */}
      {mandateChartData.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

          {/* PIB Anual */}
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-3">
            <SectionHeader
              icon={<TrendingUp className="w-4 h-4 text-emerald-400" />}
              title="Crescimento do PIB (% ao ano)"
              desc="Variação real do produto interno bruto — economias saudáveis crescem 2-4% ao ano"
            />
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={mandateChartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="ano" stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} />
                  <YAxis stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                  <Tooltip {...TOOLTIP_STYLE} formatter={(v) => [`${Number(v).toFixed(2)}%`, "PIB"]} />
                  <ReferenceLine y={0} stroke="#475569" strokeWidth={1.5} />
                  <Bar dataKey="pib" name="PIB % a.a." radius={[4, 4, 0, 0]}>
                    {mandateChartData.map((d, i) => (
                      <Cell key={i} fill={(d.pib ?? 0) >= 0 ? "#34d399" : "#fb7185"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Inflação Anual */}
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-3">
            <SectionHeader
              icon={<BarChart2 className="w-4 h-4 text-rose-400" />}
              title="Inflação IPCA (% ao ano)"
              desc="Meta do BCB é 3% ±1,5pp — acima de 4,5% é estouro da meta"
            />
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={mandateChartData.filter(d => d.inflacao != null && d.inflacao < 300)} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="ipca-grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#fb7185" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#fb7185" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="ano" stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} />
                  <YAxis stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                  <Tooltip {...TOOLTIP_STYLE} formatter={(v) => [`${Number(v).toFixed(1)}%`, "IPCA"]} />
                  <ReferenceLine y={4.5} stroke="#64748b" strokeDasharray="4 4" label={{ value: "Meta 4,5%", fill: "#64748b", fontSize: 10 }} />
                  <Area type="monotone" dataKey="inflacao" name="IPCA" stroke="#fb7185" strokeWidth={2.5} fill="url(#ipca-grad)" dot={{ fill: "#fb7185", r: 3 }} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Desemprego */}
          {mandateChartData.some(d => d.desemprego != null) && (
            <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-3">
              <SectionHeader
                icon={<Users className="w-4 h-4 text-amber-400" />}
                title="Taxa de Desemprego (% PNAD)"
                desc="% da força de trabalho que busca emprego mas não encontra — ideal abaixo de 8%"
              />
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={mandateChartData.filter(d => d.desemprego != null)} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="desemp-grad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#fbbf24" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#fbbf24" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis dataKey="ano" stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} />
                    <YAxis stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `${v}%`} domain={[0, "auto"]} />
                    <Tooltip {...TOOLTIP_STYLE} formatter={(v) => [`${Number(v).toFixed(1)}%`, "Desemprego"]} />
                    <ReferenceLine y={8} stroke="#64748b" strokeDasharray="4 4" label={{ value: "Ref. 8%", fill: "#64748b", fontSize: 10 }} />
                    <Area type="monotone" dataKey="desemprego" name="Desemprego" stroke="#fbbf24" strokeWidth={2.5} fill="url(#desemp-grad)" dot={{ fill: "#fbbf24", r: 3 }} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Desmatamento */}
          {mandateChartData.some(d => d.desmatamento != null) && (
            <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-3">
              <SectionHeader
                icon={<Leaf className="w-4 h-4 text-teal-400" />}
                title="Desmatamento Amazônia (km²/ano)"
                desc="Área desmatada anualmente — quanto menor, melhor. Meta do governo: zero até 2030"
              />
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={mandateChartData.filter(d => d.desmatamento != null)} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis dataKey="ano" stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} />
                    <YAxis stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `${(v/1000).toFixed(0)}k`} />
                    <Tooltip {...TOOLTIP_STYLE} formatter={(v) => [`${Number(v).toLocaleString("pt-BR")} km²`, "Desmatamento"]} />
                    <Bar dataKey="desmatamento" name="Desmatamento (km²)" fill="#2dd4bf" radius={[4, 4, 0, 0]} opacity={0.85} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Ranking de PIB entre todos os mandatos ── */}
      {rankingData.length > 1 && (
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-3">
          <SectionHeader
            icon={<BarChart2 className="w-4 h-4 text-cyan-400" />}
            title="Ranking: PIB Médio Anual por Mandato"
            desc="Comparativo histórico de crescimento econômico — contexto para avaliar o mandato atual"
          />
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rankingData} layout="vertical" margin={{ top: 0, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                <XAxis type="number" stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                <YAxis type="category" dataKey="label" stroke="#334155" tick={{ fill: "#94a3b8", fontSize: 11 }} width={110} />
                <Tooltip {...TOOLTIP_STYLE} formatter={(v) => [`${Number(v).toFixed(2)}% a.a.`, "PIB médio"]} />
                <ReferenceLine x={0} stroke="#475569" strokeWidth={1} />
                <Bar dataKey="pib" name="PIB médio a.a." radius={[0, 4, 4, 0]}>
                  {rankingData.map((d, i) => (
                    <Cell
                      key={i}
                      fill={d.id === mandateId ? "#22d3ee" : (d.pib ?? 0) >= 0 ? "#34d399" : "#fb7185"}
                      opacity={d.id === mandateId ? 1 : 0.6}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[11px] text-slate-600 flex items-center gap-1">
            <Info className="w-3 h-3" />
            Mandato atual destacado em ciano · Fonte: IBGE/BCB · Anos negativos refletem recessão
          </p>
        </div>
      )}

      {/* ── Marcos e Contexto ── */}
      {meta?.marcos_economicos && meta.marcos_economicos.length > 0 && (
        <div className="bg-slate-900/40 border border-slate-800/60 rounded-2xl p-5">
          <p className="text-[10px] text-slate-500 uppercase tracking-widest font-semibold mb-3">
            📌 Marcos do Mandato
          </p>
          <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {meta.marcos_economicos.map((marco, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-400">
                <span className="text-slate-600 mt-0.5 flex-shrink-0">▸</span>
                {marco}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Fontes ── */}
      <div className="bg-slate-900/30 border border-slate-800/40 rounded-xl px-4 py-3 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-slate-600">
        <span>📊 <strong className="text-slate-500">PIB:</strong> IBGE/BCB</span>
        <span>📈 <strong className="text-slate-500">IPCA:</strong> IBGE</span>
        <span>👷 <strong className="text-slate-500">Desemprego:</strong> PNAD Contínua / IBGE</span>
        <span>💵 <strong className="text-slate-500">Câmbio:</strong> Banco Central do Brasil</span>
        <span>💰 <strong className="text-slate-500">Salário Mínimo:</strong> MTE/Governo Federal</span>
        <span>🌳 <strong className="text-slate-500">Desmatamento:</strong> PRODES/INPE</span>
        <span>🔫 <strong className="text-slate-500">Violência:</strong> Atlas da Violência / FBSP</span>
        <span>🍽️ <strong className="text-slate-500">Fome:</strong> IBGE / FAO / Rede Penssan</span>
      </div>
    </div>
  );
}
