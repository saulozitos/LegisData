"use client";

import React, { useEffect, useState, useCallback } from "react";
import Header from "@/components/Header";
import {
  PresidentialMandate,
  MandateIndicatorData,
  getPresidentialMandates,
  getMandateIndicators,
} from "@/services/api";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import {
  TrendingUp,
  TrendingDown,
  Users,
  DollarSign,
  BarChart2,
  AlertTriangle,
  Briefcase,
  Minus,
  Calendar,
  Info,
} from "lucide-react";
import { getPresidentPhotoUrl } from "@/components/PresidentTimeline";

// ─── Types ────────────────────────────────────────────────────────────────────

interface KPIStat {
  primeiro: number;
  ultimo: number;
  minimo: number;
  maximo: number;
  media: number;
  variacao_pp?: number;
  total_acumulado?: number;
}

interface MandateSummary {
  mandate_id: string;
  nome: string;
  partido: string;
  inicio: string;
  fim: string | null;
  foto_url: string | null;
  total_meses: number;
  kpis: {
    inflacao_ipca?: KPIStat;
    desemprego_pnad?: KPIStat;
    aprovacao_popular?: KPIStat;
    cambio_usd_brl?: KPIStat;
    selic_meta?: KPIStat;
    emendas_bilhoes?: KPIStat & { total_acumulado?: number };
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt(value: number | undefined | null, decimals = 1): string {
  if (value == null) return "—";
  return value.toFixed(decimals);
}

function fmtDate(iso: string): string {
  const [y, m] = iso.split("-");
  const months = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];
  return `${months[parseInt(m) - 1]}/${y}`;
}

function trendIcon(delta: number | undefined) {
  if (delta == null) return <Minus className="w-4 h-4 text-slate-500" />;
  if (delta > 0.5) return <TrendingUp className="w-4 h-4 text-rose-400" />;
  if (delta < -0.5) return <TrendingDown className="w-4 h-4 text-emerald-400" />;
  return <Minus className="w-4 h-4 text-slate-400" />;
}

async function getMandateSummary(id: string): Promise<MandateSummary | null> {
  try {
    const base =
      (process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "").endsWith("/api/v1")
        ? process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "")
        : `${process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") || ""}/api/v1`) ||
      "/api/v1";
    const res = await fetch(`${base}/executivo/mandates/${id}/summary`, {
      next: { revalidate: 60 },
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────

interface KPICardProps {
  label: string;
  value: string;
  unit: string;
  sublabel?: string;
  delta?: number;
  invertDelta?: boolean; // true = queda é boa (desemprego, inflação)
  icon: React.ReactNode;
  accent: string; // tailwind color class
  tooltip?: string;
}

function KPICard({ label, value, unit, sublabel, delta, invertDelta = false, icon, accent, tooltip }: KPICardProps) {
  const isPositive = delta != null && (invertDelta ? delta < 0 : delta > 0);
  const isNegative = delta != null && (invertDelta ? delta > 0 : delta < 0);
  const deltaColor = isPositive ? "text-emerald-400" : isNegative ? "text-rose-400" : "text-slate-400";
  const deltaSign = delta != null && delta > 0 ? "+" : "";

  return (
    <div className={`relative bg-slate-900/70 border border-slate-800 rounded-2xl p-5 flex flex-col gap-3 hover:border-slate-700 transition-all group`}>
      <div className="flex items-start justify-between">
        <div className={`p-2 rounded-xl ${accent} border border-current/20`}>
          {icon}
        </div>
        {tooltip && (
          <div className="relative">
            <Info className="w-4 h-4 text-slate-600 group-hover:text-slate-400 transition-colors cursor-help" />
            <div className="absolute right-0 top-5 z-10 w-56 bg-slate-800 border border-slate-700 rounded-lg p-3 text-xs text-slate-300 hidden group-hover:block shadow-xl">
              {tooltip}
            </div>
          </div>
        )}
      </div>
      <div>
        <p className="text-slate-500 text-xs font-medium uppercase tracking-wider mb-1">{label}</p>
        <div className="flex items-baseline gap-1.5">
          <span className="text-3xl font-bold text-slate-100 tabular-nums">{value}</span>
          <span className="text-sm text-slate-500 font-medium">{unit}</span>
        </div>
        {sublabel && <p className="text-xs text-slate-500 mt-1">{sublabel}</p>}
      </div>
      {delta != null && (
        <div className={`flex items-center gap-1.5 text-sm font-semibold ${deltaColor}`}>
          {trendIcon(invertDelta ? -delta : delta)}
          <span>{deltaSign}{fmt(delta)} pp vs. início</span>
        </div>
      )}
    </div>
  );
}

// ─── Chart Section ────────────────────────────────────────────────────────────

const TOOLTIP_STYLE = {
  contentStyle: { backgroundColor: "#0f172a", borderColor: "#1e293b", borderRadius: "0.75rem", fontSize: "13px" },
  itemStyle: { color: "#f1f5f9" },
  labelStyle: { color: "#64748b", marginBottom: "6px", fontWeight: "bold" },
};

interface ChartSectionProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}

function ChartSection({ title, description, icon, children }: ChartSectionProps) {
  return (
    <section className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-md flex flex-col gap-4">
      <div className="flex items-start gap-3 pb-4 border-b border-slate-800">
        <div className="mt-0.5">{icon}</div>
        <div>
          <h2 className="text-lg font-bold text-slate-100">{title}</h2>
          <p className="text-sm text-slate-500">{description}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function ExecutivoDashboard() {
  const [mandates, setMandates] = useState<PresidentialMandate[]>([]);
  const [selectedMandateId, setSelectedMandateId] = useState<string>("");
  const [indicators, setIndicators] = useState<MandateIndicatorData[]>([]);
  const [summary, setSummary] = useState<MandateSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const m = await getPresidentialMandates();
        setMandates(m);
        if (m.length > 0) {
          setSelectedMandateId(m[m.length - 1].id); // Mais recente por padrão
        }
      } catch (err) {
        console.error("Erro ao carregar mandatos", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const loadMandateDetail = useCallback(async (id: string) => {
    if (!id) return;
    setLoadingDetail(true);
    try {
      const [indData, sumData] = await Promise.all([
        getMandateIndicators(id),
        getMandateSummary(id),
      ]);
      setIndicators(indData);
      setSummary(sumData);
    } catch (err) {
      console.error("Erro ao carregar detalhes", err);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    loadMandateDetail(selectedMandateId);
  }, [selectedMandateId, loadMandateDetail]);

  if (loading) {
    return (
      <main className="min-h-screen bg-slate-950 text-slate-50 flex items-center justify-center font-sans">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-cyan-500"></div>
      </main>
    );
  }

  const selectedMandate = mandates.find((m) => m.id === selectedMandateId);
  const kpis = summary?.kpis;

  // Formata para o eixo X dos gráficos
  const chartData = indicators.map((d) => ({
    ...d,
    label: fmtDate(d.data as string),
  }));

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50 font-sans selection:bg-cyan-500/30">
      <Header />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">

        {/* ── Cabeçalho ── */}
        <header className="space-y-2">
          <div className="flex items-center gap-3">
            <span className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 shadow-lg shadow-cyan-500/10">
              <Briefcase className="w-6 h-6" />
            </span>
            <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-slate-100 to-slate-400">
              Raio-X do Executivo
            </h1>
          </div>
          <p className="text-slate-400 max-w-2xl pl-1">
            KPIs econômicos e sociais reais por mandato presidencial — inflação, desemprego, câmbio, aprovação popular e muito mais.
          </p>
        </header>

        {/* ── Seletor de Mandatos ── */}
        <section className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-md">
          <p className="text-xs text-slate-500 uppercase tracking-wider font-semibold mb-4 flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5" />
            Selecione o Mandato
          </p>
          <div className="flex flex-wrap gap-3">
            {mandates.map((m) => (
              <button
                key={m.id}
                onClick={() => setSelectedMandateId(m.id)}
                className={`flex items-center gap-3 px-4 py-2.5 rounded-xl border transition-all ${
                  selectedMandateId === m.id
                    ? "bg-cyan-500/20 border-cyan-500/40 text-cyan-300 shadow-lg shadow-cyan-500/10"
                    : "bg-slate-950 border-slate-800 text-slate-300 hover:border-slate-600 hover:bg-slate-900"
                }`}
              >
                {m.foto_url && (
                  <img
                    src={getPresidentPhotoUrl(m.nome.toLowerCase(), m.foto_url)}
                    alt={m.nome}
                    className="w-9 h-9 rounded-full object-cover ring-2 ring-slate-700"
                  />
                )}
                <div className="text-left">
                  <p className="font-bold text-sm leading-tight">{m.nome.split(" ").slice(-1)[0]}</p>
                  <p className="text-xs text-slate-500">{m.partido} · {m.inicio?.slice(0,4)}–{m.fim?.slice(0,4) ?? "atual"}</p>
                </div>
              </button>
            ))}
          </div>
        </section>

        {/* ── Loading overlay ── */}
        {loadingDetail && (
          <div className="flex justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-cyan-500"></div>
          </div>
        )}

        {!loadingDetail && selectedMandate && summary && (
          <>
            {/* ── Cabeçalho do presidente ── */}
            <div className="flex flex-col sm:flex-row sm:items-center gap-5 bg-gradient-to-r from-slate-900/80 to-slate-950/60 border border-slate-800 rounded-2xl p-6">
              {selectedMandate.foto_url && (
                <img
                  src={getPresidentPhotoUrl(selectedMandate.nome.toLowerCase(), selectedMandate.foto_url)}
                  alt={selectedMandate.nome}
                  className="w-20 h-20 rounded-2xl object-cover ring-2 ring-cyan-500/30 shadow-xl"
                />
              )}
              <div className="flex-1">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <h2 className="text-2xl font-extrabold text-slate-100">{selectedMandate.nome}</h2>
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                    {selectedMandate.partido}
                  </span>
                </div>
                <p className="text-slate-400 text-sm">
                  {fmtDate(selectedMandate.inicio)} → {selectedMandate.fim ? fmtDate(selectedMandate.fim) : "Governo atual"}
                  {" "}· {summary.total_meses} meses de dados
                </p>
              </div>
              <div className="text-right text-xs text-slate-600 hidden sm:block">
                <p>Fontes: IBGE, BCB, Datafolha</p>
                <p>Portal da Transparência</p>
              </div>
            </div>

            {/* ── KPI Cards ── */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">

              <KPICard
                label="Inflação IPCA"
                value={fmt(kpis?.inflacao_ipca?.media)}
                unit="% a.a."
                sublabel={`Pico: ${fmt(kpis?.inflacao_ipca?.maximo)}%`}
                delta={kpis?.inflacao_ipca?.variacao_pp}
                invertDelta
                icon={<BarChart2 className="w-5 h-5 text-rose-400" />}
                accent="text-rose-400 bg-rose-400/10"
                tooltip="Média do IPCA (variação % 12 meses) durante o mandato. Fonte: IBGE"
              />

              <KPICard
                label="Desemprego"
                value={fmt(kpis?.desemprego_pnad?.media)}
                unit="% PNAD"
                sublabel={`Mín: ${fmt(kpis?.desemprego_pnad?.minimo)}% · Máx: ${fmt(kpis?.desemprego_pnad?.maximo)}%`}
                delta={(kpis?.desemprego_pnad?.ultimo ?? 0) - (kpis?.desemprego_pnad?.primeiro ?? 0)}
                invertDelta
                icon={<Users className="w-5 h-5 text-amber-400" />}
                accent="text-amber-400 bg-amber-400/10"
                tooltip="Taxa de desemprego PNAD Contínua (média do mandato). Fonte: IBGE"
              />

              <KPICard
                label="Aprovação"
                value={fmt(kpis?.aprovacao_popular?.media)}
                unit="% pop."
                sublabel={`Pico: ${fmt(kpis?.aprovacao_popular?.maximo)}% · Vale: ${fmt(kpis?.aprovacao_popular?.minimo)}%`}
                delta={(kpis?.aprovacao_popular?.ultimo ?? 0) - (kpis?.aprovacao_popular?.primeiro ?? 0)}
                icon={<Users className="w-5 h-5 text-emerald-400" />}
                accent="text-emerald-400 bg-emerald-400/10"
                tooltip="Aprovação popular média (Datafolha/CNT). Considera 'ótimo + bom'."
              />

              <KPICard
                label="Câmbio (USD)"
                value={fmt(kpis?.cambio_usd_brl?.ultimo, 2)}
                unit="R$"
                sublabel={`Início: R$ ${fmt(kpis?.cambio_usd_brl?.primeiro, 2)}`}
                delta={(kpis?.cambio_usd_brl?.ultimo ?? 0) - (kpis?.cambio_usd_brl?.primeiro ?? 0)}
                invertDelta
                icon={<DollarSign className="w-5 h-5 text-sky-400" />}
                accent="text-sky-400 bg-sky-400/10"
                tooltip="Câmbio USD/BRL (cotação média mensal). Variação = início vs. fim do mandato. Fonte: BCB"
              />

              <KPICard
                label="Selic"
                value={fmt(kpis?.selic_meta?.ultimo)}
                unit="% a.a."
                sublabel={`Média: ${fmt(kpis?.selic_meta?.media)}%`}
                delta={(kpis?.selic_meta?.ultimo ?? 0) - (kpis?.selic_meta?.primeiro ?? 0)}
                invertDelta
                icon={<TrendingUp className="w-5 h-5 text-violet-400" />}
                accent="text-violet-400 bg-violet-400/10"
                tooltip="Taxa Selic meta ao final do mandato (%). Fonte: BCB/COPOM"
              />

              <KPICard
                label="Emendas"
                value={fmt(kpis?.emendas_bilhoes?.total_acumulado, 1)}
                unit="R$ bi"
                sublabel="Total acumulado"
                icon={<AlertTriangle className="w-5 h-5 text-orange-400" />}
                accent="text-orange-400 bg-orange-400/10"
                tooltip="Total de emendas parlamentares executadas no período. Fonte: Portal da Transparência"
              />
            </div>

            {/* ── Gráficos ── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

              {/* Inflação × Aprovação */}
              <ChartSection
                title="Inflação vs. Aprovação Popular"
                description="Como a inflação impactou a popularidade do governo (IPCA 12m · Datafolha)"
                icon={<BarChart2 className="w-5 h-5 text-rose-400" />}
              >
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                      <XAxis dataKey="label" stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} interval="preserveStartEnd" />
                      <YAxis yAxisId="left" stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                      <YAxis yAxisId="right" orientation="right" stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                      <Tooltip {...TOOLTIP_STYLE} formatter={(val, name) => [`${(val as number).toFixed(1)}%`, name]} />
                      <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "8px" }} />
                      <Line yAxisId="left" type="monotone" dataKey="inflacao_ipca" name="Inflação IPCA (%)" stroke="#fb7185" strokeWidth={2.5} dot={false} />
                      <Line yAxisId="right" type="monotone" dataKey="aprovacao_popular" name="Aprovação (%)" stroke="#34d399" strokeWidth={2.5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </ChartSection>

              {/* Desemprego */}
              <ChartSection
                title="Desemprego (PNAD Contínua)"
                description="Taxa de desocupação trimestral — mede quantos buscam trabalho mas não encontram"
                icon={<Users className="w-5 h-5 text-amber-400" />}
              >
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="colorDesemp" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#fbbf24" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#fbbf24" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                      <XAxis dataKey="label" stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} interval="preserveStartEnd" />
                      <YAxis stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `${v}%`} domain={["auto", "auto"]} />
                      <Tooltip {...TOOLTIP_STYLE} formatter={(val) => [`${(val as number).toFixed(1)}%`, "Desemprego"]} />
                      <ReferenceLine y={kpis?.desemprego_pnad?.media} stroke="#64748b" strokeDasharray="4 4" label={{ value: `Média: ${fmt(kpis?.desemprego_pnad?.media)}%`, fill: "#64748b", fontSize: 11 }} />
                      <Area type="monotone" dataKey="desemprego_pnad" name="Desemprego (%)" stroke="#fbbf24" strokeWidth={2.5} fill="url(#colorDesemp)" dot={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </ChartSection>

              {/* Câmbio × Selic */}
              <ChartSection
                title="Câmbio (USD/BRL) × Selic"
                description="Relação entre política monetária e desvalorização cambial"
                icon={<DollarSign className="w-5 h-5 text-sky-400" />}
              >
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                      <XAxis dataKey="label" stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} interval="preserveStartEnd" />
                      <YAxis yAxisId="left" stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `R$${v}`} />
                      <YAxis yAxisId="right" orientation="right" stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                      <Tooltip {...TOOLTIP_STYLE} formatter={(val, name) => [name.includes("Câmbio") ? `R$ ${(val as number).toFixed(2)}` : `${(val as number).toFixed(2)}%`, name]} />
                      <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "8px" }} />
                      <Line yAxisId="left" type="monotone" dataKey="cambio_usd_brl" name="Câmbio USD/BRL" stroke="#38bdf8" strokeWidth={2.5} dot={false} />
                      <Line yAxisId="right" type="monotone" dataKey="selic_meta" name="Selic Meta (%)" stroke="#a78bfa" strokeWidth={2.5} dot={false} strokeDasharray="4 2" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </ChartSection>

              {/* Emendas */}
              <ChartSection
                title="Emendas Parlamentares (R$ bilhões)"
                description="Acumulado mensal de emendas liberadas — instrumento de negociação política do Executivo"
                icon={<AlertTriangle className="w-5 h-5 text-orange-400" />}
              >
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="colorEmendas" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#fb923c" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#fb923c" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                      <XAxis dataKey="label" stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} interval="preserveStartEnd" />
                      <YAxis stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `R$${v}bi`} />
                      <Tooltip {...TOOLTIP_STYLE} formatter={(val) => [`R$ ${(val as number).toFixed(1)} bilhões`, "Emendas"]} />
                      <Area type="monotone" dataKey="emendas_bilhoes" name="Emendas (R$ bi)" stroke="#fb923c" strokeWidth={2.5} fill="url(#colorEmendas)" dot={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
                <p className="text-xs text-slate-600 mt-1 flex items-center gap-1">
                  <Info className="w-3 h-3" />
                  Valores crescem ao longo do ano e resetam em janeiro — padrão do ciclo orçamentário.
                </p>
              </ChartSection>
            </div>

            {/* ── Nota de fontes ── */}
            <div className="bg-slate-900/40 border border-slate-800/60 rounded-xl p-4 text-xs text-slate-500 flex flex-wrap gap-x-6 gap-y-1">
              <span>📊 <strong className="text-slate-400">IPCA:</strong> IBGE (variação acumulada 12 meses)</span>
              <span>👷 <strong className="text-slate-400">Desemprego:</strong> PNAD Contínua / IBGE (trimestral)</span>
              <span>📢 <strong className="text-slate-400">Aprovação:</strong> Datafolha / CNT-MDA</span>
              <span>💵 <strong className="text-slate-400">Câmbio:</strong> Banco Central do Brasil</span>
              <span>🏦 <strong className="text-slate-400">Selic:</strong> Banco Central / COPOM</span>
              <span>📋 <strong className="text-slate-400">Emendas:</strong> Portal da Transparência</span>
            </div>
          </>
        )}

        {/* Estado vazio */}
        {!loadingDetail && mandates.length === 0 && (
          <div className="text-center py-20 text-slate-500">
            <Briefcase className="w-12 h-12 mx-auto mb-4 opacity-30" />
            <p className="text-lg font-semibold">Nenhum mandato cadastrado</p>
            <p className="text-sm mt-1">Execute o script <code className="bg-slate-800 px-1 rounded">seed_executivo.py</code> para popular os dados.</p>
          </div>
        )}
      </div>
    </main>
  );
}
