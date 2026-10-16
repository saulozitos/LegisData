"use client";

import React, { useState, useMemo } from "react";
import {
  Landmark,
  ShieldAlert,
  Users,
  Award,
  BarChart3,
  CheckCircle2,
  AlertCircle,
  Search,
  X,
  MousePointerClick,
  Scale,
  Info
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell
} from "recharts";
import {
  getCongressComposition,
  searchPoliticians,
  PartySeat,
  IpleData,
} from "../services/api";
import { useApi } from "@/hooks/useApi";
import { safeExternalUrl } from "@/lib/safeUrl";
import { fmtNum, fmtPct, isNum } from "@/lib/format";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";
import Modal from "@/components/Modal";

interface CongressCompositionPanelProps {
  mandateId: string;
  onSelectPolitician?: (id: string) => void;
  onPoliticianSelect?: (id: string) => void;
  onSelectParty?: (partido: string) => void;
}

export default function CongressCompositionPanel({
  mandateId,
  onSelectPolitician,
  onPoliticianSelect,
  onSelectParty,
}: CongressCompositionPanelProps) {
  const composition = useApi(`congress-composition:${mandateId}`, (signal) => getCongressComposition(mandateId, signal));
  const data = composition.data ?? null;
  const [activeHouse, setActiveHouse] = useState<"camara" | "senado">("camara");
  const [showIpleMetodologia, setShowIpleMetodologia] = useState<boolean>(false);

  // Estados do Modal Interativo de Parlamentares da Bancada
  const [selectedParty, setSelectedParty] = useState<string | null>(null);
  const [partySearch, setPartySearch] = useState<string>("");

  // Carregar parlamentares da bancada selecionada
  const members = useApi(
    `party-members:${selectedParty}:${activeHouse}:${mandateId}`,
    (signal) =>
      searchPoliticians(
        undefined,
        activeHouse === "camara" ? "DEPUTADO_FEDERAL" : "SENADOR",
        selectedParty ?? undefined,
        undefined,
        200,
        mandateId,
        signal
      ),
    Boolean(selectedParty)
  );

  const partyPoliticians = useMemo(() => {
    return members.data?.politicos ?? [];
  }, [members.data]);

  const loadingParty = members.loading;

  const handlePartyClick = (partido: string) => {
    if (!partido) return;
    if (onSelectParty) {
      onSelectParty(partido);
      return;
    }
    setSelectedParty(partido);
    setPartySearch("");
  };

  // Filtragem interna de parlamentares no modal (por nome, UF ou sigla de partido)
  const filteredPoliticians = useMemo(() => {
    if (!partySearch.trim()) return partyPoliticians;
    const s = partySearch.toLowerCase();
    return partyPoliticians.filter(
      (p) =>
        p.nome_eleitoral.toLowerCase().includes(s) ||
        p.nome_civil.toLowerCase().includes(s) ||
        p.uf.toLowerCase().includes(s) ||
        p.partido_sigla.toLowerCase().includes(s)
    );
  }, [partyPoliticians, partySearch]);

  if (composition.loading) return <LoadingState label="Carregando composição do Congresso..." />;
  if (composition.error) return <ErrorState onRetry={composition.retry} />;
  if (!data) return <EmptyState title="Composição do Congresso indisponível" />;

  const currentHouse = activeHouse === "camara" ? data.camara : data.senado;
  if (!currentHouse) {
    return (
      <EmptyState
        title={`Composição ${activeHouse === "camara" ? "da Câmara" : "do Senado"} indisponível para este mandato`}
      />
    );
  }
  const totalSeats = currentHouse.total_cadeiras;
  const houseLabel = `${activeHouse === "camara" ? "Câmara dos Deputados" : "Senado Federal"} (${totalSeats} cadeiras)`;
  // Quóruns constitucionais calculados sobre o total de cadeiras informado pela API.
  const quorumPec = Math.ceil((totalSeats * 3) / 5);
  const quorumSimples = Math.floor(totalSeats / 2) + 1;

  const { governabilidade } = currentHouse;
  const iple = ((governabilidade as Record<string, unknown>)?.iple as IpleData | undefined) ?? data?.iple;

  return (
    <div className="space-y-6">
      {/* Cabeçalho de Governabilidade */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 backdrop-blur-md">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                <Landmark className="w-5 h-5" aria-hidden="true" />
              </span>
              <h2 className="text-xl font-extrabold text-slate-100 tracking-tight">
                Composição do Congresso & Governabilidade Presidencial
              </h2>
            </div>
            <p className="text-xs text-slate-400">
              Mandato de <strong>{data.presidente_republica}</strong> ({data.periodo}) • Presidência das Casas Legislativas e correlação de forças partidárias.
            </p>
          </div>

          {/* Seletor Câmara / Senado */}
          <div className="flex items-center bg-slate-950 p-1.5 rounded-2xl border border-slate-800 self-start md:self-auto">
            <button
              type="button"
              aria-pressed={activeHouse === "camara"}
              onClick={() => {
                setActiveHouse("camara");
                setSelectedParty(null);
              }}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                activeHouse === "camara"
                  ? "bg-cyan-500 text-slate-950 shadow-md"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Câmara dos Deputados
            </button>
            <button
              type="button"
              aria-pressed={activeHouse === "senado"}
              onClick={() => {
                setActiveHouse("senado");
                setSelectedParty(null);
              }}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                activeHouse === "senado"
                  ? "bg-cyan-500 text-slate-950 shadow-md"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Senado Federal
            </button>
          </div>
        </div>

        {/* Barra de Governabilidade Empilhada */}
        <div className="mt-6 bg-slate-950/70 border border-slate-800/90 rounded-2xl p-4">
          <div className="flex items-center justify-between text-xs mb-2.5">
            <span className="font-bold text-slate-300">
              Distribuição de Forças: {houseLabel}
            </span>
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5 text-emerald-400 font-bold">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" aria-hidden="true" />
                Base ({governabilidade.base_aliada_cadeiras} cad. • {fmtNum(governabilidade.base_aliada_pct)}%)
              </span>
              <span className="flex items-center gap-1.5 text-amber-400 font-bold">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-500" aria-hidden="true" />
                Centro ({governabilidade.centro_cadeiras} cad. • {fmtNum(governabilidade.centro_pct)}%)
              </span>
              <span className="flex items-center gap-1.5 text-rose-400 font-bold">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500" aria-hidden="true" />
                Oposição ({governabilidade.oposicao_cadeiras} cad. • {fmtNum(governabilidade.oposicao_pct)}%)
              </span>
            </div>
          </div>

          {/* Barra Visual */}
          <div className="w-full h-4 bg-slate-900 rounded-full overflow-hidden flex shadow-inner">
            <div
              style={{ width: `${governabilidade.base_aliada_pct}%` }}
              className="bg-emerald-500 h-full transition-all duration-500"
              title={`Base Aliada: ${governabilidade.base_aliada_cadeiras} cadeiras`}
            />
            <div
              style={{ width: `${governabilidade.centro_pct}%` }}
              className="bg-amber-500 h-full transition-all duration-500"
              title={`Centro/Independente: ${governabilidade.centro_cadeiras} cadeiras`}
            />
            <div
              style={{ width: `${governabilidade.oposicao_pct}%` }}
              className="bg-rose-500 h-full transition-all duration-500"
              title={`Oposição: ${governabilidade.oposicao_cadeiras} cadeiras`}
            />
          </div>

          {/* Quóruns Constitucionais */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4 pt-3 border-t border-slate-900 text-xs">
            <div className="flex items-center gap-2">
              {governabilidade.maioria_simples_atingida ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" aria-hidden="true" />
              ) : (
                <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0" aria-hidden="true" />
              )}
              <span className="text-slate-300">
                <strong>Maioria Simples ({quorumSimples} votos):</strong>{" "}
                {governabilidade.maioria_simples_atingida
                  ? "Garantida exclusivamente pela bancada governista."
                  : "Dependente de negociação com o Centro/Independente."}
              </span>
            </div>

            <div className="flex items-center gap-2">
              {governabilidade.maioria_pec_atingida ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" aria-hidden="true" />
              ) : (
                <ShieldAlert className="w-4 h-4 text-rose-400 flex-shrink-0" aria-hidden="true" />
              )}
              <span className="text-slate-300">
                <strong>Quórum de PEC ({quorumPec} votos - 3/5):</strong>{" "}
                {governabilidade.maioria_pec_atingida
                  ? "Alcançado pela coalizão de sustentação."
                  : "Exige composição com partidos de Centro e Oposição moderada."}
              </span>
            </div>
          </div>

          {/* ========================================================================= */}
          {/* ÍNDICE DE PODER LEGISLATIVO DO EXECUTIVO (IPLE) - MODELO CIENTÍFICO QCA  */}
          {/* ========================================================================= */}
          {iple && (
            <div className="mt-5 pt-4 border-t border-slate-800/90 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                    <Scale className="w-4 h-4" aria-hidden="true" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm font-bold text-white tracking-tight">
                        Índice de Poder Legislativo do Executivo (IPLE)
                      </h3>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-bold">
                        Modelo Científico QCA
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Avalia a governabilidade e a força política do chefe do Executivo frente ao Congresso (escala 0.0 a 1.0).
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setShowIpleMetodologia((v) => !v)}
                  aria-expanded={showIpleMetodologia}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs font-semibold text-cyan-400 hover:text-cyan-300 hover:border-cyan-500/40 transition-colors self-start sm:self-auto"
                >
                  <Info className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>{showIpleMetodologia ? "Ocultar Metodologia" : "Entenda a Metodologia IPLE"}</span>
                </button>
              </div>

              {/* Painel Explicativo da Metodologia e Calibragem QCA */}
              {showIpleMetodologia && (
                <div className="bg-slate-950/90 border border-indigo-500/30 rounded-2xl p-4 sm:p-5 space-y-3.5 animate-in fade-in slide-in-from-top-2 duration-300">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                    <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                      <Award className="w-3.5 h-3.5 text-amber-400" />
                      Fórmulas & Calibragem Crisp-Set QCA
                    </h4>
                    <span className="text-[10px] font-mono text-slate-400">
                      IPLE = (TS + TMV) / 2
                    </span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-slate-300">
                    <div className="bg-slate-900/70 p-3 rounded-xl border border-slate-800/80 space-y-1">
                      <span className="font-bold text-cyan-300 block">1. Taxa de Sucesso Legislativo (TS)</span>
                      <p className="text-[11px] text-slate-400">
                        TS = |P_exec_aprov| / |P_exec|. Mede a aprovação da agenda prioritária do Executivo. <strong>Corte: ≥ 87% (Sucesso Alto)</strong>.
                      </p>
                    </div>
                    <div className="bg-slate-900/70 p-3 rounded-xl border border-slate-800/80 space-y-1">
                      <span className="font-bold text-amber-300 block">2. Taxa de Manutenção de Vetos (TMV)</span>
                      <p className="text-[11px] text-slate-400">
                        TMV = |V_mantidos| / |V_apreciados|. Exclui vetos pendentes de pauta. <strong>Corte: ≥ 70% (Manutenção Alta)</strong>.
                      </p>
                    </div>
                    <div className="bg-slate-900/70 p-3 rounded-xl border border-slate-800/80 space-y-1">
                      <span className="font-bold text-indigo-300 block">3. Fragmentação Partidária (NEP)</span>
                      <p className="text-[11px] text-slate-400">
                        NEP = 1 / Σ(p_i²), índice de Laakso & Taagepera. <strong>Corte: ≥ 8.45 (Parlamento Fragmentado)</strong>.
                      </p>
                    </div>
                    <div className="bg-slate-900/70 p-3 rounded-xl border border-slate-800/80 space-y-1">
                      <span className="font-bold text-pink-300 block">4. Polarização Ideológica Ponderada (IPP)</span>
                      <p className="text-[11px] text-slate-400">
                        IPP = Σ p_i·(x_i - x̄)², com escala ideológica de 1 (Esquerda) a 10 (Direita). <strong>Corte: &gt; 2.2 (Parlamento Polarizado)</strong>.
                      </p>
                    </div>
                  </div>

                  <div className="p-3.5 bg-cyan-950/40 border border-cyan-500/30 rounded-xl space-y-1.5">
                    <h5 className="font-bold text-cyan-300 text-xs flex items-center gap-1.5">
                      <span>⚖️</span> Por que as Taxas de Sucesso (TS) e Vetos (TMV) são idênticas entre as Casas, mas as Variáveis Contextuais (X₁, X₂, X₃) variam?
                    </h5>
                    <p className="text-[11px] text-slate-300 leading-relaxed">
                      No presidencialismo bicameral brasileiro, as mensagens de veto são apreciadas exclusivamente em <strong>Sessão Conjunta do Congresso Nacional</strong> (reunião unificada de deputados e senadores, conforme o Art. 66, § 4º da Constituição Federal), e a conversão definitiva de leis e PECs exige a aprovação de ambas as Casas. Por isso, a <strong>Taxa de Sucesso (TS)</strong> e a <strong>Taxa de Manutenção de Vetos (TMV)</strong> constituem métricas estruturais bicamerais do mandato presidencial.
                    </p>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Em contrapartida, as <strong>Variáveis de Contexto Parlamentar (Oposição X₁, Fragmentação NEP X₂ e Polarização IPP X₃)</strong> mensuram a correlação de forças específica de cada plenário, variando dinamicamente ao alternar entre a Câmara dos Deputados (513 membros) e o Senado Federal (81 membros).
                    </p>
                  </div>
                </div>
              )}

              {/* Grid dos 3 Indicadores Principais */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {/* Card 1: IPLE Geral */}
                <div className={`p-4 rounded-2xl border flex flex-col justify-between ${
                  iple.calibragem_crisp_set.iple.crisp_val === 1
                    ? "bg-gradient-to-br from-emerald-500/10 via-slate-900 to-slate-950 border-emerald-500/30"
                    : "bg-gradient-to-br from-amber-500/10 via-slate-900 to-slate-950 border-amber-500/30"
                }`}>
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wider">
                      Score IPLE
                    </span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                      iple.calibragem_crisp_set.iple.crisp_val === 1
                        ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                        : "bg-amber-500/20 text-amber-300 border-amber-500/40"
                    }`}>
                      {iple.calibragem_crisp_set.iple.classificacao}
                    </span>
                  </div>
                  <div className="my-2">
                    <span className="text-2xl sm:text-3xl font-black text-white font-mono">
                      {iple.indicadores_base.iple_score.toFixed(3)}
                    </span>
                    <span className="text-[11px] text-slate-400 block mt-0.5">
                      Média de Sucesso & Vetos (Corte ≥ 0.785)
                    </span>
                  </div>
                  <div className="w-full bg-slate-950 rounded-full h-1.5 overflow-hidden border border-slate-800">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        iple.calibragem_crisp_set.iple.crisp_val === 1 ? "bg-emerald-400" : "bg-amber-400"
                      }`}
                      style={{ width: `${Math.min(100, iple.indicadores_base.iple_score * 100)}%` }}
                    />
                  </div>
                </div>

                {/* Card 2: Taxa de Sucesso Legislativo (TS) */}
                <div className={`p-4 rounded-2xl border flex flex-col justify-between ${
                  iple.calibragem_crisp_set.ts.crisp_val === 1
                    ? "bg-gradient-to-br from-emerald-500/10 via-slate-900 to-slate-950 border-emerald-500/30"
                    : "bg-gradient-to-br from-slate-900 to-slate-950 border-slate-800"
                }`}>
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-cyan-300 uppercase tracking-wider">
                      Sucesso Legislativo (TS)
                    </span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                      iple.calibragem_crisp_set.ts.crisp_val === 1
                        ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                        : "bg-slate-800 text-slate-300 border-slate-700"
                    }`}>
                      {iple.calibragem_crisp_set.ts.classificacao}
                    </span>
                  </div>
                  <div className="my-2">
                    <span className="text-2xl sm:text-3xl font-black text-white font-mono">
                      {(iple.indicadores_base.taxa_sucesso_ts * 100).toFixed(1)}%
                    </span>
                    <span className="text-[11px] text-slate-400 block mt-0.5">
                      {iple.indicadores_base.proposicoes_executivo_aprovadas} de {iple.indicadores_base.proposicoes_executivo_total} projetos viraram lei
                    </span>
                  </div>
                  <div className="w-full bg-slate-950 rounded-full h-1.5 overflow-hidden border border-slate-800">
                    <div
                      className="h-full rounded-full bg-cyan-400 transition-all duration-500"
                      style={{ width: `${Math.min(100, iple.indicadores_base.taxa_sucesso_ts * 100)}%` }}
                    />
                  </div>
                </div>

                {/* Card 3: Taxa de Manutenção de Vetos (TMV) */}
                <div className={`p-4 rounded-2xl border flex flex-col justify-between ${
                  iple.calibragem_crisp_set.tmv.crisp_val === 1
                    ? "bg-gradient-to-br from-emerald-500/10 via-slate-900 to-slate-950 border-emerald-500/30"
                    : "bg-gradient-to-br from-slate-900 to-slate-950 border-slate-800"
                }`}>
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-amber-300 uppercase tracking-wider">
                      Manutenção de Vetos (TMV)
                    </span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                      iple.calibragem_crisp_set.tmv.crisp_val === 1
                        ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                        : "bg-slate-800 text-slate-300 border-slate-700"
                    }`}>
                      {iple.calibragem_crisp_set.tmv.classificacao}
                    </span>
                  </div>
                  <div className="my-2">
                    <span className="text-2xl sm:text-3xl font-black text-white font-mono">
                      {(iple.indicadores_base.taxa_manutencao_vetos_tmv * 100).toFixed(1)}%
                    </span>
                    <span className="text-[11px] text-slate-400 block mt-0.5">
                      {iple.indicadores_base.vetos_mantidos} de {iple.indicadores_base.vetos_total_apreciados} vetos apreciados mantidos
                    </span>
                  </div>
                  <div className="w-full bg-slate-950 rounded-full h-1.5 overflow-hidden border border-slate-800">
                    <div
                      className="h-full rounded-full bg-amber-400 transition-all duration-500"
                      style={{ width: `${Math.min(100, iple.indicadores_base.taxa_manutencao_vetos_tmv * 100)}%` }}
                    />
                  </div>
                </div>
              </div>

              {/* Variáveis Contextuais de Validação QCA (X1, X2, X3) */}
              <div className="space-y-2 pt-1">
                <div className="flex items-center justify-between text-xs px-1">
                  <span className="font-bold text-slate-300 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-cyan-400" />
                    Variáveis de Sustentabilidade na {activeHouse === "camara" ? "Câmara dos Deputados (513 assentos)" : "Senado Federal (81 assentos)"}
                  </span>
                  <span className="text-[11px] text-slate-400 font-mono hidden sm:inline">
                    NEP e Polarização calibrados para esta Casa
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                <div className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3 flex items-center justify-between">
                  <div>
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                      Oposição (X₁)
                    </span>
                    <span className="text-sm font-bold text-white font-mono">
                      {fmtPct(isNum(iple.variaveis_contextuais.tamanho_oposicao_x1) ? iple.variaveis_contextuais.tamanho_oposicao_x1 * 100 : null, 1)}
                    </span>
                  </div>
                  <span className={`text-[9px] font-semibold px-2 py-0.5 rounded-full border ${
                    iple.calibragem_crisp_set.oposicao_x1.crisp_val === 1
                      ? "bg-rose-500/15 text-rose-300 border-rose-500/30"
                      : "bg-slate-800 text-slate-400 border-slate-700"
                  }`}>
                    {iple.calibragem_crisp_set.oposicao_x1.classificacao}
                  </span>
                </div>

                <div className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3 flex items-center justify-between">
                  <div>
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                      Fragmentação NEP (X₂)
                    </span>
                    <span className="text-sm font-bold text-white font-mono">
                      {fmtNum(iple.variaveis_contextuais.fragmentacao_nep_x2, 2)} partidos
                    </span>
                  </div>
                  <span className={`text-[9px] font-semibold px-2 py-0.5 rounded-full border ${
                    iple.calibragem_crisp_set.fragmentacao_x2.crisp_val === 1
                      ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                      : "bg-slate-800 text-slate-400 border-slate-700"
                  }`}>
                    {iple.calibragem_crisp_set.fragmentacao_x2.classificacao}
                  </span>
                </div>

                <div className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3 flex items-center justify-between">
                  <div>
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                      Polarização IPP (X₃)
                    </span>
                    <span className="text-sm font-bold text-white font-mono">
                      {fmtNum(iple.variaveis_contextuais.polarizacao_ipp_x3, 2)}
                    </span>
                  </div>
                  <span className={`text-[9px] font-semibold px-2 py-0.5 rounded-full border ${
                    iple.calibragem_crisp_set.polarizacao_x3.crisp_val === 1
                      ? "bg-purple-500/15 text-purple-300 border-purple-500/30"
                      : "bg-slate-800 text-slate-400 border-slate-700"
                  }`}>
                    {iple.calibragem_crisp_set.polarizacao_x3.classificacao}
                  </span>
                </div>
              </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Cards dos Presidentes da Casa */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 backdrop-blur-md">
        <div className="flex items-center gap-2 mb-4">
          <Award className="w-4 h-4 text-cyan-400" aria-hidden="true" />
          <h3 className="text-sm font-bold text-slate-200">
            Presidentes da {activeHouse === "camara" ? "Câmara dos Deputados" : "Senado Federal"} no Mandato
          </h3>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {currentHouse.presidentes.map((p) => (
            <div
              key={`${p.nome}-${p.periodo}`}
              className="bg-slate-950/70 border border-slate-800 hover:border-slate-700 rounded-2xl p-4 flex items-center gap-3.5 transition-all"
            >
              {safeExternalUrl(p.foto_url) ? (
                <img
                  src={safeExternalUrl(p.foto_url)}
                  alt=""
                  referrerPolicy="no-referrer"
                  className="w-14 h-14 rounded-xl object-cover border border-slate-700 flex-shrink-0"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
              ) : (
                <div className="w-14 h-14 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-sm font-bold text-cyan-400 flex-shrink-0">
                  {p.partido}
                </div>
              )}
              <div>
                <h4 className="text-sm font-bold text-slate-100">{p.nome}</h4>
                <p className="text-xs text-slate-400 mt-0.5">
                  <span className="font-semibold text-cyan-400">{p.partido}</span> • {p.uf}
                </p>
                <span className="text-[11px] font-mono text-slate-400 block mt-1">
                  {p.periodo}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Gráfico de Bancadas Partidárias (INTERATIVO COM CLIQUE NAS BARRAS) */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 backdrop-blur-md space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-cyan-400" aria-hidden="true" />
            <h3 className="text-sm font-bold text-slate-200">
              Tamanho das Bancadas Partidárias na {activeHouse === "camara" ? "Câmara" : "Senado"}
            </h3>
          </div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
            <MousePointerClick className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Clique em qualquer barra para ver a lista de parlamentares</span>
          </div>
        </div>

        <div
          role="img"
          aria-label={`Gráfico de barras com o tamanho das bancadas partidárias na ${activeHouse === "camara" ? "Câmara" : "Senado"}`}
          style={{ height: `${Math.max(420, currentHouse.bancadas.length * 28)}px` }}
          className="w-full"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={currentHouse.bancadas}
              layout="vertical"
              margin={{ top: 10, right: 30, left: 90, bottom: 0 }}
              className="cursor-pointer"
              onClick={(state) => {
                if (!state) return;
                const activeState = state as unknown as {
                  activeLabel?: string | number;
                  activeTooltipIndex?: number;
                  activePayload?: Array<{ payload?: PartySeat }>;
                };
                const seat = activeState.activePayload?.[0]?.payload;
                const idx = typeof activeState.activeTooltipIndex === "number" ? activeState.activeTooltipIndex : undefined;
                const sigla =
                  seat?.partido ||
                  (typeof activeState.activeLabel === "string" ? activeState.activeLabel : undefined) ||
                  (idx !== undefined && currentHouse.bancadas[idx] ? currentHouse.bancadas[idx].partido : undefined);
                if (sigla) handlePartyClick(sigla);
              }}
            >
              <XAxis type="number" stroke="#64748b" tick={{ fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="partido"
                stroke="#94a3b8"
                tick={{ fontSize: 11, cursor: "pointer" }}
                width={85}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#090d16",
                  borderColor: "#334155",
                  borderRadius: "12px",
                  fontSize: "12px"
                }}
                formatter={(val, _name, item) => {
                  const seat = item?.payload as PartySeat | undefined;
                  const detail = seat ? ` (${fmtNum(seat.percentual)}%) - ${seat.alinhamento.replace(/_/g, " ")}` : "";
                  return [`${val} cadeiras${detail} (Clique para abrir)`, "Bancada"];
                }}
              />
              <Bar
                dataKey="cadeiras"
                radius={[0, 6, 6, 0]}
                className="cursor-pointer"
                onClick={(entry: unknown) => {
                  const bar = entry as {
                    partido?: string;
                    payload?: { partido?: string };
                    activePayload?: Array<{ payload?: { partido?: string } }>;
                    activeLabel?: string;
                  } | undefined;
                  const sigla =
                    bar?.partido ||
                    bar?.payload?.partido ||
                    bar?.activePayload?.[0]?.payload?.partido ||
                    bar?.activeLabel;
                  if (sigla) handlePartyClick(sigla);
                }}
              >
                {currentHouse.bancadas.map((entry) => (
                  <Cell
                    key={`cell-${entry.partido}`}
                    fill={entry.cor_hex || "#3b82f6"}
                    className="cursor-pointer hover:opacity-80 transition-opacity"
                    onClick={() => handlePartyClick(entry.partido)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Alternativa por teclado/leitor de tela às barras clicáveis do gráfico */}
        <ul className="flex flex-wrap gap-1.5" aria-label="Bancadas partidárias">
          {currentHouse.bancadas.map((b) => (
            <li key={b.partido}>
              <button
                type="button"
                onClick={() => handlePartyClick(b.partido)}
                className="px-2 py-1 rounded-lg text-[11px] font-semibold bg-slate-950 border border-slate-800 text-slate-300 hover:text-cyan-300 hover:border-cyan-500/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
              >
                {b.partido} · {b.cadeiras}
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* ======================================================== */}
      {/* MODAL / GAVETA: PARLAMENTARES DA BANCADA PARTIDÁRIA      */}
      {/* ======================================================== */}
      <Modal
        isOpen={Boolean(selectedParty)}
        onClose={() => setSelectedParty(null)}
        titleId="party-modal-title"
        overlayClassName="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md"
        className="bg-slate-900 border border-slate-700 rounded-3xl w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden relative"
      >
        {/* Cabeçalho do Modal */}
        <div className="p-6 border-b border-slate-800 bg-slate-950/90 relative">
          <button
            type="button"
            aria-label="Fechar"
            onClick={() => setSelectedParty(null)}
            className="absolute top-5 right-5 p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" aria-hidden="true" />
          </button>

          <div className="space-y-3 pr-8">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-black px-3 py-1 rounded-xl bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                Bancada: {selectedParty}
              </span>
              <span className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-slate-800 text-slate-300 border border-slate-700">
                {activeHouse === "camara" ? "Câmara dos Deputados" : "Senado Federal"}
              </span>
              {!loadingParty && !members.error && (
                <span className="text-xs font-bold px-2.5 py-1 rounded-lg bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  {filteredPoliticians.length} parlamentares
                </span>
              )}
            </div>

            <h3 id="party-modal-title" className="text-xl sm:text-2xl font-black text-white">
              {`Parlamentares do ${selectedParty} no(a) ${activeHouse === "camara" ? "Câmara dos Deputados" : "Senado Federal"}`}
            </h3>

            <p className="text-xs sm:text-sm text-slate-400">
              {`Lista nominal dos ${activeHouse === "camara" ? "deputados federais" : "senadores"} filiados à legenda.`}
            </p>

            {/* Campo de Busca Rápida Dentro do Modal */}
            <div className="relative pt-2">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-5" aria-hidden="true" />
              <input
                type="text"
                aria-label={`Buscar parlamentar do ${selectedParty} por nome ou UF`}
                placeholder={`Buscar parlamentar do ${selectedParty} por nome ou UF (ex: SP, RJ, MG)...`}
                value={partySearch}
                onChange={(e) => setPartySearch(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-200 placeholder-slate-400 focus:outline-none focus:border-cyan-500"
              />
              {partySearch && (
                <button
                  type="button"
                  aria-label="Limpar busca"
                  onClick={() => setPartySearch("")}
                  className="absolute right-3 top-4.5 text-slate-400 hover:text-slate-200"
                >
                  <X className="w-3.5 h-3.5" aria-hidden="true" />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Conteúdo com Grid de Cards */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {loadingParty ? (
            <div role="status" aria-live="polite" className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 animate-pulse">
              <span className="sr-only">Carregando parlamentares...</span>
              {Array.from({ length: 15 }).map((_, i) => (
                <div key={i} className="h-44 bg-slate-950/60 border border-slate-800 rounded-2xl p-3" />
              ))}
            </div>
          ) : members.error ? (
            <ErrorState onRetry={members.retry} />
          ) : filteredPoliticians.length === 0 ? (
            <div role="status" className="p-12 text-center text-slate-400 space-y-2 bg-slate-950/40 rounded-2xl border border-slate-800">
              <Users className="w-8 h-8 text-slate-400 mx-auto" aria-hidden="true" />
              <p className="text-sm font-semibold text-slate-300">Nenhum parlamentar encontrado</p>
              <p className="text-xs text-slate-400">
                {partySearch
                  ? "Tente outro termo de busca."
                  : `Nenhum membro registrado para o ${selectedParty} nesta Casa.`}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
              {filteredPoliticians.map((pol) => (
                <button
                  type="button"
                  key={pol.id}
                  onClick={() => {
                    setSelectedParty(null);
                    if (onSelectPolitician) {
                      onSelectPolitician(pol.id);
                    } else if (onPoliticianSelect) {
                      onPoliticianSelect(pol.id);
                    }
                  }}
                  title={`Clique para abrir o Raio-X de ${pol.nome_eleitoral}`}
                  className="bg-slate-950/70 border border-slate-800/90 hover:border-cyan-400/80 rounded-2xl p-3 flex flex-col items-center text-center transition-all duration-200 hover:scale-[1.03] hover:bg-slate-900 group shadow-md cursor-pointer hover:shadow-cyan-950/40 relative focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
                >
                  {/* Foto */}
                  <div className="relative mb-2.5">
                    {safeExternalUrl(pol.foto_url) ? (
                      <img
                        src={safeExternalUrl(pol.foto_url)}
                        alt=""
                        referrerPolicy="no-referrer"
                        className="w-16 h-16 rounded-xl object-cover border border-slate-700 group-hover:border-cyan-400 transition-colors shadow-sm"
                        onError={(e) => {
                          e.currentTarget.style.display = "none";
                        }}
                      />
                    ) : (
                      <div className="w-16 h-16 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-sm font-bold text-slate-300">
                        {pol.nome_eleitoral.slice(0, 2).toUpperCase()}
                      </div>
                    )}
                    <span className="absolute -bottom-1 -right-1 text-[10px] font-black px-1.5 py-0.2 rounded bg-slate-900 text-cyan-300 border border-slate-700 shadow">
                      {pol.uf}
                    </span>
                  </div>

                  {/* Nome & Cargo */}
                  <span className="text-xs font-bold text-white group-hover:text-cyan-300 transition-colors line-clamp-2 leading-tight">
                    {pol.nome_eleitoral}
                  </span>
                  <span className="text-[10px] text-slate-400 mt-1 line-clamp-1" title={pol.nome_civil}>
                    {pol.nome_civil}
                  </span>

                  <div className="mt-auto pt-2 w-full flex items-center justify-center gap-1.5 text-[10px]">
                    <span className="px-2 py-0.5 rounded-md bg-slate-900 font-bold text-slate-300 border border-slate-800">
                      {pol.partido_sigla}
                    </span>
                    <span className="text-slate-400 font-semibold">{pol.uf}</span>
                  </div>

                  <div className="mt-2 text-[10px] font-semibold text-cyan-400/80 group-hover:text-cyan-300 flex items-center gap-1 transition-colors">
                    <span>Raio-X</span>
                    <span aria-hidden="true">→</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Rodapé do Modal */}
        <div className="p-4 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <span>
            Exibindo <strong>{filteredPoliticians.length}</strong> parlamentares da bancada do <strong>{selectedParty}</strong>
          </span>
          <button
            type="button"
            onClick={() => setSelectedParty(null)}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold transition-colors"
          >
            Fechar
          </button>
        </div>
      </Modal>

      {/* ======================================================== */}
      {/* SEÇÃO DE EDUCAÇÃO CÍVICA: ESTRUTURA E PAPEL DOS PODERES */}
      {/* ======================================================== */}
      <div className="bg-slate-950/70 border border-slate-800/90 rounded-2xl p-5 sm:p-6 space-y-5">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-900">
          <div className="flex items-center gap-2.5">
            <span className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <Landmark className="w-5 h-5" aria-hidden="true" />
            </span>
            <div>
              <h3 className="text-base sm:text-lg font-bold text-slate-100">
                Educação Cívica: Como Funciona a Divisão de Poderes no Brasil?
              </h3>
              <p className="text-xs text-slate-400">
                Guia didático sobre as atribuições constitucionais de cada cargo que compõe a representação pública
              </p>
            </div>
          </div>
          <span className="text-[11px] font-semibold text-slate-400 px-3 py-1 rounded-full bg-slate-900 border border-slate-800">
            Constituição Federal de 1988
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Card 1: Presidente da República */}
          <div className="bg-slate-900/80 border border-emerald-500/20 hover:border-emerald-500/40 rounded-xl p-4.5 space-y-2.5 transition-all">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                <Users className="w-3.5 h-3.5" aria-hidden="true" /> Poder Executivo Federal
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-bold">
                Mandato: 4 anos
              </span>
            </div>
            <h4 className="text-sm font-bold text-slate-100">
              Presidente da República
            </h4>
            <p className="text-xs text-slate-300 leading-relaxed">
              Chefe de Estado e de Governo. Administra o país, executa o orçamento da União, formula diretrizes econômicas, comanda as Forças Armadas, representa o Brasil internacionalmente e sanciona ou veta projetos de lei aprovados pelo Congresso.
            </p>
          </div>

          {/* Card 2: Governador */}
          <div className="bg-slate-900/80 border border-emerald-500/20 hover:border-emerald-500/40 rounded-xl p-4.5 space-y-2.5 transition-all">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                <Users className="w-3.5 h-3.5" aria-hidden="true" /> Poder Executivo Estadual
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-bold">
                Mandato: 4 anos
              </span>
            </div>
            <h4 className="text-sm font-bold text-slate-100">
              Governador de Estado
            </h4>
            <p className="text-xs text-slate-300 leading-relaxed">
              Comanda a administração pública estadual. Responsável primordial pelas políticas e forças de <strong>Segurança Pública</strong> (Polícias Militar e Civil), rede hospitalar e de saúde de alta complexidade estadual, e ensino médio público.
            </p>
          </div>

          {/* Card 3: Senador */}
          <div className="bg-slate-900/80 border border-cyan-500/20 hover:border-cyan-500/40 rounded-xl p-4.5 space-y-2.5 transition-all">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center gap-1.5">
                <Landmark className="w-3.5 h-3.5" aria-hidden="true" /> Congresso Nacional
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-bold">
                Mandato: 8 anos
              </span>
            </div>
            <h4 className="text-sm font-bold text-slate-100">
              Senador da República (Senado Federal)
            </h4>
            <p className="text-xs text-slate-300 leading-relaxed">
              Representante paritário dos 26 Estados e do Distrito Federal (3 por ente). Além de legislar, tem atribuição exclusiva de <strong>sabatinar e aprovar ministros do STF</strong>, diretores do Banco Central, embaixadores e julgar processos de impeachment.
            </p>
          </div>

          {/* Card 4: Deputado Federal */}
          <div className="bg-slate-900/80 border border-cyan-500/20 hover:border-cyan-500/40 rounded-xl p-4.5 space-y-2.5 transition-all">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center gap-1.5">
                <Landmark className="w-3.5 h-3.5" aria-hidden="true" /> Câmara dos Deputados
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-bold">
                Mandato: 4 anos
              </span>
            </div>
            <h4 className="text-sm font-bold text-slate-100">
              Deputado Federal
            </h4>
            <p className="text-xs text-slate-300 leading-relaxed">
              Representante direto do povo (proporcional à população de cada estado). Propõe e vota <strong>leis nacionais e reformas constitucionais</strong>, define a destinação do Orçamento da União via emendas e autoriza a abertura de processos contra o Presidente da República.
            </p>
          </div>

          {/* Card 5: Deputado Estadual */}
          <div className="bg-slate-900/80 border border-indigo-500/20 hover:border-indigo-500/40 rounded-xl p-4.5 space-y-2.5 transition-all md:col-span-2 lg:col-span-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider flex items-center gap-1.5">
                <Landmark className="w-3.5 h-3.5" aria-hidden="true" /> Poder Legislativo Estadual
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 font-bold">
                Mandato: 4 anos
              </span>
            </div>
            <h4 className="text-sm font-bold text-slate-100">
              Deputado Estadual (Assembleias Legislativas)
            </h4>
            <p className="text-xs text-slate-300 leading-relaxed">
              Atua nas Assembleias Legislativas (ex: ALESP, ALERJ, ALEMG). Cria e aprova leis de abrangência estadual, fiscaliza os atos e gastos do Governador, aprova o orçamento estadual e acompanha as políticas públicas regionais implementadas pelas secretarias de Estado.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
