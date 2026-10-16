"use client";

import React, { useMemo, useState } from "react";
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
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
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
  Award,
  Scale,
} from "lucide-react";
import { getPresidentPhotoUrl } from "@/components/PresidentTimeline";
import { isActiveStatus } from "@/lib/mandate";
import { fmtNum, fmtPct, isNum } from "@/lib/format";

// ─── Helpers ──────────────────────────────────────────────────────────────────

export function fmt(v: number | null | undefined, d = 1, prefix = "", suffix = ""): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${prefix}${v.toFixed(d)}${suffix}`;
}

export function fmtBRL(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(v);
}

export function deltaColor(delta: number | null | undefined, invertGood = false): string {
  if (delta == null) return "text-slate-400";
  const isGood = invertGood ? delta < 0 : delta > 0;
  const isBad = invertGood ? delta > 0 : delta < 0;
  if (isGood) return "text-emerald-400";
  if (isBad) return "text-rose-400";
  return "text-slate-400";
}

function DeltaIcon({ delta, invertGood = false }: { delta: number | null | undefined; invertGood?: boolean }) {
  if (delta == null) return <Minus className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />;
  const isGood = invertGood ? delta < 0 : delta > 0;
  if (Math.abs(delta) < 0.5) return <Minus className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />;
  return isGood
    ? <TrendingUp className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />
    : <TrendingDown className="w-3.5 h-3.5 text-rose-400" aria-hidden="true" />;
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
            <button
              type="button"
              aria-label={`Sobre ${label}: ${tooltip}`}
              className="peer rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
            >
              <Info className="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-300 transition-colors cursor-help" aria-hidden="true" />
            </button>
            <div
              role="tooltip"
              className="absolute right-0 top-5 z-20 w-52 bg-slate-800 border border-slate-700 rounded-lg p-2.5 text-[11px] text-slate-300 hidden group-hover:block peer-hover:block peer-focus-visible:block shadow-xl leading-relaxed"
            >
              {tooltip}
            </div>
          </div>
        )}
      </div>
      <div>
        <p className="text-slate-400 text-[10px] font-semibold uppercase tracking-wider mb-0.5">{label}</p>
        <span className="text-2xl font-bold text-slate-100 tabular-nums leading-tight">{value}</span>
        {sublabel && <p className="text-[11px] text-slate-400 mt-0.5">{sublabel}</p>}
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
        <p className="text-xs text-slate-400 mt-0.5">{desc}</p>
      </div>
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

  const [rankingMetric, setRankingMetric] = useState<"pib" | "iple">("pib");

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

  const rankingIpleData = useMemo(() => {
    return allPerformances
      .filter((p) => p.iple?.indicadores_base?.iple_score != null)
      .map((p) => ({
        label: p.presidente.split(" ").slice(-1)[0] + (p.anos_cobertos ? ` (${p.anos_cobertos.slice(0, 4)})` : ""),
        fullName: p.presidente,
        iple: p.iple?.indicadores_base?.iple_score,
        ts: p.iple?.indicadores_base?.taxa_sucesso_ts,
        tmv: p.iple?.indicadores_base?.taxa_manutencao_vetos_tmv,
        id: p.id_mandato,
      }))
      .sort((a, b) => (b.iple ?? 0) - (a.iple ?? 0));
  }, [allPerformances]);

  // ── Render sem seleção ──
  if (!mandateId || !performance) {
    return (
      <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-8 text-center space-y-3">
        <Briefcase className="w-10 h-10 mx-auto text-slate-400" aria-hidden="true" />
        <p className="text-slate-300 font-semibold">Selecione um presidente na Linha do Tempo</p>
        <p className="text-sm text-slate-400">O Raio-X do Executivo exibirá KPIs econômicos e sociais detalhados do mandato selecionado.</p>
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
  const deltaFome = (p.fome_final_pct != null && p.fome_inicial_pct != null)
    ? p.fome_final_pct - p.fome_inicial_pct : null;
  // Apenas status explícito de exercício conta como "em exercício" (ex.: IMPEACHMENT, CONCLUIDO não).
  const isOngoing = isActiveStatus(p.status_mandato);
  const photoUrl = getPresidentPhotoUrl(meta?.id_referencia ?? p.id_mandato, meta?.foto_url);

  return (
    <div className="space-y-6">

      {/* ── Título da Seção: Raio-X do Executivo Integrado ── */}
      <div className="flex items-center gap-3">
        <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
          <Briefcase className="w-5 h-5" aria-hidden="true" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-base sm:text-lg font-bold text-slate-100">Raio-X do Mandato Executivo</h3>
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              Indicadores Consolidados
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Balanço fiscal, indicadores sociais e ranking comparativo com todos os mandatos presidenciais desde 1995
          </p>
        </div>
      </div>

      {/* ── Cabeçalho do Mandato ── */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-5 bg-gradient-to-r from-slate-900/90 to-slate-950/60 border border-slate-800 rounded-2xl p-5">
        <div className="relative flex-shrink-0">
          {photoUrl && (
            <img
              src={photoUrl}
              alt={p.presidente}
              referrerPolicy="no-referrer"
              className="w-20 h-20 rounded-2xl object-cover object-top ring-2 ring-slate-700 shadow-xl"
              onError={(e) => {
                const target = e.currentTarget;
                const local = getPresidentPhotoUrl(p.id_mandato);
                if (local && !target.src.endsWith(local)) {
                  target.src = local;
                } else {
                  target.style.display = "none";
                }
              }}
            />
          )}
          {isOngoing && (
            <span className="absolute -top-1 -right-1 flex h-3 w-3" aria-hidden="true">
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
            {isOngoing && (
              <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                Em exercício
              </span>
            )}
          </div>
          <p className="text-slate-400 text-sm">{p.anos_cobertos}</p>
          {meta?.marcos_economicos && meta.marcos_economicos.length > 0 && (
            <p className="text-xs text-slate-400 mt-1.5 truncate">
              📌 {meta.marcos_economicos[0]}
            </p>
          )}
        </div>
        <div className="hidden sm:flex flex-col items-end gap-1 text-xs text-slate-400">
          <span>Fontes: IBGE, BCB</span>
          <span>INPE, Atlas da Violência</span>
          <span>Portal Transparência</span>
        </div>
      </div>

      {/* ── KPI Cards: Econômico ── */}
      <div>
        <p className="text-[10px] text-slate-400 uppercase tracking-widest font-semibold mb-3 flex items-center gap-1.5">
          <BarChart2 className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />
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
          <p className="text-[10px] text-slate-400 uppercase tracking-widest font-semibold mb-3 flex items-center gap-1.5">
            <Leaf className="w-3.5 h-3.5 text-teal-400" aria-hidden="true" />
            Indicadores Sociais & Ambientais
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {p.desmatamento_acumulado_km2 != null && (
              <KPICard
                label="Desmatamento Amazônia"
                value={`${fmt(p.desmatamento_acumulado_km2 / 1000, 0)}k km²`}
                sublabel={`Média: ${fmt(p.desmatamento_medio_anual_km2, 0)} km²/ano`}
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
                delta={deltaFome}
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

      {/* ── Seção: Poder Legislativo do Executivo (IPLE) ── */}
      {p.iple && (
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                <Scale className="w-5 h-5" aria-hidden="true" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-slate-100">
                    Índice de Poder Legislativo do Executivo (IPLE)
                  </h3>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 font-mono">
                    Modelo Científico QCA
                  </span>
                </div>
                <p className="text-xs text-slate-400">
                  Mede a capacidade de aprovação de projetos (TS) e blindagem de vetos presidenciais (TMV)
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span
                className={`px-3 py-1 rounded-xl text-xs font-bold border flex items-center gap-1.5 ${
                  p.iple.calibragem_crisp_set.iple.crisp_val === 1
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                    : "bg-rose-500/10 text-rose-400 border-rose-500/30"
                }`}
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    p.iple.calibragem_crisp_set.iple.crisp_val === 1 ? "bg-emerald-400" : "bg-rose-400"
                  }`}
                />
                {p.iple.calibragem_crisp_set.iple.classificacao}
              </span>
            </div>
          </div>

          {/* Cards Principais: IPLE Score, TS e TMV */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Score IPLE */}
            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Score IPLE Principal
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                  Corte: ≥ 0.785
                </span>
              </div>
              <div className="my-2">
                <div className="text-2xl font-black font-mono text-indigo-400">
                  {p.iple.indicadores_base.iple_score.toFixed(3)}
                  <span className="text-xs font-normal text-slate-400"> / 1.000</span>
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      p.iple.indicadores_base.iple_score >= 0.785 ? "bg-indigo-500" : "bg-rose-500"
                    }`}
                    style={{ width: `${Math.min(100, p.iple.indicadores_base.iple_score * 100)}%` }}
                  />
                </div>
              </div>
              <span className="text-[11px] text-slate-400">
                Média aritmética: (TS + TMV) / 2
              </span>
            </div>

            {/* Taxa de Sucesso (TS) */}
            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Taxa de Sucesso (TS)
                </span>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${
                  p.iple.calibragem_crisp_set.ts.crisp_val === 1
                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                }`}>
                  {p.iple.calibragem_crisp_set.ts.classificacao}
                </span>
              </div>
              <div className="my-2">
                <div className="text-2xl font-black font-mono text-emerald-400">
                  {(p.iple.indicadores_base.taxa_sucesso_ts * 100).toFixed(1)}%
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-emerald-500"
                    style={{ width: `${Math.min(100, p.iple.indicadores_base.taxa_sucesso_ts * 100)}%` }}
                  />
                </div>
              </div>
              <span className="text-[11px] text-slate-400">
                {p.iple.indicadores_base.proposicoes_executivo_aprovadas} de {p.iple.indicadores_base.proposicoes_executivo_total} proposições (Corte: ≥ 87%)
              </span>
            </div>

            {/* Manutenção de Vetos (TMV) */}
            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Manutenção de Vetos (TMV)
                </span>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${
                  p.iple.calibragem_crisp_set.tmv.crisp_val === 1
                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                }`}>
                  {p.iple.calibragem_crisp_set.tmv.classificacao}
                </span>
              </div>
              <div className="my-2">
                <div className="text-2xl font-black font-mono text-sky-400">
                  {(p.iple.indicadores_base.taxa_manutencao_vetos_tmv * 100).toFixed(1)}%
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-sky-500"
                    style={{ width: `${Math.min(100, p.iple.indicadores_base.taxa_manutencao_vetos_tmv * 100)}%` }}
                  />
                </div>
              </div>
              <span className="text-[11px] text-slate-400">
                {p.iple.indicadores_base.vetos_mantidos} mantidos de {p.iple.indicadores_base.vetos_total_apreciados} apreciados (Corte: ≥ 70%)
              </span>
            </div>
          </div>

          {/* Variáveis Contextuais QCA */}
          <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800/80">
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
              Variáveis Contextuais de Calibragem QCA:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              <div className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-xs text-slate-300 font-medium block">
                    X₁: Tamanho da Oposição
                  </span>
                  <span className="text-[10px] text-slate-400">
                    {fmtNum(p.iple.variaveis_contextuais.oposicao_cadeiras, 0)} de {fmtNum(p.iple.variaveis_contextuais.total_cadeiras, 0)} assentos
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-xs font-mono font-bold text-slate-200">
                    {fmtPct(isNum(p.iple.variaveis_contextuais.tamanho_oposicao_x1) ? p.iple.variaveis_contextuais.tamanho_oposicao_x1 * 100 : null, 1)}
                  </span>
                  <span className="text-[9px] block text-slate-400">
                    {p.iple.calibragem_crisp_set.oposicao_x1.classificacao}
                  </span>
                </div>
              </div>

              <div className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-xs text-slate-300 font-medium block">
                    X₂: Fragmentação (NEP)
                  </span>
                  <span className="text-[10px] text-slate-400">
                    Laakso & Taagepera (1979)
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-xs font-mono font-bold text-slate-200">
                    {fmtNum(p.iple.variaveis_contextuais.fragmentacao_nep_x2, 2)}
                  </span>
                  <span className="text-[9px] block text-slate-400">
                    {p.iple.calibragem_crisp_set.fragmentacao_x2.classificacao}
                  </span>
                </div>
              </div>

              <div className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-xs text-slate-300 font-medium block">
                    X₃: Polarização (IPP)
                  </span>
                  <span className="text-[10px] text-slate-400">
                    Escala Dalton 1-10 ponderada
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-xs font-mono font-bold text-slate-200">
                    {fmtNum(p.iple.variaveis_contextuais.polarizacao_ipp_x3, 2)}
                  </span>
                  <span className="text-[9px] block text-slate-400">
                    {p.iple.calibragem_crisp_set.polarizacao_x3.classificacao}
                  </span>
                </div>
              </div>
            </div>
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
                    {mandateChartData.map((d) => (
                      <Cell key={d.ano} fill={(d.pib ?? 0) >= 0 ? "#34d399" : "#fb7185"} />
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

      {/* ── Ranking entre todos os mandatos ── */}
      {rankingData.length > 1 && (
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <SectionHeader
              icon={<BarChart2 className="w-4 h-4 text-cyan-400" />}
              title={rankingMetric === "pib" ? "Ranking: PIB Médio Anual por Mandato" : "Ranking: Poder Legislativo (IPLE)"}
              desc={
                rankingMetric === "pib"
                  ? "Comparativo histórico de crescimento econômico — contexto para avaliar o mandato atual"
                  : "Comparativo de governabilidade e blindagem legislativa (corte de Executivo Forte: 0.785)"
              }
            />
            {rankingIpleData.length > 1 && (
              <div className="flex items-center gap-1 p-1 bg-slate-950/80 rounded-xl border border-slate-800 text-xs">
                <button
                  type="button"
                  onClick={() => setRankingMetric("pib")}
                  className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                    rankingMetric === "pib"
                      ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  PIB Médio
                </button>
                <button
                  type="button"
                  onClick={() => setRankingMetric("iple")}
                  className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                    rankingMetric === "iple"
                      ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  IPLE (Governabilidade)
                </button>
              </div>
            )}
          </div>

          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              {rankingMetric === "pib" ? (
                <BarChart data={rankingData} layout="vertical" margin={{ top: 0, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                  <XAxis type="number" stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                  <YAxis type="category" dataKey="label" stroke="#334155" tick={{ fill: "#94a3b8", fontSize: 11 }} width={110} />
                  <Tooltip {...TOOLTIP_STYLE} formatter={(v) => [`${Number(v).toFixed(2)}% a.a.`, "PIB médio"]} />
                  <ReferenceLine x={0} stroke="#475569" strokeWidth={1} />
                  <Bar dataKey="pib" name="PIB médio a.a." radius={[0, 4, 4, 0]}>
                    {rankingData.map((d) => (
                      <Cell
                        key={d.id}
                        fill={d.id === mandateId ? "#22d3ee" : (d.pib ?? 0) >= 0 ? "#34d399" : "#fb7185"}
                        opacity={d.id === mandateId ? 1 : 0.6}
                      />
                    ))}
                  </Bar>
                </BarChart>
              ) : (
                <BarChart data={rankingIpleData} layout="vertical" margin={{ top: 0, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                  <XAxis type="number" domain={[0, 1]} stroke="#334155" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                  <YAxis type="category" dataKey="label" stroke="#334155" tick={{ fill: "#94a3b8", fontSize: 11 }} width={110} />
                  <Tooltip {...TOOLTIP_STYLE} formatter={(v) => [`${Number(v).toFixed(3)} (0 a 1)`, "Score IPLE"]} />
                  <ReferenceLine x={0.785} stroke="#818cf8" strokeDasharray="3 3" strokeWidth={1.5} />
                  <Bar dataKey="iple" name="Score IPLE" radius={[0, 4, 4, 0]}>
                    {rankingIpleData.map((d) => (
                      <Cell
                        key={d.id}
                        fill={d.id === mandateId ? "#22d3ee" : (d.iple ?? 0) >= 0.785 ? "#818cf8" : "#fb7185"}
                        opacity={d.id === mandateId ? 1 : 0.65}
                      />
                    ))}
                  </Bar>
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
          <p className="text-[11px] text-slate-400 flex items-center gap-1">
            <Info className="w-3 h-3" aria-hidden="true" />
            {rankingMetric === "pib"
              ? "Mandato atual destacado em ciano · Fonte: IBGE/BCB · Anos negativos refletem recessão"
              : "Linha tracejada em 0.785 marca o limiar de Executivo Forte / Poderoso segundo o modelo científico QCA"
            }
          </p>
        </div>
      )}

      {/* ── Contexto Político-Econômico: Ministros & Marcos ── */}
      {((meta?.ministros_fazenda_chave && meta.ministros_fazenda_chave.length > 0) ||
        (p.ministros_fazenda_principais && p.ministros_fazenda_principais.length > 0) ||
        (meta?.marcos_economicos && meta.marcos_economicos.length > 0)) && (
        <div className="bg-slate-900/40 border border-slate-800/60 rounded-2xl p-5 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Ministros da Fazenda / Economia */}
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Award className="w-4 h-4 text-emerald-400" aria-hidden="true" />
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  Ministros da Fazenda / Economia no Período
                </h4>
              </div>
              <div className="flex flex-wrap gap-2">
                {meta?.ministros_fazenda_chave && meta.ministros_fazenda_chave.length > 0 ? (
                  meta.ministros_fazenda_chave.map((min) => (
                    <span
                      key={`${min.nome}-${min.inicio}`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800/80 border border-slate-700/60 text-xs font-medium text-slate-200"
                    >
                      <span>{min.nome}</span>
                      {min.papel && (
                        <span className="text-[10px] text-emerald-400 font-bold">
                          ({min.papel})
                        </span>
                      )}
                    </span>
                  ))
                ) : p.ministros_fazenda_principais && p.ministros_fazenda_principais.length > 0 ? (
                  p.ministros_fazenda_principais.map((min) => (
                    <span
                      key={min}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-800/80 border border-slate-700/60 text-xs font-medium text-slate-200"
                    >
                      {min}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-slate-400">
                    Informação não disponível para este mandato.
                  </span>
                )}
              </div>
            </div>

            {/* Marcos e Políticas do Mandato */}
            {meta?.marcos_economicos && meta.marcos_economicos.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-sm">📌</span>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Marcos Estruturantes do Mandato
                  </h4>
                </div>
                <ul className="space-y-2">
                  {meta.marcos_economicos.map((marco) => (
                    <li key={marco} className="flex items-start gap-2 text-xs sm:text-sm text-slate-400">
                      <span className="text-emerald-400 mt-0.5 flex-shrink-0">▸</span>
                      <span>{marco}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Fontes ── */}
      <div className="bg-slate-900/30 border border-slate-800/40 rounded-xl px-4 py-3 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-slate-400">
        <span>📊 <strong className="text-slate-300">PIB:</strong> IBGE/BCB</span>
        <span>📈 <strong className="text-slate-300">IPCA:</strong> IBGE</span>
        <span>👷 <strong className="text-slate-300">Desemprego:</strong> PNAD Contínua / IBGE</span>
        <span>💵 <strong className="text-slate-300">Câmbio:</strong> Banco Central do Brasil</span>
        <span>💰 <strong className="text-slate-300">Salário Mínimo:</strong> MTE/Governo Federal</span>
        <span>🌳 <strong className="text-slate-300">Desmatamento:</strong> PRODES/INPE</span>
        <span>🔫 <strong className="text-slate-300">Violência:</strong> Atlas da Violência / FBSP</span>
        <span>🍽️ <strong className="text-slate-300">Fome:</strong> IBGE / FAO / Rede Penssan</span>
      </div>
    </div>
  );
}
